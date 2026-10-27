#!/usr/bin/env python3
"""
comfypack — reproduceerbare ComfyUI-installaties vanuit een TOML-manifest.

Alleen standaardbibliotheek (Python 3.11+); werkt op Windows en Linux.
Normaal aangeroepen door install.ps1, maar ook los te gebruiken:

  comfypack.py install  --root C:\\ComfyUI --profile standaard
  comfypack.py verify   --root C:\\ComfyUI --profile standaard
  comfypack.py list
  comfypack.py validate [--online]
  comfypack.py freeze   --root C:\\ComfyUI [--write packs/nieuw.toml]
  comfypack.py mirror   --dest \\\\server\\comfy-mirror --all
  comfypack.py add-model URL --pack eigen-loras --dir loras
"""
from __future__ import annotations

import sys

if sys.version_info < (3, 9):
    sys.exit("comfypack heeft Python 3.9 of nieuwer nodig (nu %d.%d). "
             "Tip: uv run --python 3.13 installer/comfypack.py ..." % sys.version_info[:2])

import argparse
import dataclasses
import datetime as dt
import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        sys.exit("Python %d.%d mist 'tomllib'. Installeer 'tomli' (python3 -m pip install --user tomli) "
                 "of gebruik Python 3.11+ (uv run --python 3.13 ...)." % sys.version_info[:2])
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

VERSION = "1.0.0"
IS_WIN = os.name == "nt"
REPO_DIR = Path(__file__).resolve().parent.parent
UA = f"comfypack/{VERSION}"
CHUNK = 1 << 20
TORCH_INDEX = "https://download.pytorch.org/whl/"
KNOWN_TORCH_INDEXES = ("cpu", "cu126", "cu128", "cu130", "cu132")
TORCH_PACKAGES = ("torch", "torchvision", "torchaudio")
MODEL_EXTS = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".sft", ".onnx"}
KNOWN_MODEL_DIRS = {
    "audio_encoders", "background_removal", "checkpoints", "clip", "clip_vision", "configs",
    "controlnet", "detection", "diffusers", "diffusion_models", "embeddings",
    "frame_interpolation", "geometry_estimation", "gligen", "hypernetworks",
    "latent_upscale_models", "loras", "model_patches", "optical_flow", "photomaker",
    "style_models", "text_encoders", "unet", "upscale_models", "vae", "vae_approx",
}
GIT_OPTS = ["-c", "core.longpaths=true", "-c", "advice.detachedHead=false",
            "-c", "core.autocrlf=false", "-c", "safe.directory=*"]
DEFAULTS = {
    "comfyui": {"repo": "https://github.com/Comfy-Org/ComfyUI", "ref": "master"},
    "python": {"version": "3.13", "constraints": []},
    "torch": {"packages": ["torch", "torchvision"], "index": "auto"},
    "install": {"parallel_downloads": 3, "manager": True, "prune_unlisted_nodes": False, "mirror": ""},
    "launch": {"listen": "127.0.0.1", "port": 8188, "auto_launch": True, "manager_ui": False, "args": []},
    "profiles": {},
}


# ----------------------------------------------------------------------------- output
_out_lock = threading.Lock()
try:
    sys.stdout.reconfigure(errors="replace", line_buffering=True)
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass


_log_file = None


def log(msg: str, kind: str = "") -> None:
    mark = {"step": "==> ", "ok": "[ok] ", "warn": "[!] ", "err": "[FOUT] ", "": "    "}[kind]
    line = f"{dt.datetime.now():%H:%M:%S} {mark}{msg}"
    with _out_lock:
        print(line, flush=True)
        if _log_file:
            try:
                _log_file.write(line + "\n")
                _log_file.flush()
            except OSError:
                pass


class ConfigError(Exception):
    pass


class StepError(Exception):
    pass


def human(n: float | None) -> str:
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return "?"


def toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


# ----------------------------------------------------------------------------- manifest
@dataclasses.dataclass
class Node:
    repo: str
    ref: str
    name: str
    pack: str
    requirements: bool = True
    install_script: bool = True
    pip: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return norm_repo(self.repo)


@dataclasses.dataclass
class Model:
    url: str
    dir: str
    file: str
    pack: str
    sha256: str | None = None
    size: int | None = None

    @property
    def rel(self) -> str:
        return f"{self.dir}/{self.file}"


@dataclasses.dataclass
class FileItem:
    src: Path
    dest: str
    pack: str


@dataclasses.dataclass
class Selection:
    packs: list[str]
    nodes: list[Node]
    models: list[Model]
    files: list[FileItem]
    pip: list[str]


def norm_repo(url: str) -> str:
    u = url.strip().rstrip("/")
    if u.endswith(".git"):
        u = u[:-4]
    return u.lower()


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def safe_rel(p: str, what: str) -> str:
    p = p.replace("\\", "/").strip("/")
    parts = p.split("/")
    if not p or any(x in ("", ".", "..") for x in parts) or re.match(r"^[A-Za-z]:", p):
        raise ConfigError(f"{what}: ongeldig pad '{p}' (relatief pad zonder '..' verwacht)")
    return p


def normalize_url(url: str) -> str:
    """Webpagina-links die mensen vaak kopiëren omzetten naar de directe download."""
    u = url.strip()
    parts = urllib.parse.urlsplit(u)
    host = (parts.hostname or "").lower()
    if host.endswith("huggingface.co") and "/blob/" in parts.path:
        u = u.replace("/blob/", "/resolve/", 1)
    elif host == "github.com" and "/blob/" in parts.path:
        u = u.replace("/blob/", "/raw/", 1)
    return u


def url_filename(url: str) -> str:
    name = urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1])
    return name


class Manifest:
    def __init__(self, repo_dir: Path):
        self.repo_dir = repo_dir
        cfg_path = repo_dir / "comfy-pack.toml"
        if not cfg_path.exists():
            raise ConfigError(f"{cfg_path} niet gevonden")
        self.cfg = deep_merge(DEFAULTS, self._load(cfg_path))
        self.packs: dict[str, dict] = {}
        for p in sorted((repo_dir / "packs").glob("*.toml")):
            self.packs[p.stem] = self._load(p)
        self.warnings: list[str] = []

    @staticmethod
    def _load(path: Path) -> dict:
        try:
            with open(path, "rb") as f:
                return tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"{path.name}: TOML-fout: {e}") from None

    @property
    def profiles(self) -> dict[str, list[str]]:
        return self.cfg.get("profiles", {})

    def resolve(self, profile: str | None = None, packs: list[str] | None = None) -> list[str]:
        if packs:
            wanted = packs
        elif profile:
            if profile not in self.profiles:
                raise ConfigError(f"profiel '{profile}' bestaat niet (wel: {', '.join(self.profiles) or 'geen'})")
            wanted = self.profiles[profile]
        else:
            raise ConfigError("geef --profile of --packs op")
        order: list[str] = []

        def visit(name: str, chain: tuple[str, ...]) -> None:
            if name in chain:
                raise ConfigError(f"cirkelverwijzing in 'requires': {' -> '.join(chain + (name,))}")
            if name not in self.packs:
                raise ConfigError(f"pack '{name}' bestaat niet (packs/{name}.toml)")
            for dep in self.packs[name].get("requires", []):
                visit(dep, chain + (name,))
            if name not in order:
                order.append(name)

        for n in wanted:
            visit(n, ())
        return order

    def collect(self, pack_names: list[str]) -> Selection:
        nodes: dict[str, Node] = {}
        models: dict[str, Model] = {}
        files: dict[str, FileItem] = {}
        pip: list[str] = []
        for pname in pack_names:
            data = self.packs[pname]
            known = {"description", "requires", "nodes", "models", "files", "pip"}
            for k in data:
                if k not in known:
                    self.warnings.append(f"pack '{pname}': onbekende sleutel '{k}' genegeerd")
            for i, n in enumerate(data.get("nodes", [])):
                where = f"pack '{pname}' nodes[{i}]"
                if "repo" not in n:
                    raise ConfigError(f"{where}: 'repo' ontbreekt")
                repo = n["repo"]
                ref = str(n.get("ref", "")).strip() or "HEAD"
                name = n.get("name") or url_filename(repo).removesuffix(".git")
                name = safe_rel(name, where)
                if "/" in name:
                    raise ConfigError(f"{where}: 'name' mag geen submap zijn")
                if not re.fullmatch(r"[0-9a-f]{40}", ref) and not re.match(r"^v?\d", ref):
                    self.warnings.append(f"{where}: ref '{ref}' is geen commit/tag — niet reproduceerbaar")
                node = Node(repo=repo, ref=ref, name=name, pack=pname,
                            requirements=bool(n.get("requirements", True)),
                            install_script=bool(n.get("install_script", True)),
                            pip=tuple(n.get("pip", [])))
                prev = nodes.get(node.key)
                if prev:
                    if prev.ref != node.ref:
                        raise ConfigError(f"{where}: {repo} staat ook in pack '{prev.pack}' met ref '{prev.ref}'")
                    continue
                if any(x.name.lower() == name.lower() for x in nodes.values()):
                    raise ConfigError(f"{where}: mapnaam '{name}' wordt al door een andere node gebruikt")
                nodes[node.key] = node
            for i, m in enumerate(data.get("models", [])):
                where = f"pack '{pname}' models[{i}]"
                for req in ("url", "dir"):
                    if req not in m:
                        raise ConfigError(f"{where}: '{req}' ontbreekt")
                url = normalize_url(m["url"])
                if not url.startswith(("https://", "http://")):
                    raise ConfigError(f"{where}: url moet met https:// beginnen")
                if re.search(r"civitai\.com/models/", url):
                    raise ConfigError(f"{where}: dit is een Civitai-webpagina. Gebruik de downloadlink: "
                                      f"rechtsklik op 'Download' > 'Link kopiëren' (https://civitai.com/api/download/models/…)")
                mdir = safe_rel(m["dir"], where)
                if mdir.split("/")[0] not in KNOWN_MODEL_DIRS:
                    self.warnings.append(f"{where}: map '{mdir}' is geen standaard ComfyUI-modelmap (ok voor custom nodes)")
                fname = m.get("file") or url_filename(url)
                if not fname or "." not in fname:
                    raise ConfigError(f"{where}: kan bestandsnaam niet uit URL halen; zet 'file = \"naam.safetensors\"'")
                fname = safe_rel(fname, where)
                sha = m.get("sha256")
                if sha:
                    sha = sha.lower().strip()
                    if not re.fullmatch(r"[0-9a-f]{64}", sha):
                        raise ConfigError(f"{where}: sha256 moet 64 hex-tekens zijn")
                size = m.get("size")
                if size is not None and (not isinstance(size, int) or size <= 0):
                    raise ConfigError(f"{where}: size moet een positief geheel getal (bytes) zijn")
                model = Model(url=url, dir=mdir, file=fname, pack=pname, sha256=sha, size=size)
                prev = models.get(model.rel.lower())
                if prev:
                    if prev.url != model.url or (prev.sha256 and sha and prev.sha256 != sha):
                        raise ConfigError(f"{where}: {model.rel} staat ook in pack '{prev.pack}' met een andere bron")
                    continue
                models[model.rel.lower()] = model
            for i, f in enumerate(data.get("files", [])):
                where = f"pack '{pname}' files[{i}]"
                if "src" not in f or "dest" not in f:
                    raise ConfigError(f"{where}: 'src' en 'dest' zijn verplicht")
                src = self.repo_dir / safe_rel(f["src"], where)
                if not src.exists():
                    raise ConfigError(f"{where}: bronbestand {f['src']} bestaat niet in de repo")
                dest = safe_rel(f["dest"], where)
                files[dest.lower()] = FileItem(src=src, dest=dest, pack=pname)
            pip.extend(data.get("pip", []))
        return Selection(packs=pack_names, nodes=list(nodes.values()), models=list(models.values()),
                         files=list(files.values()), pip=pip)

    def validate(self) -> list[str]:
        problems: list[str] = []
        for prof, packs in self.profiles.items():
            try:
                self.collect(self.resolve(packs=packs))
            except ConfigError as e:
                problems.append(f"profiel '{prof}': {e}")
        try:
            self.collect(self.resolve(packs=list(self.packs)))
        except ConfigError as e:
            problems.append(str(e))
        t = self.cfg["torch"]["index"]
        if t not in ("auto", "pypi") + KNOWN_TORCH_INDEXES and not str(t).startswith("http"):
            problems.append(f"[torch] index '{t}' onbekend")
        return problems


# ----------------------------------------------------------------------------- secrets
def load_secrets(root: Path | None) -> dict[str, str]:
    """Tokens uit omgeving of secrets.toml (root of repo, nooit committen)."""
    sec: dict[str, str] = {}
    for p in ([root / "secrets.toml"] if root else []) + [REPO_DIR / "secrets.toml"]:
        if p.exists():
            try:
                with open(p, "rb") as f:
                    for k, v in tomllib.load(f).items():
                        sec.setdefault(k.lower(), str(v))
            except Exception as e:
                log(f"{p} niet leesbaar: {e}", "warn")
    for env, key in (("HF_TOKEN", "huggingface"), ("CIVITAI_TOKEN", "civitai"), ("GITHUB_TOKEN", "github")):
        if os.environ.get(env):
            sec[key] = os.environ[env]
    return sec


def token_for(url: str, secrets: dict[str, str]) -> str | None:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if host.endswith("huggingface.co"):
        return secrets.get("huggingface")
    if host.endswith("civitai.com"):
        return secrets.get("civitai")
    return None


# ----------------------------------------------------------------------------- http
class _Redirects(urllib.request.HTTPRedirectHandler):
    """Onthoudt de Hugging Face sha256 (X-Linked-Etag) uit de redirect-respons."""

    def __init__(self):
        super().__init__()
        self.linked_sha: str | None = None
        self.linked_size: int | None = None

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        etag = (headers.get("X-Linked-Etag") or "").strip('"').lower()
        if re.fullmatch(r"[0-9a-f]{64}", etag):
            self.linked_sha = etag
        if (headers.get("X-Linked-Size") or "").isdigit():
            self.linked_size = int(headers["X-Linked-Size"])
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str, token: str | None, extra: dict[str, str] | None = None, timeout: int = 60):
    handler = _Redirects()
    opener = urllib.request.build_opener(handler)
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(extra or {})})
    if token:
        # 'unredirected': gaat niet mee naar de CDN (S3/R2 weigert dubbele auth)
        req.add_unredirected_header("Authorization", f"Bearer {token}")
    return opener.open(req, timeout=timeout), handler


@dataclasses.dataclass
class Probe:
    ok: bool
    status: str
    size: int | None = None
    sha256: str | None = None
    filename: str | None = None


def probe(url: str, token: str | None) -> Probe:
    """Grootte/hash/bestandsnaam ophalen met een 1-byte range-request."""
    try:
        r, h = _open(url, token, {"Range": "bytes=0-0"}, timeout=30)
        with r:
            size = None
            cr = r.headers.get("Content-Range", "")
            if "/" in cr and cr.rsplit("/", 1)[1].isdigit():
                size = int(cr.rsplit("/", 1)[1])
            elif r.status == 200 and (r.headers.get("Content-Length") or "").isdigit():
                size = int(r.headers["Content-Length"])
            fname = None
            cd = r.headers.get("Content-Disposition", "")
            mm = re.search(r"filename\*=UTF-8''([^;]+)", cd) or re.search(r'filename="?([^";]+)"?', cd)
            if mm:
                fname = urllib.parse.unquote(mm.group(1)).strip()
            return Probe(True, str(r.status), size or h.linked_size, h.linked_sha, fname)
    except urllib.error.HTTPError as e:
        hint = {401: "token nodig", 403: "geen toegang / licentie accepteren", 404: "niet gevonden"}.get(e.code, "")
        return Probe(False, f"HTTP {e.code} {hint}".strip())
    except Exception as e:
        return Probe(False, f"{type(e).__name__}: {e}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8 * CHUNK):
            h.update(chunk)
    return h.hexdigest()


class Progress:
    def __init__(self, label: str, total: int | None, start: int = 0):
        self.label, self.total, self.done = label, total, start
        self.t0 = self.tlast = time.monotonic()
        self.start = start

    def add(self, n: int) -> None:
        self.done += n
        now = time.monotonic()
        if now - self.tlast >= 15:
            self.tlast = now
            speed = (self.done - self.start) / max(now - self.t0, 0.001)
            pct = f" ({self.done * 100 // self.total}%)" if self.total else ""
            log(f"  {self.label}: {human(self.done)} / {human(self.total)}{pct}  {human(speed)}/s")


def http_download(url: str, part: Path, token: str | None, label: str) -> tuple[str | None, str | None]:
    """Download naar part met hervatten en retries. Geeft (server_sha, berekende_sha)."""
    attempt = 0
    while True:
        start = part.stat().st_size if part.exists() else 0
        hasher = hashlib.sha256() if start == 0 else None
        try:
            extra = {"Range": f"bytes={start}-"} if start else {}
            r, h = _open(url, token, extra)
            with r:
                if start and r.status != 206:
                    start, hasher = 0, hashlib.sha256()
                elif start:
                    log(f"  {label}: hervat vanaf {human(start)}")
                length = r.headers.get("Content-Length")
                total = (int(length) + start) if length and length.isdigit() else h.linked_size
                prog = Progress(label, total, start)
                with open(part, "ab" if start else "wb") as f:
                    while chunk := r.read(CHUNK):
                        f.write(chunk)
                        if hasher:
                            hasher.update(chunk)
                        prog.add(len(chunk))
                if total and part.stat().st_size < total:
                    raise http.client.IncompleteRead(b"", total - part.stat().st_size)
            return h.linked_sha, hasher.hexdigest() if hasher else None
        except urllib.error.HTTPError as e:
            if e.code == 416 and start:          # al compleet van vorige poging
                return None, None
            if e.code in (401, 403):
                raise StepError(f"HTTP {e.code}: geen toegang. Token nodig of licentie op de website "
                                f"accepteren? (zie secrets.toml)") from None
            if e.code == 404:
                raise StepError("HTTP 404: bestand niet gevonden (URL controleren)") from None
            err = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError,
                http.client.HTTPException) as e:
            err = f"{type(e).__name__}: {e}"
        attempt += 1
        if attempt > 6:
            raise StepError(f"download mislukt na {attempt} pogingen ({err})")
        wait = min(60, 2 ** attempt)
        log(f"  {label}: {err} — nieuwe poging over {wait}s (hervat vanaf {human(part.stat().st_size if part.exists() else 0)})", "warn")
        time.sleep(wait)


class HashCache:
    """Onthoudt sha256 per bestand (grootte + mtime) zodat herinstallaties snel zijn."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        try:
            self.data = json.loads(path.read_text("utf-8"))
        except Exception:
            self.data = {}

    def get(self, file: Path, key: str) -> str:
        st = file.stat()
        with self.lock:
            e = self.data.get(key)
            if e and e.get("size") == st.st_size and e.get("mtime_ns") == st.st_mtime_ns:
                return e["sha256"]
        sha = sha256_file(file)
        self.put(file, key, sha)
        return sha

    def put(self, file: Path, key: str, sha: str) -> None:
        st = file.stat()
        with self.lock:
            self.data[key] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": sha}

    def save(self) -> None:
        with self.lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self.data, indent=1), "utf-8")
                os.replace(tmp, self.path)
            except OSError:
                pass  # bv. verify zonder adminrechten: de cache is alleen een versnelling


class Downloader:
    def __init__(self, secrets: dict[str, str], mirror: str, cache: HashCache | None):
        self.secrets, self.mirror, self.cache = secrets, (mirror or "").strip(), cache

    def _sources(self, m: Model) -> list[tuple[str, str]]:
        out = []
        if self.mirror:
            if self.mirror.startswith(("http://", "https://")):
                base = self.mirror.rstrip("/") + "/"
                out.append(("mirror", base + urllib.parse.quote(m.rel)))
            else:
                out.append(("mirror", str(Path(self.mirror) / m.dir / m.file)))
        out.append(("bron", m.url))
        return out

    def ensure(self, m: Model, models_dir: Path) -> str:
        dest = models_dir / m.dir / m.file
        key = f"models/{m.rel}"
        if dest.exists():
            reason = None
            if m.size and dest.stat().st_size != m.size:
                reason = f"grootte {dest.stat().st_size} != {m.size}"
            elif m.sha256 and self.cache and self.cache.get(dest, key) != m.sha256:
                reason = "sha256 klopt niet"
            if not reason:
                return "aanwezig"
            log(f"{m.rel}: {reason} — opnieuw ophalen", "warn")
            dest.unlink()
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        last_err = None
        for kind, src in self._sources(m):
            try:
                if kind == "mirror" and not src.startswith(("http://", "https://")):
                    if not Path(src).is_file():
                        continue
                    if m.size and Path(src).stat().st_size != m.size:
                        log(f"{m.rel}: mirror-kopie heeft verkeerde grootte, overgeslagen", "warn")
                        continue
                    log(f"{m.rel}: kopiëren van mirror")
                    actual = self._copy(Path(src), part, m.file)
                    server_sha = None
                else:
                    token = token_for(src, self.secrets) if kind == "bron" else None
                    log(f"{m.rel}: downloaden van {'mirror' if kind == 'mirror' else urllib.parse.urlsplit(src).hostname}")
                    server_sha, actual = http_download(src, part, token, m.file)
                with open(part, "rb") as fh:
                    head = fh.read(512).lstrip().lower()
                if head.startswith((b"<!doctype", b"<html")) and Path(m.file).suffix.lower() in MODEL_EXTS:
                    part.unlink(missing_ok=True)
                    raise StepError("de link gaf een webpagina in plaats van een bestand — gebruik de directe downloadlink")
                if actual is None:
                    actual = sha256_file(part)
                expected = m.sha256 or server_sha
                if expected and actual != expected:
                    part.unlink(missing_ok=True)
                    raise StepError(f"sha256 klopt niet (verwacht {expected[:12]}…, kreeg {actual[:12]}…)")
                if m.size and part.stat().st_size != m.size:
                    part.unlink(missing_ok=True)
                    raise StepError(f"grootte klopt niet ({part.stat().st_size} != {m.size})")
                os.replace(part, dest)
                if self.cache:
                    self.cache.put(dest, key, actual)
                return "mirror" if kind == "mirror" else "gedownload"
            except StepError as e:
                if kind == "mirror":
                    if "404" in str(e):
                        log(f"{m.rel}: niet in mirror, val terug op bron")
                    else:
                        log(f"{m.rel}: mirror mislukt ({e}), val terug op bron", "warn")
                    part.unlink(missing_ok=True)
                    continue
                last_err = e
            except Exception as e:
                if kind == "mirror":
                    log(f"{m.rel}: mirror niet bereikbaar ({type(e).__name__}), val terug op bron", "warn")
                    continue
                last_err = StepError(f"{type(e).__name__}: {e}")
        raise last_err or StepError("geen bron beschikbaar")

    @staticmethod
    def _copy(src: Path, part: Path, label: str) -> str:
        h = hashlib.sha256()
        prog = Progress(label, src.stat().st_size)
        with open(src, "rb") as fi, open(part, "wb") as fo:
            while chunk := fi.read(8 * CHUNK):
                fo.write(chunk)
                h.update(chunk)
                prog.add(len(chunk))
        return h.hexdigest()


# ----------------------------------------------------------------------------- processen
def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None, check: bool = True,
        capture: bool = False, timeout: int | None = None) -> subprocess.CompletedProcess:
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, timeout=timeout, text=True,
                       encoding="utf-8", errors="replace",
                       stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.STDOUT if capture else None)
    if check and r.returncode != 0:
        tail = ("\n" + "\n".join((r.stdout or "").strip().splitlines()[-25:])) if capture else ""
        raise StepError(f"'{Path(str(cmd[0])).name} {' '.join(str(c) for c in cmd[1:4])} …' faalde (exit {r.returncode}){tail}")
    return r


def git(*args, cwd: Path | None = None, capture: bool = True, check: bool = True) -> str:
    exe = os.environ.get("COMFYPACK_GIT") or shutil.which("git")
    if not exe:
        raise StepError("git niet gevonden (install.ps1 regelt dit op Windows)")
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    r = run([exe, *GIT_OPTS, *args], cwd=cwd, env=env, capture=capture, check=check)
    return (r.stdout or "").strip()


def find_uv(root: Path) -> str:
    for c in (os.environ.get("COMFYPACK_UV"), str(root / ".tools" / "uv" / ("uv.exe" if IS_WIN else "uv")),
              shutil.which("uv")):
        if c and Path(c).is_file():
            return c
    raise StepError("uv niet gevonden — draai install.ps1 of installeer uv (https://docs.astral.sh/uv/)")


class InstallLock:
    def __init__(self, path: Path):
        self.path = path
        self.fh = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.path, "a+")
        try:
            if IS_WIN:
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise StepError(f"er draait al een installatie op deze map ({self.path})") from None
        return self

    def __exit__(self, *exc):
        try:
            if IS_WIN:
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        self.fh.close()


# ----------------------------------------------------------------------------- git-repo's
def ensure_repo(url: str, dest: Path, ref: str, label: str, known: dict) -> str:
    """Zet dest op exact 'ref' (shallow). Werkt ook als dest al bestanden bevat."""
    dest.mkdir(parents=True, exist_ok=True)
    if not (dest / ".git").exists():
        git("init", "-q", str(dest))
    cur_url = git("remote", "get-url", "origin", cwd=dest, check=False)
    if not cur_url or cur_url.startswith(("error", "fatal")):
        git("remote", "add", "origin", url, cwd=dest)
    elif norm_repo(cur_url) != norm_repo(url):
        git("remote", "set-url", "origin", url, cwd=dest)
    head = git("rev-parse", "-q", "--verify", "HEAD", cwd=dest, check=False)
    is_sha = bool(re.fullmatch(r"[0-9a-f]{40}", ref))
    # Commit of al eerder opgehaalde tag (tags = onveranderlijk): niets ophalen.
    if head and ((is_sha and head == ref) or (known.get("ref") == ref and known.get("commit") == head
                                               and re.match(r"^v?\d", ref))):
        dirty = git("status", "--porcelain", "--untracked-files=no", cwd=dest, check=False)
        if not dirty:
            return head
        log(f"{label}: lokale wijzigingen gevonden, worden teruggezet", "warn")
        git("checkout", "-q", "--force", "--detach", head, cwd=dest)
        return head
    log(f"{label}: ophalen {ref[:12] if is_sha else ref}")
    git("fetch", "-q", "--depth", "1", "--force", "origin", ref, cwd=dest)
    git("checkout", "-q", "--force", "--detach", "FETCH_HEAD", cwd=dest)
    if (dest / ".gitmodules").exists():
        git("submodule", "update", "-q", "--init", "--recursive", "--depth", "1", cwd=dest)
    return git("rev-parse", "HEAD", cwd=dest)


# ----------------------------------------------------------------------------- torch / gpu
@dataclasses.dataclass
class Gpu:
    name: str
    driver: float
    cc: float | None


def detect_gpu() -> Gpu | None:
    smi = shutil.which("nvidia-smi")
    if not smi and IS_WIN:
        c = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe"
        smi = str(c) if c.exists() else None
    if not smi:
        return None
    for fields in ("name,driver_version,compute_cap", "name,driver_version"):
        try:
            r = run([smi, f"--query-gpu={fields}", "--format=csv,noheader"], capture=True, check=False, timeout=30)
        except Exception:
            return None
        if r.returncode == 0 and r.stdout.strip():
            parts = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]
            try:
                drv = float(".".join(parts[1].split(".")[:2]))
                cc = float(parts[2]) if len(parts) > 2 else None
            except ValueError:
                continue
            return Gpu(parts[0], drv, cc)
    return None


def resolve_torch_index(setting: str) -> tuple[str | None, str | None, str]:
    """-> (index_url of None voor PyPI, verwachte lokale tag, uitleg)"""
    s = str(setting).strip()
    if s.startswith(("http://", "https://")):
        return s, None, f"index {s}"
    if s == "pypi":
        return None, None, "PyPI"
    if s in KNOWN_TORCH_INDEXES:
        return TORCH_INDEX + s, s, f"{s} (vast ingesteld)"
    if s != "auto":
        raise ConfigError(f"[torch] index '{s}' onbekend")
    if sys.platform == "darwin":
        return None, None, "macOS → PyPI (MPS)"
    gpu = detect_gpu()
    if not gpu:
        log("geen NVIDIA-GPU gevonden (nvidia-smi ontbreekt) → CPU-torch. Zeer traag!", "warn")
        return TORCH_INDEX + "cpu", "cpu", "cpu (geen NVIDIA)"
    desc = f"{gpu.name}, driver {gpu.driver:g}" + (f", compute {gpu.cc:g}" if gpu.cc else "")
    if gpu.cc is not None and gpu.cc < 7.5:
        log(f"{gpu.name} is ouder dan Turing: cu126 (torch 2.14 is de laatste versie met support)", "warn")
        return TORCH_INDEX + "cu126", "cu126", f"cu126 ({desc})"
    if gpu.driver >= 580:
        return TORCH_INDEX + "cu130", "cu130", f"cu130 ({desc})"
    if gpu.cc is not None and gpu.cc >= 10:
        raise StepError(f"{gpu.name} (Blackwell) vereist NVIDIA-driver >= 580; nu {gpu.driver:g}. Update de driver.")
    if gpu.driver >= 560:
        log(f"driver {gpu.driver:g} < 580: noodgedwongen cu126. Update de driver voor de beste prestaties.", "warn")
        return TORCH_INDEX + "cu126", "cu126", f"cu126 ({desc})"
    raise StepError(f"NVIDIA-driver {gpu.driver:g} is te oud (minimaal 560, advies >= 580)")


# ----------------------------------------------------------------------------- installatie
class Installer:
    def __init__(self, man: Manifest, root: Path, sel: Selection, profile: str | None, opts: argparse.Namespace):
        self.man, self.root, self.sel, self.profile, self.opts = man, root, sel, profile, opts
        self.cfg = man.cfg
        self.comfy = root / "ComfyUI"
        self.venv = root / "venv"
        self.py = self.venv / ("Scripts/python.exe" if IS_WIN else "bin/python")
        self.meta = root / ".comfypack"
        self.state_path = self.meta / "state.json"
        self.constraints = self.meta / "constraints.txt"
        try:
            self.state = json.loads(self.state_path.read_text("utf-8"))
        except Exception:
            self.state = {}
        self.state.setdefault("nodes", {})
        self.uv = find_uv(root)
        self.env = dict(os.environ)
        self.env.setdefault("UV_PYTHON_INSTALL_DIR", str(root / ".python"))
        self.env.setdefault("UV_CACHE_DIR", str(root / ".cache" / "uv"))
        self.env.setdefault("UV_PYTHON_PREFERENCE", "only-managed")
        self.env["UV_NO_PROGRESS"] = "1"
        # venv is alleen-lezen voor studenten: .pyc nu maken, anders bij elke start opnieuw
        self.env.setdefault("UV_COMPILE_BYTECODE", "1")
        self.env.pop("VIRTUAL_ENV", None)
        self.errors: list[str] = []
        self.results: dict[str, str] = {}

    # -- hulpfuncties
    def save_state(self) -> None:
        self.meta.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2), "utf-8")
        os.replace(tmp, self.state_path)

    def uv_pip(self, *args: str, label: str) -> None:
        cmd = [self.uv, "pip", "install", "--python", str(self.py), *args]
        if self.constraints.exists():
            cmd += ["--constraint", str(self.constraints)]
        r = run(cmd, env=self.env, capture=True, check=False)
        if r.returncode != 0:
            tail = "\n".join(r.stdout.strip().splitlines()[-20:])
            raise StepError(f"{label}: pakketinstallatie mislukt\n{tail}")
        changed = [ln.strip() for ln in r.stdout.splitlines() if ln.strip().startswith(("+ ", "- "))]
        if changed:
            log(f"{label}: {len([c for c in changed if c.startswith('+')])} pakket(ten) geïnstalleerd/bijgewerkt")

    def installed_versions(self, names) -> dict[str, str]:
        code = ("import importlib.metadata as m,json,sys\nout={}\nfor n in sys.argv[1:]:\n"
                " try: out[n]=m.version(n)\n except m.PackageNotFoundError: pass\nprint(json.dumps(out))")
        r = run([self.py, "-s", "-c", code, *names], env=self.env, capture=True, check=False)
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            return {}

    @staticmethod
    def hash_text(*parts) -> str:
        h = hashlib.sha256()
        for p in parts:
            h.update((p if isinstance(p, bytes) else str(p).encode()) + b"\0")
        return h.hexdigest()[:16]

    def file_bytes(self, p: Path) -> bytes:
        return p.read_bytes() if p.exists() else b""

    # -- stappen
    def step_core(self) -> None:
        c = self.cfg["comfyui"]
        log(f"ComfyUI {c['ref']}", "step")
        commit = ensure_repo(c["repo"], self.comfy, c["ref"], "ComfyUI", self.state.get("comfyui", {}))
        self.state["comfyui"] = {"ref": c["ref"], "commit": commit}
        self.save_state()

    def step_venv(self) -> None:
        want = str(self.cfg["python"]["version"])
        log(f"Python {want} (uv)", "step")
        if self.py.exists():
            r = run([self.py, "-c", "import sys;print('%d.%d'%sys.version_info[:2])"], capture=True, check=False)
            have = r.stdout.strip() if r.returncode == 0 else ""
            if have == want or (have and want.startswith(have + ".")) or (have and have.startswith(want)):
                log(f"venv aanwezig (Python {have})")
                return
            log(f"venv heeft Python {have or '?'}, verwacht {want}: opnieuw aanmaken", "warn")
            shutil.rmtree(self.venv)
            self.state.pop("torch", None)
            self.state.pop("core_reqs", None)
            self.state["nodes"] = {}
        run([self.uv, "venv", "--seed", "--python", want, str(self.venv)], env=self.env, capture=True)
        log(f"venv aangemaakt in {self.venv}", "ok")

    def step_torch(self) -> None:
        t = self.cfg["torch"]
        idx_url, tag, why = resolve_torch_index(self.opts.torch_index or t["index"])
        pkgs = list(t["packages"])
        log(f"PyTorch: {why}", "step")
        names = [re.split(r"[<>=!~\[ ;]", p, maxsplit=1)[0].lower() for p in pkgs]
        have = self.installed_versions(names)
        want_key = self.hash_text(json.dumps(pkgs), idx_url)
        reasons = []
        for spec, name in zip(pkgs, names):
            v = have.get(name)
            if not v:
                reasons.append(f"{name} ontbreekt")
            elif tag and not v.endswith("+" + tag):
                reasons.append(f"{name} {v} is geen {tag}-build")
            elif "==" in spec and v.split("+")[0] != spec.split("==", 1)[1].strip():
                reasons.append(f"{name} {v} != {spec}")
        if not reasons and self.state.get("torch") not in (None, want_key):
            reasons.append("torch-instellingen gewijzigd")
        if reasons:
            log("installeren: " + "; ".join(reasons) + " (eerste keer: ~2-3 GB)")
            args = [*pkgs]
            if idx_url:
                # extra-index heeft bij uv voorrang: torch komt van de PyTorch-index
                args += ["--extra-index-url", idx_url]
            if have:
                for n in names:
                    args += ["--reinstall-package", n]
            self.constraints.unlink(missing_ok=True)  # oude pins mogen deze stap niet blokkeren
            self.uv_pip(*args, label="torch")
        have = self.installed_versions(TORCH_PACKAGES)
        self.meta.mkdir(parents=True, exist_ok=True)
        lines = ["# automatisch gegenereerd door comfypack — custom nodes mogen torch niet vervangen"]
        lines += [f"{n}=={v}" for n, v in have.items()]
        lines += list(self.cfg["python"].get("constraints", []))
        self.constraints.write_text("\n".join(lines) + "\n", "utf-8")
        self.state["torch"] = want_key
        self.state["torch_versions"] = have
        self.save_state()
        r = run([self.py, "-s", "-c", "import torch;print(torch.__version__, torch.cuda.is_available(), "
                 "torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"],
                env=self.env, capture=True, check=False)
        info = (r.stdout or "").strip().splitlines()[-1:] or ["?"]
        if r.returncode != 0:
            raise StepError(f"torch laadt niet:\n{r.stdout[-1500:]}")
        log(f"torch {info[0]}", "ok")
        if tag and tag.startswith("cu") and " False" in info[0]:
            log("CUDA-torch geïnstalleerd maar GPU niet bruikbaar — driver controleren", "warn")

    def step_core_reqs(self) -> None:
        log("ComfyUI-afhankelijkheden", "step")
        reqs = [self.comfy / "requirements.txt"]
        if self.cfg["install"]["manager"] and (self.comfy / "manager_requirements.txt").exists():
            reqs.append(self.comfy / "manager_requirements.txt")
        key = self.hash_text(*(self.file_bytes(p) for p in reqs), self.file_bytes(self.constraints), *self.sel.pip)
        if self.state.get("core_reqs") == key:
            log("ongewijzigd")
            return
        args = []
        for p in reqs:
            args += ["-r", str(p)]
        args += self.sel.pip
        self.uv_pip(*args, label="ComfyUI")
        self.state["core_reqs"] = key
        self.save_state()
        log("afhankelijkheden in orde", "ok")

    def step_nodes(self) -> None:
        log(f"Custom nodes ({len(self.sel.nodes)})", "step")
        cn = self.comfy / "custom_nodes"
        cons = self.file_bytes(self.constraints)
        for n in self.sel.nodes:
            d = cn / n.name
            prev = self.state["nodes"].get(n.name, {})
            try:
                commit = ensure_repo(n.repo, d, n.ref, n.name, prev)
                req = d / "requirements.txt"
                key = self.hash_text(commit, self.file_bytes(req) if n.requirements else b"", cons, *n.pip)
                if prev.get("deps") != key:
                    args = []
                    if n.requirements and req.exists():
                        args += ["-r", str(req)]
                    args += list(n.pip)
                    if args:
                        self.uv_pip(*args, label=n.name)
                    inst = d / "install.py"
                    if n.install_script and inst.exists() and prev.get("commit") != commit:
                        log(f"{n.name}: install.py uitvoeren")
                        env = dict(self.env, PIP_CONSTRAINT=str(self.constraints), UV_CONSTRAINT=str(self.constraints),
                                   PIP_DISABLE_PIP_VERSION_CHECK="1", COMFYUI_PATH=str(self.comfy),
                                   VIRTUAL_ENV=str(self.venv),
                                   PATH=str(self.py.parent) + os.pathsep + self.env.get("PATH", ""))
                        run([self.py, "-s", "install.py"], cwd=d, env=env, capture=True, timeout=3600)
                self.state["nodes"][n.name] = {"repo": n.repo, "ref": n.ref, "commit": commit, "deps": key}
                self.save_state()
                self.results[f"node:{n.name}"] = "ok"
                log(f"{n.name} @ {commit[:10]}", "ok")
            except (StepError, subprocess.TimeoutExpired) as e:
                self.results[f"node:{n.name}"] = "fout"
                self.errors.append(f"node {n.name}: {e}")
                log(f"{n.name}: {e}", "err")
        listed = {n.name.lower() for n in self.sel.nodes}
        for name in list(self.state["nodes"]):
            if name.lower() not in listed:
                self.state["nodes"].pop(name)
        if self.cfg["install"]["prune_unlisted_nodes"] and cn.exists():
            dis = cn / ".disabled"
            for d in cn.iterdir():
                if d.is_dir() and not d.name.startswith((".", "__")) and d.name.lower() not in listed:
                    dis.mkdir(exist_ok=True)
                    target = dis / d.name
                    if target.exists():
                        target = dis / f"{d.name}-{dt.datetime.now():%Y%m%d%H%M%S}"
                    shutil.move(str(d), str(target))
                    log(f"{d.name}: staat niet in de packs → custom_nodes/.disabled", "warn")

    def step_files(self) -> None:
        if not self.sel.files:
            return
        log(f"Bestanden ({len(self.sel.files)})", "step")
        for f in self.sel.files:
            dest = self.comfy / f.dest
            srcs = [f.src] if f.src.is_file() else [p for p in f.src.rglob("*") if p.is_file()]
            for s in srcs:
                t = dest if f.src.is_file() else dest / s.relative_to(f.src)
                if t.exists() and t.read_bytes() == s.read_bytes():
                    continue
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(s, t)
                log(f"{t.relative_to(self.comfy)}", "ok")

    def step_launchers(self) -> None:
        log("Startscripts", "step")
        L = self.cfg["launch"]
        base = ["main.py", "--listen", str(L["listen"]), "--port", str(L["port"])]
        base.append("--auto-launch" if L["auto_launch"] else "--disable-auto-launch")
        for k in ("output_directory", "input_directory", "user_directory", "temp_directory"):
            if L.get(k):
                base += [f"--{k.replace('_', '-')}", str(L[k])]
        base += [str(a) for a in L.get("args", [])]
        student = base + (["--enable-manager"] if L["manager_ui"] and self.cfg["install"]["manager"] else [])
        admin = base + (["--enable-manager"] if self.cfg["install"]["manager"] else [])
        for fname, args, title in (("start-comfyui", student, "ComfyUI"), ("start-comfyui-beheer", admin, "ComfyUI (beheer)")):
            if IS_WIN:
                q = " ".join(f'"{a}"' if (" " in a or "%" in a) else a for a in args)
                body = (f"@echo off\r\ntitle {title}\r\ncd /d \"%~dp0ComfyUI\"\r\nset PYTHONUTF8=1\r\n"
                        f"\"%~dp0venv\\Scripts\\python.exe\" -s {q} %*\r\n"
                        f"if errorlevel 1 pause\r\n")
                p = self.root / f"{fname}.bat"
            else:
                q = " ".join(f'"{a}"' for a in args)
                body = (f"#!/usr/bin/env bash\ncd \"$(dirname \"$0\")/ComfyUI\"\n"
                        f"exec \"../venv/bin/python\" -s {q} \"$@\"\n")
                p = self.root / f"{fname}.sh"
            p.write_text(body, "utf-8", newline="")
            if not IS_WIN:
                p.chmod(0o755)
            log(p.name, "ok")
        # Snelkoppeling naar de engine zelf (freeze, verify, add-model …) met de beheerde Python.
        pyver = str(self.cfg["python"]["version"])
        script = REPO_DIR / "installer" / "comfypack.py"
        if IS_WIN:
            body = ("@echo off\r\nsetlocal\r\n"
                    "set \"UV_PYTHON_INSTALL_DIR=%~dp0.python\"\r\nset UV_PYTHON_PREFERENCE=only-managed\r\n"
                    "set UV_SYSTEM_CERTS=1\r\nset PYTHONUTF8=1\r\n"
                    f"\"{self.uv}\" run --no-project --python {pyver} -- \"{script}\" %*\r\n")
            p = self.root / "comfypack.bat"
        else:
            body = (f"#!/usr/bin/env bash\nexport UV_PYTHON_INSTALL_DIR=\"$(dirname \"$0\")/.python\" UV_PYTHON_PREFERENCE=only-managed\n"
                    f"exec \"{self.uv}\" run --no-project --python {pyver} -- \"{script}\" \"$@\"\n")
            p = self.root / "comfypack.sh"
        p.write_text(body, "utf-8", newline="")
        if not IS_WIN:
            p.chmod(0o755)

    def start_models(self, pool: ThreadPoolExecutor, dl: Downloader) -> dict:
        def job(m: Model) -> str:
            try:
                res = dl.ensure(m, self.comfy / "models")
            except Exception as e:
                log(f"{m.rel}: {e}", "err")
                raise
            if res != "aanwezig":
                log(f"{m.rel} ({res})", "ok")
            return res
        return {pool.submit(job, m): m for m in self.sel.models}

    def run(self) -> int:
        t0 = time.monotonic()
        mirror = self.opts.mirror if self.opts.mirror is not None else self.cfg["install"]["mirror"]
        log(f"comfypack {VERSION} — profiel '{self.profile or '-'}' → packs: {', '.join(self.sel.packs)}", "step")
        log(f"doelmap {self.root} | {len(self.sel.nodes)} nodes, {len(self.sel.models)} modellen"
            + (f" | mirror {mirror}" if mirror else ""))
        for w in self.man.warnings:
            log(w, "warn")
        cache = HashCache(self.meta / "hashes.json")
        dl = Downloader(load_secrets(self.root), mirror, cache)
        pool = ThreadPoolExecutor(max_workers=max(1, int(self.cfg["install"]["parallel_downloads"])))
        futs: dict = {}
        try:
            self.step_core()                     # eerst: modellen landen in ComfyUI/models
            if not self.opts.skip_models:
                log(f"Modellen ({len(self.sel.models)}) — downloads lopen op de achtergrond", "step")
                futs = self.start_models(pool, dl)
            self.step_venv()
            self.step_torch()
            self.step_core_reqs()
            self.step_nodes()
            self.step_files()
            self.step_launchers()
        except (StepError, ConfigError, subprocess.TimeoutExpired) as e:
            self.errors.append(str(e))
            log(str(e), "err")
            log("installatie afgebroken; lopende downloads worden nog afgemaakt", "warn")
        except KeyboardInterrupt:
            pool.shutdown(wait=False, cancel_futures=True)
            cache.save()
            raise
        if futs:
            log("wachten op modeldownloads…")
        counts: dict[str, int] = {}
        for fut, m in futs.items():
            try:
                res = fut.result()
                counts[res] = counts.get(res, 0) + 1
            except Exception as e:
                counts["fout"] = counts.get("fout", 0) + 1
                self.errors.append(f"model {m.rel}: {e}")
        pool.shutdown()
        cache.save()
        self.state.update({
            "profile": self.profile, "packs": self.sel.packs, "pack_commit": pack_commit(),
            "finished": dt.datetime.now().isoformat(timespec="seconds"),
            "ok": not self.errors, "errors": self.errors[-50:], "comfypack": VERSION,
        })
        self.save_state()
        mins = (time.monotonic() - t0) / 60
        log("Samenvatting", "step")
        if futs:
            log("modellen: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
        if self.errors:
            for e in self.errors:
                log(e.splitlines()[0], "err")
            log(f"klaar met {len(self.errors)} fout(en) in {mins:.1f} min — opnieuw draaien hervat waar het bleef", "err")
            return 1
        log(f"ComfyUI staat klaar in {mins:.1f} min: {self.root / ('start-comfyui.bat' if IS_WIN else 'start-comfyui.sh')}", "ok")
        return 0


def pack_commit() -> str | None:
    if (REPO_DIR / ".git").exists():
        try:
            return git("rev-parse", "HEAD", cwd=REPO_DIR)
        except Exception:
            return None
    return None


# ----------------------------------------------------------------------------- commando's
def cmd_install(a) -> int:
    man = Manifest(REPO_DIR)
    packs = man.resolve(a.profile, a.packs)
    sel = man.collect(packs)
    root = Path(a.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with InstallLock(root / ".comfypack" / "install.lock"):
        return Installer(man, root, sel, a.profile, a).run()


def cmd_verify(a) -> int:
    man = Manifest(REPO_DIR)
    root = Path(a.root).resolve()
    state = {}
    try:
        state = json.loads((root / ".comfypack" / "state.json").read_text("utf-8"))
    except Exception:
        pass
    profile = a.profile or state.get("profile")
    sel = man.collect(man.resolve(profile, a.packs or (None if profile else state.get("packs"))))
    cache = HashCache(root / ".comfypack" / "hashes.json")
    bad = 0
    log(f"Controle {root} ({', '.join(sel.packs)})", "step")
    for n in sel.nodes:
        d = root / "ComfyUI" / "custom_nodes" / n.name
        head = git("rev-parse", "HEAD", cwd=d, check=False) if (d / ".git").exists() else ""
        if not head:
            bad += 1
            log(f"node {n.name}: ontbreekt", "err")
        elif re.fullmatch(r"[0-9a-f]{40}", n.ref) and head != n.ref:
            bad += 1
            log(f"node {n.name}: staat op {head[:10]}, verwacht {n.ref[:10]}", "err")
    for m in sel.models:
        p = root / "ComfyUI" / "models" / m.dir / m.file
        if not p.exists():
            bad += 1
            log(f"model {m.rel}: ontbreekt", "err")
            continue
        if m.size and p.stat().st_size != m.size:
            bad += 1
            log(f"model {m.rel}: grootte klopt niet", "err")
        elif m.sha256 and cache.get(p, f"models/{m.rel}") != m.sha256:
            bad += 1
            log(f"model {m.rel}: sha256 klopt niet", "err")
    cache.save()
    if bad:
        log(f"{bad} probleem/problemen — draai install opnieuw om te herstellen", "err")
        return 1
    log(f"alles in orde ({len(sel.nodes)} nodes, {len(sel.models)} modellen)", "ok")
    return 0


def cmd_list(a) -> int:
    man = Manifest(REPO_DIR)
    c = man.cfg
    print(f"ComfyUI {c['comfyui']['ref']} | Python {c['python']['version']} | {' '.join(c['torch']['packages'])}\n")
    print("Profielen:")
    for name, packs in man.profiles.items():
        sel = man.collect(man.resolve(packs=packs))
        known = sum(m.size or 0 for m in sel.models)
        unknown = sum(1 for m in sel.models if not m.size)
        extra = f" + {unknown} onbekend" if unknown else ""
        print(f"  {name:<14} {', '.join(sel.packs)}  ({len(sel.nodes)} nodes, {len(sel.models)} modellen, {human(known)}{extra})")
    print("\nPacks:")
    for name, data in man.packs.items():
        print(f"  {name:<14} {data.get('description', '')}")
        for n in data.get("nodes", []):
            print(f"      node   {url_filename(n['repo']).removesuffix('.git')} @ {str(n.get('ref', 'HEAD'))[:12]}")
        for m in data.get("models", []):
            size = f"  {human(m['size'])}" if m.get("size") else ""
            print(f"      model  {m['dir']}/{m.get('file') or url_filename(m['url'])}{size}")
    return 0


def cmd_validate(a) -> int:
    man = Manifest(REPO_DIR)
    problems = man.validate()
    for w in sorted(set(man.warnings)):
        log(w, "warn")
    for p in problems:
        log(p, "err")
    if problems:
        return 2
    log(f"manifest geldig: {len(man.packs)} packs, {len(man.profiles)} profielen", "ok")
    if not a.online:
        return 0
    sel = man.collect(list(man.packs))
    secrets = load_secrets(None)
    bad = 0
    log("Online controle van model-URL's", "step")
    for m in sel.models:
        p = probe(m.url, token_for(m.url, secrets))
        notes = []
        if p.ok and m.size and p.size and p.size != m.size:
            notes.append(f"grootte {p.size} != manifest {m.size}")
        if p.ok and m.sha256 and p.sha256 and p.sha256 != m.sha256:
            notes.append("sha256 wijkt af van server")
        ok = p.ok and not notes
        bad += not ok
        log(f"{m.rel:<60} {human(p.size):>9}  {p.status} {'; '.join(notes)}", "ok" if ok else "err")
    for n in sel.nodes:
        r = git("ls-remote", n.repo, "HEAD", check=False)
        ok = bool(r) and not r.startswith(("fatal", "error"))
        bad += not ok
        log(f"node {n.name}: {'bereikbaar' if ok else 'NIET bereikbaar'}", "ok" if ok else "err")
    return 1 if bad else 0


def cmd_freeze(a) -> int:
    root = Path(a.root).resolve()
    comfy = root / "ComfyUI" if (root / "ComfyUI").exists() else root
    cn = comfy / "custom_nodes"
    if not cn.exists():
        raise ConfigError(f"{cn} niet gevonden")
    man = Manifest(REPO_DIR)
    out = [f"# Vastgelegd met comfypack freeze op {dt.date.today()} vanaf {comfy}",
           f"description = {toml_str(a.description or 'Vastgelegd vanaf referentie-PC')}", ""]
    for d in sorted(cn.iterdir(), key=lambda p: p.name.lower()):
        if not d.is_dir() or d.name.startswith((".", "__")):
            continue
        url, ref, note = "", "", ""
        if (d / ".git").exists():
            url = git("remote", "get-url", "origin", cwd=d, check=False)
            ref = git("rev-parse", "HEAD", cwd=d, check=False)
            if url.startswith(("error", "fatal")) or not re.fullmatch(r"[0-9a-f]{40}", ref):
                url, ref = "", ""
            if git("status", "--porcelain", "--untracked-files=no", cwd=d, check=False):
                note = "LET OP: lokale wijzigingen, die worden niet meegenomen"
        elif (d / "pyproject.toml").exists():       # Comfy Registry (zip) installatie
            try:
                pp = tomllib.loads((d / "pyproject.toml").read_text("utf-8"))
            except Exception:
                pp = {}
            proj = pp.get("project", {})
            urls = {k.lower(): v for k, v in proj.get("urls", {}).items()}
            url = urls.get("repository") or urls.get("source") or ""
            ver = proj.get("version", "")
            if url and ver:
                tags = git("ls-remote", "--tags", "--refs", url, check=False).splitlines()
                names = {t.rsplit("/", 1)[-1] for t in tags if "refs/tags/" in t}
                ref = next((t for t in (f"v{ver}", ver) if t in names), "")
                note = "" if ref else f"registry-versie {ver}: geen bijpassende git-tag, controleer ref"
                if not ref:
                    ref = git("ls-remote", url, "HEAD", check=False).split("\t")[0]
        if not url:
            out += [f"# {d.name}: geen git-repo of registry-info gevonden — handmatig toevoegen", ""]
            continue
        if note:
            out.append(f"# {d.name}: {note}")
        out.append("[[nodes]]")
        out.append(f"repo = {toml_str(url)}")
        out.append(f"ref = {toml_str(ref)}")
        if d.name != url_filename(url).removesuffix(".git"):
            out.append(f"name = {toml_str(d.name)}")
        out.append("")
    known = {m.rel.lower() for m in man.collect(list(man.packs)).models}
    md = comfy / "models"
    extra = []
    if md.exists():
        for p in sorted(md.rglob("*")):
            if p.is_file() and p.suffix.lower() in MODEL_EXTS:
                rel = p.relative_to(md).as_posix()
                if rel.lower() not in known:
                    extra.append((rel, p.stat().st_size))
    if extra:
        out.append("# ---- Modellen die nog in geen enkel pack staan: vul de URL in en haal het # weg")
        for rel, size in extra:
            d_, f_ = rel.rsplit("/", 1) if "/" in rel else ("", rel)
            out += ["# [[models]]", f"# dir = {toml_str(d_)}", f"# file = {toml_str(f_)}",
                    "# url = \"https://…\"", f"# size = {size}", ""]
    text = "\n".join(out).rstrip() + "\n"
    if a.write:
        p = Path(a.write)
        if p.exists() and not a.force:
            raise ConfigError(f"{p} bestaat al (gebruik --force)")
        p.write_text(text, "utf-8")
        log(f"geschreven naar {p} — controleer en commit", "ok")
    else:
        print(text)
    return 0


def cmd_mirror(a) -> int:
    man = Manifest(REPO_DIR)
    packs = list(man.packs) if a.all else man.resolve(a.profile, a.packs)
    sel = man.collect(packs)
    dest = Path(a.dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    dl = Downloader(load_secrets(None), "", HashCache(dest / ".comfypack-hashes.json"))
    log(f"Mirror {dest}: {len(sel.models)} modellen uit {', '.join(packs)}", "step")
    errors = 0
    with ThreadPoolExecutor(max_workers=int(man.cfg["install"]["parallel_downloads"])) as pool:
        futs = {pool.submit(dl.ensure, m, dest): m for m in sel.models}
        for f, m in futs.items():
            try:
                log(f"{m.rel} ({f.result()})", "ok")
            except Exception as e:
                errors += 1
                log(f"{m.rel}: {e}", "err")
    dl.cache.save()
    return 1 if errors else 0


def civitai_info(url: str, token: str | None) -> Probe | None:
    mm = re.search(r"civitai\.com/api/download/models/(\d+)", url)
    if not mm:
        return None
    try:
        r, _ = _open(f"https://civitai.com/api/v1/model-versions/{mm.group(1)}", token, timeout=30)
        with r:
            data = json.loads(r.read())
        files = data.get("files", [])
        f = next((x for x in files if x.get("primary")), files[0] if files else None)
        if not f:
            return None
        sha = (f.get("hashes", {}).get("SHA256") or "").lower() or None
        size = int(f["sizeKB"] * 1024) if f.get("sizeKB") else None
        return Probe(True, "civitai", None if sha else size, sha, f.get("name"))
    except Exception as e:
        log(f"Civitai-API niet bereikbaar ({e}); val terug op downloadinfo", "warn")
        return None


def cmd_add_model(a) -> int:
    man = Manifest(REPO_DIR)
    secrets = load_secrets(None)
    url = normalize_url(a.url)
    if url != a.url.strip():
        log("webpagina-link omgezet naar directe downloadlink")
    if re.search(r"civitai\.com/models/", url):
        raise ConfigError("dit is een Civitai-webpagina; gebruik de downloadlink (rechtsklik op 'Download' > 'Link kopiëren')")
    token = token_for(url, secrets)
    info = civitai_info(url, token) or probe(url, token)
    if not info.ok:
        raise ConfigError(f"URL niet bereikbaar: {info.status}")
    fname = a.file or info.filename or url_filename(url)
    if not fname or "." not in fname:
        raise ConfigError("bestandsnaam onbekend; geef --file op")
    sha, size = info.sha256, info.size
    if not sha and not a.no_hash:
        log(f"sha256 berekenen: {fname} wordt eenmalig gedownload ({human(size)})…")
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "f.part"
            _, sha = http_download(url, part, token, fname)
            sha = sha or sha256_file(part)
            size = part.stat().st_size
    mdir = safe_rel(a.dir, "--dir")
    rel = f"{mdir}/{fname}".lower()
    if rel in {m.rel.lower() for m in man.collect(list(man.packs)).models}:
        raise ConfigError(f"{mdir}/{fname} staat al in een pack")
    pack = REPO_DIR / "packs" / f"{a.pack}.toml"
    block = ["", "[[models]]", f"dir = {toml_str(mdir)}", f"url = {toml_str(url)}"]
    if fname != url_filename(url):
        block.append(f"file = {toml_str(fname)}")
    if sha:
        block.append(f"sha256 = {toml_str(sha)}")
    if size and not sha:
        block.append(f"size = {size}")
    if not pack.exists():
        pack.write_text(f"description = {toml_str(a.pack)}\n", "utf-8")
        log(f"nieuw pack {pack.name} — vergeet niet het aan een profiel toe te voegen", "warn")
    with open(pack, "a", encoding="utf-8") as f:
        f.write("\n".join(block) + "\n")
    Manifest(REPO_DIR).collect(list(Manifest(REPO_DIR).packs))  # controle
    log(f"{mdir}/{fname} toegevoegd aan {pack.name} ({human(size)})", "ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="comfypack", description="Reproduceerbare ComfyUI-installaties")
    ap.add_argument("--version", action="version", version=VERSION)
    ap.add_argument("--log-file", help="log ook naar dit bestand (aanvullen)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def sel_args(p):
        p.add_argument("--profile", help="profiel uit comfy-pack.toml")
        p.add_argument("--packs", type=lambda s: [x.strip() for x in s.split(",") if x.strip()],
                       help="losse packs, komma-gescheiden (in plaats van --profile)")

    p = sub.add_parser("install", help="installeren of bijwerken (idempotent)")
    p.add_argument("--root", required=True, help="installatiemap, bv. C:\\ComfyUI")
    sel_args(p)
    p.add_argument("--skip-models", action="store_true", help="modellen overslaan")
    p.add_argument("--mirror", default=None, help="mirror-pad of -URL (overschrijft comfy-pack.toml)")
    p.add_argument("--torch-index", default=None, help="overschrijft [torch] index (auto/cu130/cpu/pypi/URL)")
    p.set_defaults(fn=cmd_install)

    p = sub.add_parser("verify", help="controleren of een installatie compleet is")
    p.add_argument("--root", required=True)
    sel_args(p)
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("list", help="profielen en packs tonen")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("validate", help="manifest controleren (CI)")
    p.add_argument("--online", action="store_true", help="ook URL's en repo's controleren")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("freeze", help="custom nodes van een (referentie-)installatie vastleggen")
    p.add_argument("--root", required=True, help="installatiemap of ComfyUI-map")
    p.add_argument("--write", help="naar dit pack-bestand schrijven, bv. packs/referentie.toml")
    p.add_argument("--description")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_freeze)

    p = sub.add_parser("mirror", help="modellen naar een lokale mirror (share/HTTP-map) halen")
    p.add_argument("--dest", required=True)
    sel_args(p)
    p.add_argument("--all", action="store_true", help="alle packs")
    p.set_defaults(fn=cmd_mirror)

    p = sub.add_parser("add-model", help="model/LoRA aan een pack toevoegen (met grootte + sha256)")
    p.add_argument("url")
    p.add_argument("--pack", required=True, help="naam van het pack (packs/<naam>.toml)")
    p.add_argument("--dir", required=True, help="modelmap, bv. loras of loras/vakgroep")
    p.add_argument("--file", help="bestandsnaam (standaard uit URL/server)")
    p.add_argument("--no-hash", action="store_true", help="geen sha256 berekenen als de server die niet geeft")
    p.set_defaults(fn=cmd_add_model)

    a = ap.parse_args(argv)
    global _log_file
    if a.log_file:
        Path(a.log_file).parent.mkdir(parents=True, exist_ok=True)
        _log_file = open(a.log_file, "a", encoding="utf-8")
    if a.cmd == "mirror" and not (a.all or a.profile or a.packs):
        ap.error("mirror: geef --all, --profile of --packs")
    try:
        return a.fn(a)
    except ConfigError as e:
        log(str(e), "err")
        return 2
    except StepError as e:
        log(str(e), "err")
        return 1
    except KeyboardInterrupt:
        log("afgebroken door gebruiker", "err")
        return 130


if __name__ == "__main__":
    sys.exit(main())

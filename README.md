# ComfyUI-pakket — vakgroep 3D

Eén GitHub-repo die vastlegt **welke** ComfyUI-versie, custom nodes, modellen, LoRA's en workflows er op een PC horen, plus een installer die dat op elke Windows-PC exact zo neerzet. Vaker draaien = bijwerken; alleen wat veranderd is wordt opnieuw gedaan.

```powershell
# PowerShell als administrator, op een kale Windows-PC:
irm https://raw.githubusercontent.com/JOUW-ORG/comfyui-pack/main/install.ps1 | iex
```

Er hoeft vooraf niets geïnstalleerd te zijn: geen Python, geen git. Daarna staat er een snelkoppeling **ComfyUI** op het bureaublad van alle gebruikers.

---

## 1. Eenmalig: repo op GitHub zetten

| Stap | Wat |
|---|---|
| 1 | Maak een (publieke) repo, bv. `vakgroep3d/comfyui-pack`, en push deze map erin |
| 2 | Vervang `JOUW-ORG/comfyui-pack` in `install.ps1` (parameter `$Repo`), `ansible/comfyui.yml` en deze README |
| 3 | Optioneel: zet `HF_TOKEN` als *Actions secret* (voor de wekelijkse linkcontrole van afgeschermde modellen) |

```bash
git init -b main && git add . && git commit -m "ComfyUI-pakket"
git remote add origin https://github.com/vakgroep3d/comfyui-pack.git && git push -u origin main
```

Publiek is prima: de repo bevat alleen *verwijzingen* naar modellen en geen tokens. Privé kan ook, maar dan werkt de `irm … | iex`-regel niet zonder token; gebruik dan Ansible of `-Source`.

---

## 2. Installeren

| Situatie | Commando |
|---|---|
| Standaard | `irm https://raw.githubusercontent.com/JOUW-ORG/comfyui-pack/main/install.ps1 \| iex` |
| Ander profiel | `& ([scriptblock]::Create((irm https://raw.githubusercontent.com/JOUW-ORG/comfyui-pack/main/install.ps1))) -Profiel volledig` |
| Vanuit lokale kopie (wijzigingen testen vóór push) | `.\install.ps1 -Profiel standaard` |
| Testbranch op één PC | `… -Branch test-comfy-0.40` |
| Andere schijf | `… -InstallDir D:\ComfyUI` |
| Alleen nodes/ComfyUI bijwerken | `… -SkipModels` |
| Ook als ComfyUI nog open staat | `… -Force` |
| Modellen van de mirror | `… -Mirror http://10.0.0.5:8080` |
| Alle 28 PC's | zie [§6 Uitrollen](#6-uitrollen-naar-de-hele-vakgroep) |

**Eerste installatie** van profiel `standaard`: ± 10 GB (≈ 3 GB PyTorch + ComfyUI-afhankelijkheden, ≈ 7,4 GB modellen). Afgebroken? Gewoon opnieuw starten: downloads gaan verder waar ze waren.

### Wat komt waar

```
C:\ComfyUI\
├─ start-comfyui.bat          ← snelkoppeling wijst hierheen (studenten)
├─ start-comfyui-beheer.bat   ← zelfde, mét ComfyUI-Manager (docenten/beheer)
├─ comfypack.bat              ← de engine: verify, freeze, add-model …
├─ ComfyUI\                   ← code, custom_nodes, models, output, user   (Gebruikers: schrijven)
├─ venv\                      ← Python-omgeving met torch                   (Gebruikers: alleen lezen)
├─ .python\  .tools\  .cache\ ← Python 3.13, uv, MinGit, pakketcache
├─ .comfypack\                ← state.json, hashes, logs\install-*.log
├─ pack\                      ← kopie van deze repo (niet in bewerken: wordt overschreven)
└─ secrets.toml               ← optioneel, tokens (zie §7)
```

Alles staat buiten het gebruikersprofiel, dus de wekelijkse wipe van het `student`-account raakt de installatie niet.

---

## 3. Samenstellen

De inhoud staat in **packs** (`packs/*.toml`); een **profiel** in `comfy-pack.toml` is een lijstje packs.

```toml
# comfy-pack.toml
[profiles]
minimaal  = ["basis"]
standaard = ["basis", "sdxl"]
volledig  = ["basis", "sdxl", "z-image", "eigen-loras"]
```

| Pack | Inhoud | Download |
|---|---|---|
| `basis` | rgthree, KJNodes, Custom-Scripts · Real-ESRGAN upscalers · TAESD live-previews | 100 MB |
| `sdxl` | SDXL 1.0 base · Lightning 4-staps LoRA · workflow *Vakgroep/SDXL Lightning 4 stappen* | 7,3 GB |
| `z-image` | Z-Image Turbo (diffusion model, Qwen3-4B encoder, VAE) — workflow via *Templates* | ± 20 GB |
| `eigen-loras` | leeg sjabloon voor jullie eigen LoRA's | — |

### Model of LoRA toevoegen — één commando

```bash
python installer/comfypack.py add-model https://huggingface.co/ByteDance/SDXL-Lightning/blob/main/sdxl_lightning_8step_lora.safetensors --pack eigen-loras --dir loras
python installer/comfypack.py add-model https://civitai.com/api/download/models/123456 --pack eigen-loras --dir loras/stijl
```

Vult bestandsnaam, grootte en sha256 automatisch in (Hugging Face en Civitai leveren de hash; anders wordt het bestand één keer gedownload om te hashen). Daarna: `validate`, commit, push.

Handmatig kan ook:

```toml
[[models]]
dir = "loras/vakgroep"            # submap onder ComfyUI/models
url = "https://…/bestand.safetensors"
file = "andere_naam.safetensors"  # optioneel
sha256 = "…"                      # aanrader; bij Hugging Face wordt anders de server-hash gebruikt
size = 123456789                  # optioneel, in bytes
```

### Eigen LoRA's hosten

| Waar | Grootte | Hoe |
|---|---|---|
| **GitHub Release van deze repo** | max. 2 GB per bestand | `gh release create loras-v1 stijl_v1.safetensors` → URL `…/releases/download/loras-v1/stijl_v1.safetensors` |
| Hugging Face (publiek of privé) | onbeperkt | privé: token in `secrets.toml` |
| Civitai | onbeperkt | API-key in `secrets.toml` |

Geen git LFS gebruiken: de repo blijft klein en snel.

### Custom node toevoegen

```toml
[[nodes]]
repo = "https://github.com/auteur/ComfyUI-iets"
ref  = "a1b2c3…"   # commit (40 tekens) of release-tag — branch kan, maar is niet reproduceerbaar
# name = "mapnaam"   requirements = false   install_script = false   pip = ["pakket==1.0"]
```

Commit opzoeken: `git ls-remote https://github.com/auteur/ComfyUI-iets HEAD`.

### Werkwijze met een referentie-PC (aanrader)

1. Op één PC: `start-comfyui-beheer.bat`, nodes installeren via de Manager en uitproberen.
2. Vastleggen (op die PC staat de engine al klaar als `comfypack.bat`):
   ```powershell
   C:\ComfyUI\comfypack.bat freeze --root C:\ComfyUI > nieuw.toml
   ```
   Zet `nieuw.toml` in `packs/` van je eigen werkkopie van de repo. Schrijft alle nodes met hun exacte commit (ook Manager/registry-installaties), plus de modellen die nog in geen pack staan (alleen de URL invullen).
3. Pack aan een profiel toevoegen, `validate`, push → alle PC's krijgen exact hetzelfde.

### Workflows en andere bestanden meegeven

```toml
[[files]]
src  = "workflows/mijn-workflow.json"                       # in deze repo
dest = "user/default/workflows/Vakgroep/Mijn workflow.json"  # relatief t.o.v. ComfyUI/
```

Workflows in `user/default/workflows/` staan in de workflow-zijbalk. Map werkt ook als `src`.

### Velden

| Waar | Veld | Betekenis |
|---|---|---|
| pack | `description`, `requires` | omschrijving; packs die automatisch mee moeten |
| pack | `pip` | extra Python-pakketten |
| `[[nodes]]` | `repo`, `ref`, `name`, `requirements`, `install_script`, `pip` | zie boven |
| `[[models]]` | `url`, `dir`, `file`, `sha256`, `size` | zie boven |
| `[[files]]` | `src`, `dest` | zie boven |
| `[install]` | `prune_unlisted_nodes` | nodes die niet in de packs staan naar `custom_nodes/.disabled` |
| `[launch]` | `listen`, `port`, `auto_launch`, `manager_ui`, `output_directory`, `args` | startscript |

---

## 4. Bijwerken

| Wil je… | Doe |
|---|---|
| Nieuwe ComfyUI | `[comfyui] ref = "v0.40.0"` → testbranch → op één PC `-Branch` → merge |
| Nieuwe torch | `[torch] packages` aanpassen (torch en torchvision samen) |
| Node bijwerken | `ref` naar nieuwere commit |
| Model eruit | regel weghalen (bestand blijft op de PC staan; verwijderen is bewust handwerk) |

Herinstallatie slaat over wat klopt: git-repo's al op de juiste commit, pakketten met ongewijzigde requirements, modellen met kloppende grootte/hash (hash wordt gecachet). Een tweede run zonder wijzigingen duurt enkele seconden (getest: 3 s).

**Bescherming tegen kapotte torch:** na de torch-installatie worden `torch` en `torchvision` met exacte build (`+cu130`) vastgezet als *constraint*. Een custom node die een andere torch eist faalt dan met een duidelijke melding, in plaats van stilletjes de GPU-versie te vervangen door een CPU-versie.

---

## 5. GPU en PyTorch

`[torch] index = "auto"` kiest per PC:

| PC | Keuze |
|---|---|
| NVIDIA RTX 20xx of nieuwer, driver ≥ 580 | `cu130` |
| NVIDIA GTX 10xx of ouder | `cu126` (torch 2.14 is de laatste versie die deze kaarten ondersteunt) |
| RTX 20–40xx met driver 560–579 | `cu126` + waarschuwing: driver bijwerken |
| RTX 50xx (Blackwell) met driver < 580 | stopt: eerst driver bijwerken |
| Geen NVIDIA | `cpu` (werkt, maar zeer traag) |

Forceren per PC: `-TorchIndex cu130`.

---

## 6. Uitrollen naar de hele vakgroep

### Ansible (WinRM)

```bash
ansible-playbook -i inventory.ini ansible/comfyui.yml
ansible-playbook -i inventory.ini ansible/comfyui.yml -e comfypack_profile=volledig -l pc-3d-01
ansible-playbook -i inventory.ini ansible/comfyui.yml -e comfypack_force=true
```

Het playbook draait 7 PC's tegelijk (async, max. 6 uur), zet optioneel tokens neer en sluit af met een samenvatting per PC uit `.comfypack\state.json`. Exitcode installer: `0` ok · `1` deels mislukt (opnieuw draaien hervat) · `2` manifestfout · `3` bootstrapfout.

### Mirror: modellen één keer van internet

Zonder mirror haalt elke PC alles zelf: 28 × 7,4 GB ≈ 207 GB alleen aan modellen voor `standaard`. Met mirror één keer.

```bash
# op de Linux-controller
python3 installer/comfypack.py mirror --dest /srv/comfy-mirror --all
python3 -m http.server 8080 -d /srv/comfy-mirror        # of nginx
# playbook: -e comfypack_mirror=http://<controller-ip>:8080
```

Een HTTP-mirror werkt direct vanuit WinRM. Een SMB-share (`\\server\share`) werkt bij handmatige installaties, maar via WinRM loop je tegen het *double hop*-probleem (geen toegang tot netwerkshares); gebruik dan `become: true` / `become_method: runas` met wachtwoord, of HTTP. Wat niet in de mirror staat, wordt automatisch van de originele bron gehaald, en elke kopie wordt tegen de sha256 gecontroleerd.

### Gedeeld `student`-account

- Snelkoppeling staat op het **openbare** bureaublad en in het startmenu.
- *Gebruikers* (SID `S-1-5-32-545`, werkt ook op Nederlandstalige Windows) krijgen schrijfrechten op `ComfyUI\` (output, input, workflows, runtime-downloads van nodes). `venv` blijft alleen-lezen, dus studenten kunnen geen pakketten kapotmaken.
- Studenten zien standaard geen Manager (`[launch] manager_ui = false`). Beheer gebruikt `start-comfyui-beheer.bat`.
- Output staat standaard in `C:\ComfyUI\ComfyUI\output` en overleeft dus de profiel-wipe. Liever per student of op de homeshare: `[launch] output_directory = 'H:\ComfyUI-output'` (omgevingsvariabelen zoals `%USERNAME%` werken).

---

## 7. Tokens (afgeschermde modellen)

Kopieer `secrets.example.toml` naar `C:\ComfyUI\secrets.toml` (per PC, of via het playbook uit een Ansible-vault) of naar de repo-map voor `add-model`/`mirror`. Staat in `.gitignore`. Omgevingsvariabelen `HF_TOKEN` / `CIVITAI_TOKEN` gaan voor. Tokens worden nooit doorgestuurd naar de CDN waarnaar Hugging Face/Civitai doorverwijzen.

---

## 8. Commando's

`install.ps1` regelt alles op Windows. De engine is los te gebruiken: op een geïnstalleerde PC als `C:\ComfyUI\comfypack.bat <commando>`, of vanuit je werkkopie met elke Python 3.11+ (alleen standaardbibliotheek, ook op Linux):

| Commando | Doet |
|---|---|
| `comfypack.py list` | profielen, packs, inhoud en downloadgrootte |
| `comfypack.py validate [--online]` | manifest controleren; `--online` test ook alle links en repo's |
| `comfypack.py add-model URL --pack P --dir D` | model/LoRA toevoegen met hash |
| `comfypack.py freeze --root C:\ComfyUI --write packs/x.toml` | referentie-PC vastleggen |
| `comfypack.py verify --root C:\ComfyUI` | installatie controleren (nodes, modellen, hashes) |
| `comfypack.py mirror --dest PAD --all` | mirror vullen |
| `comfypack.py install --root PAD --profile P` | wat `install.ps1` aanroept |

GitHub Actions controleert bij elke push het manifest en de PowerShell-syntax, test elke maandag of alle downloadlinks nog werken, en doet bij wijzigingen aan de installer een volledige rooktest-installatie op een schone Windows-runner (inclusief ComfyUI opstarten en controleren dat alle custom nodes laden).

---

## 9. Problemen oplossen

| Melding | Oorzaak / oplossing |
|---|---|
| `ComfyUI draait nog` | ComfyUI afsluiten of `-Force` |
| `HTTP 401/403 … token nodig` | model is afgeschermd: token in `secrets.toml` en licentie accepteren op de modelpagina |
| `sha256 klopt niet` | download corrupt of bestand op de bron gewijzigd; opnieuw draaien of hash in het pack bijwerken |
| `pakketinstallatie mislukt` bij een node | meestal een node die een andere torch/numpy eist: andere commit kiezen, of `requirements = false` + zelf `pip = [...]` |
| `NVIDIA-driver … te oud` | driver bijwerken (≥ 580) |
| SSL-fouten op het schoolnetwerk | git en uv gebruiken de Windows-certificaatstore; controleer of het proxy-certificaat via GPO is uitgerold |
| Iets anders | log: `C:\ComfyUI\.comfypack\logs\install-*.log` |

---

## 10. Licenties

Elk model heeft een eigen licentie; controleer die vóór je iets toevoegt.

| Onderdeel | Licentie |
|---|---|
| ComfyUI | GPL-3.0 |
| SDXL 1.0 base, SDXL-Lightning | CreativeML OpenRAIL++-M |
| Z-Image Turbo | Apache 2.0 |
| Real-ESRGAN | BSD-3-Clause |
| TAESD | MIT |

Let op bij 3D-modellen: de licentie van **Hunyuan3D 2.x** (Tencent) geldt uitdrukkelijk *niet* in de EU, daarom staat dat model hier niet in.

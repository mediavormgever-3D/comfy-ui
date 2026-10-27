# Handleiding ComfyUI vakgroep 3D

Versie oktober 2026 · repo [mediavormgever-3D/comfy-ui](https://github.com/mediavormgever-3D/comfy-ui)

## Wegwijzer

Zoek hieronder wat je wilt doen en lees alleen dat hoofdstuk. De rest mag je overslaan.

| Ik wil… | Hoofdstuk | Wie | Duur |
| --- | --- | --- | --- |
| ComfyUI openen en een beeld maken | Studenten: ComfyUI gebruiken | iedereen | 5 min |
| ComfyUI op een PC zetten | ComfyUI op één PC installeren | docent met adminrechten | 30–90 min, vooral wachten |
| Een PC bijwerken naar de nieuwste versie | Bijwerken | docent met adminrechten | 2–10 min |
| Een LoRA of model toevoegen | Een LoRA of model toevoegen | docent met GitHub-toegang | 10 min |
| Een custom node toevoegen | Een custom node toevoegen | beheerder | 20 min |
| Alle PC's in één keer installeren of bijwerken | Alle PC's tegelijk | beheerder met Ansible | 1 commando |
| Er gaat iets mis | Als er iets misgaat | iedereen | — |
| Het door Claude laten doen | Met Claude (Cowork-plugin) | iedereen met de plugin | — |

**Drie woorden die steeds terugkomen:**

- **Repo** — de map op GitHub waarin staat wat er op elke PC hoort. Wat daar verandert, komt bij de volgende installatie op de PC's.
- **Pack** — een pakketje dat bij elkaar hoort, bijvoorbeeld *sdxl*: het model, de LoRA en de workflow.
- **Profiel** — een lijstje packs. *standaard* is wat de meeste PC's krijgen; *volledig* bevat alles.

## Studenten: ComfyUI gebruiken

Dubbelklik op het icoon **ComfyUI** op het bureaublad, wacht tot de browser opent en kies de workflow *SDXL Lightning 4 stappen*. Je eerste beeld staat er binnen een minuut.

**Starten**

1. Dubbelklik op **ComfyUI** op het bureaublad (of zoek "ComfyUI" in het startmenu).
2. Er opent een **zwart venster** met tekst. Dat is ComfyUI zelf: **laat het open**, maar je hoeft er niets in te doen.
3. Na 10 tot 30 seconden opent de browser vanzelf met ComfyUI.
   - Opent er geen browser? Typ dan zelf in de adresbalk: `http://127.0.0.1:8188`

**Je eerste beeld**

1. Klik in de balk links op **Workflows**.
2. Open de map **Vakgroep** en klik op **SDXL Lightning 4 stappen**.
3. Typ in het **groene blok** wat je wilt zien. Engels werkt het best, bijvoorbeeld: `a red armchair in a white studio, product photo`
4. Druk op **Ctrl + Enter**. Na enkele seconden verschijnt je beeld rechts in beeld.
5. Nog een versie? Druk nog een keer op **Ctrl + Enter**: je krijgt telkens een nieuwe variant.

Laat de instellingen in het blok *KSampler* staan (4 stappen, CFG 1.0). Deze workflow is daarop afgesteld; met andere waarden wordt het beeld slechter.

| Formaat | Breedte × hoogte |
| --- | --- |
| Vierkant | 1024 × 1024 |
| Liggend | 1216 × 832 |
| Staand | 832 × 1216 |

Het formaat verander je in het blok *Empty Latent Image*.

**Waar staan je beelden?**

In `C:\ComfyUI\ComfyUI\output\vakgroep`. Iedereen op deze PC kan die map zien en leegmaken. **Kopieer wat je wilt bewaren naar je eigen opslag** (OneDrive of je H-schijf).

**Stoppen**

Sluit het **zwarte venster**. Alleen de browser sluiten is niet genoeg: dan blijft ComfyUI de videokaart bezet houden.

**Gaat er iets mis?** Een rood omrand blok of een foutmelding: maak een foto van het scherm en meld het bij je docent.

## ComfyUI op één PC installeren

Open PowerShell als administrator, plak één regel en wacht tot er een groene regel *klaar* staat. Je hoeft vooraf niets te installeren.

**Controleer eerst**

- [ ] Je hebt adminrechten op deze PC.
- [ ] Er is genoeg vrije ruimte op C: — **20 GB** voor profiel *standaard*, **45 GB** voor *volledig*.
- [ ] De PC heeft een NVIDIA-videokaart met driver **580 of nieuwer**. Typ `nvidia-smi` in PowerShell: rechtsboven staat *Driver Version*.
- [ ] ComfyUI is niet geopend.

**Installeren**

1. Klik op **Start**, typ `PowerShell`, klik met de **rechtermuisknop** op *Windows PowerShell* en kies **Als administrator uitvoeren**. Klik **Ja**.
2. Kopieer deze regel, klik met de **rechtermuisknop** in het blauwe venster (dat plakt) en druk op **Enter**:

```powershell
irm https://raw.githubusercontent.com/mediavormgever-3D/comfy-ui/main/install.ps1 | iex
```

3. Laat het venster openstaan. De eerste keer duurt het 30 tot 90 minuten; daarna gaat het veel sneller.
4. Klaar als de laatste regels er zo uitzien:

```text
16:42:07 [ok] ComfyUI staat klaar in 34.2 min: C:\ComfyUI\start-comfyui.bat
16:42:09 [ok] klaar - start met de snelkoppeling of C:\ComfyUI\start-comfyui.bat
```

5. Sluit het venster en test: dubbelklik op **ComfyUI** op het bureaublad (zie *Studenten: ComfyUI gebruiken*).

**Wat je onderweg ziet**

| Kleur | Betekent | Wat jij doet |
| --- | --- | --- |
| Blauw `==>` | een nieuwe stap begint | niets |
| Grijs | voortgang, bijvoorbeeld een download met percentage | niets |
| Groen `[ok]` | onderdeel gelukt | niets |
| Geel `[!]` | waarschuwing, de installatie gaat door | lezen, meestal niets |
| Rood `[FOUT]` | iets is mislukt | zie *Als er iets misgaat* |

De langste stappen zijn **PyTorch** (2–3 GB) en **Modellen**. Downloads tonen elke 15 seconden hun voortgang. Lijkt het stil te staan? Wacht minstens 5 minuten.

**Venster per ongeluk gesloten, stroom weg of laptop dicht?** Geen probleem: plak dezelfde regel opnieuw. Hij gaat verder waar hij was gebleven, ook halverwege een download.

**Een ander profiel**

Zet de profielnaam (`minimaal`, `standaard` of `volledig`) vóór de installatieregel:

```powershell
$env:COMFYPACK_PROFILE='volledig'; irm https://raw.githubusercontent.com/mediavormgever-3D/comfy-ui/main/install.ps1 | iex
```

Gebruik dezelfde regel ook bij elke latere update van die PC.

**Wat er na afloop op de PC staat**

- Snelkoppeling **ComfyUI** op het bureaublad en in het startmenu, voor alle gebruikers.
- Alles in `C:\ComfyUI`, buiten de gebruikersprofielen: de wekelijkse wipe van het studentaccount raakt het niet.
- Een logboek van elke installatie in `C:\ComfyUI\.comfypack\logs`.

## Bijwerken

Bijwerken is dezelfde installatieregel nog een keer draaien. Alleen wat veranderd is wordt opnieuw gedaan; zonder wijzigingen duurt het een paar seconden.

**Een PC bijwerken**

1. Sluit ComfyUI (het zwarte venster).
2. Open PowerShell **als administrator** en plak dezelfde regel als bij installeren:

```powershell
irm https://raw.githubusercontent.com/mediavormgever-3D/comfy-ui/main/install.ps1 | iex
```

3. Wacht op de groene regel *klaar*.

Had deze PC een ander profiel, bijvoorbeeld *volledig*? Gebruik dan weer de regel met `$env:COMFYPACK_PROFILE='volledig';` ervoor. Zonder die toevoeging krijgt de PC *standaard*.

**Handige toevoegingen**

Voor opties gebruik je deze vorm en zet je de toevoegingen aan het eind:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/mediavormgever-3D/comfy-ui/main/install.ps1))) -Profiel volledig -Force
```

| Toevoeging | Wanneer |
| --- | --- |
| `-Force` | ComfyUI staat nog open en je wilt het laten afsluiten |
| `-SkipModels` | alleen ComfyUI en nodes bijwerken, geen modellen (sneller) |
| `-Branch <naam>` | een testversie proberen op één PC (zie hieronder) |
| `-InstallDir D:\ComfyUI` | op een andere schijf installeren |

**Klopt alles op deze PC?**

Open PowerShell (geen administrator nodig) en typ:

```powershell
C:\ComfyUI\comfypack.bat verify --root C:\ComfyUI
```

Groen *alles in orde* = de PC is compleet. Rood = er ontbreekt iets; draai de installatieregel opnieuw.

**Een nieuwe ComfyUI-versie uitrollen** (beheerder)

Zonder git, gewoon via de website:

1. Zoek de nieuwste versie op [github.com/Comfy-Org/ComfyUI/releases](https://github.com/Comfy-Org/ComfyUI/releases): het label bij *Latest*, bijvoorbeeld `v0.43.0`.
2. Open in de repo het bestand `comfy-pack.toml` en klik op het **potloodje** (Edit).
3. Verander onder `[comfyui]` de regel `ref = "v0.39.0"` in de nieuwe versie.
4. Klik **Commit changes…**, kies **Create a new branch for this commit and start a pull request**, noem hem `test` en klik **Propose changes**, dan **Create pull request**.
5. Installeer op **één** PC de testversie:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/mediavormgever-3D/comfy-ui/refs/heads/test/install.ps1))) -Branch test
```

6. Werkt alles, ook de custom nodes? Klik in de pull request op **Merge pull request**. Pas dan krijgen de andere PC's de nieuwe versie bij hun volgende update.

Gaat het mis op de test-PC? Draai de gewone installatieregel: de PC gaat terug naar de versie van `main`.

PyTorch bijwerken (`[torch] packages`) doet alleen de beheerder: torch en torchvision moeten bij elkaar passen.

## Een LoRA of model toevoegen

Je plakt een downloadlink in het bestand `packs/eigen-loras.toml` op de GitHub-website, als pull request. Na de merge haalt elke PC met profiel *standaard* of *volledig* het bestand op bij de volgende update. Je hebt geen software nodig, alleen toegang tot de repo.

**Stap 1 — Zorg voor een downloadlink**

| Waar staat het bestand? | Zo kopieer je de link |
| --- | --- |
| Hugging Face | Open de modelpagina → *Files and versions* → klik op het bestand → kopieer de adresbalk. Een link met `/blob/` mag: die wordt automatisch omgezet. |
| Civitai | Rechtsklik op de knop **Download** → *Link kopiëren*. Begint met `https://civitai.com/api/download/models/`; de gewone pagina-link werkt **niet**. Zet in stap 2 ook de regel `file = "naam.safetensors"` erbij. Civitai vraagt een API-sleutel; die zet de beheerder één keer klaar (zie *Alle PC's tegelijk*). |
| Op je eigen PC (zelf getrainde LoRA) | Eerst uploaden naar GitHub, zie hieronder. |

**Eigen LoRA uploaden** (max. 2 GB per bestand)

1. Ga in de repo naar **Releases** (rechts op de hoofdpagina) → **Draft a new release**.
2. Klik **Choose a tag**, typ `loras-v1` en klik **Create new tag**. Volgende keer: `loras-v2`, enzovoort.
3. Sleep je `.safetensors`-bestand naar het vak *Attach binaries*. Wacht tot de upload klaar is.
4. Klik **Publish release**.
5. Klik onder *Assets* met de **rechtermuisknop** op je bestand → *Link kopiëren*.

Gebruik in bestandsnamen geen spaties: `vakgroep_stijl_v1.safetensors` in plaats van `Vakgroep stijl v1.safetensors`.

**Stap 2 — Link toevoegen**

1. Open in de repo de map `packs` en klik op `eigen-loras.toml`.
2. Klik op het **potloodje** (Edit).
3. Ga helemaal naar onderen, maak een lege regel en plak dit blok:

```toml
[[models]]
dir = "loras/vakgroep"
url = "https://plak-hier-je-link"
```

4. Vervang `https://plak-hier-je-link` door je link. Laat de aanhalingstekens staan.
5. Is het geen LoRA? Verander dan `loras/vakgroep` in de juiste map:

| Soort bestand | `dir` |
| --- | --- |
| LoRA | `loras/vakgroep` |
| Checkpoint (een compleet model, vaak 2–7 GB) | `checkpoints` |
| VAE | `vae` |
| Upscaler | `upscale_models` |
| ControlNet | `controlnet` |

6. Klik **Commit changes…**, kies **Create a new branch for this commit and start a pull request**, klik **Propose changes** en daarna **Create pull request**.

**Stap 3 — Controleren en mergen**

Onder in de pull request verschijnt na een paar minuten bij *Manifest controleren* een groen vinkje of een rood kruis.

- **Groen**: klik **Merge pull request**. De PC's krijgen het bestand bij hun volgende update (zie *Bijwerken*).
- **Rood**: klik op *Details* en zoek de regel met `[FOUT]`. Die zegt wat er mis is, bijvoorbeeld een Civitai-pagina-link in plaats van een downloadlink. Verbeter het bestand in dezelfde branch (tabblad *Files changed* → **…** → *Edit file*).

**De LoRA gebruiken in ComfyUI**

Dubbelklik op een lege plek in het werkveld, typ `lora` en kies **Load LoRA**. Je bestand staat in de lijst als `vakgroep/…`. Zet de triggerwoorden van de LoRA in je prompt.

## Een custom node toevoegen

Probeer een node uit op één referentie-PC, leg hem vast met één commando en zet het resultaat via een pull request in `packs/basis.toml`. Zo krijgt elke PC exact dezelfde versie die jij hebt getest.

**Stap 1 — Uitproberen op de referentie-PC**

1. Kies één PC als referentie, bijvoorbeeld je eigen docenten-PC. Nooit een studenten-PC.
2. Open in Verkenner `C:\ComfyUI`, klik met de **rechtermuisknop** op `start-comfyui-beheer.bat` en kies **Als administrator uitvoeren**. Alleen zo mag de Manager pakketten installeren.
3. Klik in ComfyUI op de knop **Manager**.
4. Zoek de node, klik **Install** en start ComfyUI opnieuw als daarom gevraagd wordt.
5. Test of hij doet wat je wilt. Niet goed? Verwijder hem in de Manager en probeer een andere.

**Stap 2 — Vastleggen**

Open PowerShell (geen administrator nodig) en plak:

```powershell
C:\ComfyUI\comfypack.bat freeze --root C:\ComfyUI --write "$([Environment]::GetFolderPath('Desktop'))\nieuwe-nodes.toml"
```

Op je bureaublad staat nu `nieuwe-nodes.toml`. Open het met Kladblok. Je ziet een blok per node, zoals:

```toml
[[nodes]]
repo = "https://github.com/kijai/ComfyUI-KJNodes"
ref = "37a6c45a07bb06cc392431ddbbc741e691c467f4"
```

De lange code achter `ref` is de exacte versie. Daarom krijgt elke PC precies wat jij hebt getest.

**Stap 3 — Toevoegen aan het pakket**

1. Open op GitHub `packs/basis.toml` en klik op het **potloodje**.
2. Kopieer uit `nieuwe-nodes.toml` **alleen de blokken van je nieuwe nodes**. Nodes die al in een pack staan, laat je weg.
3. Plak ze onder de laatste `[[nodes]]`.
4. Klik **Commit changes…** → **Create a new branch…** → **Propose changes** → **Create pull request**.

**Stap 4 — Laten testen**

In de pull request starten twee controles:

- *Manifest controleren* — na een paar minuten.
- *Rooktest Windows-installatie* — ongeveer een kwartier. Die installeert alles op een schone Windows-PC en controleert of je nieuwe node laadt.

Beide groen? Dan merget de beheerder, en de PC's krijgen de node bij hun volgende update (zie *Bijwerken*). Rooktest rood? Open *Details* en de stap *ComfyUI start en laadt alle nodes*: daar staat welke node niet laadt.

Onderaan `nieuwe-nodes.toml` staan ook modellen die met de hand op de referentie-PC zijn gezet. Die voeg je toe zoals in *Een LoRA of model toevoegen*.

## Alle PC's tegelijk

Vanaf de Linux-controller installeer of update je alle PC's met één Ansible-commando. Vul eerst de mirror: dan komen de modellen één keer van internet en daarna via het schoolnetwerk.

Zonder mirror haalt elke PC alles zelf: voor profiel *standaard* is dat 28 × ongeveer 7,4 GB aan modellen, ruim 200 GB over de internetlijn.

**Eenmalig voorbereiden**

1. Zet een kopie van de repo op de controller en installeer de Windows-modules voor Ansible:

```bash
git clone https://github.com/mediavormgever-3D/comfy-ui.git ~/comfy-ui
ansible-galaxy collection install ansible.windows
```

De engine heeft Python 3.9 of nieuwer nodig (`python3 --version`). Bij 3.9 of 3.10 eerst: `python3 -m pip install --user tomli`.

2. Maak in de map `~/comfy-ui` een `inventory.ini` met de groep `vakgroep3d`. De PC-namen hieronder zijn een voorbeeld:

```ini
[vakgroep3d]
pc-3d-[01:28]

[vakgroep3d:vars]
ansible_connection=winrm
ansible_port=5985
ansible_winrm_transport=ntlm
ansible_user=TALNET\<account>
```

3. Alleen nodig voor Civitai of afgeschermde Hugging Face-modellen — tokens in een versleutelde kluis naast `inventory.ini`:

```bash
mkdir -p group_vars/vakgroep3d
ansible-vault create group_vars/vakgroep3d/vault.yml
```

Zet daarin (alleen wat je hebt):

```yaml
vault_hf_token: "hf_..."
vault_civitai_token: "..."
```

`inventory.ini` en `group_vars/` staan in `.gitignore`: ze komen nooit in de repo.

**Elke keer: mirror bijwerken**

```bash
cd ~/comfy-ui && git pull
python3 installer/comfypack.py mirror --dest /srv/comfy-mirror --all
python3 -m http.server 8080 -d /srv/comfy-mirror
```

De tweede regel haalt alleen wat nog ontbreekt. De derde maakt de mirror bereikbaar op poort 8080: **laat dat venster open** zolang je uitrolt (staat er een firewall aan? `sudo ufw allow 8080`).

**Uitrollen**

In een tweede terminal, in `~/comfy-ui`:

```bash
ansible-playbook -i inventory.ini ansible/comfyui.yml -k -e comfypack_mirror=http://<ip-controller>:8080
```

`-k` vraagt het wachtwoord van je account. Gebruik je de kluis, zet er dan ook `--ask-vault-pass` achter.

| Wil je… | Zet erachter |
| --- | --- |
| Eén PC (eerst testen) | `-l pc-3d-01` |
| Ander profiel | `-e comfypack_profile=volledig` |
| Ook als ComfyUI open staat | `-e comfypack_force=true` |
| Alleen ComfyUI en nodes, geen modellen | `-e comfypack_skip_models=true` |
| Een testbranch | `-e comfypack_branch=<naam>` |

Ansible werkt 7 PC's tegelijk af, dus 28 PC's in 4 rondes. De PC's moeten aanstaan; plan het buiten lestijd. Aan het eind staat per PC één regel, bijvoorbeeld:

```text
pc-3d-01: OK | profiel standaard | ComfyUI v0.39.0 | pack 1a2b3c4d |
```

Staat er *FOUTEN* achter een PC? Draai het commando nog eens voor alleen die PC (`-l`). Lukt het dan nog niet: log in op die PC en lees het laatste logboek in `C:\ComfyUI\.comfypack\logs`.

## Als er iets misgaat

Bijna elk probleem is opgelost door de installatieregel nog een keer te draaien: hij herstelt wat ontbreekt of kapot is. Helpt dat niet, zoek dan de melding hieronder op.

**Tijdens het gebruik**

| Wat je ziet | Oorzaak | Oplossing |
| --- | --- | --- |
| Browser: *Deze site is niet bereikbaar* | ComfyUI start nog op, of het zwarte venster is dicht | 30 seconden wachten en **F5**. Zwart venster weg? Opnieuw dubbelklikken op ComfyUI. |
| Zwart venster blijft staan met rode tekst en *Druk op een toets* | installatie op deze PC is onvolledig | foto maken, docent draait *Bijwerken* op deze PC |
| Rood omrand blok, melding *Value not in list* | het model hoort niet bij het profiel van deze PC | docent installeert het juiste profiel, of kies een ander model in dat blok |
| *Out of memory* of *CUDA out of memory* | videokaart vol | Blender en andere 3D-programma's sluiten, kleiner formaat kiezen |
| Eén beeld duurt minuten | ComfyUI gebruikt de processor in plaats van de videokaart (in het zwarte venster staat *Device: cpu*) | docent controleert de NVIDIA-driver en draait *Bijwerken* |

**Tijdens het installeren**

| Melding (rood of geel) | Oplossing |
| --- | --- |
| `ComfyUI draait nog` | ComfyUI sluiten, of `-Force` erachter zetten |
| `er draait al een installatie op deze map` | er loopt al een installatie, bijvoorbeeld via Ansible: wachten |
| `irm` geeft *404* of *Kan de externe server niet vinden* | link verkeerd overgetypt, repo staat op privé, of geen internet |
| `Toegang geweigerd` / *Access denied* | PowerShell is niet **als administrator** gestart |
| `profiel '…' bestaat niet` | tikfout in de profielnaam; de melding noemt de juiste namen |
| `weinig vrije ruimte` | ruimte maken op C: of installeren met `-InstallDir D:\ComfyUI` |
| `NVIDIA-driver … te oud` of `vereist NVIDIA-driver >= 580` | NVIDIA-driver bijwerken, daarna opnieuw installeren |
| `HTTP 401` / `HTTP 403 … token nodig` | model is afgeschermd: beheerder zet de token klaar (zie *Alle PC's tegelijk*) |
| `de link gaf een webpagina in plaats van een bestand` | in het pack staat een pagina-link: vervang hem door de downloadlink |
| `sha256 klopt niet` | download beschadigd: opnieuw draaien. Blijft het? Het bestand is op de bron veranderd; de beheerder werkt de hash bij. |
| `pakketinstallatie mislukt` bij een node | deze node past niet bij de rest (vaak een andere torch-versie): haal zijn blok uit het pack of kies een andere versie |
| *certificate* of *SSL*-fout | het schoolnetwerk onderschept versleuteld verkeer: ICT moet het proxycertificaat op de PC zetten |

**Laatste redmiddel: schoon opnieuw**

Open PowerShell als administrator. Dit verwijdert alles behalve de modellen, zodat je niet opnieuw gigabytes hoeft te downloaden:

```powershell
powershell -ExecutionPolicy Bypass -File C:\ComfyUI\pack\uninstall.ps1 -KeepModels -Force
```

Daarna de gewone installatieregel.

**Hulp vragen**

Stuur het nieuwste logboek mee uit `C:\ComfyUI\.comfypack\logs`. Daarin staat precies wat er gebeurde.

## Met Claude (Cowork-plugin)

Met de plugin **comfyui-vakgroep** in Claude Cowork kun je dit allemaal in gewone taal vragen. Claude maakt dan zelf de pull request, met alle controles. Voorbeelden:

- "Voeg deze LoRA toe aan het pakket: https://civitai.com/models/…"
- "Werkt deze workflow op de schoolcomputers?" (sleep de .json of een ComfyUI-PNG in het gesprek)
- "Is er een nieuwe ComfyUI-versie?"
- "Geef me het commando om PC 12 met profiel volledig te installeren."
- "De installatie op PC 7 faalt, hier is het log."

Claude merget nooit zelf: jij of de beheerder klikt op **Merge pull request** als de controles groen zijn.

## Spiekbriefje

Alle commando's op één plek. Kopieer de regel onder het commentaar (`#`).

**Op een Windows-PC**

```powershell
# Installeren of bijwerken, profiel standaard (PowerShell als administrator)
irm https://raw.githubusercontent.com/mediavormgever-3D/comfy-ui/main/install.ps1 | iex

# Installeren of bijwerken met een ander profiel (minimaal / standaard / volledig)
$env:COMFYPACK_PROFILE='volledig'; irm https://raw.githubusercontent.com/mediavormgever-3D/comfy-ui/main/install.ps1 | iex

# Testversie op één PC
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/mediavormgever-3D/comfy-ui/refs/heads/test/install.ps1))) -Branch test

# Controleren of de PC compleet is (geen administrator nodig)
C:\ComfyUI\comfypack.bat verify --root C:\ComfyUI

# Custom nodes van de referentie-PC vastleggen
C:\ComfyUI\comfypack.bat freeze --root C:\ComfyUI --write "$([Environment]::GetFolderPath('Desktop'))\nieuwe-nodes.toml"

# Alles verwijderen behalve de modellen (PowerShell als administrator)
powershell -ExecutionPolicy Bypass -File C:\ComfyUI\pack\uninstall.ps1 -KeepModels -Force
```

**Op de Linux-controller** (in `~/comfy-ui`)

```bash
# Mirror bijwerken en beschikbaar maken (venster open laten)
git pull
python3 installer/comfypack.py mirror --dest /srv/comfy-mirror --all
python3 -m http.server 8080 -d /srv/comfy-mirror

# Alle PC's installeren of bijwerken
ansible-playbook -i inventory.ini ansible/comfyui.yml -k -e comfypack_mirror=http://<ip-controller>:8080

# Overzicht van profielen, packs en downloadgrootte
python3 installer/comfypack.py list
```

**Belangrijke plekken op een PC**

| Wat | Waar |
| --- | --- |
| ComfyUI starten | `C:\ComfyUI\start-comfyui.bat` (de snelkoppeling) |
| Starten met Manager | `C:\ComfyUI\start-comfyui-beheer.bat` (als administrator) |
| Gemaakte beelden | `C:\ComfyUI\ComfyUI\output` |
| Modellen en LoRA's | `C:\ComfyUI\ComfyUI\models` |
| Workflows | `C:\ComfyUI\ComfyUI\user\default\workflows` |
| Logboeken van installaties | `C:\ComfyUI\.comfypack\logs` |
| Tokens (alleen als nodig) | `C:\ComfyUI\secrets.toml` |

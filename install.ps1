<#
.SYNOPSIS
    Installeert of werkt ComfyUI bij volgens dit pakket. Veilig om vaker te draaien.

.DESCRIPTION
    Regelt alles zelf, zonder vooraf geinstalleerde software:
      * uv (Python-beheer) en, als git ontbreekt, MinGit - beide gepind + sha256-gecontroleerd
      * deze pack-repo ophalen/bijwerken naar <InstallDir>\pack
      * ComfyUI, Python-venv, PyTorch (GPU-detectie), custom nodes, modellen, workflows
      * startscripts, snelkoppeling op het (openbare) bureaublad, schrijfrechten voor studenten

    Een regel, PowerShell als administrator:
        irm https://raw.githubusercontent.com/mediavormgever-3D/comfy-ui/main/install.ps1 | iex

    Met opties:
        & ([scriptblock]::Create((irm https://raw.githubusercontent.com/mediavormgever-3D/comfy-ui/main/install.ps1))) -Profiel volledig

    Vanuit een lokale kopie (test je wijzigingen voor je pusht):
        .\install.ps1 -Profiel standaard

.PARAMETER Profiel
    Profiel uit comfy-pack.toml (minimaal / standaard / volledig / ...).
.PARAMETER InstallDir
    Installatiemap. Standaard C:\ComfyUI. Kies een snelle schijf met ruimte (SSD).
.PARAMETER Repo
    Git-URL van de pack-repo. Pas de standaardwaarde hieronder een keer aan na het forken.
.PARAMETER Branch
    Branch van de pack-repo (handig om een nieuwe versie eerst op een PC te testen).
.PARAMETER Source
    Lokale map met de pack-repo (USB, share). Er wordt dan niets van GitHub gehaald.
.PARAMETER Mirror
    Map/share of http-URL met modellen; overschrijft [install] mirror.
.PARAMETER TorchIndex
    auto | cu130 | cu132 | cu126 | cpu - overschrijft [torch] index.
.PARAMETER SkipModels
    Alles behalve modellen (snelle update van nodes/ComfyUI).
.PARAMETER Force
    Draaiende ComfyUI-processen van deze installatie eerst afsluiten.
#>
[CmdletBinding()]
param(
    [string]$Profiel    = $(if ($env:COMFYPACK_PROFILE) { $env:COMFYPACK_PROFILE } else { 'standaard' }),
    [string]$InstallDir = $(if ($env:COMFYPACK_ROOT)    { $env:COMFYPACK_ROOT }    else { 'C:\ComfyUI' }),
    [string]$Repo       = $(if ($env:COMFYPACK_REPO)    { $env:COMFYPACK_REPO }    else { 'https://github.com/mediavormgever-3D/comfy-ui.git' }),
    [string]$Branch     = $(if ($env:COMFYPACK_BRANCH)  { $env:COMFYPACK_BRANCH }  else { 'main' }),
    [string]$Source,
    [string]$Mirror,
    [string]$TorchIndex,
    [switch]$SkipModels,
    [switch]$NoShortcut,
    [switch]$NoAcl,
    [switch]$Force
)

# Gepinde hulpprogramma's (bijwerken: versie + sha256 aanpassen)
$UvVersion  = '0.13.5'
$UvUrl      = "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip"
$UvSha256   = 'a38b8d1902b7cfbc76b423ba1bb456f623f42064cdc72628b6075b89afd1019a'
$GitUrl     = 'https://github.com/git-for-windows/git/releases/download/v2.56.0.windows.3/MinGit-2.56.0.3-64-bit.zip'
$GitSha256  = '2e5619966e588fde5f8122c5557cad50c0fbafcaed736689f40ec1dfb1d78ea7'

function Invoke-ComfyPack {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'      # Invoke-WebRequest is anders 10x trager in PS 5.1
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $script:LogFile = $null
    function Say([string]$Msg, [string]$Kind = '') {
        $mark = @{ step = '==> '; ok = '[ok] '; warn = '[!] '; err = '[FOUT] '; '' = '    ' }[$Kind]
        $color = @{ step = 'Cyan'; ok = 'Green'; warn = 'Yellow'; err = 'Red'; '' = 'Gray' }[$Kind]
        $line = '{0:HH:mm:ss} {1}{2}' -f (Get-Date), $mark, $Msg
        Write-Host $line -ForegroundColor $color
        if ($script:LogFile) { Add-Content -LiteralPath $script:LogFile -Value $line -Encoding UTF8 }
    }
    function Invoke-Native([string]$Exe, [string[]]$ArgList) {
        $eap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'   # stderr van git/uv is geen fout
        try { & $Exe @ArgList } finally { $ErrorActionPreference = $eap }
        if ($LASTEXITCODE -ne 0) { throw "$(Split-Path $Exe -Leaf) $($ArgList[0]) faalde (exit $LASTEXITCODE)" }
    }
    function Expand-Zip([string]$Zip, [string]$Dest) {
        New-Item -ItemType Directory -Force -Path $Dest | Out-Null
        $tar = Join-Path $env:SystemRoot 'System32\tar.exe'          # veel sneller dan Expand-Archive
        if (Test-Path -LiteralPath $tar) { Invoke-Native $tar @('-xf', $Zip, '-C', $Dest) }
        else { Expand-Archive -LiteralPath $Zip -DestinationPath $Dest -Force }
    }
    function Get-Pinned([string]$Url, [string]$Sha256, [string]$Dest) {
        Say "downloaden: $Url"
        Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing
        $h = (Get-FileHash -LiteralPath $Dest -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($h -ne $Sha256) { Remove-Item -LiteralPath $Dest -Force; throw "sha256 van $Url klopt niet ($h)" }
    }

    # ---------------------------------------------------------------- controles
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'Alleen 64-bit Windows wordt ondersteund.' }
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    $InstallDir = [IO.Path]::GetFullPath($InstallDir)
    $tools = Join-Path $InstallDir '.tools'
    $meta  = Join-Path $InstallDir '.comfypack'
    New-Item -ItemType Directory -Force -Path $tools, (Join-Path $meta 'logs') | Out-Null
    $script:LogFile = Join-Path $meta ('logs\install-{0:yyyyMMdd-HHmmss}.log' -f (Get-Date))

    Say "ComfyUI-pakket -> $InstallDir (profiel '$Profiel')" 'step'
    if (-not $isAdmin) { Say 'geen administrator: geen snelkoppeling voor alle gebruikers en geen schrijfrechten voor studenten' 'warn' }

    $drive = Get-PSDrive -Name $InstallDir.Substring(0, 1) -ErrorAction SilentlyContinue
    if ($drive -and $drive.Free -lt 40GB) { Say ("weinig vrije ruimte op {0}: {1:N0} GB" -f $drive.Name, ($drive.Free / 1GB)) 'warn' }

    # Draait ComfyUI nog? Dan zitten bestanden op slot.
    $running = @(Get-CimInstance Win32_Process -Filter "Name LIKE 'python%.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($InstallDir, [StringComparison]::OrdinalIgnoreCase) })
    if ($running.Count -gt 0) {
        if (-not $Force) { throw "ComfyUI draait nog ($($running.Count) proces(sen)). Sluit het af of gebruik -Force." }
        Say 'draaiende ComfyUI wordt afgesloten (-Force)' 'warn'
        $running | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 2
    }

    # ---------------------------------------------------------------- uv
    $uvDir = Join-Path $tools 'uv'
    $uv = Join-Path $uvDir 'uv.exe'
    $haveUv = ''
    if (Test-Path -LiteralPath $uv) { $haveUv = ((& $uv --version) -split ' ')[1] }
    if ($haveUv -ne $UvVersion) {
        Say "uv $UvVersion installeren" 'step'
        $zip = Join-Path $tools 'uv.zip'
        Get-Pinned $UvUrl $UvSha256 $zip
        if (Test-Path -LiteralPath $uvDir) { Remove-Item -LiteralPath $uvDir -Recurse -Force }
        Expand-Zip $zip $uvDir
        Remove-Item -LiteralPath $zip -Force
    }

    # ---------------------------------------------------------------- git
    $git = (Get-Command git.exe -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    if (-not $git) {
        $gitDir = Join-Path $tools 'git'
        $git = Join-Path $gitDir 'cmd\git.exe'
        if (-not (Test-Path -LiteralPath $git)) {
            Say 'git niet gevonden: MinGit installeren (alleen voor ComfyUI)' 'step'
            $zip = Join-Path $tools 'mingit.zip'
            Get-Pinned $GitUrl $GitSha256 $zip
            Expand-Zip $zip $gitDir
            Remove-Item -LiteralPath $zip -Force
        }
    }
    $env:Path = (Split-Path $git) + ';' + $env:Path
    # Windows-certificaatstore (werkt met TLS-inspectie op het schoolnetwerk) en lange paden
    $env:GIT_CONFIG_COUNT = '2'
    $env:GIT_CONFIG_KEY_0 = 'http.sslBackend'; $env:GIT_CONFIG_VALUE_0 = 'schannel'
    $env:GIT_CONFIG_KEY_1 = 'core.longpaths';  $env:GIT_CONFIG_VALUE_1 = 'true'

    # ---------------------------------------------------------------- pack-repo
    $repoGiven = $script:RepoGiven -or $env:COMFYPACK_REPO
    if ($Source) {
        $packDir = (Resolve-Path -LiteralPath $Source).Path
        Say "pack-bron: $packDir (lokaal)" 'step'
    } elseif (-not $repoGiven -and $PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'comfy-pack.toml'))) {
        $packDir = $PSScriptRoot
        Say "pack-bron: $packDir (deze map)" 'step'
    } else {
        if ($Repo -match 'mediavormgever-3D') { throw 'Zet eerst je eigen repo-URL in install.ps1 ($Repo) of geef -Repo op.' }
        $packDir = Join-Path $InstallDir 'pack'
        Say "pack-bron: $Repo ($Branch)" 'step'
        if (Test-Path (Join-Path $packDir '.git')) {
            Invoke-Native $git @('-C', $packDir, 'remote', 'set-url', 'origin', $Repo)
            Invoke-Native $git @('-C', $packDir, 'fetch', '-q', '--depth', '1', 'origin', $Branch)
            Invoke-Native $git @('-C', $packDir, 'reset', '-q', '--hard', 'FETCH_HEAD')
        } else {
            if (Test-Path -LiteralPath $packDir) { Remove-Item -LiteralPath $packDir -Recurse -Force }
            Invoke-Native $git @('clone', '-q', '--depth', '1', '--branch', $Branch, $Repo, $packDir)
        }
        Say ("pack-versie {0}" -f (& $git -C $packDir rev-parse --short HEAD)) 'ok'
    }

    # ---------------------------------------------------------------- installatie (Python)
    $pyVer = '3.13'
    $cfgText = Get-Content -LiteralPath (Join-Path $packDir 'comfy-pack.toml') -Raw
    if ($cfgText -match '(?ms)^\[python\]\s*$(.*?)(?=^\[|\z)') {
        if ($Matches[1] -match '(?m)^\s*version\s*=\s*"([^"]+)"') { $pyVer = $Matches[1] }
    }

    $env:UV_PYTHON_INSTALL_DIR = Join-Path $InstallDir '.python'   # niet in een (gewist) gebruikersprofiel
    if (-not $env:UV_CACHE_DIR) { $env:UV_CACHE_DIR = Join-Path $InstallDir '.cache\uv' }
    $env:UV_PYTHON_PREFERENCE = 'only-managed'
    $env:UV_SYSTEM_CERTS = '1'
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:COMFYPACK_UV = $uv
    $env:COMFYPACK_GIT = $git

    $cpArgs = @('run', '--no-project', '--python', $pyVer, '--',
        (Join-Path $packDir 'installer\comfypack.py'), '--log-file', $script:LogFile,
        'install', '--root', $InstallDir, '--profile', $Profiel)
    if ($SkipModels) { $cpArgs += '--skip-models' }
    if ($Mirror)     { $cpArgs += @('--mirror', $Mirror) }
    if ($TorchIndex) { $cpArgs += @('--torch-index', $TorchIndex) }

    $eap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { & $uv @cpArgs } finally { $ErrorActionPreference = $eap }
    $code = $LASTEXITCODE

    # ---------------------------------------------------------------- Windows-integratie
    $startBat = Join-Path $InstallDir 'start-comfyui.bat'
    if (Test-Path -LiteralPath $startBat) {
        $ico = Join-Path $InstallDir 'comfyui.ico'
        $icoSrc = Join-Path $packDir 'installer\assets\comfyui.ico'
        if (Test-Path -LiteralPath $icoSrc) { Copy-Item -LiteralPath $icoSrc -Destination $ico -Force }

        if ($isAdmin -and -not $NoAcl) {
            # Mappen in C:\ erven standaard 'Wijzigen' voor alle ingelogde gebruikers. Daarom:
            # overerving uit, beheerders/SYSTEM volledig, Gebruikers alleen lezen (venv, Python, tools) ...
            # SID's zijn taalonafhankelijk: S-1-5-32-544 Administrators, S-1-5-18 SYSTEM, S-1-5-32-545 Users
            Invoke-Native 'icacls.exe' @($InstallDir, '/inheritance:r', '/grant:r',
                '*S-1-5-32-544:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-545:(OI)(CI)RX', '/C', '/Q') | Out-Null
            # ... en alleen in ComfyUI\ mogen Gebruikers schrijven (output, input, user, models).
            Invoke-Native 'icacls.exe' @((Join-Path $InstallDir 'ComfyUI'), '/grant', '*S-1-5-32-545:(OI)(CI)M', '/C', '/Q') | Out-Null
            Say 'rechten: Gebruikers schrijven alleen in ComfyUI\, de rest is alleen-lezen' 'ok'
        }
        if (-not $NoShortcut) {
            $targets = @()
            if ($isAdmin) {
                $targets += [Environment]::GetFolderPath('CommonDesktopDirectory')
                $targets += [Environment]::GetFolderPath('CommonPrograms')
            } else {
                $targets += [Environment]::GetFolderPath('Desktop')
                $targets += [Environment]::GetFolderPath('Programs')
            }
            $ws = New-Object -ComObject WScript.Shell
            foreach ($t in $targets) {
                $lnk = $ws.CreateShortcut((Join-Path $t 'ComfyUI.lnk'))
                $lnk.TargetPath = $startBat
                $lnk.WorkingDirectory = $InstallDir
                $lnk.Description = 'ComfyUI starten'
                if (Test-Path -LiteralPath $ico) { $lnk.IconLocation = "$ico,0" }
                $lnk.Save()
            }
            Say 'snelkoppeling ComfyUI op bureaublad en in startmenu' 'ok'
        }
    }

    switch ($code) {
        0       { Say "klaar - start met de snelkoppeling of $startBat" 'ok' }
        1       { Say 'klaar met fouten (zie hierboven). Opnieuw draaien hervat waar het bleef.' 'err' }
        default { Say "installatie mislukt (exit $code)" 'err' }
    }
    Say "log: $($script:LogFile)"
    $script:ComfyPackExit = $code
}

$script:RepoGiven = $PSBoundParameters.ContainsKey('Repo')
$script:ComfyPackExit = 3
try {
    Invoke-ComfyPack          # niet toewijzen: dan streamt de uitvoer van uv/python live naar het scherm
} catch {
    Write-Host ("[FOUT] {0}" -f $_.Exception.Message) -ForegroundColor Red
    if ($script:LogFile) { Add-Content -LiteralPath $script:LogFile -Value "[FOUT] $($_.Exception.Message)" -Encoding UTF8 }
    $script:ComfyPackExit = 3
}
# Alleen 'exit' als dit als bestand draait: bij 'irm | iex' zou exit het venster sluiten.
if ($PSCommandPath) { exit $script:ComfyPackExit }

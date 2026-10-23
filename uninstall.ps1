<#
.SYNOPSIS
    Verwijdert een ComfyUI-installatie van dit pakket.
.EXAMPLE
    .\uninstall.ps1                      # vraagt om bevestiging
    .\uninstall.ps1 -KeepModels -Force   # alles weg behalve ComfyUI\models, zonder vragen
#>
[CmdletBinding()]
param(
    [string]$InstallDir = $(if ($env:COMFYPACK_ROOT) { $env:COMFYPACK_ROOT } else { 'C:\ComfyUI' }),
    [switch]$KeepModels,
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
$InstallDir = [IO.Path]::GetFullPath($InstallDir)
if (-not (Test-Path -LiteralPath (Join-Path $InstallDir '.comfypack'))) {
    throw "$InstallDir is geen installatie van dit pakket (.comfypack ontbreekt)."
}
if (-not $Force) {
    $what = if ($KeepModels) { "alles behalve ComfyUI\models" } else { "ALLES, inclusief modellen en output" }
    if ((Read-Host "Verwijder $what in $InstallDir ? Typ JA") -cne 'JA') { Write-Host 'Afgebroken.'; return }
}

Get-CimInstance Win32_Process -Filter "Name LIKE 'python%.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($InstallDir, [StringComparison]::OrdinalIgnoreCase) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$ws = New-Object -ComObject WScript.Shell
foreach ($dir in 'CommonDesktopDirectory', 'CommonPrograms', 'Desktop', 'Programs') {
    $lnk = Join-Path ([Environment]::GetFolderPath($dir)) 'ComfyUI.lnk'
    if ((Test-Path -LiteralPath $lnk) -and $ws.CreateShortcut($lnk).TargetPath.StartsWith($InstallDir, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $lnk -Force
    }
}

# rd met \\?\-prefix: werkt ook bij paden langer dan 260 tekens (custom nodes)
function Remove-Tree([string]$Path) {
    if (Test-Path -LiteralPath $Path) { cmd.exe /c "rd /s /q `"\\?\$Path`"" | Out-Null }
}
if ($KeepModels) {
    Get-ChildItem -LiteralPath $InstallDir -Force | Where-Object { $_.Name -ne 'ComfyUI' } | ForEach-Object {
        if ($_.PSIsContainer) { Remove-Tree $_.FullName } else { Remove-Item -LiteralPath $_.FullName -Force }
    }
    Get-ChildItem -LiteralPath (Join-Path $InstallDir 'ComfyUI') -Force | Where-Object { $_.Name -ne 'models' } | ForEach-Object {
        if ($_.PSIsContainer) { Remove-Tree $_.FullName } else { Remove-Item -LiteralPath $_.FullName -Force }
    }
    Write-Host "Verwijderd; modellen staan nog in $InstallDir\ComfyUI\models (worden bij herinstallatie hergebruikt)."
} else {
    Remove-Tree $InstallDir
    Write-Host "$InstallDir verwijderd."
}

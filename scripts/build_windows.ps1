param(
    [string]$Version = "0.1.0",
    [switch]$Installer
)
$ErrorActionPreference = "Stop"
python -m pip install --upgrade build pyinstaller
python -m build
$dist = Join-Path $PWD "dist\meteotracker-$Version-portable"
if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
python -m PyInstaller --noconfirm --clean --name Meteotracker --onedir --windowed `
    --collect-all PySide6 --collect-all pyproj `
    --add-data "config;config" `
    --paths src `
    src/meteotracker_qc/gui/__main__.py
if ($Installer) {
    $iscc = Get-Command iscc -ErrorAction SilentlyContinue
    if (-not $iscc) { throw "Inno Setup (iscc.exe) is required for -Installer" }
    & $iscc.Source "/DAppVersion=$Version" "installer\Meteotracker.iss"
}
Write-Host "Portable build: dist\Meteotracker"

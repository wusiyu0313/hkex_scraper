param(
  [string]$AppName = "HKEXIOScraper"
)

$ErrorActionPreference = "Stop"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

$browserDir = Join-Path $PWD "ms-playwright"
$env:PLAYWRIGHT_BROWSERS_PATH = $browserDir
python -m playwright install chromium

# Flet (PyInstaller-based) packaging for Windows
flet pack ui_app.py `
  --name $AppName `
  --onedir `
  --add-data "config.yaml:." `
  --add-data "consultants.yaml:." `
  --add-data "scraper:scraper" `
  --add-data "ms-playwright:ms-playwright"

Write-Host "Build complete. Check ./dist/$AppName" -ForegroundColor Green

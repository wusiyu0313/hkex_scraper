#!/usr/bin/env bash
set -euo pipefail

APP_NAME="${1:-HKEXIOScraper}"

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

export PLAYWRIGHT_BROWSERS_PATH="$(pwd)/ms-playwright"
python3 -m playwright install chromium

# Flet (PyInstaller-based) packaging for macOS arm64
flet pack ui_app.py \
  --name "$APP_NAME" \
  --add-data "config.yaml:." \
  --add-data "consultants.yaml:." \
  --add-data "scraper:scraper" \
  --add-data "ms-playwright:ms-playwright"

echo "Build complete. Check ./dist/$APP_NAME"

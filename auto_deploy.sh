#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

VENV="$APP_DIR/.venv"
PY=${PY:-python3}

if [ ! -d "$VENV" ]; then
  $PY -m venv "$VENV"
fi
source "$VENV/bin/activate"

pip install -U pip
pip install -r requirements.txt

echo "部署完成。可运行:"
echo "source $VENV/bin/activate && (\n  nohup python engine.py >/dev/null 2>&1 &\n  nohup python webapp.py >/dev/null 2>&1 &\n)"
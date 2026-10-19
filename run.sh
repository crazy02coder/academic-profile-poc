  https://eng.ku.edu.tr/hakkimizda/akademik-kadro/#!/usr/bin/env bash
# Tek komut: bash run.sh  → http://127.0.0.1:8000
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ]; then
  .venv/bin/python -m pip install -q -r requirements.txt
  .venv/bin/python -m playwright install chromium      # REA launch modu için
  .venv/bin/python -m patchright install chromium      # Scrapling StealthyFetcher için
  touch .venv/.installed
fi
if command -v npm >/dev/null && [ ! -x node_modules/.bin/rea ]; then npm install --no-audit --no-fund || echo "REA kurulamadı; Scrapling-only modda devam."; fi
if command -v ollama >/dev/null && ! curl -s -m 2 http://127.0.0.1:11434/api/tags >/dev/null; then
  (ollama serve >/dev/null 2>&1 &) ; sleep 2
fi
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}"

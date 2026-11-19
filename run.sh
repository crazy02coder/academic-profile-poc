#!/usr/bin/env bash
# Tek komut: bash run.sh  → http://127.0.0.1:8000   (Linux, macOS ve Windows'ta Git Bash)
set -euo pipefail
cd "$(dirname "$0")"
# Windows'ta Python dosyaları varsayılan olarak yerel kod sayfasıyla (cp1254) açar; veri dosyaları UTF-8'dir.
export PYTHONUTF8=1
# Python 3.11+ gerekir. Sanal ortamın Python'u Linux/macOS'ta .venv/bin, Windows'ta .venv/Scripts altındadır.
PY=.venv/bin/python
[ -x .venv/Scripts/python.exe ] && PY=.venv/Scripts/python.exe
if [ ! -x "$PY" ]; then
  BASE=""
  for candidate in "${PYTHON:-}" python3.13 python3.12 python3.11 python3 python "py -3.13" "py -3.12" "py -3.11"; do
    [ -n "$candidate" ] || continue
    if $candidate -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then BASE="$candidate"; break; fi
  done
  if [ -z "$BASE" ]; then echo "Python 3.11 ya da üstü bulunamadı. Kurup yeniden deneyin (ya da PYTHON=/yol/python bash run.sh)."; exit 1; fi
  $BASE -m venv .venv
  [ -x .venv/Scripts/python.exe ] && PY=.venv/Scripts/python.exe
fi
if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ]; then
  "$PY" -m pip install -q -r requirements.txt
  "$PY" -m playwright install chromium      # REA launch modu için
  "$PY" -m patchright install chromium      # Scrapling StealthyFetcher için
  touch .venv/.installed
fi
if command -v npm >/dev/null && [ ! -e node_modules/.bin/rea ]; then npm install --no-audit --no-fund || echo "REA kurulamadı; Scrapling-only modda devam."; fi
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}"

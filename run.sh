#!/usr/bin/env bash
# SmartClear — one-command local setup and launch.
#   ./run.sh            set up (first time) and start on http://localhost:8000
#   ./run.sh --retrain  also rebuild the OCR cache and reseed the synthetic set
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3.12}
command -v "$PY" >/dev/null || PY=python3

if [ ! -d .venv ]; then
  echo "▸ Creating Python virtualenv"
  "$PY" -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi

if [ ! -d frontend/dist ]; then
  echo "▸ Building frontend"
  (cd frontend && npm install --no-audit --no-fund && npm run build)
fi

if [ ! -f storage/smartclear.db ] || [ "${1:-}" = "--retrain" ]; then
  echo "▸ Seeding taxpayer records and processing the synthetic set"
  .venv/bin/python backend/scripts/build_cache.py >/dev/null
  .venv/bin/python backend/scripts/seed.py
fi

echo "▸ SmartClear running at http://localhost:8000  (login: officer / smartclear)"
cd backend && exec ../.venv/bin/uvicorn smartclear.api:app --host 127.0.0.1 --port 8000

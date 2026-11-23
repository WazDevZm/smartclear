#!/usr/bin/env bash
# SmartClear — one-command local setup and launch.
#   ./run.sh            set up (first time) and start on http://localhost:8000
#   ./run.sh --retrain  also rebuild the OCR cache, retrain the tamper model and re-evaluate
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

if [ "${1:-}" = "--retrain" ] || [ ! -f models/tamper_model.joblib ]; then
  echo "▸ Extracting synthetic NRCs (OCR cache)"
  .venv/bin/python backend/scripts/build_cache.py
  echo "▸ Training tamper model"
  .venv/bin/python backend/scripts/train_tamper.py
fi

if [ ! -f storage/smartclear.db ] || [ "${1:-}" = "--retrain" ]; then
  echo "▸ Seeding taxpayer records and processing the synthetic set"
  .venv/bin/python backend/scripts/build_cache.py >/dev/null
  .venv/bin/python backend/scripts/seed.py
  .venv/bin/python backend/scripts/evaluate.py
  .venv/bin/python backend/scripts/evaluate_registry.py >/dev/null
fi

# Existing databases from before the MoHA registry: seed it and check every case against it
if [ ! -f storage/moha_registry.db ]; then
  echo "▸ Seeding the Ministry of Home Affairs sandbox registry"
  .venv/bin/python backend/scripts/registry_backfill.py
  .venv/bin/python backend/scripts/evaluate_registry.py >/dev/null
fi

# The server sends extracted data to the registry over HTTP, as it would to the real MoHA service
export MOHA_API_URL=${MOHA_API_URL:-http://127.0.0.1:8000/moha/api/v1}

echo "▸ SmartClear running at http://localhost:8000  (login: officer / futureminds)"
[ -f .env ] && grep -q "^OPENROUTER_API_KEY=." .env && echo "▸ AI assistant: OpenRouter" || echo "▸ AI assistant: built-in rules (set OPENROUTER_API_KEY in .env for AI explanations)"
cd backend && exec ../.venv/bin/uvicorn smartclear.api:app --host 127.0.0.1 --port 8000

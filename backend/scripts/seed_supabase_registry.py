"""Load the NRC bank in Supabase (mohais_citizens) from the local MoHA register.

Usage: .venv/bin/python backend/scripts/seed_supabase_registry.py
Needs SUPABASE_URL and SUPABASE_SECRET_KEY in .env. Safe to re-run: rows are upserted by NRC number.
Afterwards set REGISTRY_BACKEND=supabase so verification reads from Supabase.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smartclear import registry, supabase_store  # noqa: E402
from smartclear.config import REGISTRY_DB_PATH, SUPABASE_SECRET_KEY, SUPABASE_URL  # noqa: E402

if __name__ == "__main__":
    if not (SUPABASE_URL and SUPABASE_SECRET_KEY):
        sys.exit("Set SUPABASE_URL and SUPABASE_SECRET_KEY in .env first.")
    if not REGISTRY_DB_PATH.exists():
        registry.seed()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rows = [{**r, "updated_at": now} for r in registry.citizen_rows()]
    print(f"Upserting {supabase_store.upsert(rows)} citizens into {SUPABASE_URL} ({supabase_store.TABLE})")
    print(f"NRC bank now holds {supabase_store.count()} citizens")

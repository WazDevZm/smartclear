"""Supabase-hosted NRC bank for the Ministry of Home Affairs registry (``mohais_citizens``).

Read through Supabase's REST API (PostgREST) with no extra dependencies. Enabled with ``REGISTRY_BACKEND=supabase``
plus ``SUPABASE_URL`` / ``SUPABASE_SECRET_KEY``; otherwise the registry uses its local SQLite copy.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .config import SUPABASE_SECRET_KEY, SUPABASE_TIMEOUT_S, SUPABASE_URL

TABLE = "mohais_citizens"
COLUMNS = ("nrc_number", "card_number", "full_name", "date_of_birth", "sex", "place_of_birth_district", "district",
           "registration_date", "status", "updated_at")
# fields the local register keeps that the Supabase table does not
_LOCAL_ONLY = ("place_of_birth_village", "village", "chief", "status_note")


def _request(method: str, path: str, body=None, prefer: str | None = None):
    headers = {"apikey": SUPABASE_SECRET_KEY, "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
               "Content-Type": "application/json", "Accept": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/{path}", method=method, headers=headers,
                                 data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=SUPABASE_TIMEOUT_S) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def _row(r: dict) -> dict:
    return {**{k: None for k in _LOCAL_ONLY}, **r}


def get_by_nrc(nrc: str) -> dict | None:
    rows = _request("GET", f"{TABLE}?select=*&nrc_number=eq.{urllib.parse.quote(nrc)}&limit=1")
    return _row(rows[0]) if rows else None


def by_date_of_birth(dob_iso: str) -> list[dict]:
    return [_row(r) for r in _request("GET", f"{TABLE}?select=*&date_of_birth=eq.{urllib.parse.quote(dob_iso)}")]


def count() -> int:
    return len(_request("GET", f"{TABLE}?select=nrc_number"))


def upsert(rows: list[dict]) -> int:
    """Insert or update citizens (by NRC number). Needs the secret key; used by the seeding script only."""
    payload = [{k: r.get(k) for k in COLUMNS} for r in rows]
    _request("POST", f"{TABLE}?on_conflict=nrc_number", payload,
             prefer="resolution=merge-duplicates,return=minimal")
    return len(payload)

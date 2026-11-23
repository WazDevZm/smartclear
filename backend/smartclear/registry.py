"""Ground-truth national registry: a sandbox stand-in for the Ministry of Home Affairs (MoHA) NRC database.

In production SmartClear would call the Department of National Registration's verification service. This module
plays that role for the pilot so the full *extract -> verify against source of truth -> explain -> officer decides*
flow can be exercised end to end.

* Its own SQLite database (``storage/moha_registry.db``), separate from SmartClear's case database, because it
  represents a different authority's system.
* Its own FastAPI app (mounted at ``/moha/api/v1``) guarded by an ``X-API-Key`` header, so it can be split out and
  run as an independent service without changing the client.
* Verification-style API: callers submit the details they extracted and get per-field match / mismatch outcomes,
  plus the card's status in the register (active, reported lost, revoked, deceased).

Seeded from the facilitators' verified ground truth (``data/facilitator_ground_truth.csv``). For altered cards the
register holds the ORIGINAL identity (taken from the captured taxpayer record, which seed.py derives from the
pre-alteration values), because the alteration happened on the physical card, not in the national register.
"""
from __future__ import annotations

import csv
import hmac
import sqlite3
import time
import uuid
from contextlib import contextmanager

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from . import gazetteer
from . import supabase_store
from .config import GROUND_TRUTH_CSV, MOHA_API_KEY, REGISTRY_BACKEND, REGISTRY_DB_PATH, TAXPAYER_RECORDS_CSV
from .verify import compare_names, fmt_nrc, norm_nrc, norm_name, parse_date

SCHEMA = """
CREATE TABLE IF NOT EXISTS citizens (
  nrc_number TEXT PRIMARY KEY, card_number TEXT, full_name TEXT, date_of_birth TEXT, sex TEXT,
  place_of_birth_village TEXT, place_of_birth_district TEXT, village TEXT, district TEXT, chief TEXT,
  registration_date TEXT, status TEXT DEFAULT 'active', status_note TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_cit_name ON citizens(full_name);
CREATE TABLE IF NOT EXISTS requests (
  id TEXT PRIMARY KEY, ts REAL, client TEXT, nrc_number TEXT, outcome TEXT
);
"""

STATUSES = {
    "active": "Card is valid.",
    "reported_lost": "This card was reported lost or stolen. Confirm the holder is the owner.",
    "replaced": "A newer card has been issued for this NRC number; this card number is no longer current.",
    "revoked": "This NRC was revoked by the Department of National Registration.",
    "deceased": "The register records this person as deceased.",
}

# Register-only identities (not on any synthetic card) that exercise the non-active statuses through the API.
EXTRA_CITIZENS = [
    ("111111/11/1", "Z10000001", "BWALYA MUTALE KAPASA", "1985-03-14", "M", "MANSA", "MANSA", "reported_lost",
     "Reported lost at Mansa Central Police, 2025-11-02."),
    ("222222/22/1", "Z10000002", "THANDIWE BANDA NGOMA", "1979-09-30", "F", "CHIPATA", "CHIPATA", "deceased",
     "Death registered 2024-06-18."),
    ("333333/33/1", "Z10000003", "MOSES CHILESHE LUNGU", "1992-01-05", "M", "KITWE", "KITWE", "revoked",
     "Duplicate registration revoked by DNR, 2023-02-11."),
    ("444444/44/1", "Z10000099", "AGNES MWILA SAKALA", "1988-07-21", "F", "KASAMA", "KASAMA", "replaced",
     "Replacement card Z10000099 issued 2026-01-15 (previous Z10000004)."),
]


@contextmanager
def conn():
    c = sqlite3.connect(REGISTRY_DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)


def _iso(v: str | None) -> str | None:
    d = parse_date(v)
    return d.isoformat() if d else None


def seed() -> int:
    """(Re)build the register from the facilitators' ground truth. Returns the number of citizens."""
    if REGISTRY_DB_PATH.exists():
        REGISTRY_DB_PATH.unlink()
    init()
    gt = list(csv.DictReader(open(GROUND_TRUTH_CSV)))
    records = {r["source_doc"]: r for r in csv.DictReader(open(TAXPAYER_RECORDS_CSV))} \
        if TAXPAYER_RECORDS_CSV.exists() else {}
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    rows = []
    for r in gt:
        nrc, name, dob = r["nrc_number"], r["full_name"], _iso(r["date_of_birth"])
        rec = records.get(r["file"])
        if r["tampered_field"] and rec:
            # the card was altered; the register keeps the true value
            if r["tampered_field"] == "nrc_number":
                nrc = rec["nrc_number"]
            elif r["tampered_field"] == "full_name":
                name = rec["full_name"]
            elif r["tampered_field"] == "date_of_birth":
                dob = rec["date_of_birth"]
        if not nrc:
            continue
        district = r["district"]
        if "district_inconsistency" in (r["fraud_types"] or ""):
            # the card's district field was changed; the register agrees with the place of birth
            district = r["place_of_birth_district"]
        rows.append((fmt_nrc(nrc), r["card_number"], norm_name(name), dob, r["sex"], r["place_of_birth_village"],
                     r["place_of_birth_district"], r["village"], district, r["chief"],
                     _iso(r["registration_date"]), "active", None, now))
    for nrc, card, name, dob, sex, pob, dist, status, note in EXTRA_CITIZENS:
        rows.append((nrc, card, name, dob, sex, pob, pob, pob, dist, None, None, status, note, now))
    with conn() as c:
        c.executemany("INSERT OR REPLACE INTO citizens VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def backend() -> str:
    return "supabase" if REGISTRY_BACKEND == "supabase" else "sqlite"


def citizen_rows() -> list[dict]:
    """Every citizen in the local register (the source the Supabase NRC bank is loaded from)."""
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM citizens")]


def _citizen(c, nrc: str | None) -> dict | None:
    if not nrc:
        return None
    if backend() == "supabase":
        return supabase_store.get_by_nrc(fmt_nrc(nrc))
    r = c.execute("SELECT * FROM citizens WHERE nrc_number=?", (fmt_nrc(nrc),)).fetchone()
    return dict(r) if r else None


def _find_by_name_dob(c, name: str | None, dob: str | None) -> dict | None:
    """Used when the NRC number is unreadable: exact date of birth + a matching name."""
    d = _iso(dob)
    if not (name and d):
        return None
    rows = supabase_store.by_date_of_birth(d) if backend() == "supabase" else \
        c.execute("SELECT * FROM citizens WHERE date_of_birth=?", (d,))
    for r in rows:
        if compare_names(name, r["full_name"])["outcome"] == "match":
            return dict(r)
    return None


def verify_identity(payload: dict, client: str = "unknown") -> dict:
    """Core registry check. payload: {nrc_number, full_name, date_of_birth, sex?, card_number?}."""
    request_id = f"MOHA-{uuid.uuid4().hex[:10].upper()}"
    with conn() as c:
        cit = _citizen(c, payload.get("nrc_number"))
        matched_by = "nrc_number" if cit else None
        if cit is None and not norm_nrc(payload.get("nrc_number")):
            cit = _find_by_name_dob(c, payload.get("full_name"), payload.get("date_of_birth"))
            matched_by = "name_and_date_of_birth" if cit else None
        if cit is None:
            outcome = "not_found"
            result = {"request_id": request_id, "found": False, "outcome": outcome, "status": None, "checks": {},
                      "message": "No citizen with this NRC number exists in the national register."
                      if norm_nrc(payload.get("nrc_number")) else
                      "NRC number unreadable and no citizen matches the name and date of birth."}
        else:
            checks = {}
            en = norm_nrc(payload.get("nrc_number"))
            if en:
                ok = en == norm_nrc(cit["nrc_number"])
                checks["nrc_number"] = {"outcome": "match" if ok else "mismatch",
                                        "submitted": fmt_nrc(en), "registry": cit["nrc_number"]}
            else:
                checks["nrc_number"] = {"outcome": "not_supplied", "submitted": None, "registry": cit["nrc_number"]}
            nm = compare_names(payload.get("full_name"), cit["full_name"])
            checks["full_name"] = {"outcome": "not_supplied" if nm["outcome"] == "unreadable" else nm["outcome"],
                                   "score": nm["score"], "detail": nm["detail"],
                                   "submitted": norm_name(payload.get("full_name")) or None,
                                   "registry": cit["full_name"]}
            sd = _iso(payload.get("date_of_birth"))
            checks["date_of_birth"] = ({"outcome": "match" if sd == cit["date_of_birth"] else "mismatch",
                                        "submitted": sd, "registry": cit["date_of_birth"]} if sd else
                                       {"outcome": "not_supplied", "submitted": None,
                                        "registry": cit["date_of_birth"]})
            for k in ("sex", "card_number", "district"):
                v, reg_v = payload.get(k), cit[k]
                if v and reg_v:
                    if k == "district":   # compare official names, so "KAPIRI" equals "KAPIRI MPOSHI"
                        same = (gazetteer.canonical(v) or v.upper()) == (gazetteer.canonical(reg_v) or reg_v.upper())
                    else:
                        same = v.replace(" ", "").upper() == reg_v.replace(" ", "").upper()
                    checks[k] = {"outcome": "match" if same else "mismatch", "submitted": v, "registry": reg_v}
            outs = [ch["outcome"] for ch in checks.values()]
            if cit["status"] != "active":
                outcome = "status_alert"
            elif "mismatch" in outs:
                outcome = "mismatch"
            elif "partial" in outs or "not_supplied" in outs:
                outcome = "partial"
            else:
                outcome = "match"
            result = {"request_id": request_id, "found": True, "matched_by": matched_by, "outcome": outcome,
                      "status": cit["status"], "status_message": STATUSES.get(cit["status"], ""),
                      "status_note": cit["status_note"], "checks": checks,
                      "registered_district": cit["district"], "registration_date": cit["registration_date"],
                      "register_backend": backend()}
        c.execute("INSERT INTO requests VALUES (?,?,?,?,?)",
                  (request_id, time.time(), client, fmt_nrc(payload.get("nrc_number")), outcome))
    return result


# ---- HTTP API: the registry as an independent service -------------------------------------------------------------
moha_app = FastAPI(title="Ministry of Home Affairs — National Registration (sandbox)", version="1.0",
                   description="Ground-truth NRC verification service used by SmartClear. Synthetic data only.")


def _client(x_api_key: str | None) -> str:
    if not x_api_key or not hmac.compare_digest(x_api_key, MOHA_API_KEY):
        raise HTTPException(401, "Missing or invalid X-API-Key")
    return "smartclear"


class VerifyRequest(BaseModel):
    nrc_number: str | None = None
    full_name: str | None = None
    date_of_birth: str | None = None
    sex: str | None = None
    card_number: str | None = None
    district: str | None = None


@moha_app.on_event("startup")
def _startup():
    init()


@moha_app.get("/health")
def health():
    with conn() as c:
        n = c.execute("SELECT COUNT(*) FROM citizens").fetchone()[0]
    return {"status": "ok", "citizens": n}


@moha_app.post("/verify")
def verify_endpoint(body: VerifyRequest, x_api_key: str | None = Header(None)):
    return verify_identity(body.model_dump(), _client(x_api_key))


@moha_app.get("/citizens/{nrc:path}")
def citizen_endpoint(nrc: str, x_api_key: str | None = Header(None)):
    _client(x_api_key)
    with conn() as c:
        cit = _citizen(c, nrc)
    if not cit:
        raise HTTPException(404, "NRC not found in the national register")
    return cit


@moha_app.get("/stats")
def stats_endpoint(x_api_key: str | None = Header(None)):
    _client(x_api_key)
    with conn() as c:
        return {"citizens": c.execute("SELECT COUNT(*) FROM citizens").fetchone()[0],
                "by_status": {r[0]: r[1] for r in c.execute("SELECT status, COUNT(*) FROM citizens GROUP BY status")},
                "requests": {r[0]: r[1] for r in c.execute("SELECT outcome, COUNT(*) FROM requests GROUP BY outcome")}}

"""SQLite persistence: captured taxpayer records, verification cases, officer reviews and an audit trail."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS taxpayers (
  tpin TEXT PRIMARY KEY, nrc_number TEXT, full_name TEXT, date_of_birth TEXT, sex TEXT,
  district TEXT, phone TEXT, captured_at TEXT, source_doc TEXT, scenario TEXT
);
CREATE INDEX IF NOT EXISTS ix_tp_nrc ON taxpayers(nrc_number);
CREATE TABLE IF NOT EXISTS cases (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ref TEXT UNIQUE, filename TEXT, tpin TEXT,
  status TEXT DEFAULT 'pending', risk_score REAL, risk_band TEXT, verification TEXT,
  nrc_number TEXT, full_name TEXT, date_of_birth TEXT, n_flags INTEGER,
  result TEXT, image_path TEXT, source_path TEXT, created_at TEXT, updated_at TEXT,
  decided_by TEXT, decision_note TEXT
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, action TEXT, case_id INTEGER, detail TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)


def audit(c, actor, action, case_id=None, detail=None):
    c.execute("INSERT INTO audit(ts,actor,action,case_id,detail) VALUES (?,?,?,?,?)",
              (now(), actor, action, case_id, json.dumps(detail) if detail is not None else None))


def get_taxpayer(c, tpin=None, nrc=None):
    if tpin:
        r = c.execute("SELECT * FROM taxpayers WHERE tpin=?", (tpin,)).fetchone()
    elif nrc:
        r = c.execute("SELECT * FROM taxpayers WHERE nrc_number=?", (nrc,)).fetchone()
    else:
        r = None
    return dict(r) if r else None


def case_row(r) -> dict:
    d = dict(r)
    d["result"] = json.loads(d["result"]) if d.get("result") else None
    return d

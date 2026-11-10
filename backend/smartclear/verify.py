"""Record verification: compare extracted NRC details with the taxpayer's captured record.

* NRC number  — exact match after normalisation (digits only)
* Date of birth — exact match after parsing any common date format
* Full name   — normalisation + similarity, tolerant of order, case, punctuation and a
                missing middle name; outcomes: match / partial (officer decides) / mismatch
"""
from __future__ import annotations

import re
from datetime import date, datetime

from rapidfuzz import fuzz

from .config import NAME_MATCH_THRESHOLD, NAME_REVIEW_THRESHOLD

CENTURY_PIVOT = (date.today().year % 100)


def norm_nrc(v: str | None) -> str | None:
    if not v:
        return None
    d = re.sub(r"\D", "", v)
    return d if len(d) == 9 else (d or None)


def fmt_nrc(v: str | None) -> str | None:
    d = norm_nrc(v)
    return f"{d[:6]}/{d[6:8]}/{d[8]}" if d and len(d) == 9 else v


def parse_date(v: str | None) -> date | None:
    """Parse NRC dd.mm.yy and common captured-record formats."""
    if not v:
        return None
    v = v.strip()
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(v, f).date()
        except ValueError:
            pass
    m = re.match(r"^(\d{1,2})[./\-](\d{1,2})[./\-](\d{2})$", v)
    if m:
        dd, mm, yy = map(int, m.groups())
        year = 2000 + yy if yy <= CENTURY_PIVOT else 1900 + yy
        try:
            return date(year, mm, dd)
        except ValueError:
            return None
    return None


def norm_name(v: str | None) -> str:
    if not v:
        return ""
    v = re.sub(r"[^A-Za-z\s'-]", " ", v).upper().replace("-", " ").replace("'", "")
    return re.sub(r"\s+", " ", v).strip()


def compare_names(extracted: str | None, record: str | None) -> dict:
    a, b = norm_name(extracted), norm_name(record)
    if not a:
        return {"outcome": "unreadable", "score": 0, "detail": "Name could not be read from the document."}
    if not b:
        return {"outcome": "no_record", "score": 0, "detail": "No name on the captured record."}
    sort_score = fuzz.token_sort_ratio(a, b)
    set_score = fuzz.token_set_ratio(a, b)
    ta, tb = set(a.split()), set(b.split())
    subset = (ta <= tb or tb <= ta) and len(ta & tb) >= 2
    if a == b:
        return {"outcome": "match", "score": 100, "detail": "Exact match."}
    # Token alignment: every name on the shorter side should have a close counterpart
    short, long_ = (a.split(), b.split()) if len(a.split()) <= len(b.split()) else (b.split(), a.split())
    worst = min(max(fuzz.ratio(t, u) for u in long_) for t in short)
    if worst < 70:
        odd = min(short, key=lambda t: max(fuzz.ratio(t, u) for u in long_))
        return {"outcome": "mismatch", "score": round(sort_score),
                "detail": f"Name '{odd}' does not appear on the other side."}
    if sort_score >= NAME_MATCH_THRESHOLD:
        why = "Same names in a different order." if sorted(a.split()) == sorted(b.split()) else \
            "Minor spelling/format difference."
        return {"outcome": "match", "score": round(sort_score), "detail": why}
    if subset:
        return {"outcome": "partial", "score": round(set_score),
                "detail": "One name is missing (e.g. middle name) — confirm with taxpayer."}
    if sort_score >= NAME_REVIEW_THRESHOLD:
        return {"outcome": "partial", "score": round(sort_score), "detail": "Similar but not identical — officer to confirm."}
    return {"outcome": "mismatch", "score": round(sort_score), "detail": "Names do not correspond."}


def verify(fields: dict, record: dict | None) -> dict:
    """fields: extracted values {nrc_number, full_name, date_of_birth}; record: captured taxpayer record."""
    if not record:
        return {"overall": "no_record", "checks": {}, "summary": "No captured taxpayer record linked to this document."}
    checks = {}
    en, rn = norm_nrc(fields.get("nrc_number")), norm_nrc(record.get("nrc_number"))
    if not en:
        checks["nrc_number"] = {"outcome": "unreadable", "extracted": None, "record": fmt_nrc(rn),
                                "detail": "NRC number could not be read from the document."}
    else:
        ok = en == rn
        checks["nrc_number"] = {"outcome": "match" if ok else "mismatch", "extracted": fmt_nrc(en), "record": fmt_nrc(rn),
                                "detail": "Exact match." if ok else "NRC number differs from the captured record."}
    ed, rd = parse_date(fields.get("date_of_birth")), parse_date(record.get("date_of_birth"))
    if not ed:
        checks["date_of_birth"] = {"outcome": "unreadable", "extracted": None, "record": rd.isoformat() if rd else None,
                                   "detail": "Date of birth could not be read from the document."}
    else:
        ok = ed == rd
        checks["date_of_birth"] = {"outcome": "match" if ok else "mismatch", "extracted": ed.isoformat(),
                                   "record": rd.isoformat() if rd else None,
                                   "detail": "Exact match." if ok else "Date of birth differs from the captured record."}
    nm = compare_names(fields.get("full_name"), record.get("full_name"))
    checks["full_name"] = {**nm, "extracted": norm_name(fields.get("full_name")) or None, "record": norm_name(record.get("full_name"))}

    outs = [c["outcome"] for c in checks.values()]
    if "mismatch" in outs:
        overall = "mismatch"
    elif any(o in ("partial", "unreadable") for o in outs):
        overall = "review"
    else:
        overall = "match"
    summary = {"match": "All key details match the captured record.",
               "review": "Some details need officer confirmation.",
               "mismatch": "One or more key details do not match the captured record."}[overall]
    return {"overall": overall, "checks": checks, "summary": summary}

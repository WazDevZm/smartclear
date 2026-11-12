"""Zambian administrative reference data used for OCR post-correction and consistency checks.

The district list is loaded from a verified CSV (``data/zambia_districts.csv``, Zambia administrative
boundaries 2020: one row per district with DISTRICT, PROVINCE and DIST_CODE columns). Replace that file
to update the reference; no code change is needed.

District matching is two-level, so an OCR slip is never silently turned into a different district:

* score >= DISTRICT_AUTO_CORRECT   -> the value is corrected to the canonical district (raw OCR kept)
* score >= DISTRICT_SUGGEST        -> the OCR value is kept and the district is offered as a suggestion
* otherwise                        -> the value is left untouched
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache

from .config import DISTRICT_AUTO_CORRECT, DISTRICT_SUGGEST, DISTRICTS_CSV

# Common alternative spellings -> the spelling used in the verified CSV.
ALIASES = {
    "KAPIRI": "KAPIRI MPOSHI",
    "CHIKANKATA": "CHIKANKANTA",
    "MILENGE": "MILENGI",
    "MUSHINDAMO": "MUSHINDANO",
    "ITEZHI TEZHI": "ITEZHI-TEZHI",
    "ITEZHITEZHI": "ITEZHI-TEZHI",
    "SHIWANGANDU": "SHIWANG'ANDU",
    "CHIENGE": "CHIENGI",
}


def _key(value: str) -> str:
    """Comparison key: upper case letters only (spaces, hyphens and apostrophes dropped)."""
    return re.sub(r"[^A-Z]", "", value.upper())


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, str], dict[str, str]]:
    """Return (district -> province, district -> district code) from the verified CSV."""
    province, code = {}, {}
    with open(DISTRICTS_CSV, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            name = re.sub(r"\s+", " ", (row.get("DISTRICT") or "").strip().upper())
            if not name:
                continue
            province[name] = (row.get("PROVINCE") or "").strip()
            code[name] = (row.get("DIST_CODE") or "").strip()
    if not province:
        raise RuntimeError(f"No districts found in {DISTRICTS_CSV}")
    return province, code


def _index() -> dict[str, str]:
    """Comparison key -> canonical district, including aliases."""
    province, _ = _load()
    idx = {_key(d): d for d in province}
    for alias, canonical in ALIASES.items():
        if canonical in province:
            idx.setdefault(_key(alias), canonical)
    return idx


def province(name: str | None) -> str | None:
    c = canonical(name)
    return _load()[0].get(c) if c else None


def districts() -> list[str]:
    return sorted(_load()[0])


def district_code(name: str | None) -> str | None:
    c = canonical(name)
    return _load()[1].get(c) if c else None


def canonical(value: str | None) -> str | None:
    """Exact (spelling-insensitive) lookup of a district or alias; None if unknown."""
    if not value:
        return None
    return _index().get(_key(value))


def is_known_district(value: str | None) -> bool:
    return canonical(value) is not None


@dataclass
class DistrictMatch:
    district: str | None      # canonical district, if any candidate scored >= DISTRICT_SUGGEST
    score: float              # 0-100 similarity of the best candidate
    matched_text: str         # the part of the input that matched
    status: str               # exact | corrected | suggested | none


TRIM_MIN_LEN = 8        # only long words may have stray characters trimmed
TRIM_PENALTY = 3.0      # similarity points deducted per trimmed character


def _candidates(text: str) -> dict[str, int]:
    """Pieces of an OCR string that might be a district -> number of characters trimmed.

    Pieces are the whole string, each word and each pair of neighbouring words. Long words are
    also tried with up to two stray characters trimmed from either end, because OCR often glues a
    neighbouring mark onto a word (e.g. 'TMWANSABOBW'); trimming costs TRIM_PENALTY per character
    so short village names are not bent into districts."""
    words = [w for w in re.split(r"[\s.,:;/]+", text.upper()) if w]
    pieces = {text.upper().strip()}
    pieces.update(words)
    pieces.update(" ".join(words[i:i + 2]) for i in range(len(words) - 1))
    out: dict[str, int] = {}
    for p in pieces:
        k = _key(p)
        if len(k) < 4:
            continue
        out[k] = 0
        if len(k) < TRIM_MIN_LEN:
            continue
        for a in range(3):
            for b in range(3):
                t = k[a:len(k) - b]
                if (a or b) and len(t) >= 6:
                    out[t] = min(out.get(t, 99), a + b)
    return out


def match_district(text: str | None, auto: float = DISTRICT_AUTO_CORRECT,
                   suggest: float = DISTRICT_SUGGEST) -> DistrictMatch:
    """Find the district named in an OCR string (whole value, a word, or a trimmed word)."""
    if not text or not _key(text):
        return DistrictMatch(None, 0.0, "", "none")
    exact = canonical(text)
    if exact:
        return DistrictMatch(exact, 100.0, text, "exact")
    from rapidfuzz import fuzz

    idx = _index()
    best = (0.0, None, "", 0)
    for cand, trimmed in _candidates(text).items():
        if cand in idx:
            # a district spelled exactly inside a longer string (e.g. 'T MWANSABOMBWE')
            score, hit = 97.0 - TRIM_PENALTY * trimmed, idx[cand]
        else:
            score, hit = 0.0, None
            for k, d in idx.items():
                if abs(len(k) - len(cand)) > 3:
                    continue
                s = fuzz.ratio(cand, k) - TRIM_PENALTY * trimmed
                if s > score:
                    score, hit = s, d
        if hit is not None and score > best[0]:
            best = (score, hit, cand, trimmed)
    score, hit, cand, trimmed = best
    if hit is None or score < suggest:
        return DistrictMatch(None, round(score, 1), cand, "none")
    if score >= auto or (not trimmed and _one_slip(cand, _key(hit), idx)):
        return DistrictMatch(hit, round(score, 1), cand, "corrected")
    return DistrictMatch(hit, round(score, 1), cand, "suggested")


def _one_slip(cand: str, key: str, idx: dict[str, str]) -> bool:
    """A single wrong letter in a word of 5+ letters (XAFUE -> KAFUE) is corrected even though
    its similarity is only ~80%, provided no other district is within two edits (unambiguous)."""
    from rapidfuzz.distance import Levenshtein

    if len(key) < 5 or Levenshtein.distance(cand, key) != 1:
        return False
    return all(Levenshtein.distance(cand, k) > 2 for k in idx if k != key)


def snap_district(value: str | None, min_score: float = DISTRICT_AUTO_CORRECT) -> tuple[str | None, bool]:
    """Backwards-compatible helper: (canonical_district, was_corrected); unknown values are untouched."""
    if not value:
        return value, False
    m = match_district(value, auto=min_score)
    if m.status == "exact":
        return m.district, m.district != value.upper().strip()
    if m.status == "corrected":
        return m.district, True
    return value.upper().strip(), False

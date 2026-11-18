"""Zambian administrative reference data used for OCR post-correction and consistency checks."""
from __future__ import annotations

import csv
from pathlib import Path

PROVINCE_DISTRICTS = {
    "Lusaka": ["LUSAKA", "CHONGWE", "KAFUE", "LUANGWA", "RUFUNSA", "SHIBUYUNJI", "CHILANGA", "CHIRUNDU"],
    "Copperbelt": ["NDOLA", "KITWE", "CHINGOLA", "MUFULIRA", "LUANSHYA", "KALULUSHI", "CHILILABOMBWE",
                   "LUFWANYAMA", "MASAITI", "MPONGWE"],
    "Central": ["KABWE", "KAPIRI", "KAPIRI MPOSHI", "MKUSHI", "MUMBWA", "SERENJE", "CHIBOMBO", "CHISAMBA",
                "ITEZHI-TEZHI", "LUANO", "NGABWE", "CHITAMBO"],
    "Southern": ["LIVINGSTONE", "CHOMA", "MONZE", "MAZABUKA", "KALOMO", "NAMWALA", "GWEMBE", "SIAVONGA",
                 "SINAZONGWE", "KAZUNGULA", "PEMBA", "CHIKANKATA", "ZIMBA"],
    "Eastern": ["CHIPATA", "PETAUKE", "LUNDAZI", "KATETE", "CHADIZA", "NYIMBA", "MAMBWE", "SINDA", "VUBWI",
                "LUSANGAZI", "CHASEFU"],
    "Northern": ["KASAMA", "MBALA", "MPULUNGU", "LUWINGU", "MUNGWI", "KAPUTA", "CHILUBI", "NSAMA",
                 "MPOROKOSO", "LUNTE", "SENGA HILL", "LUPOSOSHI"],
    "Muchinga": ["CHINSALI", "MPIKA", "NAKONDE", "ISOKA", "MAFINGA", "SHIWANG'ANDU", "KANCHIBIYA", "LAVUSHIMANDA"],
    "Luapula": ["MANSA", "SAMFYA", "KAWAMBWA", "NCHELENGE", "MWENSE", "CHIENGI", "MILENGE", "CHEMBE", "CHIPILI",
                "LUNGA", "MWANSABOMBWE", "CHIFUNABULI"],
    "North-Western": ["SOLWEZI", "MWINILUNGA", "KASEMPA", "ZAMBEZI", "KABOMPO", "CHAVUMA", "MUFUMBWE",
                      "IKELENGE", "MANYINGA", "KALUMBILA", "MUSHINDAMO"],
    "Western": ["MONGU", "SENANGA", "KAOMA", "SESHEKE", "KALABO", "LUKULU", "SHANGOMBO", "SIOMA", "NALOLO",
                "LIMULUNGA", "LUAMPA", "MITETE", "MULOBEZI", "MWANDI", "NKEYEMA", "SIKONGO"],
}
DISTRICT_PROVINCE = {d: p for p, ds in PROVINCE_DISTRICTS.items() for d in ds}
DISTRICT_CODES: dict[str, str] = {}

# Merge the provided 2020 administrative boundary attributes with the legacy
# district names above so older NRC spellings remain recognizable.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DISTRICT_CSV = _PROJECT_ROOT / "data" / "references" / "zambia_districts_2020.csv"
if _DISTRICT_CSV.exists():
    with _DISTRICT_CSV.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            district = (row.get("DISTRICT") or "").strip().upper()
            province = (row.get("PROVINCE") or "").strip()
            code = (row.get("DIST_CODE") or "").strip()
            if district and province:
                DISTRICT_PROVINCE[district] = province
                if code:
                    DISTRICT_CODES[district] = code

PROVINCE_DISTRICTS = {
    province: sorted(district for district, owner in DISTRICT_PROVINCE.items()
                     if owner.casefold() == province.casefold())
    for province in {p for p in DISTRICT_PROVINCE.values()}
}
DISTRICTS = sorted(DISTRICT_PROVINCE)

def snap_district(value: str | None, min_score: int = 80) -> tuple[str | None, bool]:
    """Return (canonical_district, was_corrected). Leaves unknown values untouched."""
    if not value:
        return value, False
    from rapidfuzz import process, fuzz

    v = value.upper().strip()
    if v in DISTRICT_PROVINCE:
        return v, False
    hit = process.extractOne(v, DISTRICTS, scorer=fuzz.ratio)
    if hit and hit[1] >= min_score:
        return hit[0], True
    return v, False


def is_known_district(value: str | None) -> bool:
    return bool(value) and value.upper() in DISTRICT_PROVINCE

def suggest_district(value: str | None, min_score: int = 85, min_margin: int = 8):
    """Return a conservative (name, similarity, margin) directory suggestion."""
    if not value:
        return None, 0, 0
    from rapidfuzz import process, fuzz

    normalized = " ".join(value.upper().replace(".", " ").split())
    if normalized in DISTRICT_PROVINCE:
        return normalized, 100, 100
    hits = process.extract(normalized, DISTRICTS, scorer=fuzz.ratio, limit=2)
    if not hits:
        return None, 0, 0
    margin = int(hits[0][1] - (hits[1][1] if len(hits) > 1 else 0))
    score = int(hits[0][1])
    if score < min_score or margin < min_margin:
        return None, score, margin
    return hits[0][0], score, margin

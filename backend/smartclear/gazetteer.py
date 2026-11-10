"""Zambian administrative reference data used for OCR post-correction and consistency checks."""
from __future__ import annotations

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

"""Rule-based flags and risk score.

A flag means "an officer should look at this" — never an automated fraud determination.
Each flag carries a code, severity, plain-language message and the evidence behind it.
"""
from __future__ import annotations

import json
import re
from datetime import date
from functools import lru_cache

from .config import MIN_REGISTRATION_AGE, OCR_LOW_CONFIDENCE, REFERENCE_PATH
from .gazetteer import DISTRICT_PROVINCE
from .verify import parse_date

SEVERITY_WEIGHT = {"high": 70, "medium": 40, "low": 15}
FIELDS = ("nrc_number", "full_name", "date_of_birth")
FIELD_LABEL = {"nrc_number": "NRC number", "full_name": "Full name", "date_of_birth": "Date of birth"}


@lru_cache(maxsize=1)
def reference() -> dict:
    if REFERENCE_PATH.exists():
        return json.loads(REFERENCE_PATH.read_text())
    return {"district_codes": {}}


def _flag(code, severity, title, message, field=None, evidence=None):
    return {"code": code, "severity": severity, "title": title, "message": message, "field": field,
            "evidence": evidence or {}}


def rule_flags(fields: dict, conf: dict, today: date | None = None) -> list[dict]:
    today = today or date.today()
    flags = []
    nrc = fields.get("nrc_number")
    if not nrc:
        flags.append(_flag("NRC_UNREADABLE", "high", "NRC number unreadable",
                           "The registration number could not be read — it may be obscured or erased.", "nrc_number"))
    elif not re.fullmatch(r"\d{6}/\d{2}/\d", nrc):
        flags.append(_flag("NRC_FORMAT", "medium", "Unusual NRC format",
                           f"'{nrc}' does not follow the NNNNNN/NN/N pattern.", "nrc_number"))
    if not fields.get("full_name"):
        flags.append(_flag("NAME_UNREADABLE", "high", "Name unreadable",
                           "The full name could not be read — it may be obscured or erased.", "full_name"))
    dob = parse_date(fields.get("date_of_birth"))
    reg = parse_date(fields.get("registration_date"))
    if not fields.get("date_of_birth"):
        flags.append(_flag("DOB_UNREADABLE", "high", "Date of birth unreadable",
                           "The date of birth could not be read — it may be obscured or erased.", "date_of_birth"))
    elif dob is None:
        flags.append(_flag("DOB_INVALID", "high", "Invalid date of birth",
                           f"'{fields.get('date_of_birth')}' is not a valid calendar date.", "date_of_birth"))

    # Reference check: district code in the NRC number vs place-of-birth district
    codes = reference().get("district_codes", {})
    pob_d, dist = fields.get("place_of_birth_district"), fields.get("district")
    if nrc and re.fullmatch(r"\d{6}/\d{2}/\d", nrc) and codes:
        code = nrc.split("/")[1]
        expected = codes.get(code)
        if expected and pob_d and expected != pob_d:
            flags.append(_flag("NRC_CODE_DISTRICT", "high", "NRC code doesn't match district",
                               f"NRC district code {code} belongs to {expected}, but the card shows place of birth "
                               f"district {pob_d}.", "nrc_number", {"code": code, "expected": expected, "card": pob_d}))
        elif not expected:
            flags.append(_flag("NRC_CODE_UNKNOWN", "low", "Unrecognised NRC district code",
                               f"District code {code} is not in the reference table.", "nrc_number", {"code": code}))
    if pob_d and dist and pob_d != dist:
        flags.append(_flag("DISTRICT_INCONSISTENT", "high", "District fields disagree",
                           f"Place-of-birth district is {pob_d} but the district field reads {dist}.", "district",
                           {"place_of_birth_district": pob_d, "district": dist,
                            "provinces": [DISTRICT_PROVINCE.get(pob_d), DISTRICT_PROVINCE.get(dist)]}))

    if dob:
        if dob > today:
            flags.append(_flag("DOB_FUTURE", "high", "Date of birth in the future", f"{dob.isoformat()} is after today.",
                               "date_of_birth"))
        if reg:
            age = (reg - dob).days / 365.25
            if reg < dob:
                flags.append(_flag("REG_BEFORE_BIRTH", "high", "Registered before birth",
                                   "Registration date is earlier than the date of birth.", "registration_date"))
            elif age < MIN_REGISTRATION_AGE:
                flags.append(_flag("UNDERAGE_REGISTRATION", "high", "Registered under age 16",
                                   f"Card was issued at age {age:.1f}; NRCs are issued from age {MIN_REGISTRATION_AGE}.",
                                   "date_of_birth", {"age_at_registration": round(age, 1)}))
        if (today - dob).days / 365.25 > 110:
            flags.append(_flag("AGE_IMPLAUSIBLE", "medium", "Implausible age", "Holder would be over 110 years old.",
                               "date_of_birth"))
    if reg and reg > today:
        flags.append(_flag("REG_FUTURE", "high", "Registration date in the future", f"{reg.isoformat()} is after today.",
                           "registration_date"))

    for f in FIELDS:
        c = conf.get(f)
        if fields.get(f) and c is not None and c < OCR_LOW_CONFIDENCE:
            flags.append(_flag("LOW_OCR_CONFIDENCE", "low", f"{FIELD_LABEL[f]} hard to read",
                               f"OCR confidence {c:.0%} — please check the value against the image.", f))
    return flags


def risk(flags: list[dict], verification: dict) -> dict:
    score = 0.0
    for fl in flags:
        score = max(score, SEVERITY_WEIGHT[fl["severity"]] + 5 * (sum(1 for x in flags if x["severity"] == "high") - 1))
    ov = verification.get("overall")
    if ov == "mismatch":
        score = max(score, 75)
    elif ov == "review":
        score = max(score, 35)
    score = float(min(100, round(score)))
    band = "high" if score >= 70 else "review" if score >= 30 else "clear"
    rec = {"clear": "Details verified and no anomalies found — proceed, subject to officer confirmation.",
           "review": "Check the highlighted items before completing registration.",
           "high": "Do not complete registration until the flagged issues are resolved."}[band]
    return {"score": score, "band": band, "recommendation": rec}

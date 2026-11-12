"""Anomaly / fraud flagging: explainable rules + the trained tamper model.

A flag means "an officer should look at this" — never an automated fraud determination.
Each flag carries a code, severity, plain-language message and the evidence behind it.
"""
from __future__ import annotations

import json
import re
from datetime import date
from functools import lru_cache

import joblib
import numpy as np

from .config import (MIN_REGISTRATION_AGE, OCR_LOW_CONFIDENCE, REFERENCE_PATH, TAMPER_FIELD_THRESHOLD,
                     TAMPER_MODEL_PATH)
from .forensics import FEATURE_LABELS, FIELDS, compute_features, crop_box, vectorize
from .gazetteer import canonical, province
from .verify import parse_date

SEVERITY_WEIGHT = {"high": 70, "medium": 40, "low": 15}
FIELD_LABEL = {"nrc_number": "NRC number", "full_name": "Full name", "date_of_birth": "Date of birth"}


@lru_cache(maxsize=1)
def tamper_model():
    if not TAMPER_MODEL_PATH.exists():
        return None
    return joblib.load(TAMPER_MODEL_PATH)


@lru_cache(maxsize=1)
def reference() -> dict:
    if REFERENCE_PATH.exists():
        return json.loads(REFERENCE_PATH.read_text())
    return {"district_codes": {}}


def _flag(code, severity, title, message, field=None, evidence=None):
    return {"code": code, "severity": severity, "title": title, "message": message, "field": field,
            "evidence": evidence or {}}


def explain(feats: dict, model_pack: dict, top=3) -> list[str]:
    med, iqr = model_pack["medians"], model_pack["iqr"]
    scored = []
    for k, label in FEATURE_LABELS.items():
        z = (feats[k] - med[k]) / (abs(iqr[k]) + 1e-6)
        if k in ("ocr_conf", "sharpness", "edge_energy"):
            z = -z          # low values are the suspicious direction
        scored.append((z, label))
    seen, out = set(), []
    for z, label in sorted(scored, reverse=True):
        if z > 1.5 and label not in seen:
            seen.add(label)
            out.append(label)
        if len(out) >= top:
            break
    return out


def tamper_scores(deskewed: np.ndarray, boxes: dict) -> dict:
    pack = tamper_model()
    out = {}
    for f in FIELDS:
        box = boxes.get(f)
        if pack is None or box is None or deskewed is None:
            out[f] = {"probability": None, "reasons": []}
            continue
        feats = compute_features(crop_box(deskewed, box), f)
        p = float(pack["model"].predict_proba(vectorize(feats)[None, :])[0, 1])
        out[f] = {"probability": round(p, 4), "reasons": explain(feats, pack) if p >= 0.3 else [],
                  "features": {k: round(float(v), 4) for k, v in feats.items()}}
    return out


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
        expected = canonical(expected) or expected
        if expected and pob_d and expected != (canonical(pob_d) or pob_d):
            flags.append(_flag("NRC_CODE_DISTRICT", "high", "NRC code doesn't match district",
                               f"NRC district code {code} belongs to {expected}, but the card shows place of birth "
                               f"district {pob_d}.", "nrc_number", {"code": code, "expected": expected, "card": pob_d}))
        elif not expected:
            flags.append(_flag("NRC_CODE_UNKNOWN", "low", "Unrecognised NRC district code",
                               f"District code {code} is not in the reference table.", "nrc_number", {"code": code}))
    if pob_d and dist and (canonical(pob_d) or pob_d) != (canonical(dist) or dist):
        flags.append(_flag("DISTRICT_INCONSISTENT", "high", "District fields disagree",
                           f"Place-of-birth district is {pob_d} but the district field reads {dist}.", "district",
                           {"place_of_birth_district": pob_d, "district": dist,
                            "provinces": [province(pob_d), province(dist)]}))

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


def model_flags(scores: dict) -> list[dict]:
    flags = []
    for f, s in scores.items():
        p = s.get("probability")
        if p is not None and p >= TAMPER_FIELD_THRESHOLD:
            sev = "high" if p >= 0.75 else "medium"
            why = "; ".join(s["reasons"]) or "Image characteristics differ from genuine typed fields."
            flags.append(_flag("TAMPER_SUSPECTED", sev, f"{FIELD_LABEL[f]} may be altered",
                               f"Tamper model score {p:.0%}. {why}.", f, {"probability": p, "reasons": s["reasons"]}))
    return flags


def risk(flags: list[dict], verification: dict, scores: dict) -> dict:
    score = 0.0
    for fl in flags:
        score = max(score, SEVERITY_WEIGHT[fl["severity"]] + 5 * (sum(1 for x in flags if x["severity"] == "high") - 1))
    for s in scores.values():
        if s.get("probability") is not None:
            score = max(score, 100 * s["probability"] * 0.95)
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

"""AI intelligence layer: explain a case's flags in plain language and recommend a next step to the officer.

Human-in-the-loop by design:
* The AI only explains and suggests. It cannot approve, reject or change a record; the officer's decision is
  recorded separately, together with whether it followed or overrode the suggestion.
* Personal data never leaves SmartClear. The model receives an anonymised case summary: outcomes, which part of a
  value differs (e.g. "district code digits differ", "year of birth differs by 10 years"), flag types and tamper
  reasons, but no names, NRC numbers or dates of birth.
* If the AI service is unavailable or returns something unusable, a deterministic rule-based explainer produces the
  same structure, so officers always get guidance (``source`` says which one produced it).
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

from .config import AI_BUDGET_S, AI_TIMEOUT_S, GEMINI_API_KEY, GEMINI_MODELS
from .verify import norm_nrc, parse_date

ACTIONS = {
    "approve": "Approve the registration",
    "request_info": "Ask the taxpayer for more information or a corrected form",
    "escalate": "Escalate to a supervisor for investigation",
    "reject": "Reject the registration",
}
FIELD = {"nrc_number": "NRC number", "full_name": "full name", "date_of_birth": "date of birth", "sex": "sex",
         "card_number": "card number", "district": "district"}
_NRC_RE = re.compile(r"\b\d{6}\s*/\s*\d{2}\s*/\s*\d\b")
_DATE_RE = re.compile(r"\b\d{1,4}[./-]\d{1,2}[./-]\d{2,4}\b")


# ---- anonymised facts ---------------------------------------------------------------------------------------------
def _nrc_diff(a: str | None, b: str | None) -> str:
    a, b = norm_nrc(a), norm_nrc(b)
    if not a or not b or len(a) != 9 or len(b) != 9:
        return "one side unreadable or malformed"
    if a == b:
        return "identical"
    parts = [("serial number", a[:6], b[:6]), ("district code", a[6:8], b[6:8]), ("final digit", a[8], b[8])]
    diff = [f"{n} ({sum(x != y for x, y in zip(p, q))} digit(s) differ)" for n, p, q in parts if p != q]
    return "differs in " + ", ".join(diff)


def _date_diff(a: str | None, b: str | None) -> str:
    da, db = parse_date(a), parse_date(b)
    if not da or not db:
        return "one side unreadable"
    if da == db:
        return "identical"
    days = abs((da - db).days)
    bits = [w for w, x, y in (("day", da.day, db.day), ("month", da.month, db.month), ("year", da.year, db.year))
            if x != y]
    span = f"{abs(da.year - db.year)} year(s)" if da.year != db.year else f"{days} day(s)"
    return f"differs by {span} ({', '.join(bits)} changed)"


def _name_diff(check: dict) -> str:
    o, score = check.get("outcome"), check.get("score")
    detail = (check.get("detail") or "").lower()
    if o == "match":
        kind = "same names in different order" if "order" in detail else "exact or near-exact"
    elif o == "partial":
        kind = "one name missing (e.g. middle name)" if "missing" in detail else "similar but not identical"
    elif o == "mismatch":
        kind = "at least one name does not correspond"
    else:
        kind = o or "unknown"
    return f"{o}: {kind}" + (f" (similarity {score}/100)" if score is not None else "")


def _compare(checks: dict, a_key: str, b_key: str) -> dict:
    out = {}
    for k, ch in checks.items():
        o = ch.get("outcome")
        if k == "full_name":
            out[FIELD[k]] = _name_diff(ch)
        elif k == "nrc_number":
            out[FIELD[k]] = f"{o}: {_nrc_diff(ch.get(a_key), ch.get(b_key))}"
        elif k == "date_of_birth":
            out[FIELD[k]] = f"{o}: {_date_diff(ch.get(a_key), ch.get(b_key))}"
        else:
            out[FIELD.get(k, k)] = o
    return out


def _redact(text: str, names: set[str]) -> str:
    text = _NRC_RE.sub("[NRC]", text or "")
    text = _DATE_RE.sub("[DATE]", text)
    for n in sorted(names, key=len, reverse=True):
        if len(n) > 2:
            text = re.sub(rf"\b{re.escape(n)}\b", "[NAME]", text, flags=re.I)
    return text


def case_facts(case: dict) -> dict:
    """Anonymised, model-ready summary of a case."""
    r = case["result"]
    f = r["extraction"]["fields"]
    ver, reg = r.get("verification", {}), r.get("registry") or {}
    names = set()
    for src in (f.get("full_name", {}).get("value"),
                *(ch.get(k) for ch in ver.get("checks", {}).values() for k in ("extracted", "record")),
                *(ch.get(k) for ch in reg.get("checks", {}).values() for k in ("submitted", "registry"))):
        if isinstance(src, str):
            names.update(t for t in re.split(r"\s+", src) if t.isalpha())
    low_conf = [FIELD.get(k, k.replace("_", " ")) for k, v in f.items()
                if v.get("value") and v.get("confidence", 1) < 0.8]
    unreadable = [FIELD[k] for k in ("nrc_number", "full_name", "date_of_birth") if not f.get(k, {}).get("value")]
    return {
        "risk": {"score": r["risk"]["score"], "band": r["risk"]["band"]},
        "card_vs_taxpayer_form": {"overall": ver.get("overall"),
                                  "fields": _compare(ver.get("checks", {}), "extracted", "record")},
        "card_vs_national_register": {
            "outcome": reg.get("outcome", "not_checked"), "found": reg.get("found"),
            "matched_by": reg.get("matched_by"), "card_status": reg.get("status"),
            "status_message": _redact(reg.get("status_message") or "", names) or None,
            "fields": _compare(reg.get("checks", {}), "submitted", "registry")},
        "flags": [{"code": fl["code"], "severity": fl["severity"], "title": fl["title"],
                   "message": _redact(fl["message"], names)} for fl in r.get("flags", [])],
        "tamper_signals": {FIELD[k]: {"probability": round(v.get("probability") or 0, 2),
                                      "reasons": v.get("reasons", [])}
                           for k, v in r.get("tamper", {}).items() if k in FIELD},
        "unreadable_key_fields": unreadable,
        "low_confidence_fields": low_conf,
        "document_warnings": [_redact(w, names) for w in r["extraction"].get("warnings", [])][:5],
    }


# ---- deterministic explainer (always available) -------------------------------------------------------------------
def rule_based(facts: dict) -> dict:
    reg = facts["card_vs_national_register"]
    form = facts["card_vs_taxpayer_form"]
    codes = {fl["code"] for fl in facts["flags"]}
    tamper = [k for k, v in facts["tamper_signals"].items() if v["probability"] >= 0.5]
    reasons, steps, questions = [], [], []
    action, conf = "approve", "high"

    def bad_fields(section):
        return [k for k, v in section["fields"].items() if str(v).startswith("mismatch")]

    reg_bad, form_bad = bad_fields(reg), bad_fields(form)
    if reg["outcome"] == "not_found":
        action, headline = "escalate", "This NRC number is not in the national register."
        reasons.append({"issue": "NRC not found in the register",
                        "meaning": "Either the number was misread, or the card is not a genuine registered NRC."})
        steps += ["Compare the NRC number on the card with the scan by eye.",
                  "If it was read correctly, escalate. A card whose number is not registered should not be accepted."]
    elif reg.get("card_status") in ("deceased", "revoked", "reported_lost"):
        action = "escalate"
        headline = f"The register shows this card as {reg['card_status'].replace('_', ' ')}."
        reasons.append({"issue": f"Card status: {reg['card_status'].replace('_', ' ')}",
                        "meaning": reg.get("status_message") or "The card should not be in active use."})
        steps += ["Do not complete the registration.", "Escalate to a supervisor with the register reference."]
        questions.append("Can you show another form of identification?")
    elif reg_bad and not form_bad and form["overall"] in ("match", "review"):
        action, headline = "escalate", "The card disagrees with the national register, but matches the form."
        reasons.append({"issue": "Card differs from the register on " + ", ".join(reg_bad),
                        "meaning": "The form was probably filled in from the card. If the card itself was changed, "
                                   "both would agree with each other but not with the register."})
        steps += ["Look closely at the highlighted parts of the card for signs of changes.",
                  "Escalate for investigation, attaching the register reference."]
    elif form_bad and not reg_bad and reg["outcome"] in ("match", "partial"):
        action, headline = "request_info", "The card is genuine per the register; the form has an error."
        reasons.append({"issue": "Form differs from the card on " + ", ".join(form_bad),
                        "meaning": "The card matches the national register, so the mistake is most likely a "
                                   "typing error on the registration form."})
        steps += ["Ask the taxpayer to confirm the correct details.", "Have the form corrected, then re-check."]
        questions.append(f"Can you confirm your {', '.join(form_bad)} as shown on your NRC?")
        conf = "medium"
    elif reg_bad and form_bad:
        action, headline = "escalate", "Details disagree with both the register and the form."
        reasons.append({"issue": "Several sources disagree",
                        "meaning": "The card, the form and the register do not agree. This needs a closer look."})
        steps.append("Escalate to a supervisor.")
    else:
        headline = "No serious problems found."
    if tamper:
        if action == "approve":
            action, headline = "escalate", "The card shows signs it may have been changed."
        reasons.append({"issue": "Possible changes to the card: " + ", ".join(tamper),
                        "meaning": "The model saw signs such as a different ink, font or a patched area. "
                                   "This is a hint to look closer, not proof."})
        steps.append("Zoom in on the highlighted fields and compare ink, font and alignment.")
    if "UNDERAGE_REGISTRATION" in codes:
        reasons.append({"issue": "Card issued before age 16",
                        "meaning": "NRCs are issued from age 16, so the date of birth or the issue date may be wrong."})
        if action == "approve":
            action = "escalate"
        steps.append("Check the date of birth and registration date on the card.")
    if {"NRC_CODE_DISTRICT", "DISTRICT_INCONSISTENT"} & codes:
        reasons.append({"issue": "District details don't agree",
                        "meaning": "The district code in the NRC number or the district fields are inconsistent."})
        if action == "approve":
            action = "request_info"
        steps.append("Ask the taxpayer where they were born and registered.")
    partial = reg["outcome"] == "partial" or form["overall"] == "review"
    if partial and action == "approve":
        action, conf = "request_info", "medium"
        headline = "Mostly matches, but something needs confirming."
        steps.append("Confirm the highlighted details with the taxpayer.")
    if facts["unreadable_key_fields"]:
        reasons.append({"issue": "Unreadable: " + ", ".join(facts["unreadable_key_fields"]),
                        "meaning": "SmartClear could not read these, so it did not guess."})
        steps.append("Read these fields from the card yourself, or ask for a clearer scan.")
        if action == "approve":
            action, conf = "request_info", "medium"
    if reg["outcome"] == "unavailable":
        steps.append("The national register could not be reached. Check the card manually or try again.")
        conf = "low"
    if action == "approve":
        steps = ["Glance over the card to confirm it looks right, then approve."]
    return {
        "headline": headline,
        "explanation": _summary(action, reasons),
        "reasons": reasons,
        "suggested_action": action,
        "next_steps": steps or ["Review the case and decide."],
        "questions_for_taxpayer": questions,
        "confidence": conf,
    }


def _summary(action, reasons):
    if not reasons:
        return ("The card matches the national register and the taxpayer's form, and no warning signs were found. "
                "You can approve it after a quick visual check.")
    return " ".join(r["meaning"] for r in reasons[:2]) + " " + {
        "approve": "Nothing here blocks approval.",
        "request_info": "Asking the taxpayer to confirm should resolve this.",
        "escalate": "This is worth a supervisor's attention before registration goes ahead.",
        "reject": "The evidence points against accepting this card.",
    }[action]


# ---- LLM explainer -------------------------------------------------------------------------------------------------
SYSTEM = """You are SmartClear's assistant for Zambia Revenue Authority (ZRA) registration officers.
An officer is checking a taxpayer's National Registration Card (NRC). You receive an ANONYMISED summary comparing:
(a) the card with the taxpayer's registration form, and (b) the card with the Ministry of Home Affairs national
register (the source of truth), plus automated warning flags and tamper signals.

Your job: explain in plain, friendly English (no jargon, no model names, no probabilities unless helpful) what the
results mean, and recommend ONE next step. Rules:
- You advise; the officer decides. Never say a person is a fraudster. Say "this needs a closer look", not "fraud".
- Base everything ONLY on the summary. Do not invent details. Values are redacted; refer to fields, not values.
- Key reasoning: if the card matches the register but not the form, the form likely has a typing error
  (request_info). If the card disagrees with the register, the card may have been changed or be fake (escalate).
  NRC not in register, or card status lost/revoked/deceased -> escalate. Everything matching with no warnings ->
  approve. Unreadable fields -> officer reads them / asks for a clearer scan.
- suggested_action must be one of: approve, request_info, escalate, reject. Prefer escalate over reject; reject
  only when the evidence is unambiguous.
Return ONLY a JSON object with exactly these keys:
{"headline": str (max 15 words), "explanation": str (2-4 short sentences),
 "reasons": [{"issue": str, "meaning": str}], "suggested_action": str,
 "next_steps": [str, ...] (2-4 concrete actions for the officer),
 "questions_for_taxpayer": [str, ...] (0-3 polite questions), "confidence": "low"|"medium"|"high"}"""


def _parse_json(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                return None
    return None


def _valid(d: dict | None) -> bool:
    return (isinstance(d, dict) and d.get("suggested_action") in ACTIONS
            and isinstance(d.get("headline"), str) and isinstance(d.get("explanation"), str)
            and isinstance(d.get("next_steps"), list) and d["next_steps"])


def call_llm(facts: dict, baseline: dict) -> tuple[dict | None, dict]:
    """Returns (parsed answer or None, call metadata). Tries each configured model in turn."""
    meta = {"attempts": []}
    if not GEMINI_API_KEY:
        meta["error"] = "no GEMINI_API_KEY configured"
        return None, meta
    user = ("Case summary (anonymised):\n" + json.dumps(facts, indent=1) +
            "\n\nThe rule-based checker suggests: " + baseline["suggested_action"] +
            ". You may disagree if the summary supports it.")
    deadline = time.perf_counter() + AI_BUDGET_S
    for model in GEMINI_MODELS:
        remaining = deadline - time.perf_counter()
        if remaining < 4:      # not enough time left for a useful answer: let the rules answer
            meta["attempts"].append({"model": model, "error": "skipped: time budget used up"})
            continue
        t0 = time.perf_counter()
        body = {"model": model, "temperature": 0.2, "max_tokens": 3000, "reasoning_effort": "low",
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}
        req = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {GEMINI_API_KEY}", "Content-Type": "application/json"})
        attempt = {"model": model}
        try:
            with urllib.request.urlopen(req, timeout=min(AI_TIMEOUT_S, remaining)) as r:
                data = json.loads(r.read())
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
            parsed = _parse_json(content)
            attempt["ms"] = round((time.perf_counter() - t0) * 1000)
            if _valid(parsed):
                attempt["ok"] = True
                meta["attempts"].append(attempt)
                meta["model"] = data.get("model", model)
                return parsed, meta
            attempt["error"] = "unusable response"
        except urllib.error.HTTPError as e:
            attempt["error"] = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            attempt["error"] = type(e).__name__
        meta["attempts"].append(attempt)
    return None, meta


def explain(case: dict, use_llm: bool = True) -> dict:
    facts = case_facts(case)
    baseline = rule_based(facts)
    out, meta = (call_llm(facts, baseline) if use_llm else (None, {"attempts": []}))
    if out:
        out = {k: out.get(k) for k in ("headline", "explanation", "reasons", "suggested_action", "next_steps",
                                       "questions_for_taxpayer", "confidence")}
        out["reasons"] = [x for x in (out.get("reasons") or []) if isinstance(x, dict)]
        out["questions_for_taxpayer"] = [q for q in (out.get("questions_for_taxpayer") or []) if isinstance(q, str)]
        if out.get("confidence") not in ("low", "medium", "high"):
            out["confidence"] = "medium"
        source = "ai"
    else:
        out, source = baseline, "rules"
    out.update({
        "source": source,
        "model": meta.get("model"),
        "rule_based_action": baseline["suggested_action"],
        "agrees_with_rules": out["suggested_action"] == baseline["suggested_action"],
        "suggested_action_label": ACTIONS[out["suggested_action"]],
        "attempts": meta.get("attempts", []),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "human_in_the_loop": "Suggestion only. The officer makes and records the decision.",
        "data_shared": "Anonymised summary only: no names, NRC numbers or dates of birth were sent.",
    })
    return out

"""Verification flow: send extracted applicant data to the MoHA ground-truth API and fold the answer into the case.

The registry's answer becomes ``result["registry"]`` and, where it disagrees with the card, explainable flags that
raise the risk score. Nothing is decided automatically: a registry mismatch is evidence for the officer.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from . import flags as F
from . import registry
from .config import MOHA_API_KEY, MOHA_API_URL, MOHA_TIMEOUT_S

LABEL = {**F.FIELD_LABEL, "sex": "Sex", "card_number": "Card number", "district": "District"}
_PAYLOAD_FIELDS = ("nrc_number", "full_name", "date_of_birth", "sex", "card_number", "district")


def lookup(fields: dict) -> dict:
    """Call the registry with the extracted values. Never raises: failures come back as outcome 'unavailable'."""
    payload = {k: fields.get(k) for k in _PAYLOAD_FIELDS}
    t0 = time.perf_counter()
    try:
        if MOHA_API_URL:
            req = urllib.request.Request(f"{MOHA_API_URL}/verify", data=json.dumps(payload).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "X-API-Key": MOHA_API_KEY})
            with urllib.request.urlopen(req, timeout=MOHA_TIMEOUT_S) as r:
                res = json.loads(r.read())
            transport = "http"
        else:
            res = registry.verify_identity(payload, client="smartclear:in-process")
            transport = "in-process"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        res = {"found": False, "outcome": "unavailable", "checks": {},
               "message": f"National register could not be reached ({type(e).__name__}). Verify the card manually."}
        transport = "http" if MOHA_API_URL else "in-process"
    res["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    res["transport"] = transport
    res["source"] = "Ministry of Home Affairs — National Registration (sandbox)"
    return res


def registry_flags(reg: dict) -> list[dict]:
    out = []
    o = reg.get("outcome")
    if o == "unavailable":
        out.append(F._flag("REGISTRY_UNAVAILABLE", "low", "National register not reached",
                           reg.get("message", "Verify the card manually."), None))
        return out
    if o == "not_found":
        out.append(F._flag("REGISTRY_NOT_FOUND", "high", "NRC not in national register",
                           reg.get("message", "No citizen with this NRC number exists in the register."), "nrc_number"))
        return out
    if reg.get("status") and reg["status"] != "active":
        sev = "medium" if reg["status"] == "replaced" else "high"
        out.append(F._flag("REGISTRY_STATUS", sev, f"Register status: {reg['status'].replace('_', ' ')}",
                           " ".join(x for x in (reg.get("status_message"), reg.get("status_note")) if x), "nrc_number",
                           {"status": reg["status"]}))
    checks = reg.get("checks", {})
    bad = [k for k, ch in checks.items() if ch["outcome"] == "mismatch" and k != "district"]
    if bad:
        out.append(F._flag("REGISTRY_MISMATCH", "high", "Card doesn't match national register",
                           "Differs from the register on: " + ", ".join(LABEL.get(k, k) for k in bad) + ".", bad[0],
                           {k: {"card": checks[k]["submitted"], "registry": checks[k]["registry"]} for k in bad}))
    if checks.get("district", {}).get("outcome") == "mismatch":
        # medium: the district is printed faintly and OCR misreads it more often than the key fields
        d = checks["district"]
        out.append(F._flag("REGISTRY_DISTRICT", "medium", "District differs from register",
                           f"The card reads {d['submitted']}; the register records {d['registry']}.", "district"))
    partial = [k for k, ch in checks.items() if ch["outcome"] == "partial"]
    if partial:
        out.append(F._flag("REGISTRY_PARTIAL", "medium", "Name differs slightly from register",
                           checks[partial[0]].get("detail") or "Confirm the name with the taxpayer.", partial[0]))
    if reg.get("matched_by") == "name_and_date_of_birth":
        out.append(F._flag("REGISTRY_MATCHED_BY_NAME", "low", "Found in register by name and date of birth",
                           f"The NRC number could not be read; the register lists NRC {checks['nrc_number']['registry']} "
                           "for this person. Compare it with the card.", "nrc_number"))
    return out


def apply(result: dict) -> dict:
    """Run the registry check for a processed document and update flags + risk in place."""
    fields = {k: v["value"] for k, v in result["extraction"]["fields"].items()}
    reg = lookup(fields)
    result["registry"] = reg
    result["flags"] = [f for f in result["flags"] if not f["code"].startswith("REGISTRY_")] + registry_flags(reg)
    order = {"high": 0, "medium": 1, "low": 2}
    result["flags"].sort(key=lambda f: order[f["severity"]])
    result["risk"] = F.risk(result["flags"], result["verification"], result["tamper"])
    return result

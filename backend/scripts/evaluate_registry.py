"""Evaluate the MoHA registry verification flow on the labelled synthetic set.

Uses the cases already in the database (their extracted fields), re-runs the registry check and compares the outcome
with the facilitators' fraud labels. Writes models/registry_evaluation.json (shown on the Model performance page).
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smartclear import db, moha_client  # noqa: E402
from smartclear.config import GROUND_TRUTH_CSV, MODELS_DIR  # noqa: E402

if __name__ == "__main__":
    gt = {r["file"]: r for r in csv.DictReader(open(GROUND_TRUTH_CSV))}
    tp = fp = fn = tn = 0
    by_type = defaultdict(lambda: {"caught": 0, "total": 0})
    outcomes, latencies, false_alarms = Counter(), [], []
    with db.conn() as c:
        rows = c.execute("SELECT filename, result FROM cases").fetchall()
    seen = set()
    for r in rows:
        g = gt.get(r["filename"])
        if not g or r["filename"] in seen:   # count each labelled document once
            continue
        seen.add(r["filename"])
        fields = {k: v["value"] for k, v in json.loads(r["result"])["extraction"]["fields"].items()}
        reg = moha_client.lookup(fields)
        latencies.append(reg["latency_ms"])
        outcomes[reg["outcome"]] += 1
        flagged = bool([f for f in moha_client.registry_flags(reg) if f["severity"] in ("high", "medium")])
        fraud = g["is_fraud"] == "1"
        tp += flagged and fraud
        fp += flagged and not fraud
        fn += fraud and not flagged
        tn += not fraud and not flagged
        if flagged and not fraud:
            false_alarms.append({"doc": g["doc_id"], "outcome": reg["outcome"]})
        for t in filter(None, g["fraud_types"].split(";")):
            by_type[t]["total"] += 1
            by_type[t]["caught"] += flagged
    latencies.sort()
    out = {
        "documents": tp + fp + fn + tn,
        "recall": round(tp / max(1, tp + fn), 4), "precision": round(tp / max(1, tp + fp), 4),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "by_fraud_type": dict(by_type), "outcomes": dict(outcomes), "false_alarms": false_alarms,
        "latency_ms": {"median": latencies[len(latencies) // 2] if latencies else None,
                       "p90": latencies[int(len(latencies) * 0.9)] if latencies else None},
        "note": "Registry check alone (high/medium registry flags), on the synthetic set. Underage registration is a "
                "property of a genuine registered card and is caught by the rules, not the registry.",
    }
    (MODELS_DIR / "registry_evaluation.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: out[k] for k in ("recall", "precision", "tp", "fp", "fn", "by_fraud_type", "outcomes",
                                          "latency_ms")}, indent=1))

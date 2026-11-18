"""Evaluate SmartClear against the three success measures in the ZRA Challenge Brief.

1. Extraction accuracy   — extracted fields vs the manually verified reading (data/ground_truth.csv)
2. Verification accuracy — automated match/review/mismatch vs expected outcome (data/taxpayer_records.csv)
3. Fraud-flagging        — document flags vs the labelled fraudulent set. Tamper-model scores are the
                           out-of-fold cross-validated scores, so documents are never scored by a model
                           that saw them during training.
Plus a robustness check: extraction on perturbed copies (rotation, shift, JPEG, noise) of a sample.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from smartclear import db  # noqa: E402
from smartclear.config import DATA_DIR, MODELS_DIR, SYNTHETIC_PDF_DIR, TAMPER_FIELD_THRESHOLD  # noqa: E402
from smartclear.document import load_document  # noqa: E402
from smartclear.extraction import extract  # noqa: E402
from smartclear.verify import norm_name  # noqa: E402

FIELDS = ["nrc_number", "full_name", "date_of_birth", "card_number", "sex", "place_of_birth_village",
          "place_of_birth_district", "village", "district", "chief", "registration_date", "special_marks"]
KEY = ["nrc_number", "full_name", "date_of_birth"]


def norm(f, v):
    v = (v or "").strip().upper()
    return norm_name(v) if f in ("full_name",) else v.replace(" ", "")


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
            "tp": tp, "fp": fp, "fn": fn}


def main(robust_n=20):
    gt = {r["doc_id"]: r for r in csv.DictReader(open(DATA_DIR / "ground_truth.csv"))}
    recs = {r["source_doc"]: r for r in csv.DictReader(open(DATA_DIR / "taxpayer_records.csv"))}
    tm = json.loads((MODELS_DIR / "tamper_metrics.json").read_text())
    oof = tm["oof_scores"]
    with db.conn() as c:
        cases = [db.case_row(r) for r in c.execute("SELECT * FROM cases WHERE ref LIKE 'SC-0%' OR ref LIKE 'SC-1%' "
                                                    "OR ref LIKE 'SC-2%'")]
    by_doc = {"NRC-SYN-" + c["ref"][3:]: c for c in cases}

    # ---- 1. Extraction
    ext = {f: {"correct": 0, "total": 0, "errors": []} for f in FIELDS}
    unreadable_expected = {"correct": 0, "total": 0}
    for doc, g in gt.items():
        res = by_doc[doc]["result"]["extraction"]["fields"]
        for f in FIELDS:
            truth, got = norm(f, g[f]), norm(f, res[f]["value"])
            if f in KEY and g["tampered_field"] == f and g["tamper_technique"] == "blur_erasure":
                unreadable_expected["total"] += 1
                unreadable_expected["correct"] += int(got == "" or res[f]["confidence"] < 0.8)
                continue
            ext[f]["total"] += 1
            if truth == got:
                ext[f]["correct"] += 1
            else:
                ext[f]["errors"].append({
                    "doc": doc,
                    "expected": g[f],
                    "got": res[f]["value"],
                    "raw": res[f].get("raw", ""),
                    "confidence": res[f].get("confidence", 0.0),
                    "status": res[f].get("status", "unknown"),
                    "bbox": res[f].get("bbox"),
                })
    extraction = {f: {"accuracy": round(v["correct"] / v["total"], 4), "n": v["total"], "errors": v["errors"]}
                  for f, v in ext.items()}
    key_correct = sum(ext[f]["correct"] for f in KEY)
    key_total = sum(ext[f]["total"] for f in KEY)
    docs_all_key = sum(1 for doc, g in gt.items() if all(
        norm(f, g[f]) == norm(f, by_doc[doc]["result"]["extraction"]["fields"][f]["value"])
        for f in KEY if not (g["tampered_field"] == f and g["tamper_technique"] == "blur_erasure")))

    # ---- 2. Verification
    conf = {}
    correct = 0
    for doc, g in gt.items():
        exp = recs[g["file"]]["expected_outcome"]
        got = by_doc[doc]["result"]["verification"]["overall"]
        conf.setdefault(exp, {}).setdefault(got, 0)
        conf[exp][got] += 1
        correct += int(exp == got)
    mm_tp = sum(1 for d, g in gt.items() if recs[g["file"]]["expected_outcome"] == "mismatch"
                and by_doc[d]["result"]["verification"]["overall"] == "mismatch")
    mm_fp = sum(1 for d, g in gt.items() if recs[g["file"]]["expected_outcome"] != "mismatch"
                and by_doc[d]["result"]["verification"]["overall"] == "mismatch")
    mm_fn = sum(1 for d, g in gt.items() if recs[g["file"]]["expected_outcome"] == "mismatch"
                and by_doc[d]["result"]["verification"]["overall"] != "mismatch")
    verification = {"accuracy": round(correct / len(gt), 4), "confusion": conf, "mismatch_detection": prf(mm_tp, mm_fp, mm_fn)}

    # ---- 3. Fraud flagging (document level) — rule flags + OUT-OF-FOLD tamper scores
    def doc_flagged(doc, use_oof=True):
        r = by_doc[doc]["result"]
        rule = [f for f in r["flags"] if f["code"] not in ("TAMPER_SUSPECTED", "RECORD_MISMATCH", "LOW_OCR_CONFIDENCE")
                and f["severity"] in ("high", "medium")]
        tam = any(oof.get(f"{doc}:{f}", 0) >= TAMPER_FIELD_THRESHOLD for f in KEY) if use_oof else \
            any(f["code"] == "TAMPER_SUSPECTED" for f in r["flags"])
        return bool(rule) or tam, [f["code"] for f in rule] + (["TAMPER_SUSPECTED"] if tam else [])

    tp = fp = fn = 0
    per_type = {}
    fps, fns = [], []
    for doc, g in gt.items():
        flagged, codes = doc_flagged(doc)
        y = g["is_fraud"] == "1"
        tp += flagged and y
        fp += flagged and not y
        fn += (not flagged) and y
        if flagged and not y:
            fps.append({"doc": doc, "flags": codes})
        if y and not flagged:
            fns.append({"doc": doc, "types": g["fraud_types"]})
        for t in filter(None, g["fraud_types"].split(";")):
            per_type.setdefault(t, {"caught": 0, "total": 0})
            per_type[t]["total"] += 1
            per_type[t]["caught"] += int(flagged)
    band_counts = {}
    for doc, g in gt.items():
        b = by_doc[doc]["result"]["risk"]["band"]
        band_counts.setdefault("fraud" if g["is_fraud"] == "1" else "genuine", {}).setdefault(b, 0)
        band_counts["fraud" if g["is_fraud"] == "1" else "genuine"][b] += 1
    flagging = {**prf(tp, fp, fn), "by_fraud_type": per_type, "false_positives": fps, "missed": fns,
                "risk_band_distribution_as_deployed": band_counts,
                "note": "Tamper-model contribution uses 5-fold out-of-fold scores (document-grouped)."}

    # ---- 4. Robustness: perturbed scans
    rng = np.random.default_rng(0)
    pdfs = sorted(Path(SYNTHETIC_PDF_DIR).glob("*.pdf"))
    sample = [pdfs[i] for i in rng.choice(len(pdfs), size=min(robust_n, len(pdfs)), replace=False)]
    rob = {"correct": 0, "total": 0, "errors": []}
    for p in sample:
        img = load_document(p.read_bytes(), p.name)
        H, W = img.shape[:2]
        ang = rng.uniform(-3, 3)
        M = cv2.getRotationMatrix2D((W / 2, H / 2), ang, rng.uniform(0.95, 1.05))
        M[:, 2] += rng.uniform(-15, 15, 2)
        pert = cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_REPLICATE)
        pert = np.clip(pert + rng.normal(0, 3, pert.shape), 0, 255).astype(np.uint8)
        pert = cv2.imdecode(cv2.imencode(".jpg", pert, [cv2.IMWRITE_JPEG_QUALITY, 70])[1], cv2.IMREAD_COLOR)
        ex = extract(pert)
        g = gt[p.stem.upper()]
        for f in KEY:
            if g["tampered_field"] == f and g["tamper_technique"] == "blur_erasure":
                continue
            rob["total"] += 1
            ok = norm(f, g[f]) == norm(f, ex.value(f))
            rob["correct"] += ok
            if not ok:
                rob["errors"].append({"doc": p.stem, "field": f, "expected": g[f], "got": ex.value(f),
                                      "rotation_deg": round(ang, 2)})
        print(f"  robustness {p.stem} rot={ang:+.1f}", flush=True)
    robustness = {"key_field_accuracy": round(rob["correct"] / rob["total"], 4), "n_docs": len(sample),
                  "perturbation": "rotation ±3°, scale ±5%, shift ±15px, Gaussian noise σ=3, JPEG q70",
                  "errors": rob["errors"][:10]}

    times = [c["result"]["timing_ms"]["total"] for c in cases]
    out = {
        "dataset": {"documents": len(gt), "fraudulent": sum(g["is_fraud"] == "1" for g in gt.values())},
        "extraction": {"key_fields_accuracy": round(key_correct / key_total, 4),
                       "documents_all_key_fields_correct": round(docs_all_key / len(gt), 4),
                       "erased_fields_correctly_reported_unreadable": unreadable_expected,
                       "per_field": extraction},
        "verification": verification,
        "fraud_flagging": flagging,
        "robustness": robustness,
        "processing_time_ms": {"median": float(np.median(times)), "p90": float(np.percentile(times, 90))},
        "tamper_model_cv": {k: tm[k] for k in ("cv_synthetic_plus_real", "cv_synthetic_only")},
    }
    (MODELS_DIR / "evaluation.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: out[k] for k in ("dataset", "processing_time_ms")}, indent=1))
    print("extraction key-field accuracy:", out["extraction"]["key_fields_accuracy"],
          "| docs all key correct:", out["extraction"]["documents_all_key_fields_correct"])
    print("per field:", {f: v["accuracy"] for f, v in extraction.items()})
    print("verification:", json.dumps(verification))
    print("flagging:", {k: flagging[k] for k in ("precision", "recall", "f1", "tp", "fp", "fn")})
    print("by type:", per_type, "FP:", fps, "missed:", fns)
    print("robustness:", robustness["key_field_accuracy"], robustness["errors"][:5])


if __name__ == "__main__":
    main()

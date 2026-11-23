"""Compare the stock and fine-tuned (onnx) text recognizers side by side.

Two tests, both on synthetic data only:

1. Whole card: the 100 synthetic NRC PDFs supplied by the facilitators (data/synthetic_nrc/),
   run through the same page preparation and pipeline the API uses, scored per field against
   data/ground_truth.csv with the same normalisation as scripts/evaluate.py. The fine-tuned
   recognizer was not trained on these cards. Fields that were deliberately blurred/erased
   (blur_erasure tampers) are left out, as in evaluate.py.
2. Single crops: the held-out test crops in data/ocr_rec/test (12 identities never used for
   training), read by the recognizer alone. Skipped if data/ocr_rec is not present locally.

The OCR result cache is bypassed so each reader is measured fresh.

Run from the project root:
    .venv/Scripts/python backend/scripts/compare_readers.py            # both tests
    .venv/Scripts/python backend/scripts/compare_readers.py --limit 10 # quick check
Writes docs/metrics/reader_comparison.json and prints a summary table.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402

from smartclear import cache as _cache  # noqa: E402
from smartclear.config import DATA_DIR, OCR_READERS, ROOT, SYNTHETIC_PDF_DIR  # noqa: E402
from smartclear.document import prepare_document_pages  # noqa: E402
from smartclear.extraction import get_engine  # noqa: E402
from smartclear.pipeline import process_pages  # noqa: E402
from smartclear.verify import norm_name  # noqa: E402

FIELDS = ["nrc_number", "full_name", "date_of_birth", "card_number", "sex", "place_of_birth_village",
          "place_of_birth_district", "village", "district", "chief", "registration_date", "special_marks"]
KEY = ["nrc_number", "full_name", "date_of_birth"]
OUT = ROOT / "docs" / "metrics" / "reader_comparison.json"

# Measure fresh: never read or write the OCR result cache during the comparison.
_cache.load = lambda key: (None, None)
_cache.store = lambda key, payload, disp: None


def norm(field: str, value: str | None) -> str:
    """Same normalisation as scripts/evaluate.py."""
    v = (value or "").strip().upper()
    return norm_name(v) if field == "full_name" else v.replace(" ", "")


def set_reader(reader: str) -> None:
    os.environ["SMARTCLEAR_OCR_READER"] = reader


def whole_card(reader: str, limit: int | None) -> dict:
    set_reader(reader)
    gt = list(csv.DictReader(open(DATA_DIR / "ground_truth.csv", encoding="utf-8")))[:limit]
    per_field = {f: {"correct": 0, "total": 0, "errors": []} for f in FIELDS}
    docs_all_key = 0
    seconds = []
    for g in gt:
        pdf = SYNTHETIC_PDF_DIR / g["file"]
        t0 = time.time()
        images, _ = prepare_document_pages(pdf.read_bytes(), pdf.name)
        result, _, _ = process_pages(images, None, None)
        seconds.append(time.time() - t0)
        fields = result["extraction"]["fields"]
        all_key = True
        for f in FIELDS:
            if f in KEY and g["tampered_field"] == f and g["tamper_technique"] == "blur_erasure":
                continue  # deliberately unreadable: not an extraction target
            got = (fields.get(f) or {}).get("value")
            ok = norm(f, g[f]) == norm(f, got)
            per_field[f]["total"] += 1
            per_field[f]["correct"] += ok
            if not ok:
                if f in KEY:
                    all_key = False
                if len(per_field[f]["errors"]) < 5:
                    per_field[f]["errors"].append({"doc": g["doc_id"], "expected": g[f], "got": got})
        docs_all_key += all_key
        print(f"  [{reader}] {g['doc_id']} {seconds[-1]:.1f}s", flush=True)
    key_c = sum(per_field[f]["correct"] for f in KEY)
    key_t = sum(per_field[f]["total"] for f in KEY)
    all_c = sum(v["correct"] for v in per_field.values())
    all_t = sum(v["total"] for v in per_field.values())
    return {
        "documents": len(gt),
        "key_fields_accuracy": round(key_c / key_t, 4) if key_t else None,
        "all_fields_accuracy": round(all_c / all_t, 4) if all_t else None,
        "docs_all_key_fields_correct": docs_all_key,
        "per_field": {f: {"accuracy": round(v["correct"] / v["total"], 4) if v["total"] else None,
                          "correct": v["correct"], "n": v["total"], "errors": v["errors"]}
                      for f, v in per_field.items()},
        "median_seconds_per_doc": round(sorted(seconds)[len(seconds) // 2], 2) if seconds else None,
    }


def crops(reader: str) -> dict | None:
    base = DATA_DIR / "ocr_rec"
    label_file = base / "test.txt"
    if not label_file.exists():
        return None
    set_reader(reader)
    engine = get_engine()
    by_source = defaultdict(lambda: {"exact": 0, "no_space": 0, "n": 0})
    errors = []
    for line in label_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rel, truth = line.split("\t", 1)
        img = cv2.imread(str(base / rel))
        res, _ = engine(img, use_det=False, use_cls=False)
        got = str(res[0][0]).strip() if res else ""
        source = rel.split("/")[1]
        for key in (source, "all"):
            s = by_source[key]
            s["n"] += 1
            s["exact"] += got == truth
            s["no_space"] += got.replace(" ", "") == truth.replace(" ", "")
        if got != truth and len(errors) < 10:
            errors.append({"crop": rel, "expected": truth, "got": got})
    return {
        "by_source": {k: {"n": v["n"], "exact": round(v["exact"] / v["n"], 4),
                          "ignoring_spaces": round(v["no_space"] / v["n"], 4)} for k, v in by_source.items()},
        "errors": errors,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="only the first N documents (quick check)")
    ap.add_argument("--skip-cards", action="store_true", help="run the crop test only")
    args = ap.parse_args()

    report = {"note": "Synthetic data only. Real NRC cards have not been measured.", "readers": {}}
    for reader in OCR_READERS:
        print(f"== {reader}", flush=True)
        report["readers"][reader] = {
            "crops": crops(reader),
            "whole_card": None if args.skip_cards else whole_card(reader, args.limit),
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nmetric".ljust(44) + "".join(r.rjust(10) for r in OCR_READERS))
    rows = []
    if not args.skip_cards:
        rows += [("whole card: key fields (NRC, name, DOB)", lambda r: r["whole_card"]["key_fields_accuracy"]),
                 ("whole card: all 12 fields", lambda r: r["whole_card"]["all_fields_accuracy"])]
        rows += [(f"  {f}", (lambda f: lambda r: r["whole_card"]["per_field"][f]["accuracy"])(f)) for f in FIELDS]
    if report["readers"]["stock"]["crops"]:
        rows += [("crops: exact (all)", lambda r: r["crops"]["by_source"]["all"]["exact"]),
                 ("crops: ignoring spaces (all)", lambda r: r["crops"]["by_source"]["all"]["ignoring_spaces"])]
        for src in ("clean", "flatbed", "phone", "photocopy"):
            rows.append((f"  crops {src}, ignoring spaces",
                         (lambda s: lambda r: r["crops"]["by_source"].get(s, {}).get("ignoring_spaces"))(src)))
    for label, get in rows:
        vals = []
        for reader in OCR_READERS:
            v = get(report["readers"][reader])
            vals.append("-" if v is None else f"{v:.1%}")
        print(label.ljust(44) + "".join(v.rjust(10) for v in vals))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()

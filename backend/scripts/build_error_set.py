"""Build a synthetic-only field error set with source crops for manual review.

Run after refreshing models/evaluation.json with backend/scripts/evaluate.py.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
from smartclear.config import DATA_DIR, MODELS_DIR, STORAGE_DIR
from smartclear.document import load_document
from smartclear.extraction import extract

OUT = STORAGE_DIR / "error_review"
FIELDS = {
    "nrc_number": "NRC number", "full_name": "Full name", "date_of_birth": "Date of birth",
    "card_number": "Card number", "sex": "Sex", "place_of_birth_village": "Birth village",
    "place_of_birth_district": "Birth district", "parent_place_of_birth": "Parent place of birth",
    "village": "Village", "district": "District", "chief": "Chief",
    "registration_date": "Registration date", "special_marks": "Special marks",
}

def main() -> None:
    report = json.loads((MODELS_DIR / "evaluation.json").read_text(encoding="utf-8"))
    with (DATA_DIR / "ground_truth.csv").open(encoding="utf-8", newline="") as stream:
        truth = {row["doc_id"]: row for row in csv.DictReader(stream)}
    errors = [
        {"field": field, **item}
        for field, metrics in report["extraction"]["per_field"].items()
        for item in metrics.get("errors", [])
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    rows, cache = [], {}
    for index, item in enumerate(errors, 1):
        doc_id, field = item["doc"], item["field"]
        source = DATA_DIR / "synthetic_nrc" / (doc_id.lower() + ".pdf")
        if not source.exists():
            continue
        if doc_id not in cache:
            image = load_document(source.read_bytes(), source.name)
            cache[doc_id] = (image, extract(image, force_crop=True))
        image, extraction = cache[doc_id]
        field_result = extraction.fields.get(field)
        box = field_result.bbox if field_result else None
        if box:
            height, width = image.shape[:2]
            x0, y0, x1, y1 = box
            px, py = max(24, int((x1 - x0) * 0.6)), max(18, int((y1 - y0) * 1.0))
            crop = image[max(0, y0 - py):min(height, y1 + py),
                         max(0, x0 - px):min(width, x1 + px)]
        else:
            crop = image
        crop_name = f"{index:03d}_{doc_id}_{field}.png"
        cv2.imwrite(str(OUT / crop_name), crop)
        expected = item.get("expected", truth.get(doc_id, {}).get(field))
        rows.append({
            "doc_id": doc_id, "field": field, "field_label": FIELDS.get(field, field),
            "expected": expected, "extracted": item.get("got"),
            "evaluation_raw_ocr": item.get("raw"),
            "evaluation_confidence": item.get("confidence"),
            "evaluation_status": item.get("status", "unknown"),
            "replay_extracted": field_result.value if field_result else None,
            "replay_raw_ocr": field_result.raw if field_result else "",
            "replay_confidence": field_result.confidence if field_result else 0.0,
            "replay_status": field_result.to_dict().get("status") if field_result else "unreadable",
            "replay_reason": field_result.status_reason if field_result else None,
            "replay_alternatives": field_result.alternatives if field_result else [],
            "evidence_crop": crop_name,
        })
    manifest = {
        "source": "Synthetic NRC cards only", "count": len(rows),
        "note": "Classify each error as OCR, crop/layout, field assignment, or normalization.",
        "errors": rows,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} synthetic field-error cases to {OUT}")

if __name__ == "__main__":
    main()

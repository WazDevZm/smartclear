"""Run extraction over the synthetic NRC PDFs once and cache the results.

Outputs, per document, to storage/cache/docs/:
  <DOC>.png   deskewed card image
  <DOC>.json  extracted fields, forensic boxes, OCR tokens, timing
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402

from smartclear.config import STORAGE_DIR, SYNTHETIC_PDF_DIR  # noqa: E402
from smartclear.document import load_document  # noqa: E402
from smartclear.extraction import Token, extract, run_ocr  # noqa: E402

CACHE = STORAGE_DIR / "cache" / "docs"


def process(pdf: Path, force=False) -> dict:
    doc = pdf.stem.upper()
    js = CACHE / f"{doc}.json"
    if js.exists() and not force:
        return json.loads(js.read_text())
    img = load_document(pdf.read_bytes(), pdf.name)
    t0 = time.time()
    toks = run_ocr(img)
    ex = extract(img, toks)
    rec = {
        "doc_id": doc,
        "file": pdf.name,
        "extraction": ex.to_dict(),
        "forensic_boxes": ex.forensic_boxes,
        "tokens": [[t.quad.tolist(), t.text, t.conf] for t in toks],
        "seconds": round(time.time() - t0, 3),
    }
    cv2.imwrite(str(CACHE / f"{doc}.png"), ex.deskewed if ex.deskewed is not None else img)
    js.write_text(json.dumps(rec))
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(SYNTHETIC_PDF_DIR))
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(Path(a.src).glob("*.pdf"))
    for i, p in enumerate(pdfs, 1):
        r = process(p, a.force)
        f = r["extraction"]["fields"]
        print(f"[{i:3d}/{len(pdfs)}] {r['doc_id']}  {f['nrc_number']['value']}  {f['full_name']['value']}  "
              f"{f['date_of_birth']['value']}  ({r['seconds']}s)", flush=True)


if __name__ == "__main__":
    main()

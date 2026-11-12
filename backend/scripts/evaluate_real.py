"""Per-field extraction accuracy on hand-labelled REAL NRC scans.

Real NRCs are personal data: keep them only in ``data/real_nrc/`` (git-ignored) on approved machines.

Layout:
  data/real_nrc/<scan>.pdf|.png|.jpg   one scan per card (front, or front + back pages)
  data/real_nrc/labels.csv             one row per scan, verified by a person against the card

labels.csv columns: file, then any of the field names below. In a field cell:
  * the value printed on the card (dates as dd.mm.yy, NRC as NNNNNN/NN/N, card no. as Z########)
  * EMPTY  if the card genuinely has nothing there (the extractor should return no value)
  * blank  if not labelled; the field is not scored for that card

Run:  python backend/scripts/evaluate_real.py            (creates a labels template if none exists)
Writes data/real_nrc/results.json and prints per-field accuracy with 95% Wilson intervals, the
character error rate, and which errors were blanks vs wrong values.
"""
from __future__ import annotations

import csv
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rapidfuzz.distance import Levenshtein  # noqa: E402

from smartclear.config import DATA_DIR  # noqa: E402
from smartclear.document import prepare_document_pages  # noqa: E402
from smartclear.gazetteer import canonical  # noqa: E402
from smartclear.pipeline import process_pages  # noqa: E402

REAL_DIR = DATA_DIR / "real_nrc"
LABELS = REAL_DIR / "labels.csv"
FIELDS = ["nrc_number", "card_number", "full_name", "date_of_birth", "sex", "place_of_birth_village",
          "place_of_birth_district", "parent_place_of_birth", "village", "district", "chief",
          "registration_date", "special_marks"]
KEY_FIELDS = {"nrc_number", "full_name", "date_of_birth"}
SCANS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def norm(field: str, value: str | None) -> str:
    v = " ".join((value or "").upper().split())
    if field in ("district", "place_of_birth_district"):
        return canonical(v) or v
    return v


def write_template():
    REAL_DIR.mkdir(parents=True, exist_ok=True)
    scans = sorted(p.name for p in REAL_DIR.iterdir() if p.suffix.lower() in SCANS)
    with open(LABELS, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", *FIELDS])
        for s in scans:
            w.writerow([s] + [""] * len(FIELDS))
    print(f"Created {LABELS} with {len(scans)} scan(s). Fill in the values printed on each card "
          f"(EMPTY for a blank field) and run again.")


def main():
    if not LABELS.exists():
        write_template()
        return
    rows = list(csv.DictReader(open(LABELS, newline="", encoding="utf-8-sig")))
    stats = {f: {"n": 0, "ok": 0, "blank": 0, "wrong": 0, "hallucinated": 0, "edits": 0, "chars": 0}
             for f in FIELDS}
    per_card, times = [], []
    for row in rows:
        path = REAL_DIR / row["file"]
        if not path.exists():
            print(f"!! missing scan {row['file']}")
            continue
        t0 = time.time()
        images, _ = prepare_document_pages(path.read_bytes(), path.name)
        result, _, _ = process_pages(images)
        times.append(time.time() - t0)
        got = {k: v["value"] for k, v in result["extraction"]["fields"].items()}
        errors = {}
        for f in FIELDS:
            truth = (row.get(f) or "").strip()
            if not truth:
                continue
            s = stats[f]
            s["n"] += 1
            want = "" if truth.upper() == "EMPTY" else norm(f, truth)
            have = norm(f, got.get(f))
            if have == want:
                s["ok"] += 1
                continue
            errors[f] = {"expected": want or None, "extracted": have or None}
            if not have:
                s["blank"] += 1
            elif not want:
                s["hallucinated"] += 1
            else:
                s["wrong"] += 1
            if want:
                s["edits"] += Levenshtein.distance(have, want)
                s["chars"] += len(want)
        per_card.append({"file": row["file"], "errors": errors, "seconds": round(times[-1], 2),
                         "risk": result["risk"]["band"], "warnings": result["extraction"]["warnings"]})
        print(f"{row['file']}: {len(errors)} field error(s) {sorted(errors)}")

    print(f"\n{'field':26s} {'acc':>6s} {'95% CI':>13s}  n   blank wrong extra  CER")
    total_ok = total_n = 0
    for f in FIELDS:
        s = stats[f]
        if not s["n"]:
            continue
        lo, hi = wilson(s["ok"], s["n"])
        cer = s["edits"] / s["chars"] if s["chars"] else 0.0
        total_ok += s["ok"]
        total_n += s["n"]
        mark = "*" if f in KEY_FIELDS else " "
        print(f"{mark}{f:25s} {s['ok'] / s['n']:6.1%} [{lo:5.1%},{hi:5.1%}] {s['n']:3d} {s['blank']:5d} "
              f"{s['wrong']:5d} {s['hallucinated']:5d} {cer:5.1%}")
    if total_n:
        print(f"\nAll labelled fields: {total_ok}/{total_n} = {total_ok / total_n:.1%}   (* = key field)")
    if times:
        print(f"Median processing time: {sorted(times)[len(times) // 2]:.1f}s over {len(times)} scan(s)")
    out = {"cards": per_card, "fields": stats}
    (REAL_DIR / "results.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()

"""Evaluate extraction on *real* scanned NRCs — the counterpart to evaluate.py.

Real NRCs are personal data: keep them only in a git-ignored folder (data/real_nrc/ or data/real/)
on approved machines, e.g. inside the ZRA sandbox.

Two modes:

1. Labelled set (per-field accuracy):
       python backend/scripts/evaluate_real.py                # uses data/real_nrc/
       python backend/scripts/evaluate_real.py --dir data/real
   The folder holds the scans plus labels.csv (created as a template on the first run):
   columns file + any field names below. In a field cell write the value printed on the card
   (dates dd.mm.yy, NRC NNNNNN/NN/N, card no. Z########), EMPTY if the card has nothing there,
   or leave it blank to skip scoring it. Prints per-field accuracy with 95% Wilson intervals,
   the character error rate, and whether errors were blanks, wrong values or invented values;
   writes <dir>/results.json.

2. Quick look at individual scans (dump fields, confidences, flags and warnings):
       python backend/scripts/evaluate_real.py path/to/scan.pdf [more.pdf ...]
       python backend/scripts/evaluate_real.py --truth truth.json scan.pdf
   --truth is a JSON object {filename: {field: expected_value}}; labelled fields are marked
   MATCH / MISREAD.

NOTE: one real scan is an anecdote, not a measurement. Report per-field results with
confidence intervals and the sample size, as set out in NEXT_STEPS.md — never a single number.
"""
from __future__ import annotations

import argparse
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


def run(path: Path) -> tuple[dict, float]:
    t0 = time.time()
    images, _ = prepare_document_pages(path.read_bytes(), path.name)
    result, _, _ = process_pages(images)
    return result, time.time() - t0


# ---------------------------------------------------------------- quick look (mode 2)
def dump(paths: list[Path], truth_file: Path | None):
    truth = json.loads(truth_file.read_text()) if truth_file else {}
    totals = hits = 0
    for p in paths:
        result, secs = run(p)
        exp = truth.get(p.name, {})
        print(f"\n=== {p.name} ===  (risk {result['risk']['band']}, "
              f"verification {result['verification']['overall']}, {secs:.1f}s)")
        for k, f in result["extraction"]["fields"].items():
            line = f"  {k:28} {str(f['value']):26} conf {f['confidence']:.2f}"
            if f.get("corrected_from"):
                line += f"  (read as {f['corrected_from']})"
            if f.get("suggestion"):
                line += f"  (possible: {f['suggestion']})"
            if k in exp:
                totals += 1
                ok = norm(k, f["value"]) == norm(k, str(exp[k]))
                hits += ok
                line += f"  expected {exp[k]!r}  {'MATCH' if ok else 'MISREAD'}"
            print(line)
        print(f"  flags: {', '.join(f['code'] for f in result['flags']) or 'none'}")
        for w in result["extraction"]["warnings"]:
            print(f"  warning: {w}")
    if totals:
        print(f"\nLabelled fields: {hits}/{totals} exact reads ({100 * hits / totals:.1f}%)")
        print("Quote this with a confidence interval and the sample size — one document is an anecdote.")


# ---------------------------------------------------------------- labelled set (mode 1)
def write_template(folder: Path, labels: Path):
    folder.mkdir(parents=True, exist_ok=True)
    scans = sorted(p.name for p in folder.iterdir() if p.suffix.lower() in SCANS)
    with open(labels, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", *FIELDS])
        for s in scans:
            w.writerow([s] + [""] * len(FIELDS))
    print(f"Created {labels} with {len(scans)} scan(s). Fill in the values printed on each card "
          f"(EMPTY for a blank field) and run again.")


def evaluate(folder: Path):
    labels = folder / "labels.csv"
    if not labels.exists():
        write_template(folder, labels)
        return
    rows = list(csv.DictReader(open(labels, newline="", encoding="utf-8-sig")))
    stats = {f: {"n": 0, "ok": 0, "blank": 0, "wrong": 0, "hallucinated": 0, "edits": 0, "chars": 0}
             for f in FIELDS}
    per_card, times = [], []
    for row in rows:
        path = folder / row["file"]
        if not path.exists():
            print(f"!! missing scan {row['file']}")
            continue
        result, secs = run(path)
        times.append(secs)
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
        per_card.append({"file": row["file"], "errors": errors, "seconds": round(secs, 2),
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
    (folder / "results.json").write_text(json.dumps({"cards": per_card, "fields": stats}, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scans", nargs="*", type=Path, help="scan files for a quick look (mode 2)")
    ap.add_argument("--truth", type=Path, default=None, help="JSON {filename: {field: expected}} for mode 2")
    ap.add_argument("--dir", type=Path, default=DATA_DIR / "real_nrc", help="labelled folder for mode 1")
    args = ap.parse_args()
    if args.scans:
        dump(args.scans, args.truth)
    else:
        evaluate(args.dir)


if __name__ == "__main__":
    main()

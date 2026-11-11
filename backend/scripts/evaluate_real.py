"""Evaluate extraction on *real* scanned NRCs — the counterpart to evaluate.py.

Real scans contain personal data and live outside this repository. Keep them in a
git-ignored folder (e.g. data/real/) and pass the paths on the command line:

    .venv/bin/python backend/scripts/evaluate_real.py path/to/scan.pdf [more.pdf ...]
    .venv/bin/python backend/scripts/evaluate_real.py --truth truth.json scan.pdf

--truth accepts a JSON object mapping filename -> {field: expected_value}; where a
value is provided the report marks it match / misread so you can quote per-field
accuracy. Without --truth the script just dumps the extracted fields, confidences
and warnings, for manual review inside the ZRA sandbox.

NOTE: one real scan is an anecdote, not a measurement. Report per-field results
with confidence intervals, as set out in NEXT_STEPS.md — never a single number.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smartclear.document import load_document  # noqa: E402
from smartclear.pipeline import process  # noqa: E402

KEY_FIELDS = ("nrc_number", "card_number", "full_name", "date_of_birth", "sex", "registration_date")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+", type=Path)
    ap.add_argument("--truth", type=Path, default=None, help="JSON: {filename: {field: expected}}")
    args = ap.parse_args()

    truth = json.loads(args.truth.read_text()) if args.truth else {}
    totals, hits = 0, 0
    for p in args.pdfs:
        data = p.read_bytes()
        img = load_document(data, p.name)
        result, _ = process(img)
        fields = {k: v for k, v in result["extraction"]["fields"].items()}
        exp = truth.get(p.name, {})
        print(f"\n=== {p.name} ===  (risk {result['risk']['band']}, verification {result['verification']['overall']})")
        print(f"  page: scale {result['page']['scale']}, cards detected {len(result['page']['cards'])}")
        for k, f in fields.items():
            line = f"  {k:28} {str(f['value']):26} conf {f['confidence']:.2f}"
            if k in exp:
                totals += 1
                ok = (f["value"] or "").strip().upper() == str(exp[k]).strip().upper()
                hits += ok
                line += f"  expected {exp[k]!r}  {'MATCH' if ok else 'MISREAD'}"
            print(line)
        print(f"  flags: {', '.join(f['code'] for f in result['flags']) or 'none'}")
        for w in result["extraction"]["warnings"]:
            print(f"  warning: {w}")
    if totals:
        print(f"\nKey/labelled fields: {hits}/{totals} exact reads ({100 * hits / totals:.1f}%)")
        print("Quote this with a confidence interval and the sample size — one document is an anecdote.")


if __name__ == "__main__":
    main()

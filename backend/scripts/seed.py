"""Seed the SmartClear sandbox.

1. Learn the NRC district-code reference table from GENUINE synthetic cards.
2. Generate synthetic "captured taxpayer records" (the ZRA records dataset is still being
   identified, per the Challenge Brief). Each record is derived from the card's ground truth
   with a labelled scenario so verification accuracy can be measured:
     exact, format_variation, name_reordered, missing_middle_name, minor_typo  -> expect match / review
     entry_error_dob, entry_error_nrc, different_person                       -> expect mismatch
   For altered cards the record keeps the ORIGINAL (pre-alteration) value, as it would in reality.
3. Process every synthetic PDF through the full pipeline into a review case.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smartclear import db  # noqa: E402
from smartclear.api import create_case  # noqa: E402
from smartclear.config import DATA_DIR, DB_PATH, REFERENCE_PATH, STORAGE_DIR, SYNTHETIC_PDF_DIR  # noqa: E402
from smartclear.verify import parse_date  # noqa: E402

CACHE = STORAGE_DIR / "cache" / "docs"
SURNAMES = ["BANDA", "PHIRI", "MWALE", "ZULU", "TEMBO", "LUNGU", "MBEWE", "SAKALA", "MULENGA", "CHANDA", "MUSONDA",
            "KAPEMBWA", "NGOMA", "SIAME", "HAMOONGA", "CHILESHE", "NYIRENDA", "MUMBA"]
FIRST = ["MWILA", "GRACE", "PATRICK", "MARY", "JOSEPH", "CHOLA", "BRIAN", "NATASHA", "KELVIN", "ESTHER"]


def build_reference(gt):
    codes = defaultdict(Counter)
    for r in gt:
        if r["is_fraud"] == "0" and r["nrc_number"]:
            codes[r["nrc_number"].split("/")[1]][r["place_of_birth_district"]] += 1
    table = {c: cnt.most_common(1)[0][0] for c, cnt in sorted(codes.items())}
    REFERENCE_PATH.write_text(json.dumps({"district_codes": table,
                                          "source": "learned from genuine synthetic specimens; replace with official "
                                                    "NRB district code table"}, indent=2))
    return table


def typo(s, rng):
    i = rng.randrange(1, len(s) - 1)
    return s[:i] + rng.choice("AEIOUNMLK") + s[i + 1:]


def make_records(gt, rng, codes):
    inv = {v: k for k, v in codes.items()}
    rows = []
    for i, r in enumerate(gt):
        k = r["doc_id"][-4:]
        nrc, name, dob = r["nrc_number"], r["full_name"], r["date_of_birth"]
        tf, tech = r["tampered_field"], r["tamper_technique"]
        scenario, expected = None, None
        # Unknown true values for erased fields -> plausible original values
        if tf == "nrc_number":
            code = inv.get(r["place_of_birth_district"], "11")
            orig = nrc or f"{rng.randrange(100000, 999999)}/{code}/1"
            if tech == "digit_patch" and nrc:
                d = list(nrc)
                d[0] = str((int(d[0]) + rng.randrange(1, 9)) % 10) if d[0].isdigit() else d[0]
                pos = rng.choice([j for j, ch in enumerate(nrc[:6])])
                d = list(nrc)
                d[pos] = str((int(d[pos]) + rng.randrange(1, 9)) % 10)
                orig = "".join(d)
            nrc, scenario = orig, f"altered_card:{tech}"
            expected = "mismatch" if tech == "digit_patch" else "review"
        elif tf == "full_name":
            parts = (name or "").split()
            if tech == "blur_erasure" or not parts:
                name, expected = f"{rng.choice(FIRST)} {rng.choice(SURNAMES)} {rng.choice(SURNAMES)}", "review"
            else:
                parts[-1] = rng.choice([s for s in SURNAMES if s not in parts])
                name, expected = " ".join(parts), "mismatch"
            scenario = f"altered_card:{tech}"
        elif tf == "date_of_birth":
            d = parse_date(dob)
            if tech == "blur_erasure" or not d:
                dob, expected = (date(1970, 1, 1) + timedelta(days=rng.randrange(0, 12000))).strftime("%d.%m.%y"), "review"
            else:
                dob, expected = d.replace(year=d.year - rng.choice([10, 1, 2, -1])).strftime("%d.%m.%y"), "mismatch"
            scenario = f"altered_card:{tech}"

        dobd = parse_date(dob)
        dob_iso = dobd.isoformat() if dobd else None
        if scenario is None:
            u = rng.random()
            if u < 0.45:
                scenario, expected = "exact", "match"
            elif u < 0.60:
                scenario, expected = "format_variation", "match"
                name = name.title()
            elif u < 0.70:
                scenario, expected = "name_reordered", "match"
                p = name.split()
                name = " ".join(p[-1:] + p[:-1])
            elif u < 0.78:
                scenario, expected = "missing_middle_name", "review"
                p = name.split()
                name = f"{p[0]} {p[-1]}" if len(p) >= 3 else name
            elif u < 0.84:
                scenario, expected = "minor_typo", "match"
                p = name.split()
                p[-1] = typo(p[-1], rng) if len(p[-1]) > 4 else p[-1]
                name = " ".join(p)
            elif u < 0.91:
                scenario, expected = "entry_error_dob", "mismatch"
                dob_iso = (dobd + timedelta(days=rng.choice([1, 31, 365]))).isoformat()
            elif u < 0.96:
                scenario, expected = "entry_error_nrc", "mismatch"
                d = list(nrc)
                d[2] = str((int(d[2]) + 3) % 10)
                nrc = "".join(d)
            else:
                scenario, expected = "different_person", "mismatch"
                name = f"{rng.choice(FIRST)} {rng.choice(SURNAMES)}"
        rows.append({"tpin": f"10{(48213 + i * 7919) % 100000000:08d}", "nrc_number": nrc, "full_name": name,
                     "date_of_birth": dob_iso, "sex": r["sex"], "district": r["district"],
                     "phone": f"+26097{rng.randrange(1000000, 9999999)}", "captured_at": "2026-10-01",
                     "source_doc": r["file"], "scenario": scenario, "expected_outcome": expected})
    return rows


def main():
    rng = random.Random(2026)
    gt = list(csv.DictReader(open(DATA_DIR / "ground_truth.csv")))
    codes = build_reference(gt)
    print(f"reference: {len(codes)} district codes")
    recs = make_records(gt, rng, codes)
    with open(DATA_DIR / "taxpayer_records.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, list(recs[0].keys()))
        w.writeheader()
        w.writerows(recs)
    print("scenarios:", Counter(r["scenario"].split(":")[0] for r in recs))

    if DB_PATH.exists():
        DB_PATH.unlink()
    db.init()
    from smartclear import flags

    flags.reference.cache_clear()
    with db.conn() as c:
        for r in recs:
            c.execute("INSERT INTO taxpayers VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (r["tpin"], r["nrc_number"], r["full_name"], r["date_of_birth"], r["sex"], r["district"],
                       r["phone"], r["captured_at"], r["source_doc"], r["scenario"]))
    by_doc = {r["source_doc"]: r for r in recs}
    pdfs = sorted(Path(SYNTHETIC_PDF_DIR).glob("*.pdf"))
    for i, p in enumerate(pdfs, 1):
        js = CACHE / f"{p.stem.upper()}.json"
        tokens = json.loads(js.read_text())["tokens"] if js.exists() else None
        with db.conn() as c:
            cid = create_case(c, p.read_bytes(), p.name, by_doc[p.name]["tpin"], "system:seed", tokens=tokens,
                              ref=f"SC-{p.stem[-4:]}")
            row = c.execute("SELECT risk_band, verification, n_flags FROM cases WHERE id=?", (cid,)).fetchone()
        print(f"[{i:3d}/{len(pdfs)}] {p.name}: {row['risk_band']:6s} verification={row['verification']:8s} "
              f"flags={row['n_flags']}", flush=True)

    # Spread the seeded cases across the last 14 days + mark a subset decided,
    # so the dashboard's volume/decision panels carry real numbers.
    from seed_timeline import spread_timeline  # type: ignore
    with db.conn() as c:
        spread_timeline(c)


if __name__ == "__main__":
    main()

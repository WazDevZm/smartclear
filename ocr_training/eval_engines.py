"""Score OCR engines on the NRC text crops (data/ocr_rec).

Each crop is one field from one card, so the metric is per-field exact match after
trimming whitespace, plus per-field normalized edit similarity.

    .venv/Scripts/python ocr_training/eval_engines.py --engine rapidocr --split val
    .venv_paddle/Scripts/python ocr_training/eval_engines.py --engine trocr --split test

Results are written to ocr_training/results/<engine>_<split>.json.
Use val to choose between engines; use test only for the final report.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "ocr_rec"
RESULTS = ROOT / "ocr_training" / "results"
NAME = re.compile(r"_(front|back)_(.+)\.png$")


def read_split(split: str) -> list[tuple[str, str, str]]:
    rows = []
    for line in (DATA / f"{split}.txt").read_text(encoding="utf-8").splitlines():
        rel, text = line.split("\t", 1)
        m = NAME.search(rel)
        field = m.group(2) if m else "unknown"
        rows.append((rel, field, text))
    return rows


def edit_similarity(a: str, b: str) -> float:
    from rapidfuzz.distance import Levenshtein
    if not a and not b:
        return 1.0
    return 1 - Levenshtein.distance(a, b) / max(len(a), len(b))


def make_engine(name: str):
    if name == "rapidocr":
        from rapidocr_onnxruntime import RapidOCR
        eng = RapidOCR()

        def run(img: Image.Image) -> str:
            # Recognition only: the crops are already tight single-field boxes, so the
            # text detector is skipped (on a tight crop it finds nothing useful).
            import numpy as np
            res, _ = eng(np.asarray(img.convert("RGB"))[:, :, ::-1].copy(),
                         use_det=False, use_cls=False, use_rec=True)
            if not res:
                return ""
            return res[0][0]
        return run

    if name.startswith("trocr"):
        import torch
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
        model_id = {"trocr": "microsoft/trocr-base-printed",
                    "trocr-small": "microsoft/trocr-small-printed"}[name]
        proc = TrOCRProcessor.from_pretrained(model_id)
        model = VisionEncoderDecoderModel.from_pretrained(model_id).eval()

        def run(img: Image.Image) -> str:
            pix = proc(images=img.convert("RGB"), return_tensors="pt").pixel_values
            with torch.no_grad():
                ids = model.generate(pix, max_new_tokens=32)
            return proc.batch_decode(ids, skip_special_tokens=True)[0]
        return run

    raise SystemExit(f"unknown engine {name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True)
    ap.add_argument("--split", default="val", choices=["train", "val", "test"])
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    rows = read_split(args.split)
    if args.limit:
        rows = rows[: args.limit]
    run = make_engine(args.engine)

    per_field = defaultdict(lambda: {"n": 0, "exact": 0, "sim": 0.0})
    errors = []
    t0 = time.time()
    for rel, field, truth in rows:
        img = Image.open(DATA / rel)
        pred = run(img).strip()
        ok = pred.replace(" ", "") == truth.strip().replace(" ", "")
        s = per_field[field]
        s["n"] += 1
        s["exact"] += int(ok)
        s["sim"] += edit_similarity(pred, truth.strip())
        if not ok:
            errors.append({"crop": rel, "truth": truth, "pred": pred})
    secs = time.time() - t0

    total_n = sum(s["n"] for s in per_field.values())
    total_ok = sum(s["exact"] for s in per_field.values())
    report = {
        "engine": args.engine,
        "split": args.split,
        "crops": total_n,
        "exact_match": round(total_ok / total_n, 4),
        "seconds_per_crop": round(secs / total_n, 3),
        "per_field": {f: {"n": s["n"], "exact": round(s["exact"] / s["n"], 4),
                          "similarity": round(s["sim"] / s["n"], 4)}
                      for f, s in sorted(per_field.items())},
        "errors_sample": errors[:40],
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{args.engine}_{args.split}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{args.engine} on {args.split}: exact={report['exact_match']:.3f} "
          f"crops={total_n} sec/crop={report['seconds_per_crop']}")
    for f, s in report["per_field"].items():
        print(f"  {f:12s} n={s['n']:4d} exact={s['exact']:.3f} sim={s['similarity']:.3f}")
    print("wrote", out)


if __name__ == "__main__":
    main()

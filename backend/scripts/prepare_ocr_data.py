"""Arrange the synthetic NRC set into train / val / test and cut out text crops for OCR training.

Input  : data/nrc_synth_v5/  (unzipped from "claude data/*.zip")
Output : data/ocr_rec/{train,val,test}/...   PaddleOCR recognition crops
         data/ocr_rec/{train,val,test}.txt   PaddleOCR label files ("path<TAB>text")
         data/ocr_rec/manifest.json          counts per split / source / field

Splits are by identity (never by image), so no card appears in two splits.
The source splits.json names its test group "test_synthetic"; it is written out as "test".

Run from the project root:
    .venv/Scripts/python backend/scripts/prepare_ocr_data.py
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "nrc_synth_v5"
OUT = ROOT / "data" / "ocr_rec"

# Fields that carry printed text (photo, thumbprint, signatures and crest are images, not text).
TEXT_FIELDS = {
    "front": ["reg_no"],
    "back": ["card_no", "given", "surname", "dob", "pob", "pob2", "sex",
             "village", "district", "chief", "reg_date", "marks", "renunc"],
}
PAD = 3          # pixels of margin around each box
MIN_SIDE = 6     # boxes smaller than this (px) are skipped
UNKNOWN_CHARS = re.compile(r"[^A-Z0-9 ./\-]")


def load_splits() -> dict[str, set[str]]:
    raw = json.loads((SRC / "splits.json").read_text(encoding="utf-8"))
    rename = {"test_synthetic": "test"}
    return {rename.get(k, k): set(v) for k, v in raw.items()}


def crop_box(img: Image.Image, box: list[float]) -> Image.Image | None:
    x0, y0, x1, y1 = box
    x0, y0 = max(0, int(x0) - PAD), max(0, int(y0) - PAD)
    x1, y1 = min(img.width, int(x1) + PAD), min(img.height, int(y1) + PAD)
    if x1 - x0 < MIN_SIDE or y1 - y0 < MIN_SIDE:
        return None
    return img.crop((x0, y0, x1, y1))


def main() -> None:
    labels = json.loads((SRC / "labels.json").read_text(encoding="utf-8"))
    splits = load_splits()
    split_of = {i: s for s, ids in splits.items() for i in ids}

    if OUT.exists():
        for p in OUT.iterdir():
            if p.is_dir():
                import shutil
                shutil.rmtree(p)
            else:
                p.unlink()
    OUT.mkdir(parents=True)

    lines: dict[str, list[str]] = defaultdict(list)
    stats = Counter()
    skipped = Counter()
    field_counts: dict[str, Counter] = defaultdict(Counter)
    issues: list[str] = []

    for lab in labels:
        ident = lab["id"]
        split = split_of.get(ident)
        if split is None:
            issues.append(f"{ident}: not in any split, skipped")
            continue

        # Source 1: clean renders (ground-truth quality).
        clean_src = SRC / lab["clean"]["front"]
        sources = [("clean", None)]
        # Source 2: the styled scan/photo for this identity (flatbed, phone, photocopy).
        styled_src = SRC / lab["image"]
        sources.append((lab["style"], styled_src))

        for source, img_path in sources:
            for side in ("front", "back"):
                if source == "clean":
                    img_file = SRC / lab["clean"][side]
                    fields = lab["clean"]["fields"].get(side, {})
                else:
                    if side not in lab.get("sides", {}):
                        continue  # phone photos hold one side only
                    img_file = img_path
                    fields = lab["sides"][side]["fields"]

                if not img_file.exists():
                    issues.append(f"{ident}: missing image {img_file.name}")
                    continue
                img = Image.open(img_file).convert("RGB")

                for field in TEXT_FIELDS[side]:
                    if field not in fields:
                        continue
                    text = (fields[field].get("text") or "").strip()
                    if not text:
                        skipped["empty_text"] += 1
                        continue
                    if UNKNOWN_CHARS.search(text.upper()):
                        issues.append(f"{ident} {side}.{field}: unusual characters in {text!r}")
                    crop = crop_box(img, fields[field]["bbox"])
                    if crop is None:
                        skipped["box_too_small"] += 1
                        continue

                    rel = f"{split}/{source}/{ident}_{side}_{field}.png"
                    dest = OUT / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    crop.save(dest)
                    lines[split].append(f"{rel}\t{text}")
                    stats[(split, source)] += 1
                    field_counts[split][field] += 1

    for split, rows in lines.items():
        (OUT / f"{split}.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")

    manifest = {
        "identities": {s: len(ids) for s, ids in splits.items()},
        "crops": {f"{s}/{src}": n for (s, src), n in sorted(stats.items())},
        "crops_per_split": {s: len(r) for s, r in lines.items()},
        "crops_per_field": {s: dict(c) for s, c in field_counts.items()},
        "skipped": dict(skipped),
        "issues": issues,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("identities:", manifest["identities"])
    print("crops per split:", manifest["crops_per_split"])
    print("skipped:", manifest["skipped"])
    print(f"issues: {len(issues)} (see {OUT / 'manifest.json'})")


if __name__ == "__main__":
    main()

"""Compare the card finder with hand-labelled corners. Real scans stay on this machine.

    python tools/label_corners/check_corners.py "C:/Users/you/Documents/smartclear_private_scans"

Reads corners.json and the page PNGs from that folder, runs preprocess.find_card_quads on
each labelled page, and prints the overlap (IoU) of every labelled card with its best match.
Nothing is written or uploaded.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from smartclear.preprocess import find_card_quads  # noqa: E402


def iou(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float32)
    b = b.astype(np.float32)
    inter, _ = cv2.intersectConvexConvex(a, b)
    union = cv2.contourArea(a) + cv2.contourArea(b) - inter
    return float(inter / union) if union > 0 else 0.0


def main() -> None:
    folder = Path(sys.argv[1])
    labels = json.loads((folder / "corners.json").read_text(encoding="utf-8"))["labels"]
    total, hits = 0, 0
    for name, info in labels.items():
        if info.get("none"):
            continue
        data = np.fromfile(folder / name, np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            print(f"{name}: could not read")
            continue
        found = find_card_quads(img)
        print(f"{name}: {len(found)} detected, {len(info['cards'])} labelled")
        for i, card in enumerate(info["cards"]):
            gt = np.array(card, np.float32)
            best = max((iou(gt, q) for q in found), default=0.0)
            total += 1
            ok = best >= 0.8
            hits += ok
            print(f"   card {i + 1}: IoU {best:.2f} {'OK' if ok else 'MISS'}")
    if total:
        print(f"\n{hits}/{total} labelled cards matched at IoU >= 0.8")


if __name__ == "__main__":
    main()

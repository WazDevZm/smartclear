"""Detect individual NRC cards on a scanned page and normalise the image geometry.

Synthetic specimens are generated as a tight, full-page card pair and need no
detection. Real scans (and photos) place one or two cards on a larger white page,
sometimes slightly rotated, and the card is much smaller in pixels than the
calibration geometry in extraction.py expects (~924 px card width).

Strategy:
  1. Threshold the page against the white scanner background and find large,
     card-like contours (aspect ratio and fill filtering).
  2. If cards are found, scale the whole page so the largest card is at the
     calibrated 924 px width. The layout of the page is preserved, so the
     anchor-based field zones in extraction.py remain valid.
  3. If no card is found (tight crop, unusual background), the page is returned
     unscaled and the caller falls back to the original behaviour.
"""
from __future__ import annotations

import cv2
import numpy as np

TARGET_CARD_WIDTH = 924          # calibrated width used by extraction.py
MIN_CARD_ASPECT = 1.15           # credit-card-ish; real scans measured ~1.2-1.6
MAX_CARD_ASPECT = 2.4
MIN_FILL = 0.55                  # contour area / bounding-rect area
MIN_CARD_FRACTION = 0.08         # a card must cover at least 8% of the page
MAX_SCALE = 3.0
MIN_SCALE = 0.5


def detect_cards(image: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Return bounding boxes (x, y, w, h) of card-like regions, top-to-bottom."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 235, 255, cv2.THRESH_BINARY_INV)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25)))
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    H, W = image.shape[:2]
    page = float(H * W)
    boxes = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area < MIN_CARD_FRACTION * page:
            continue
        aspect = w / max(h, 1)
        if not (MIN_CARD_ASPECT <= aspect <= MAX_CARD_ASPECT):
            continue
        if cv2.contourArea(c) / area < MIN_FILL:
            continue
        boxes.append((x, y, w, h))
    boxes.sort(key=lambda b: b[1])
    return boxes


def normalize_page(image: np.ndarray) -> tuple[np.ndarray, dict]:
    """Scale the page so the detected cards are at the calibrated width.

    Returns (image, info) where info carries the detected card boxes (in the
    returned image's coordinates), the applied scale and whether detection ran.
    """
    boxes = detect_cards(image)
    if not boxes:
        return image, {"scaled": False, "scale": 1.0, "cards": []}
    widest = max(b[2] for b in boxes)
    scale = TARGET_CARD_WIDTH / widest
    scale = float(np.clip(scale, MIN_SCALE, MAX_SCALE))
    if abs(scale - 1.0) < 0.02:
        scaled = image.copy()
    else:
        scaled = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    info = {"scaled": abs(scale - 1.0) >= 0.02, "scale": round(scale, 4),
            "cards": [[int(v * scale) for v in b] for b in boxes]}
    return scaled, info

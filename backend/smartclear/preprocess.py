"""Rectify real NRC scans and photos before text reading.

Real scans and phone photos differ from the synthetic specimens the layout was calibrated on:
the card can be rotated, shot at an angle, sit on a coloured background, or share the page
with other paper. This module finds each card as a quadrilateral, straightens it (perspective
warp to the card's real proportions), evens out the contrast, and stacks the front and back
cards into one page in the layout the extraction already expects.

Only cards whose outline sits inside the page are used. Synthetic specimens fill the page
edge to edge, so they are left to the original path (see pipeline.process).
"""
from __future__ import annotations

import cv2
import numpy as np

CARD_W = 924                 # calibrated card width used by extraction.py
CARD_RATIO = 1.586           # ISO/ID-1 card: 85.6 mm x 54 mm
CARD_H = int(round(CARD_W / CARD_RATIO))
GAP = 20                     # white gap between the front and back cards
MIN_AREA_FRACTION = 0.05     # a card covers at least 5% of the page
MAX_AREA_FRACTION = 0.97
MIN_RATIO, MAX_RATIO = 1.3, 2.0
MIN_FILL = 0.85              # share of the fitted rectangle that the card outline covers
EDGE_MARGIN = 0.01           # outlines this close to the page edge are paper edges, not cards


def _order(pts: np.ndarray) -> np.ndarray:
    """Order four points as top-left, top-right, bottom-right, bottom-left."""
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)


def _touches_edge(box: tuple[int, int, int, int], W: int, H: int) -> bool:
    x, y, w, h = box
    mx, my = EDGE_MARGIN * W, EDGE_MARGIN * H
    return x <= mx or y <= my or x + w >= W - mx or y + h >= H - my


def find_card_quads(image: np.ndarray) -> list[np.ndarray]:
    """Return the four-corner outlines of cards on the page, largest first, without overlaps."""
    H, W = image.shape[:2]
    scale = min(1.0, 1100.0 / max(H, W))
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else image
    h_s, w_s = small.shape[:2]
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    page_area = float(h_s * w_s)
    cands = []
    for c in cnts:
        # Cards have rounded corners, so fit a rotated rectangle to the outline rather than
        # requiring exactly four polygon corners. The outline must fill that rectangle well.
        hull = cv2.convexHull(c)
        area = cv2.contourArea(hull)
        if not (MIN_AREA_FRACTION * page_area <= area <= MAX_AREA_FRACTION * page_area):
            continue
        rect = cv2.minAreaRect(hull)
        if rect[1][0] * rect[1][1] <= 0 or area / (rect[1][0] * rect[1][1]) < MIN_FILL:
            continue
        quad = _order(cv2.boxPoints(rect).astype(np.float32))
        top = np.linalg.norm(quad[1] - quad[0]); bottom = np.linalg.norm(quad[2] - quad[3])
        left = np.linalg.norm(quad[3] - quad[0]); right = np.linalg.norm(quad[2] - quad[1])
        w, h = (top + bottom) / 2, (left + right) / 2
        if min(w, h) < 1:
            continue
        ratio = max(w, h) / min(w, h)
        if not (MIN_RATIO <= ratio <= MAX_RATIO):
            continue
        x, y, bw, bh = cv2.boundingRect(quad.astype(np.int32))
        if _touches_edge((x, y, bw, bh), w_s, h_s):
            continue
        cands.append((area, quad))
    cands.sort(key=lambda t: -t[0])
    chosen: list[np.ndarray] = []
    for _, q in cands:
        if all(_iou(q, o) < 0.3 for o in chosen):
            chosen.append(q)
        if len(chosen) == 2:
            break
    return [q / scale for q in chosen]


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    ax, ay, aw, ah = cv2.boundingRect(a.astype(np.int32))
    bx, by, bw, bh = cv2.boundingRect(b.astype(np.int32))
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / float(aw * ah + bw * bh - inter + 1e-6)


def _warp_card(image: np.ndarray, quad: np.ndarray) -> np.ndarray:
    dst = np.array([[0, 0], [CARD_W - 1, 0], [CARD_W - 1, CARD_H - 1], [0, CARD_H - 1]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(quad.astype(np.float32), dst)
    card = cv2.warpPerspective(image, M, (CARD_W, CARD_H), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
    return card


def _enhance(card: np.ndarray) -> np.ndarray:
    """Even out lighting and boost text contrast; returns a 3-channel image for the recognizer."""
    gray = cv2.cvtColor(card, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    blur = cv2.GaussianBlur(gray, (0, 0), 1.2)
    sharp = cv2.addWeighted(gray, 1.6, blur, -0.6, 0)
    return cv2.cvtColor(np.clip(sharp, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


def rectify_page(image: np.ndarray) -> tuple[np.ndarray, dict]:
    """Return (page, info). info['cards'] is empty when no card outline was found (page unchanged)."""
    quads = find_card_quads(image)
    if not quads:
        return image, {"rectified": False, "cards": [], "scale": 1.0, "scaled": False}
    cards = [_enhance(_warp_card(image, q)) for q in sorted(quads, key=lambda q: q[:, 1].mean())]
    if len(cards) == 1:
        page = cards[0]
        boxes = [[0, 0, CARD_W, CARD_H]]
    else:
        white = np.full((GAP, CARD_W, 3), 255, np.uint8)
        page = np.vstack([cards[0], white, cards[1]])
        boxes = [[0, 0, CARD_W, CARD_H], [0, CARD_H + GAP, CARD_W, CARD_H]]
    return page, {"rectified": True, "cards": boxes, "scale": 1.0, "scaled": True}

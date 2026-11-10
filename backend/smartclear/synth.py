"""Synthetic forgery generator used to train the tamper model.

Reproduces the alteration techniques observed in the labelled synthetic NRC set:
  * digit_patch       — a correction patch over one digit with a re-typed digit on top
  * digit_splice      — one or two digits replaced in a different font / ink colour
  * font_substitution — a word (typically a surname) re-typed in a different typeface/ink
  * blur_erasure      — a field smudged/blurred so it cannot be read

Plus benign augmentations (JPEG re-compression, noise, brightness, slight defocus)
applied to BOTH genuine and forged samples so the model cannot shortcut on
"any processing = tamper".
"""
from __future__ import annotations

import os
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

TECHNIQUES = ("digit_patch", "digit_splice", "font_substitution", "blur_erasure")

_FONT_DIRS = ["/System/Library/Fonts/Supplemental", "/System/Library/Fonts", "/Library/Fonts",
              "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation", "C:/Windows/Fonts"]
MONO = ["Courier New.ttf", "Courier New Bold.ttf", "Menlo.ttc", "DejaVuSansMono.ttf", "LiberationMono-Regular.ttf",
        "cour.ttf"]
SANS = ["Arial.ttf", "Helvetica.ttc", "Verdana.ttf", "Tahoma.ttf", "Trebuchet MS.ttf", "Arial Narrow.ttf",
        "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "arial.ttf"]

INKS_TINTED = [(150, 85, 40), (130, 90, 60), (120, 70, 30), (110, 95, 80), (95, 80, 70), (160, 110, 60)]  # BGR
INKS_DARK = [(35, 35, 35), (55, 50, 50), (25, 25, 30), (70, 65, 60)]


@lru_cache(maxsize=None)
def _font_paths(names: tuple) -> list[str]:
    out = []
    for n in names:
        for d in _FONT_DIRS:
            p = os.path.join(d, n)
            if os.path.exists(p):
                out.append(p)
                break
    return out


def _font(kind: str, px: int, rng) -> ImageFont.ImageFont:
    paths = _font_paths(tuple(MONO if kind == "mono" else SANS))
    if not paths:
        return ImageFont.load_default()
    return ImageFont.truetype(paths[rng.integers(len(paths))], px)


def _ink_mask(crop: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    k = max(7, (min(crop.shape[:2]) // 2) | 1)
    bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    diff = bg - gray
    return (diff > max(25.0, float(np.percentile(diff, 99)) * 0.45)).astype(np.uint8)


def _segments(mask: np.ndarray, min_gap: int) -> list[tuple[int, int]]:
    cols = mask.sum(0) > 0
    segs, start, gap = [], None, 0
    for x, c in enumerate(cols):
        if c:
            if start is None:
                start = x
            gap = 0
            end = x
        elif start is not None:
            gap += 1
            if gap >= min_gap:
                segs.append((start, end))
                start = None
    if start is not None:
        segs.append((start, end))
    return segs


def _text_rows(mask: np.ndarray) -> tuple[int, int]:
    rows = np.where(mask.sum(1) > 0)[0]
    if len(rows) == 0:
        return 0, mask.shape[0]
    return int(rows.min()), int(rows.max()) + 1


def _render(region: np.ndarray, text: str, x: int, y_top: int, height: int, font_kind: str, color, rng,
            scale_jitter=(0.95, 1.1), max_width=None):
    pil = Image.fromarray(cv2.cvtColor(region, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    target = max(6, int(height * rng.uniform(*scale_jitter)))
    px = target
    font = _font(font_kind, px, rng)
    for _ in range(6):   # fit cap-height to target
        bb = font.getbbox(text)
        h = bb[3] - bb[1]
        if h <= 0:
            break
        px = max(6, int(px * target / h))
        font = _font(font_kind, px, rng) if abs(h - target) > 1 else font
        if abs(h - target) <= 1:
            break
    bb = font.getbbox(text)
    if max_width and bb[2] - bb[0] > max_width * 1.25:
        px = max(6, int(px * max_width * 1.1 / (bb[2] - bb[0])))
        font = _font(font_kind, px, rng)
        bb = font.getbbox(text)
    dy = int(rng.integers(-2, 3))
    draw.text((x - bb[0], y_top - bb[1] + dy), text, font=font, fill=tuple(int(c) for c in color[::-1]))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def _erase(crop: np.ndarray, mask: np.ndarray, x0: int, x1: int) -> np.ndarray:
    m = np.zeros_like(mask)
    m[:, max(0, x0 - 1):x1 + 2] = mask[:, max(0, x0 - 1):x1 + 2]
    m = cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=1)
    return cv2.inpaint(crop, m * 255, 3, cv2.INPAINT_TELEA)


def tamper(img: np.ndarray, box, field: str, value: str | None, technique: str, rng) -> np.ndarray:
    out = img.copy()
    x0, y0, x1, y1 = [int(v) for v in box]
    crop = out[y0:y1, x0:x1].copy()
    if crop.size == 0:
        return out
    mask = _ink_mask(crop)
    ty0, ty1 = _text_rows(mask)
    th = max(6, ty1 - ty0)
    segs = _segments(mask, 2)
    if not segs:
        technique = "blur_erasure"
    ink_x0 = segs[0][0] if segs else 0
    ink_x1 = segs[-1][1] if segs else crop.shape[1]

    if technique == "blur_erasure":
        sigma = rng.uniform(2.5, 6.0)
        blurred = cv2.GaussianBlur(crop, (0, 0), sigma)
        if rng.random() < 0.5:
            blurred = cv2.addWeighted(blurred, 0.75, np.full_like(blurred, int(np.median(crop))), 0.25, 0)
        a, b = ink_x0, ink_x1
        if field == "full_name" and rng.random() < 0.3:     # sometimes only part of the field
            words = _segments(mask, 8)
            if words:
                a, b = words[int(rng.integers(len(words)))]
        feather = np.zeros(crop.shape[:2], np.float32)
        feather[:, max(0, a - 3):b + 4] = 1.0
        feather = cv2.GaussianBlur(feather, (0, 0), 2)[..., None]
        crop = (blurred * feather + crop * (1 - feather)).astype(np.uint8)

    elif technique in ("digit_patch", "digit_splice"):
        s = (value or "").replace(" ", "")
        n = len(s) if s and field != "full_name" else max(1, int(round((ink_x1 - ink_x0) / 10)))
        pitch = (ink_x1 - ink_x0 + 1) / max(n, 1)
        idxs = [i for i, ch in enumerate(s) if ch.isdigit()] if s and field != "full_name" else list(range(n))
        if not idxs:
            idxs = list(range(n))
        k = 1 if technique == "digit_patch" else int(rng.integers(1, 3))
        i = int(rng.choice(idxs[:-1] if k == 2 and len(idxs) > 1 else idxs))
        cx0 = int(ink_x0 + i * pitch)
        cx1 = int(ink_x0 + (i + k) * pitch)
        new = "".join(str(int(rng.integers(10))) for _ in range(k)) if field != "full_name" else \
            "".join(chr(65 + int(rng.integers(26))) for _ in range(k))
        if technique == "digit_patch":
            pad = int(rng.integers(1, 4))
            bgc = np.median(crop.reshape(-1, 3), axis=0)
            patch = np.clip(bgc + rng.uniform(18, 45), 0, 255)
            crop[max(0, ty0 - pad - 1):min(crop.shape[0], ty1 + pad), max(0, cx0 - pad):min(crop.shape[1], cx1 + pad)] = patch
            color = INKS_DARK[int(rng.integers(len(INKS_DARK)))]
            crop = _render(crop, new, cx0 + 1, ty0, th, "mono", color, rng, (1.0, 1.15), max_width=cx1 - cx0)
        else:
            crop = _erase(crop, mask, cx0, cx1)
            color = INKS_TINTED[int(rng.integers(len(INKS_TINTED)))] if rng.random() < 0.75 else \
                INKS_DARK[int(rng.integers(len(INKS_DARK)))]
            kind = "mono" if rng.random() < 0.6 else "sans"
            crop = _render(crop, new, cx0, ty0, th, kind, color, rng, (0.85, 1.12), max_width=cx1 - cx0)

    elif technique == "font_substitution":
        words = _segments(mask, 8) if field == "full_name" else [(ink_x0, ink_x1)]
        if field == "full_name" and value:
            names = value.split()
            j = len(words) - 1 if rng.random() < 0.6 else int(rng.integers(len(words)))
            word = names[j] if j < len(names) else names[-1]
        else:
            j, word = 0, (value or "00.00.00")
            if field != "full_name" and rng.random() < 0.5 and len(word) > 3:   # only the tail of the string
                cut = int(rng.integers(len(word) // 2, len(word) - 1))
                a, b = words[0]
                pitch = (b - a + 1) / len(word)
                words = [(int(a + cut * pitch), b)]
                word = word[cut:]
        a, b = words[min(j, len(words) - 1)]
        crop = _erase(crop, mask, a, b)
        color = INKS_TINTED[int(rng.integers(len(INKS_TINTED)))] if rng.random() < 0.7 else \
            INKS_DARK[int(rng.integers(len(INKS_DARK)))]
        crop = _render(crop, word, a, ty0, th, "sans", color, rng, (0.9, 1.15), max_width=b - a)

    out[y0:y1, x0:x1] = crop
    return out


def benign_augment(img: np.ndarray, rng) -> np.ndarray:
    out = img.astype(np.float32)
    out = out * rng.uniform(0.92, 1.06) + rng.uniform(-8, 8)
    if rng.random() < 0.5:
        out += rng.normal(0, rng.uniform(0.5, 3.5), out.shape)
    out = np.clip(out, 0, 255).astype(np.uint8)
    if rng.random() < 0.3:
        out = cv2.GaussianBlur(out, (0, 0), rng.uniform(0.3, 0.7))
    if rng.random() < 0.7:
        ok, enc = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, int(rng.integers(60, 96))])
        out = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    return out

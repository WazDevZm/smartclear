"""Content-hash cache for the heavy document-processing steps (OCR + extraction).

The same scan submitted again (a re-upload, a demo re-run, a batch re-check) produces
identical pixels, so recomputing everything burns ~30-60s of CPU for the same answer.
Cache stores the *display-coordinate* extraction payload; the verification step is
always re-run fresh (the captured record can change).

Cache key = sha256(normalized pixels) + CACHE_VERSION, so editing the extraction code
invalidates stale entries once CACHE_VERSION is bumped.
Storage lives under storage/ (git-ignored, same protections as uploads).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

CACHE_VERSION = "v7-no-tamper"  # bumped: tamper scores removed from the cached payload


def _dir():
    from .config import STORAGE_DIR

    d = STORAGE_DIR / "ocr_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def key_for(image: np.ndarray) -> str:
    h = hashlib.sha256()
    h.update(CACHE_VERSION.encode())
    h.update(np.ascontiguousarray(image).tobytes())
    h.update(str(image.shape).encode())
    return h.hexdigest()


def load(key: str):
    """Return (payload, display_image) or (None, None)."""
    try:
        d = _dir()
        meta = d / f"{key}.json"
        png = d / f"{key}.png"
        if not meta.exists() or not png.exists():
            return None, None
        payload = json.loads(meta.read_text())
        disp = cv2.imdecode(np.frombuffer(png.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
        if disp is None:
            return None, None
        return payload, disp
    except Exception:
        return None, None


def store(key: str, payload: dict, disp: np.ndarray) -> None:
    try:
        d = _dir()
        ok, buf = cv2.imencode(".png", disp)
        if not ok:
            return
        (d / f"{key}.png").write_bytes(buf.tobytes())
        (d / f"{key}.json").write_text(json.dumps(payload))
    except Exception:
        pass  # caching is an optimisation — never break verification

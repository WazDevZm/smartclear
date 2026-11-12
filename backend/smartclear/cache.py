"""Content-hash cache for the heavy document-processing steps (OCR + extraction + tamper).

The same scan submitted again (a re-upload, a demo re-run, a batch re-check) produces
identical pixels, so recomputing everything burns ~30-60s of CPU for the same answer.
Cache stores the *display-coordinate* extraction payload plus the tamper scores; the
verification step is always re-run fresh (the captured record can change).

Cache key = sha256(normalized pixels) + CACHE_VERSION + tamper-model stamp, so editing
the extraction code or retraining the model invalidates stale entries automatically.
Storage lives under storage/ (git-ignored, same protections as uploads).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import cv2
import numpy as np

CACHE_VERSION = "v6-orient-stretch-districts"


def _dir():
    from .config import STORAGE_DIR

    d = STORAGE_DIR / "ocr_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _model_stamp() -> str:
    from .config import TAMPER_MODEL_PATH

    try:
        st = os.stat(TAMPER_MODEL_PATH)
        return f"{int(st.st_mtime)}-{st.st_size}"
    except OSError:
        return "no-model"


def key_for(image: np.ndarray) -> str:
    h = hashlib.sha256()
    h.update(CACHE_VERSION.encode())
    h.update(np.ascontiguousarray(image).tobytes())
    h.update(str(image.shape).encode())
    h.update(_model_stamp().encode())
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

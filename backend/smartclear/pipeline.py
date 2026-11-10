"""SmartClear pipeline: Scanned NRC -> AI/OCR extraction -> record verification -> flagging -> officer review."""
from __future__ import annotations

import time

import cv2
import numpy as np

from . import flags as F
from .extraction import Token, extract, run_ocr
from .verify import verify

KEY_FIELDS = ("nrc_number", "full_name", "date_of_birth")


def _to_deskewed(bbox, M):
    if not bbox or M is None:
        return bbox
    x0, y0, x1, y1 = bbox
    pts = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]], float) @ np.asarray(M).T
    return [int(pts[:, 0].min()), int(pts[:, 1].min()), int(pts[:, 0].max()), int(pts[:, 1].max())]


def process(image: np.ndarray, record: dict | None = None, tokens: list | None = None) -> tuple[dict, np.ndarray]:
    """Run the full pipeline. Returns (result dict, deskewed image for display)."""
    t0 = time.time()
    toks = [Token(t, c, np.array(q)) for q, t, c in tokens] if tokens else run_ocr(image)
    t_ocr = time.time()
    ex = extract(image, toks)
    t_ext = time.time()
    fields = {k: f.value for k, f in ex.fields.items()}
    conf = {k: f.confidence for k, f in ex.fields.items()}

    verification = verify(fields, record)
    t_ver = time.time()
    scores = F.tamper_scores(ex.deskewed, ex.forensic_boxes)
    flags = F.rule_flags(fields, conf) + F.model_flags(scores)
    if verification["overall"] == "mismatch":
        bad = [k for k, c in verification["checks"].items() if c["outcome"] == "mismatch"]
        flags.append(F._flag("RECORD_MISMATCH", "high", "Doesn't match captured record",
                             "Mismatch on: " + ", ".join(F.FIELD_LABEL[b] for b in bad) + ".", bad[0] if bad else None))
    order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: order[f["severity"]])
    rk = F.risk(flags, verification, scores)
    t_end = time.time()

    ext = ex.to_dict()
    for k, f in ext["fields"].items():
        f["bbox"] = _to_deskewed(f["bbox"], ex.deskew_matrix)
    disp = ex.deskewed if ex.deskewed is not None else image
    result = {
        "extraction": ext,
        "forensic_boxes": ex.forensic_boxes,
        "verification": verification,
        "tamper": {k: {"probability": v["probability"], "reasons": v["reasons"]} for k, v in scores.items()},
        "flags": flags,
        "risk": rk,
        "image_size": [int(disp.shape[1]), int(disp.shape[0])],
        "timing_ms": {"ocr": round((t_ocr - t0) * 1000), "extraction": round((t_ext - t_ocr) * 1000),
                      "verification": round((t_ver - t_ext) * 1000), "flagging": round((t_end - t_ver) * 1000),
                      "total": round((t_end - t0) * 1000)},
    }
    return result, disp


def encode_png(img: np.ndarray) -> bytes:
    return cv2.imencode(".png", img)[1].tobytes()

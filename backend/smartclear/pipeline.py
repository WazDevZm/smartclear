"""SmartClear pipeline: Scanned NRC -> AI/OCR extraction -> record verification -> flagging -> officer review."""
from __future__ import annotations

import time

import cv2
import numpy as np

from . import cache as _cache
from . import flags as F
from .cards import normalize_page
from .extraction import Token, extract, run_ocr
from .verify import verify

KEY_FIELDS = ("nrc_number", "full_name", "date_of_birth")


def _offset_box(box, off):
    if not box:
        return box
    return [box[0] + off[0], box[1] + off[1], box[2] + off[0], box[3] + off[1]]


def _offset_field(f, off):
    from .extraction import Field
    return Field(value=f.value, confidence=f.confidence, bbox=_offset_box(f.bbox, off), raw=f.raw)


def _process_split(image, page_info, record):
    """Process a multi-card page by splitting it into per-card jobs (in parallel) and merging.

    Two threads OCR two card crops instead of one giant page. Per-card extraction
    works unchanged (it just sees a small clean card). Falls back to None when the
    data-side card cannot be anchored — the caller then uses the whole-page path.
    """
    from concurrent.futures import ThreadPoolExecutor

    from .extraction import Extraction, extract

    cards = page_info["cards"]
    jobs = []
    for i, (x, y, w, h) in enumerate(cards):
        pad = int(0.02 * w)
        x0, y0 = max(0, x - pad), max(0, y - pad)
        crop = image[y0:min(image.shape[0], y + h + pad), x0:min(image.shape[1], x + w + pad)]
        jobs.append((crop, (x0, y0)))

    with ThreadPoolExecutor(max_workers=2) as pool:
        extracted = list(pool.map(lambda jb: extract(jb[0], None, page_cards=[(0, 0, jb[0].shape[1], jb[0].shape[0])]), jobs))

    data_ex = data_off = photo_ex = photo_off = None
    for e, (crop, off) in zip(extracted, jobs):
        if e.anchored:
            data_ex, data_off = e, off
        else:
            photo_ex, photo_off = e, off
    if data_ex is None:
        # The two "cards" might be front/back on the same side; try harder: pick the
        # card whose tokens contain the data-side anchor.
        return None

    merged = Extraction()
    merged.tokens = data_ex.tokens
    merged.skew_deg = data_ex.skew_deg
    merged.anchored = True
    merged.deskew_matrix = None          # boxes are already mapped to page coordinates
    merged.deskewed = image
    merged.warnings = ["Multi-card page: cards were read separately; check the card number against the image."]
    merged.warnings += list(data_ex.warnings)
    if photo_ex is not None:
        merged.warnings += [w for w in photo_ex.warnings if "anchor" not in w.lower()]

    for k, f in data_ex.fields.items():
        if k == "nrc_number" and photo_ex is not None and photo_ex.fields.get("nrc_number") and photo_ex.fields["nrc_number"].value:
            continue                     # prefer the photo-side read when it exists
        merged.fields[k] = _offset_field(f, data_off)
    for key, e, off in (("nrc_number", photo_ex, photo_off), ("card_number", photo_ex, photo_off), ("card_number", data_ex, data_off)):
        f = e.fields.get(key) if e is not None else None
        if f and f.value and (key not in merged.fields or not merged.fields[key].value):
            merged.fields[key] = _offset_field(f, off)
    for key in list(data_ex.forensic_boxes):
        merged.forensic_boxes[key] = _offset_box(data_ex.forensic_boxes[key], data_off)
    if photo_ex is not None and photo_ex.forensic_boxes.get("nrc_number"):
        merged.forensic_boxes["nrc_number"] = _offset_box(photo_ex.forensic_boxes["nrc_number"], photo_off)
    return merged


def _to_deskewed(bbox, M):
    if not bbox or M is None:
        return bbox
    x0, y0, x1, y1 = bbox
    pts = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]], float) @ np.asarray(M).T
    return [int(pts[:, 0].min()), int(pts[:, 1].min()), int(pts[:, 0].max()), int(pts[:, 1].max())]


def _restore_cached(payload: dict, disp: np.ndarray):
    """Rebuild an Extraction-like object from a cached payload (bboxes are in display coords)."""
    from .extraction import Extraction, Field

    ex = Extraction()
    ex.skew_deg = payload.get("skew_deg", 0.0)
    ex.anchored = payload.get("anchored", True)
    ex.warnings = list(payload.get("warnings", []))
    ex.deskew_matrix = None          # no re-mapping of bboxes
    ex.deskewed = disp
    ex.forensic_boxes = payload.get("forensic_boxes", {})
    for k, v in payload.get("fields", {}).items():
        ex.fields[k] = Field(v.get("value"), v.get("confidence", 0.0), bbox=v.get("bbox"), raw=v.get("raw", ""))
    return ex


def process(image: np.ndarray, record: dict | None = None, tokens: list | None = None) -> tuple[dict, np.ndarray]:
    """Run the full pipeline. Returns (result dict, deskewed image for display)."""
    t0 = time.time()
    cache_key = None
    if tokens:
        toks = [Token(t, c, np.array(q)) for q, t, c in tokens]
        page_info = {"scaled": False, "scale": 1.0, "cards": []}
        ex = extract(image, toks)
        disp = ex.deskewed if ex.deskewed is not None else image
    else:
        image, page_info = normalize_page(image)
        cache_key = _cache.key_for(image)
        cached_payload, cached_disp = _cache.load(cache_key)
        if cached_payload is not None:
            ex = _restore_cached(cached_payload, cached_disp)
            page_info = cached_payload.get("page", page_info)
            disp = cached_disp
        else:
            ex = _process_split(image, page_info, record) if len(page_info["cards"]) >= 2 else None
            if ex is not None:
                disp = image
            else:
                toks = run_ocr(image)
                ex = extract(image, toks, page_cards=page_info.get("cards") or None)
                disp = ex.deskewed if ex.deskewed is not None else image
    t_ocr = time.time()
    t_ext = t_ocr          # extraction happens inside the branches above
    fields = {k: f.value for k, f in ex.fields.items()}
    conf = {k: f.confidence for k, f in ex.fields.items()}

    verification = verify(fields, record)
    t_ver = time.time()
    flags = F.rule_flags(fields, conf)
    if verification["overall"] == "mismatch":
        bad = [k for k, c in verification["checks"].items() if c["outcome"] == "mismatch"]
        flags.append(F._flag("RECORD_MISMATCH", "high", "Doesn't match captured record",
                             "Mismatch on: " + ", ".join(F.FIELD_LABEL[b] for b in bad) + ".", bad[0] if bad else None))
    order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: order[f["severity"]])
    rk = F.risk(flags, verification)
    t_end = time.time()

    ext = ex.to_dict()
    for k, f in ext["fields"].items():
        f["bbox"] = _to_deskewed(f["bbox"], ex.deskew_matrix)
    if cache_key:
        payload = {"fields": ext["fields"], "forensic_boxes": ex.forensic_boxes,
                   "skew_deg": ex.skew_deg, "anchored": ex.anchored,
                   "warnings": ex.warnings, "page": page_info}
        _cache.store(cache_key, payload, disp)
    disp = ex.deskewed if ex.deskewed is not None else image
    result = {
        "extraction": ext,
        "forensic_boxes": ex.forensic_boxes,
        "verification": verification,
        "flags": flags,
        "risk": rk,
        "image_size": [int(disp.shape[1]), int(disp.shape[0])],
        "page": page_info,
        "timing_ms": {"ocr": round((t_ocr - t0) * 1000), "extraction": round((t_ext - t_ocr) * 1000),
                      "verification": round((t_ver - t_ext) * 1000), "flagging": round((t_end - t_ver) * 1000),
                      "total": round((t_end - t0) * 1000)},
    }
    return result, disp


def encode_png(img: np.ndarray) -> bytes:
    return cv2.imencode(".png", img)[1].tobytes()

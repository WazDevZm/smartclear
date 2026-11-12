"""SmartClear pipeline: Scanned NRC -> AI/OCR extraction -> record verification -> flagging -> officer review."""
from __future__ import annotations

import copy
import dataclasses
import re
import time

import cv2
import numpy as np

from . import cache as _cache
from . import flags as F
from .cards import normalize_page
from .extraction import DIGIT_FIX, REG_RE, Token, extract, run_ocr
from .verify import verify

KEY_FIELDS = ("nrc_number", "full_name", "date_of_birth")


def _orientation_score(tokens: list[Token]) -> tuple[float, bool, int, int]:
    useful = [token for token in tokens if token.conf >= 0.35]
    horizontal = sum(token.w >= token.h for token in useful)
    vertical = len(useful) - horizontal
    score = sum(token.conf if token.w >= token.h else -1.5 * token.conf for token in useful)
    normalized = [re.sub(r"[^A-Z0-9/]", "", token.text.upper()) for token in useful]
    has_title = any("REGIST" in text and "CARD" in text for text in normalized)
    has_nrc = any(REG_RE.search(text.translate(DIGIT_FIX)) for text in normalized)
    score += 12 * has_title + 8 * has_nrc + min(len(useful), 20) * 0.15
    return score, has_title or has_nrc, horizontal, vertical


def _orient_page(image: np.ndarray, tokens: list[Token] | None = None) -> tuple[np.ndarray, list[Token], int]:
    """Try quarter-turns only when OCR does not show a readable card orientation."""
    if min(image.shape[:2]) < 160:
        return image, tokens if tokens is not None else [], 0

    original_tokens = tokens if tokens is not None else run_ocr(image)
    original_score, has_anchor, horizontal, vertical = _orientation_score(original_tokens)
    if has_anchor and horizontal >= vertical:
        return image, original_tokens, 0

    if vertical > horizontal:
        rotations = (
            (90, cv2.ROTATE_90_CLOCKWISE),
            (270, cv2.ROTATE_90_COUNTERCLOCKWISE),
        )
    elif horizontal > vertical:
        rotations = ((180, cv2.ROTATE_180),)
    else:
        rotations = (
            (90, cv2.ROTATE_90_CLOCKWISE),
            (180, cv2.ROTATE_180),
            (270, cv2.ROTATE_90_COUNTERCLOCKWISE),
        )
    best = (original_score, image, original_tokens, 0)
    for degrees, code in rotations:
        rotated = cv2.rotate(image, code)
        rotated_tokens = run_ocr(rotated)
        score, _, _, _ = _orientation_score(rotated_tokens)
        if score > best[0]:
            best = (score, rotated, rotated_tokens, degrees)
    return best[1], best[2], best[3]


TITLE_SCALE_TOLERANCE = 0.2   # rescale when the printed title is >20% off its calibrated width
LOW_RES_SIDE = 1600           # pages smaller than this get a 2x retry when no title is found


def _rescale_to_title(image: np.ndarray, tokens: list[Token]) -> tuple[np.ndarray, list[Token], float]:
    """Resize the page so the 'REGISTRATION CARD' title has its calibrated width.

    Field zones and the zone re-read (2x crops) were calibrated at that size; a high-resolution
    scan or phone photo otherwise produces oversized crops that the detector shrinks and misreads.
    Costs one extra OCR pass, only for pages that are far off the calibrated size."""
    from .extraction import REFERENCE_TITLE_WIDTH

    def find_title(toks):
        return next((t for t in toks if "REGISTRATIONCARD" in re.sub(r"[^A-Z]", "", t.text.upper())
                     and t.w > 30), None)

    title = find_title(tokens)
    base = 1.0
    if title is None and max(image.shape[:2]) < LOW_RES_SIDE:
        # Low-resolution scan: the title may be too small to read at all. Look again at 2x.
        up = cv2.resize(image, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        up_tokens = run_ocr(up)
        if find_title(up_tokens) is not None:
            image, tokens, base = up, up_tokens, 2.0
            title = find_title(tokens)
    if title is None:
        return image, tokens, base
    scale = REFERENCE_TITLE_WIDTH / title.w
    if abs(scale - 1.0) <= TITLE_SCALE_TOLERANCE:
        return image, tokens, base
    scale = float(np.clip(scale, 0.25, 3.0))
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    resized = cv2.resize(image, None, fx=scale, fy=scale, interpolation=interp)
    return resized, run_ocr(resized), base * scale


def _offset_box(box, off):
    if not box:
        return box
    return [box[0] + off[0], box[1] + off[1], box[2] + off[0], box[3] + off[1]]


def _offset_field(f, off):
    # keep every attribute (district correction / suggestion included), move only the box
    return dataclasses.replace(f, bbox=_offset_box(f.bbox, off))


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
    elif photo_ex is not None and photo_ex.fields.get("nrc_number") and photo_ex.fields["nrc_number"].bbox:
        # the photo side is not anchored, so it has no forensic box: use the number's OCR box
        x0, y0, x1, y1 = _offset_box(photo_ex.fields["nrc_number"].bbox, photo_off)
        merged.forensic_boxes["nrc_number"] = [x0 - 6, y0 - 4, x1 + 6, y1 + 4]
    # drop any degenerate box (e.g. an expected-offset guess clipped at the card edge)
    merged.forensic_boxes = {k: b for k, b in merged.forensic_boxes.items()
                             if b and b[2] - b[0] > 4 and b[3] - b[1] > 4}
    merged.side = data_ex.side
    merged.layout_scale = data_ex.layout_scale
    merged.vertical_stretch = data_ex.vertical_stretch
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
    ex.side = payload.get("side", "front" if ex.anchored else "unknown")
    ex.layout_scale = payload.get("layout_scale", 1.0)
    ex.vertical_stretch = payload.get("vertical_stretch", 1.0)
    ex.warnings = list(payload.get("warnings", []))
    ex.deskew_matrix = None          # no re-mapping of bboxes
    ex.deskewed = disp
    ex.forensic_boxes = payload.get("forensic_boxes", {})
    for k, v in payload.get("fields", {}).items():
        ex.fields[k] = Field(v.get("value"), v.get("confidence", 0.0), bbox=v.get("bbox"), raw=v.get("raw", ""),
                             corrected_from=v.get("corrected_from"), suggestion=v.get("suggestion"),
                             match_score=v.get("match_score"))
    return ex


def process(image: np.ndarray, record: dict | None = None, tokens: list | None = None) -> tuple[dict, np.ndarray]:
    """Run the full pipeline. Returns (result dict, deskewed image for display)."""
    t0 = time.time()
    cache_key = None
    cached_tamper = None
    rotation = 0
    if tokens:
        # Pre-computed OCR tokens (evaluation scripts, tests): no page normalisation or caching
        toks = tokens if isinstance(tokens[0], Token) else [Token(t, c, np.array(q)) for q, t, c in tokens]
        page_info = {"scaled": False, "scale": 1.0, "cards": []}
        image, toks, rotation = _orient_page(image, toks)
        ex = extract(image, toks)
        disp = ex.deskewed if ex.deskewed is not None else image
    else:
        image, page_info = normalize_page(image)
        cache_key = _cache.key_for(image)
        cached_payload, cached_disp = _cache.load(cache_key)
        if cached_payload is not None:
            ex = _restore_cached(cached_payload, cached_disp)
            page_info = cached_payload.get("page", page_info)
            rotation = page_info.get("rotation_degrees", 0)
            cached_tamper = cached_payload.get("tamper")
            disp = cached_disp
        else:
            ex = _process_split(image, page_info, record) if len(page_info["cards"]) >= 2 else None
            if ex is not None:
                disp = image
            else:
                # one OCR pass, reused by extraction unless the page has to be turned or resized
                image, toks, rotation = _orient_page(image)
                if not page_info.get("cards"):
                    image, toks, title_scale = _rescale_to_title(image, toks)
                    if title_scale != 1.0:
                        page_info["title_scale"] = round(title_scale, 3)
                ex = extract(image, toks, page_cards=page_info.get("cards") or None)
                disp = ex.deskewed if ex.deskewed is not None else image
    page_info["rotation_degrees"] = rotation
    t_ocr = time.time()
    t_ext = t_ocr          # extraction happens inside the branches above
    fields = {k: f.value for k, f in ex.fields.items()}
    conf = {k: f.confidence for k, f in ex.fields.items()}

    verification = verify(fields, record)
    t_ver = time.time()
    scores = cached_tamper if cached_tamper is not None else F.tamper_scores(ex.deskewed, ex.forensic_boxes)
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
    if cache_key and cached_tamper is None:
        payload = {"fields": ext["fields"], "forensic_boxes": ex.forensic_boxes,
                   "skew_deg": ex.skew_deg, "anchored": ex.anchored, "side": ex.side,
                   "layout_scale": ex.layout_scale, "vertical_stretch": ex.vertical_stretch,
                   "warnings": ex.warnings, "tamper": scores, "page": page_info}
        _cache.store(cache_key, payload, disp)
    disp = ex.deskewed if ex.deskewed is not None else image
    if disp.ndim == 3:
        disp = cv2.cvtColor(disp, cv2.COLOR_BGR2GRAY)
    result = {
        "extraction": ext,
        "forensic_boxes": ex.forensic_boxes,
        "verification": verification,
        "tamper": {k: {"probability": v["probability"], "reasons": v["reasons"]} for k, v in scores.items()},
        "flags": flags,
        "risk": rk,
        "image_size": [int(disp.shape[1]), int(disp.shape[0])],
        "page": page_info,
        "timing_ms": {"ocr": round((t_ocr - t0) * 1000), "extraction": round((t_ext - t_ocr) * 1000),
                      "verification": round((t_ver - t_ext) * 1000), "flagging": round((t_end - t_ver) * 1000),
                      "total": round((t_end - t0) * 1000)},
    }
    return result, disp


def process_pages(
    images: list[np.ndarray],
    record: dict | None = None,
    tokens: list | None = None,
) -> tuple[dict, np.ndarray, list[dict]]:
    """Extract each page independently and merge front/back-owned fields."""
    if not images:
        raise ValueError("At least one document page is required")

    runs = []
    for image in images:
        supplied = tokens if len(images) == 1 else None
        if supplied and isinstance(supplied[0], Token):
            page_tokens = supplied
        elif supplied:
            page_tokens = [Token(text, confidence, np.array(quad))
                           for quad, text, confidence in supplied]
        else:
            page_tokens = None
        result, preview = process(image, record, page_tokens)   # orients the page itself
        runs.append((result, preview, result.get("page", {}).get("rotation_degrees", 0)))

    front_index = next((i for i, (result, _, _) in enumerate(runs)
                        if result["extraction"]["side"] == "front"), None)
    back_index = next((i for i, (result, _, _) in enumerate(runs)
                       if result["extraction"]["side"] == "back"), None)
    primary_index = front_index if front_index is not None else back_index
    if primary_index is None:
        primary_index = 0

    widths = [preview.shape[1] for _, preview, _ in runs]
    heights = [preview.shape[0] for _, preview, _ in runs]
    offsets = []
    cursor_y = 0
    for height in heights:
        offsets.append(cursor_y)
        cursor_y += height + 24
    canvas = np.full((cursor_y - 24, max(widths), 3), 255, dtype=np.uint8)
    for (_, preview, _), y in zip(runs, offsets):
        if preview.ndim == 2:
            preview = cv2.cvtColor(preview, cv2.COLOR_GRAY2BGR)
        h, w = preview.shape[:2]
        canvas[y:y + h, :w] = preview
    selected_for_field = {}
    for name in runs[primary_index][0]["extraction"]["fields"]:
        preferred = back_index if name == "nrc_number" else front_index
        candidates = [preferred] if preferred is not None else []
        candidates += [i for i in range(len(runs)) if i not in candidates]
        source = next((i for i in candidates
                       if runs[i][0]["extraction"]["fields"][name]["value"]), None)
        if source is None:
            source = preferred if preferred is not None else primary_index
        selected_for_field[name] = source

    extraction = copy.deepcopy(runs[primary_index][0]["extraction"])
    forensic_boxes = {}
    tamper = {}
    for name, source in selected_for_field.items():
        source_result = runs[source][0]
        extraction["fields"][name] = copy.deepcopy(source_result["extraction"]["fields"][name])
        box = extraction["fields"][name]["bbox"]
        if box:
            box[1] += offsets[source]
            box[3] += offsets[source]
            extraction["fields"][name]["page_index"] = source
        source_box = source_result["forensic_boxes"].get(name)
        if source_box:
            forensic_boxes[name] = [source_box[0], source_box[1] + offsets[source],
                                    source_box[2], source_box[3] + offsets[source]]
        if name in source_result["tamper"]:
            tamper[name] = copy.deepcopy(source_result["tamper"][name])

    merged_fields = {name: field["value"] for name, field in extraction["fields"].items()}
    confidence = {name: field["confidence"] for name, field in extraction["fields"].items()}
    verification = verify(merged_fields, record)
    flags = F.rule_flags(merged_fields, confidence) + F.model_flags(tamper)
    if verification["overall"] == "mismatch":
        bad = [name for name, check in verification["checks"].items() if check["outcome"] == "mismatch"]
        flags.append(F._flag("RECORD_MISMATCH", "high", "Doesn't match captured record",
                             "Mismatch on: " + ", ".join(F.FIELD_LABEL[name] for name in bad) + ".",
                             bad[0] if bad else None))
    order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda flag: order[flag["severity"]])
    risk = F.risk(flags, verification, tamper)

    warnings = []
    page_details = []
    for index, (result, _, rotation) in enumerate(runs):
        side = result["extraction"]["side"]
        page_details.append({"index": index, "side": side, "rotation_degrees": rotation})
        warnings.extend(f"Page {index + 1}: {warning}" for warning in result["extraction"]["warnings"])
        if rotation:
            warnings.append(f"Page {index + 1}: automatically rotated {rotation} degrees for reading.")
        if side == "unknown":
            warnings.append(f"Page {index + 1}: page side was not recognized; its text was not used.")
    extraction["warnings"] = warnings

    categories = ("ocr", "extraction", "verification", "flagging", "total")
    timing = {key: sum(result["timing_ms"][key] for result, _, _ in runs) for key in categories}
    result = {
        "extraction": extraction,
        "forensic_boxes": forensic_boxes,
        "verification": verification,
        "tamper": tamper,
        "flags": flags,
        "risk": risk,
        "image_size": [canvas.shape[1], canvas.shape[0]],
        "timing_ms": timing,
        "pages": page_details,
    }
    return result, canvas, page_details


def encode_png(img: np.ndarray) -> bytes:
    return cv2.imencode(".png", img)[1].tobytes()

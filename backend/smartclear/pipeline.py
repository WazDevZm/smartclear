"""SmartClear pipeline: Scanned NRC -> AI/OCR extraction -> record verification -> flagging -> officer review."""
from __future__ import annotations

import copy
import re
import time

import cv2
import numpy as np

from . import flags as F
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


def _to_deskewed(bbox, M):
    if not bbox or M is None:
        return bbox
    x0, y0, x1, y1 = bbox
    pts = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]], float) @ np.asarray(M).T
    return [int(pts[:, 0].min()), int(pts[:, 1].min()), int(pts[:, 0].max()), int(pts[:, 1].max())]


def process(image: np.ndarray, record: dict | None = None, tokens: list | None = None) -> tuple[dict, np.ndarray]:
    """Run the full pipeline. Returns (result dict, deskewed image for display)."""
    t0 = time.time()
    if tokens and isinstance(tokens[0], Token):
        toks = tokens
    elif tokens:
        toks = [Token(t, c, np.array(q)) for q, t, c in tokens]
    else:
        toks = run_ocr(image)
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
        oriented, page_tokens, rotation = _orient_page(image, page_tokens)
        result, preview = process(oriented, record, page_tokens)
        runs.append((result, preview, rotation))

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

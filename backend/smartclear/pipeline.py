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


def process(image: np.ndarray, record: dict | None = None, tokens: list | None = None,
            force_crop: bool = False) -> tuple[dict, np.ndarray]:
    """Run the full pipeline. Returns (result dict, deskewed image for display)."""
    t0 = time.time()
    if tokens is not None and isinstance(tokens, list) and not tokens:
        toks = []
    elif tokens and isinstance(tokens[0], Token):
        toks = tokens
    elif tokens:
        toks = [Token(t, c, np.array(q)) for q, t, c in tokens]
    else:
        toks = run_ocr(image)
    t_ocr = time.time()
    ex = extract(image, toks, force_crop=force_crop)
    t_ext = time.time()
    fields = {k: f.value for k, f in ex.fields.items()}
    conf = {k: f.confidence for k, f in ex.fields.items()}

    verification = verify(fields, record)
    t_ver = time.time()
    scores = F.tamper_scores(ex.deskewed, ex.forensic_boxes)
    flags = F.rule_flags(fields, conf) + F.model_flags(scores)
    for name, field_result in ex.fields.items():
        if field_result.status_reason in (
            "Full-page OCR and field-crop OCR disagree.",
            "Only one OCR pass produced a field reading.",
        ):
            flags.append(F._flag(
                "OCR_CROP_DISAGREEMENT", "medium", f"{name.replace('_', ' ').title()} needs review",
                "The full-page and field-crop reads differed or one pass found no text.", name,
                {"candidates": field_result.alternatives},
            ))
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
    force_crop: bool = False,
    page_isolated: list[bool] | None = None,
    page_sources: list[dict] | None = None,
) -> tuple[dict, np.ndarray, list[dict]]:
    """Extract each page independently and merge front/back-owned fields."""
    if not images:
        raise ValueError("At least one document page is required")

    if page_isolated is None:
        page_isolated = [True] * len(images)
    if len(page_isolated) != len(images):
        raise ValueError("Each document page needs a card-isolation status")
    if page_sources is None:
        page_sources = [{"source_page_index": i, "card_index": None} for i in range(len(images))]
    if len(page_sources) != len(images):
        raise ValueError("Each card crop needs its source page metadata")

    runs = []
    for page_index, image in enumerate(images):
        if not page_isolated[page_index]:
            # Keep the uncropped page for evidence, but never submit page text to OCR.
            blank = np.full_like(image, 255)
            skipped, _ = process(blank, record, tokens=[], force_crop=False)
            skipped["extraction"]["fields"]["special_marks"] = {
                "value": "NIL", "confidence": 0.0, "bbox": None, "raw": "DEFAULT:NIL",
                "status": "accepted", "status_reason": "Defaulted to NIL for the current workflow.",
                "alternatives": [],
            }
            skipped["extraction"]["warnings"] = [
                "Card edges were not confidently isolated; this page was not read."
            ]
            preview = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
            runs.append((skipped, preview, 0))
            continue
        supplied = tokens if len(images) == 1 else None
        if supplied and isinstance(supplied[0], Token):
            page_tokens = supplied
        elif supplied:
            page_tokens = [Token(text, confidence, np.array(quad))
                           for quad, text, confidence in supplied]
        else:
            page_tokens = None
        oriented, page_tokens, rotation = _orient_page(image, page_tokens)
        result, preview = process(oriented, record, page_tokens, force_crop=force_crop)
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
    field_names = runs[primary_index][0]["extraction"]["fields"]
    for name in field_names:
        if name == "nrc_number":
            # NRC number is normally on the back, with front as a same-card fallback.
            choices = [i for i in (back_index, front_index) if i is not None]
            source = next((i for i in choices
                           if runs[i][0]["extraction"]["fields"][name]["value"]), None)
            selected_for_field[name] = source if source is not None else (choices[0] if choices else primary_index)
        elif name == "special_marks":
            # This field is a configured NIL default, not OCR from either side.
            selected_for_field[name] = front_index if front_index is not None else primary_index
        else:
            # Front-side fields must never be borrowed from a back-side page.
            selected_for_field[name] = front_index

    extraction = copy.deepcopy(runs[primary_index][0]["extraction"])
    forensic_boxes = {}
    crop_boxes = {}
    tamper = {}
    front_only_fields = set(field_names) - {"nrc_number", "special_marks"}
    for name, source in selected_for_field.items():
        if source is None and name in front_only_fields:
            extraction["fields"][name] = {
                "value": None, "confidence": 0.0, "bbox": None, "raw": "",
                "status": "unreadable",
                "status_reason": "Front of the card was not detected; this field was left blank.",
                "alternatives": [],
            }
            continue
        source = primary_index if source is None else source
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
        source_crop = source_result["extraction"].get("crop_boxes", {}).get(name)
        if source_crop:
            crop_boxes[name] = [source_crop[0], source_crop[1] + offsets[source],
                                source_crop[2], source_crop[3] + offsets[source]]
        if name in source_result["tamper"]:
            tamper[name] = copy.deepcopy(source_result["tamper"][name])

    merged_fields = {name: field["value"] for name, field in extraction["fields"].items()}
    confidence = {name: field["confidence"] for name, field in extraction["fields"].items()}
    verification = verify(merged_fields, record)
    flags = F.rule_flags(merged_fields, confidence) + F.model_flags(tamper)
    for name, field_result in extraction["fields"].items():
        if field_result.get("status_reason") in (
            "Full-page OCR and field-crop OCR disagree.",
            "Only one OCR pass produced a field reading.",
        ):
            flags.append(F._flag(
                "OCR_CROP_DISAGREEMENT", "medium", f"{name.replace('_', ' ').title()} needs review",
                "The full-page and field-crop reads differed or one pass found no text.", name,
                {"candidates": field_result.get("alternatives", [])},
            ))
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
        source = page_sources[index]
        source_index = int(source.get("source_page_index", index))
        card_index = source.get("card_index")
        label = f"Page {source_index + 1}"
        if card_index is not None:
            label += f", card {int(card_index) + 1}"
        page_details.append({"index": index, "source_page_index": source_index,
                             "card_index": card_index, "side": side, "rotation_degrees": rotation})
        warnings.extend(f"{label}: {warning}" for warning in result["extraction"]["warnings"])
        if rotation:
            warnings.append(f"{label}: automatically rotated {rotation} degrees for reading.")
        if side == "unknown" and page_isolated[index]:
            warnings.append(f"{label}: page side was not recognized; its text was not used.")
    if front_index is None:
        warnings.append("No front side was detected; front-side fields were left blank rather than read from the back.")
    extraction["warnings"] = warnings
    extraction["crop_boxes"] = crop_boxes

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

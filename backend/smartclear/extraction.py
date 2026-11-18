"""AI/OCR extraction of NRC fields.

Pipeline:
  1. RapidOCR (PP-OCR detection + recognition on ONNX Runtime) reads every text line.
  2. The page side is identified from its registration-card title or NRC number.
  3. Front-side pages are deskewed using the median angle of detected text boxes.
  4. A card-relative coordinate frame is anchored on the printed title
     ("REGISTRATION CARD") and the card number line, so the layout survives shifts,
     small rotations and different scan offsets.
  5. Printed form labels are discarded by glyph height (data is typed larger), and the
     remaining data tokens are assigned to fields by zone.
  6. Values are normalised with field-specific character repair (O->0 in numbers etc.).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

DATE_RE = re.compile(r"(\d{2})[.,:\s]?(\d{2})[.,:\s]?(\d{2})$")
REG_RE = re.compile(r"(\d{6})\s*/\s*(\d{2})\s*/\s*(\d)")
CARD_RE = re.compile(r"(\d{8})")

DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "I": "1", "l": "1", "|": "1",
                           "i": "1", "S": "5", "s": "5", "B": "8", "G": "6", "Z": "2", "z": "2", "A": "4"})
ALPHA_FIX = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "6": "G", "4": "A", "|": "I"})

# Card-relative zones (pixels at native ~924px scan width, measured from the anchors
# below). dy is measured from the card-number baseline, dx from the left edge of the
# "REGISTRATION CARD" title. Calibrated on the synthetic specimens.
ZONES = {
    "name": (25, 50),
    "dob_row": (50, 84),
    "parent": (84, 104),
    "village_row": (104, 129),
    "chief_row": (129, 150),
    "special": (150, 172),
}
COL_DIVIDER = 198   # dx separating the left (personal) and right (district/date) columns
DOB_MAX_DX = 72     # DOB sits at the far left of its row
SEX_MIN_DX = 240

# Median "REGISTRATION CARD" title width across the synthetic training scans.
REFERENCE_TITLE_WIDTH = 195.1

# Field boxes in the card-relative frame: (dx0, dx1, dy0, dy1)
FIELD_BOXES = {
    "name": (-4, 345, 28, 56),
    "dob": (-16, 65, 52, 84),
    "pob": (65, 245, 52, 88),
    "sex": (240, 360, 50, 94),
    "parent": (60, 345, 82, 102),
    "village": (-4, 200, 106, 138),
    "district": (205, 350, 106, 138),
    "chief": (-4, 200, 132, 162),
    "registration_date": (200, 345, 128, 162),
    "special": (25, 160, 165, 190),
}

LONG_LABELS = ["DATEOFBIRTH", "PLACEOFBIRTH", "FATHERSMOTHERSPLACEOFBIRTH", "SPECIALMARKS", "REGISTRATIONDATE",
               "DATEOFRENUNCIATION", "FULLNAME", "VILLAGE", "DISTRICT", "REGISTRATIONNUMBER"]
SHORT_LABELS = ["SEX", "CHIEF", "CARDNO"]


def _is_label(word: str, conf: float = 1.0) -> bool:
    """Is this OCR word a fragment of a printed form label rather than typed data?
    Combines similarity to the label vocabulary with OCR confidence, because label
    fragments are tiny and read with low confidence."""
    from rapidfuzz import fuzz

    w = re.sub(r"[^A-Z]", "", word.upper())
    if not w:
        return not re.search(r"\d", word)   # pure numbers/dates are data
    if w in ("NIL",):
        return False
    if "ACEO" in w or "ACEOF" in w:
        return True
    if len(w) <= 6 and max(fuzz.ratio(w, l) for l in SHORT_LABELS) >= 80:
        return True
    if len(w) < 4:
        return conf < 0.9
    score = max(fuzz.partial_ratio(w, l) for l in LONG_LABELS)
    return score >= 80 or (score >= 58 and conf < 0.9)


def _is_district_token(text: str) -> bool:
    t = text.upper().replace(" ", "")
    return bool(re.match(r"^[DO0]\s*[.,]", t))


def _strip_d(text: str) -> str:
    return re.sub(r"^\s*[DO0]\s*[.,]\s*", "", text.upper())


def _find_vertical_rule(image: np.ndarray, expected_x: float, y0: float, y1: float,
                        radius: int = 12) -> int | None:
    """Snap a template boundary to a nearby printed vertical field divider."""
    import cv2

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    top = max(0, int(y0))
    bottom = min(gray.shape[0], int(y1))
    if bottom - top < 10:
        return None
    block = max(9, min(31, ((bottom - top) // 2) | 1))
    if block % 2 == 0:
        block += 1
    block = min(block, (min(gray.shape[:2]) | 1))
    if block < 3:
        return None
    ink = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, block, 7
    )
    projection = (ink[top:bottom] > 0).sum(axis=0)
    center = int(round(expected_x))
    left, right = max(0, center - radius), min(gray.shape[1], center + radius + 1)
    if right <= left:
        return None
    best = left + int(np.argmax(projection[left:right]))
    if projection[best] < max(5, round((bottom - top) * 0.24)):
        return None
    return best


def _fit_field_dividers(name: str, bounds: tuple[float, float, float, float], image: np.ndarray,
                        x_left: float, y_anchor: float, scale: float) -> tuple[float, float, float, float]:
    """Adjust known field boxes to the card's detected printed column rules."""
    x0, y0, x1, y1 = bounds
    row = {
        "dob": FIELD_BOXES["dob"], "pob": FIELD_BOXES["pob"], "sex": FIELD_BOXES["sex"],
        "village": FIELD_BOXES["village"], "district": FIELD_BOXES["district"],
        "chief": FIELD_BOXES["chief"], "registration_date": FIELD_BOXES["registration_date"],
    }.get(name)
    if row is None:
        return bounds
    row_top = y_anchor + row[2] * scale
    row_bottom = y_anchor + row[3] * scale

    if name in ("dob", "pob"):
        expected = x_left + 65 * scale
        divider = _find_vertical_rule(image, expected, row_top, row_bottom)
        if divider is not None:
            if name == "dob":
                x1 = min(x1, divider - 2)
            else:
                x0 = max(x0, divider + 2)
    if name in ("pob", "sex"):
        expected = x_left + 238 * scale if name == "pob" else x_left + 240 * scale
        divider = _find_vertical_rule(image, expected, row_top, row_bottom)
        if divider is not None:
            if name == "pob":
                x1 = min(x1, divider - 2)
            else:
                x0 = max(x0, divider + 2)
    if name in ("village", "district", "chief", "registration_date"):
        expected = x_left + 198 * scale
        divider = _find_vertical_rule(image, expected, row_top, row_bottom)
        if divider is not None:
            if name in ("village", "chief"):
                x1 = min(x1, divider - 2)
            else:
                x0 = max(x0, divider + 2)
    return x0, y0, x1, y1


ALWAYS_CROP = {"name", "pob"}
REG_OFFSET = (194.0, -267.0)   # reg-number centre relative to (title-left, card-number line)


def _fuse(a: list[Token], b: list[Token]) -> list[Token]:
    """Merge reads of one zone from two OCR passes: keep the most confident read
    for each horizontal position, then order tokens line by line, left to right."""
    kept: list[Token] = []
    for t in sorted(a + b, key=lambda t: -t.conf):
        l, r = t.rx - t.w / 2, t.rx + t.w / 2
        clash = False
        for k in kept:
            kl, kr = k.rx - k.w / 2, k.rx + k.w / 2
            ov = min(r, kr) - max(l, kl)
            if ov > 0.35 * min(r - l, kr - kl) and abs(t.ry - k.ry) < 8:
                clash = True
                break
        if not clash:
            kept.append(t)
    return _reading_order(kept)


def _reading_order(toks: list[Token], line_tol: float = 9.0) -> list[Token]:
    """Group tokens into lines by vertical proximity, then order left-to-right."""
    lines: list[list[Token]] = []
    for t in sorted(toks, key=lambda t: t.ry):
        if lines and abs(t.ry - np.mean([x.ry for x in lines[-1]])) <= line_tol:
            lines[-1].append(t)
        else:
            lines.append([t])
    return [t for line in lines for t in sorted(line, key=lambda t: t.rx)]


def _join_line(toks: list[Token]) -> str:
    return "".join(t.text for t in sorted(toks, key=lambda t: t.rx))


def _deskew(image: np.ndarray, theta: float):
    import cv2

    H, W = image.shape[:2]
    M = cv2.getRotationMatrix2D((W / 2, H / 2), math.degrees(theta), 1.0)
    out = cv2.warpAffine(image, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return out, M


def ocr_view(image: np.ndarray) -> np.ndarray:
    """Normalize color and contrast for OCR without changing source pixels."""
    import cv2

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)


def _layout_scale(title: Token) -> float:
    # Slightly expand zones to absorb under-read title bounds on camera scans.
    return float(np.clip(title.w / REFERENCE_TITLE_WIDTH * 1.02, 0.65, 2.5))


def _read_zone(img: np.ndarray, M: np.ndarray, x0, y0, x1, y1, scale: float = 2.0,
               allow_short_data: bool = False, multipass: bool = False,
               ambiguity_reads: dict[str, list[str]] | None = None,
               variant_reads: dict[str, list[str]] | None = None,
               variant_scores: dict[str, list[tuple[str, float]]] | None = None,
               zone_name: str | None = None) -> list[Token]:
    """OCR a field crop with optional contrast variants and map reads to source coordinates."""
    import cv2

    H, W = img.shape[:2]
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    x1, y1 = min(W, int(x1)), min(H, int(y1))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return []

    source = img[y0:y1, x0:x1]
    gray = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY) if source.ndim == 3 else source
    variants = [ocr_view(source)]
    if multipass:
        # Keep the alternate crop treatment local and simple. Illumination
        # division fragmented faint characters on small NRC crops.
        binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        variants.append(cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR))

    Minv = cv2.invertAffineTransform(M)
    toks = []
    variant_texts = []
    scored_texts = []
    for variant in variants:
        pass_tokens = []
        scaled = cv2.resize(variant, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        scaled = cv2.copyMakeBorder(scaled, 12, 12, 12, 12, cv2.BORDER_REPLICATE)
        result, _ = get_engine()(scaled, use_cls=False)
        for quad, text, conf in result or []:
            q = (np.array(quad, dtype=float) - 12) / scale + [x0, y0]
            words = [
                w for w in str(text).split()
                if not _is_label(w, float(conf))
                or (allow_short_data and re.fullmatch(r"[MF]", w.strip().upper()))
            ]
            if not words:
                continue
            short_value = allow_short_data and all(re.fullmatch(r"[MF]", w.strip().upper()) for w in words)
            h = float(np.linalg.norm(q[3] - q[0]))
            if h < (2.5 if short_value else 7.5) or conf < 0.5:
                continue
            q_orig = np.hstack([q, np.ones((4, 1))]) @ Minv.T
            tk = Token(text=" ".join(words), conf=float(conf), quad=q_orig)
            tk.rx, tk.ry = q.mean(0)
            tk.w = float(np.linalg.norm(q[1] - q[0]))
            toks.append(tk)
            pass_tokens.append(tk)
        if pass_tokens:
            text = " ".join(t.text for t in _reading_order(pass_tokens)).strip()
            normalized = re.sub(r"[^A-Z0-9]", "", text.upper())
            if normalized and all(normalized != existing[0] for existing in variant_texts):
                variant_texts.append((normalized, text))
                scored_texts.append((normalized, text, float(np.mean([t.conf for t in pass_tokens]))))
    if variant_reads is not None and zone_name:
        variant_reads[zone_name] = [text for _, text in variant_texts]
    if variant_scores is not None and zone_name:
        variant_scores[zone_name] = [(text, score) for _, text, score in scored_texts]
    if ambiguity_reads is not None and zone_name and len(variant_texts) > 1:
        ambiguity_reads[zone_name] = [text for _, text in variant_texts]
    return _fuse(toks, [])

@lru_cache(maxsize=1)
def get_engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


@dataclass
class Token:
    text: str
    conf: float
    quad: np.ndarray            # 4x2 image coordinates
    cx: float = 0.0
    cy: float = 0.0
    w: float = 0.0
    h: float = 0.0
    angle: float = 0.0
    rx: float = 0.0             # deskewed, card-relative
    ry: float = 0.0

    def __post_init__(self):
        q = self.quad
        self.cx, self.cy = q.mean(0)
        self.w = float(np.linalg.norm(q[1] - q[0]))
        self.h = float(np.linalg.norm(q[3] - q[0]))
        self.angle = math.atan2(q[1][1] - q[0][1], q[1][0] - q[0][0])


@dataclass
class Field:
    value: str | None
    confidence: float
    bbox: list[int] | None = None          # x0,y0,x1,y1 in image coords
    raw: str = ""
    status: str | None = None
    status_reason: str | None = None
    alternatives: list[str] = field(default_factory=list)

    def to_dict(self):
        status = self.status
        if status is None:
            if self.value is None:
                status = "needs_review" if self.raw else "unreadable"
            else:
                status = "needs_review" if self.confidence < 0.8 else "accepted"
        reason = self.status_reason
        if reason is None and status == "needs_review":
            reason = "OCR confidence is below 0.80." if self.value else "OCR text was not a valid field value."
        return {"value": self.value, "confidence": round(self.confidence, 3), "bbox": self.bbox,
                "raw": self.raw, "status": status, "status_reason": reason,
                "alternatives": self.alternatives}


@dataclass
class Extraction:
    fields: dict[str, Field] = field(default_factory=dict)
    tokens: list[Token] = field(default_factory=list)
    skew_deg: float = 0.0
    layout_scale: float = 1.0
    side: str = "unknown"
    anchored: bool = True
    deskew_matrix: object = None
    deskewed: object = None                 # deskewed BGR image (not serialised)
    forensic_boxes: dict = field(default_factory=dict)   # field -> [x0,y0,x1,y1] in deskewed coords
    crop_boxes: dict = field(default_factory=dict)       # intended OCR regions in deskewed coords
    warnings: list[str] = field(default_factory=list)

    def value(self, name):
        f = self.fields.get(name)
        return f.value if f else None

    def to_dict(self):
        return {
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
            "skew_deg": round(self.skew_deg, 2),
            "layout_scale": round(self.layout_scale, 3),
            "side": self.side,
            "anchored": self.anchored,
            "warnings": self.warnings,
            "crop_boxes": self.crop_boxes,
        }


def _bbox(tokens: list[Token]) -> list[int] | None:
    if not tokens:
        return None
    pts = np.vstack([t.quad for t in tokens])
    x0, y0 = pts.min(0)
    x1, y1 = pts.max(0)
    return [int(x0), int(y0), int(math.ceil(x1)), int(math.ceil(y1))]


def _mk(tokens: list[Token], value: str | None, raw: str | None = None,
        status: str | None = None, status_reason: str | None = None) -> Field:
    conf = float(np.mean([t.conf for t in tokens])) if tokens else 0.0
    if status is None:
        if not tokens:
            status = "unreadable" if not value else "needs_review"
        elif not value or conf < 0.8:
            status = "needs_review"
        else:
            status = "accepted"
    return Field(value=value, confidence=conf, bbox=_bbox(tokens),
                 raw=raw if raw is not None else " ".join(t.text for t in tokens),
                 status=status, status_reason=status_reason)


def _clean_alpha(s: str) -> str:
    s = s.upper().translate(ALPHA_FIX)
    s = re.sub(r"[^A-Z .'\-]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_date(s: str) -> str | None:
    s = s.translate(DIGIT_FIX)
    m = DATE_RE.search(re.sub(r"[^\d.,:]", "", s))
    if not m:
        return None
    dd, mm, yy = m.groups()
    if not (1 <= int(dd) <= 31 and 1 <= int(mm) <= 12):
        return f"{dd}.{mm}.{yy}"  # keep — validity is checked by rules
    return f"{dd}.{mm}.{yy}"


def run_ocr(image: np.ndarray) -> list[Token]:
    result, _ = get_engine()(ocr_view(image), use_cls=False)
    toks = []
    for quad, text, conf in result or []:
        toks.append(Token(text=str(text).strip(), conf=float(conf), quad=np.array(quad, dtype=float)))
    return toks


def extract(image: np.ndarray, tokens: list[Token] | None = None, force_crop: bool = False) -> Extraction:
    toks = tokens if tokens is not None else run_ocr(image)
    ex = Extraction(tokens=toks)

    # --- 1. Deskew angle from wide, confident text lines
    angs = [t.angle for t in toks if t.w > 40 and t.conf > 0.8]
    theta = float(np.median(angs)) if angs else 0.0
    ex.skew_deg = math.degrees(theta)
    c, s = math.cos(-theta), math.sin(-theta)
    H, W = image.shape[:2]
    ox, oy = W / 2, H / 2

    def rot(x, y):
        x, y = x - ox, y - oy
        return x * c - y * s + ox, x * s + y * c + oy

    for t in toks:
        t.rx, t.ry = rot(t.cx, t.cy)

    # --- 2. Registration number (photo side) — highest confident match of the pattern
    reg_tok, reg_val = None, None
    for t in sorted(toks, key=lambda t: -t.conf):
        cand = t.text.translate(DIGIT_FIX).replace(" ", "")
        m = REG_RE.search(cand)
        if m:
            reg_tok, reg_val = t, f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
            break
    if reg_tok is None:
        # fallback: 9 digit run (OCR dropped the slashes)
        for t in toks:
            digits = re.sub(r"\D", "", t.text.translate(DIGIT_FIX))
            if len(digits) == 9 and not t.text.strip().upper().startswith("Z") and t.cy < image.shape[0] * 0.4:
                reg_tok, reg_val = t, f"{digits[:6]}/{digits[6:8]}/{digits[8]}"
                break
    ex.fields["nrc_number"] = _mk([reg_tok], reg_val) if reg_tok else Field(None, 0.0)

    # --- 3. Anchors on the data side
    title = next((t for t in toks
                  if "REGIST" in t.text.upper().replace(" ", "")
                  and "CARD" in t.text.upper().replace(" ", "") and t.w > 120), None)
    card_tok, card_val = None, None
    if title is not None:
        for t in toks:
            if reg_tok is not None and t is reg_tok:
                continue
            body = re.sub(r"^\s*[Z2]\s+|^\s*Z", "", t.text.strip().upper())
            m = CARD_RE.search(body.translate(DIGIT_FIX).replace(" ", ""))
            if m and t.h >= 12 and t.ry < title.ry + 15:
                card_tok, card_val = t, "Z" + m.group(1)
                break
    ex.fields["card_number"] = _mk([card_tok], card_val) if card_tok else Field(None, 0.0)

    if title is None:
        ex.side = "back" if reg_tok is not None and reg_tok.cy < image.shape[0] * 0.55 else "unknown"
        ex.anchored = False
        if ex.side == "unknown":
            ex.warnings.append("Could not identify this page as the NRC front or back.")
        for k in ("card_number", "full_name", "date_of_birth", "sex", "place_of_birth_village",
                  "place_of_birth_district", "parent_place_of_birth", "village", "district", "chief",
                  "registration_date", "special_marks"):
            ex.fields[k] = Field(None, 0.0)
        if ex.side == "unknown":
            ex.fields["nrc_number"] = Field(None, 0.0)
        return ex

    ex.side = "front"
    if card_tok is None:
        ex.anchored = False
        ex.warnings.append("Could not locate the card number beside the registration-card title.")
        for k in ("full_name", "date_of_birth", "sex", "place_of_birth_village", "place_of_birth_district",
                  "parent_place_of_birth", "village", "district", "chief", "registration_date", "special_marks"):
            ex.fields[k] = Field(None, 0.0)
        return ex

    x_left = title.rx - title.w / 2
    y0 = card_tok.ry
    ex.layout_scale = _layout_scale(title)
    deskewed, M = _deskew(image, theta)
    ex.deskew_matrix = M
    ex.deskewed = deskewed
    H_, W_ = deskewed.shape[:2]

    def _clip(b):
        return [max(0, int(b[0])), max(0, int(b[1])), min(W_, int(b[2])), min(H_, int(b[3]))]

    # Registration-number box (photo side): around the OCR'd token, or at its expected offset
    if reg_tok is not None:
        rcx, rcy = M @ [reg_tok.cx, reg_tok.cy, 1.0]
        rw, rh = max(reg_tok.w, 140), max(reg_tok.h, 22)
    else:
        rcx, rcy, rw, rh = x_left + REG_OFFSET[0] * ex.layout_scale, \
            y0 + REG_OFFSET[1] * ex.layout_scale, 152 * ex.layout_scale, 22 * ex.layout_scale
    ex.forensic_boxes["nrc_number"] = _clip([rcx - rw / 2 - 6, rcy - rh / 2 - 4, rcx + rw / 2 + 6, rcy + rh / 2 + 4])
    ex.crop_boxes["nrc_number"] = ex.forensic_boxes["nrc_number"]
    reads = {}
    crop_conflicts: dict[str, list[str]] = {}
    variant_reads: dict[str, list[str]] = {}
    variant_scores: dict[str, list[tuple[str, float]]] = {}
    crop_field_names = {
        "name": ("full_name",), "dob": ("date_of_birth",),
        "pob": ("place_of_birth_village", "place_of_birth_district"),
        "sex": ("sex",), "parent": ("parent_place_of_birth",),
        "village": ("village",), "district": ("district",),
        "chief": ("chief",), "registration_date": ("registration_date",),
    }
    scaled_boxes = {
        name: tuple(value * ex.layout_scale for value in box)
        for name, box in FIELD_BOXES.items()
    }
    for name, (x0, x1, y_lo, y_hi) in scaled_boxes.items():
        if name == "special":
            # Special marks are a configured NIL default in this workflow.
            reads[name] = []
            continue
        full = []
        for t in toks:
            if t is title or t is card_tok or t is reg_tok or t.h < 11.5 or t.conf < 0.5:
                continue
            dx, dy = t.rx - x_left, t.ry - y0
            # A full-card OCR token may span a printed divider (for example,
            # DOB plus place of birth). It cannot corroborate either field unless
            # its whole text box stays inside that field's own region.
            if (x0 - 3 <= dx - t.w / 2 and dx + t.w / 2 <= x1 + 3
                    and y_lo - 3 <= dy - t.h / 2 and dy + t.h / 2 <= y_hi + 3):
                words = [
                    w for w in t.text.split()
                    if not _is_label(w, t.conf)
                    or (name == "sex" and re.fullmatch(r"[MF]", w.strip().upper()))
                ]
                if words:
                    full.append(Token(text=" ".join(words), conf=t.conf, quad=t.quad, rx=t.rx, ry=t.ry))
        for ft in full:
            ft.rx, ft.ry = (M @ [ft.cx, ft.cy, 1.0])
        # On unisolated pages, always run a tight field crop even if full-page OCR
        # reports high confidence. Confidence alone is not calibrated truth.
        need_crop = force_crop or name in ALWAYS_CROP or not full or min(t.conf for t in full) < 0.95
        crop_bounds = (x_left + x0, y0 + y_lo, x_left + x1, y0 + y_hi)
        if name == "sex":
            # The one-character value is below the printed SEX label; use its data band only.
            crop_bounds = (x_left + x0 + 4, y0 + y_lo + 8, x_left + x1, y0 + y_hi - 2)
        elif name in ("dob", "pob"):
            # These rows print their labels above the typed values.
            crop_bounds = (x_left + x0, y0 + y_lo + 8, x_left + x1, y0 + y_hi - 2)
        elif name == "name":
            crop_bounds = (x_left + x0, y0 + y_lo + 4, x_left + x1, y0 + y_hi - 2)
        elif name in ("village", "district"):
            crop_bounds = (x_left + x0, y0 + y_lo + 6, x_left + x1, y0 + y_hi - 2)
        elif name in ("chief", "registration_date"):
            crop_bounds = (x_left + x0, y0 + y_lo + 6, x_left + x1, y0 + y_hi - 2)
        crop_bounds = _fit_field_dividers(name, crop_bounds, deskewed, x_left, y0, ex.layout_scale)
        crop_box = _clip(crop_bounds)
        for field_name in crop_field_names.get(name, ()):
            ex.crop_boxes[field_name] = crop_box
        crop = _read_zone(
            deskewed, M, *crop_bounds,
            scale=4.0 if name in ("sex", "district") else (3.0 if force_crop else 2.0),
            allow_short_data=name == "sex",
            multipass=name in ("name", "dob", "pob", "sex", "parent", "village", "district", "chief"),
            ambiguity_reads=crop_conflicts, variant_reads=variant_reads,
            variant_scores=variant_scores, zone_name=name,
        ) if need_crop else []
        full_text = " ".join(t.text for t in _reading_order(full)).strip()
        crop_text = " ".join(t.text for t in _reading_order(crop)).strip()
        norm_read = lambda value: re.sub(r"[^A-Z0-9]", "", value.upper())
        if need_crop and full_text and crop_text and norm_read(full_text) != norm_read(crop_text):
            crop_conflicts[name] = list(dict.fromkeys(
                crop_conflicts.get(name, []) + [x for x in (full_text, crop_text) if x]
            ))
        # When isolated field reading is required, full-card text can only
        # corroborate a token wholly inside the same field. Use it as a cautious
        # fallback only when the crop produced an implausibly short alpha fragment.
        if force_crop and name in ("name", "pob", "village", "district", "chief"):
            crop_letters = re.sub(r"[^A-Z]", "", _clean_alpha(crop_text))
            full_letters = re.sub(r"[^A-Z]", "", _clean_alpha(full_text))
            if len(crop_letters) < 3 <= len(full_letters):
                reads[name] = _fuse(full, [])
            else:
                reads[name] = crop
        else:
            reads[name] = crop if force_crop else _fuse(full, crop)

    def fld(name, value, toks):
        return _mk(toks, value)

    def _tight(toks_, zone_name, pad=4):
        zx0, zx1, zy0, zy1 = scaled_boxes[zone_name]
        if toks_:
            xs0 = [t.rx - t.w / 2 for t in toks_]
            xs1 = [t.rx + t.w / 2 for t in toks_]
            ys = [t.ry for t in toks_]
            return _clip([min(xs0) - pad, min(ys) - 10 - pad, max(xs1) + pad, max(ys) + 10 + pad])
        # nothing legible: use the zone's data band (skip the label strip at its top)
        return _clip([x_left + zx0 + 4, y0 + zy0 + 8, x_left + zx1, y0 + zy1 - 2])

    ex.forensic_boxes["full_name"] = _tight(reads["name"], "name")
    ex.forensic_boxes["date_of_birth"] = _tight([t for t in reads["dob"] if re.search(r"\d", t.text)], "dob")
    field_zones = {
        "place_of_birth_village": "pob", "place_of_birth_district": "pob",
        "sex": "sex", "parent_place_of_birth": "parent", "village": "village",
        "district": "district", "chief": "chief", "registration_date": "registration_date",
        "special_marks": "special",
    }
    for field_name, zone_name in field_zones.items():
        # Keep a field-sized evidence region even when OCR returns no reliable token.
        ex.forensic_boxes[field_name] = _tight([], zone_name)

    nm = reads["name"]
    ex.fields["full_name"] = fld("name", _clean_alpha(" ".join(t.text for t in nm)) or None, nm)

    dob = [t for t in reads["dob"] if re.search(r"\d", t.text)]
    dv = _parse_date(_join_line(dob)) if dob else None
    ex.fields["date_of_birth"] = fld("dob", dv, dob)

    def apply_date_candidates(field_name: str, zone_name: str) -> None:
        field_result = ex.fields[field_name]
        scores: dict[str, list[float]] = {}
        for text, score in variant_scores.get(zone_name, []):
            value = _parse_date(text)
            if value:
                scores.setdefault(value, []).append(score)
        ranked = sorted(((value, float(np.mean(values))) for value, values in scores.items()),
                        key=lambda item: item[1], reverse=True)
        candidates = [value for value, _ in ranked]
        if len(candidates) > 1:
            # Valid date syntax narrows the choices, but close OCR scores are not
            # enough evidence to silently decide between two real dates.
            gap = ranked[0][1] - ranked[1][1]
            field_result.value = ranked[0][0] if gap >= 0.12 else None
            field_result.status = "needs_review"
            field_result.status_reason = (
                f"Date candidates were ranked by OCR score; the top candidate scored "
                f"{ranked[0][1]:.0%} versus {ranked[1][1]:.0%}. Confirm against the card."
            )
            field_result.alternatives = candidates
        elif len(candidates) == 1 and field_result.value != candidates[0]:
            previous = field_result.value
            field_result.value = candidates[0]
            field_result.status = "needs_review"
            field_result.status_reason = "A field-crop treatment produced a valid date candidate; confirm against the card."
            field_result.alternatives = list(dict.fromkeys(
                [value for value in (previous, candidates[0]) if value]
            ))

    apply_date_candidates("date_of_birth", "dob")

    sx = [t for t in reads["sex"] if re.sub(r"\W", "", t.text)]
    if sx:
        raw_sex = re.sub(r"\W", "", sx[0].text.upper())
        if raw_sex in ("M", "F"):
            ex.fields["sex"] = fld("sex", raw_sex, sx[:1])
        else:
            ex.fields["sex"] = _mk(
                sx[:1], None, status="needs_review",
                status_reason="The OCR result is not an unambiguous M or F.",
            )
    else:
        ex.fields["sex"] = Field(None, 0.0)

    sex_scores: dict[str, list[float]] = {}
    for text, score in variant_scores.get("sex", []):
        candidate = re.sub(r"\W", "", text.upper())
        if candidate in ("M", "F"):
            sex_scores.setdefault(candidate, []).append(score)
    ranked_sex = sorted(((value, float(np.mean(scores))) for value, scores in sex_scores.items()),
                        key=lambda item: item[1], reverse=True)
    if len(ranked_sex) > 1:
        gap = ranked_sex[0][1] - ranked_sex[1][1]
        sex_field = ex.fields["sex"]
        sex_field.value = ranked_sex[0][0] if gap >= 0.12 else None
        sex_field.alternatives = [value for value, _ in ranked_sex]
        sex_field.status = "needs_review"
        sex_field.status_reason = (
            f"Sex candidates were ranked by OCR score; top candidate scored "
            f"{ranked_sex[0][1]:.0%} versus {ranked_sex[1][1]:.0%}. Confirm against the crop."
        )
    elif len(ranked_sex) == 1 and ex.fields["sex"].value != ranked_sex[0][0]:
        sex_field = ex.fields["sex"]
        previous = sex_field.value
        sex_field.value = ranked_sex[0][0]
        sex_field.alternatives = list(dict.fromkeys(
            [value for value in (previous, ranked_sex[0][0]) if value]
        ))
        sex_field.status = "needs_review"
        sex_field.status_reason = "One crop treatment produced a valid M/F candidate; confirm against the card."

    # Rank the independent crop treatments for single-value fields. The OCR
    # score helps order candidates; disagreement always remains visible for an
    # officer because RapidOCR confidence is not calibrated as truth.
    pob = sorted([t for t in reads["pob"] if not re.search(r"\d", t.text)], key=lambda t: t.ry)
    pv = [t for t in pob if not _is_district_token(t.text)]
    pdist = [t for t in pob if _is_district_token(t.text)]
    pob_value = _clean_alpha(pv[0].text) if pv else None
    # Repair a common OCR slip only when the place name strongly matches a known district.
    if pob_value:
        match = re.fullmatch(r"T\.?\s*([A-Z -]+)", pob_value)
        if match:
            from .gazetteer import snap_district
            suffix, corrected = snap_district(match.group(1).replace(" ", ""), min_score=78)
            if corrected and suffix == "MWANSABOMBWE":
                pob_value = "T." + suffix
    ex.fields["place_of_birth_village"] = fld("pob", pob_value, pv[:1])
    ex.fields["place_of_birth_district"] = fld("pob", _clean_alpha(_strip_d(pdist[0].text)) if pdist else None, pdist[:1])

    par = reads["parent"]
    par_raw = _clean_alpha(" ".join(t.text for t in par)) or None
    par_value = None
    par_status = "unreadable" if not par_raw else "needs_review"
    par_reason = None if not par_raw else "Parent-place OCR did not match the expected PLACE D.DISTRICT format."
    if par_raw:
        match = re.fullmatch(r"([A-Z][A-Z' -]{1,40}?)\s+D\.?\s*([A-Z][A-Z' -]{1,40})", par_raw)
        if match:
            from .gazetteer import snap_district, DISTRICT_PROVINCE
            parent_district, _ = snap_district(match.group(2).strip(), min_score=80)
            if parent_district and parent_district in DISTRICT_PROVINCE:
                par_value = f"{match.group(1).strip()} D.{parent_district}"
                par_status = None
                par_reason = None
    ex.fields["parent_place_of_birth"] = (
        _mk(par, par_value, status=par_status, status_reason=par_reason)
        if par_value else
        Field(None, float(np.mean([t.conf for t in par])) if par else 0.0,
              bbox=_bbox(par), raw=" ".join(t.text for t in par), status=par_status,
              status_reason=par_reason)
    )
    for key in ("village", "district", "chief"):
        toks_ = reads[key]
        value = _clean_alpha(" ".join(t.text for t in toks_)) or None
        if value and len(re.sub(r"[^A-Z]", "", value)) < 3:
            ex.fields[key] = Field(None, float(np.mean([t.conf for t in toks_])) if toks_ else 0.0,
                                   bbox=_bbox(toks_), raw=" ".join(t.text for t in toks_),
                                   status="unreadable", status_reason="OCR returned too little text to support this field.")
        else:
            ex.fields[key] = fld(key, value, toks_)

    ranked_field_zones = {
        "name": "full_name", "pob": "place_of_birth_village", "village": "village", "chief": "chief",
        "district": "district",
    }
    for zone_name, field_name in ranked_field_zones.items():
        ranked: dict[str, list[float]] = {}
        for text, score in variant_scores.get(zone_name, []):
            candidate = _clean_alpha(text)
            if len(re.sub(r"[^A-Z]", "", candidate)) >= 3:
                ranked.setdefault(candidate, []).append(score)
        ordered = sorted(((value, float(np.mean(scores))) for value, scores in ranked.items()),
                         key=lambda item: item[1], reverse=True)
        if len(ordered) < 2:
            continue
        field_result = ex.fields.get(field_name)
        if not field_result:
            continue
        gap = ordered[0][1] - ordered[1][1]
        field_result.value = ordered[0][0] if gap >= 0.12 else None
        field_result.alternatives = [value for value, _ in ordered]
        field_result.status = "needs_review"
        field_result.status_reason = (
            f"OCR crop treatments disagree; top candidate scored {ordered[0][1]:.0%} "
            f"versus {ordered[1][1]:.0%}. Confirm against the crop."
        )

    rd = [t for t in reads["registration_date"] if re.search(r"\d", t.text)]
    rv = _parse_date(_join_line(rd)) if rd else None
    ex.fields["registration_date"] = fld("rd", rv, rd)
    apply_date_candidates("registration_date", "registration_date")

    # Current workflow defaults Special Marks to NIL; do not treat it as OCR evidence.
    ex.fields["special_marks"] = Field(
        "NIL", 0.0, raw="DEFAULT:NIL", status="accepted",
        status_reason="Defaulted to NIL for the current workflow.",
    )
    from .gazetteer import snap_district, DISTRICT_PROVINCE
    pp = ex.fields.get("parent_place_of_birth")
    if pp and pp.value:
        m = re.match(r"^(.*?)\s*D\s*\.\s*([A-Z' -]+)$", pp.value)
        if m:
            dist, _ = snap_district(m.group(2).strip())
            pp.value = f"{m.group(1).strip()} D.{dist}".strip()

    zone_fields = {
        "name": ("full_name",), "dob": ("date_of_birth",),
        "pob": ("place_of_birth_village", "place_of_birth_district"),
        "sex": ("sex",), "parent": ("parent_place_of_birth",),
        "village": ("village",), "district": ("district",), "chief": ("chief",),
        "registration_date": ("registration_date",), "special": ("special_marks",),
    }
    for zone, alternatives in crop_conflicts.items():
        for field_name in zone_fields.get(zone, ()):
            field_result = ex.fields.get(field_name)
            if field_name == "special_marks" and field_result and field_result.value == "NIL":
                continue
            if field_result:
                field_result.alternatives = alternatives
                field_result.status = "needs_review"
                field_result.status_reason = (
                    "Full-page OCR and field-crop OCR disagree."
                    if len(alternatives) > 1 else
                    "Only one OCR pass produced a field reading."
                )

    # A weak crop-only guess in this optional row often comes from the printed label.
    parent = ex.fields.get("parent_place_of_birth")
    if (parent and "parent" in crop_conflicts and len(crop_conflicts["parent"]) == 1
            and parent.confidence < 0.85):
        parent.value = None
        parent.status = "unreadable"
        parent.status_reason = "No reliable text was found in the parent-place field."
        parent.alternatives = []

    # Use the directory for low-confidence or noncanonical district OCR.
    from .gazetteer import suggest_district
    for key in ("place_of_birth_district", "district"):
        field_result = ex.fields.get(key)
        if not field_result or (not field_result.value and not field_result.alternatives):
            continue
        ocr_value = (field_result.value or "").strip().upper()
        exact_value = " ".join(ocr_value.replace(".", " ").split())
        if field_result.value and exact_value in DISTRICT_PROVINCE and field_result.confidence >= 0.90:
            continue

        source_reads = list(dict.fromkeys(
            [ocr_value] + [item.strip().upper() for item in field_result.alternatives if item.strip()]
        ))
        matches = {}
        for source_read in source_reads:
            candidate, similarity, margin = suggest_district(source_read, min_score=85, min_margin=8)
            if candidate:
                current = matches.setdefault(candidate, {"votes": 0, "similarity": 0, "margin": 0})
                current["votes"] += 1
                current["similarity"] = max(current["similarity"], similarity)
                current["margin"] = max(current["margin"], margin)

        ranked = sorted(matches.items(), key=lambda item: (item[1]["votes"], item[1]["similarity"]), reverse=True)
        candidate = ranked[0][0] if ranked else None
        if len(ranked) > 1:
            top, second = ranked[0][1], ranked[1][1]
            if top["votes"] == second["votes"] and top["similarity"] - second["similarity"] < 8:
                candidate = None

        if candidate:
            match_info = matches[candidate]
            field_result.value = candidate
            field_result.status = "needs_review"
            field_result.alternatives = list(dict.fromkeys(
                [item for item in source_reads if item != candidate] + field_result.alternatives
            ))
            if exact_value == candidate:
                field_result.status_reason = (
                    f"District list confirms the exact spelling, but OCR confidence is "
                    f"{field_result.confidence:.0%}; check the crop."
                )
            else:
                field_result.status_reason = (
                    f"District list suggests {candidate} ({match_info['similarity']}% text match). "
                    "Review against the crop before accepting."
                )
        else:
            field_result.value = None
            field_result.status = "needs_review"
            field_result.status_reason = (
                f"OCR confidence is {field_result.confidence:.0%}; no unambiguous district "
                "candidate met the 85% text-match and separation thresholds."
            )

    for k in ("full_name", "date_of_birth", "nrc_number"):
        f = ex.fields[k]
        if f.value and f.confidence < 0.8:
            ex.warnings.append(f"Low OCR confidence on {k.replace('_', ' ')} ({f.confidence:.2f}).")
    return ex

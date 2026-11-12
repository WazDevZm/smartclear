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

DATE_RE = re.compile(r"(\d{1,2})[.,:\s]?(\d{2})[.,:\s]?(\d{2})$")   # real cards may print 8.12.23
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
    "dob": (-6, 80, 52, 84),
    "pob": (70, 200, 52, 88),
    "sex": (240, 345, 50, 80),
    "parent": (60, 345, 82, 102),
    "village": (-4, 200, 106, 131),
    "district": (200, 345, 106, 131),
    "chief": (-4, 200, 132, 157),
    "registration_date": (200, 345, 128, 156),
    "special": (50, 200, 152, 176),
}

# Printed labels used as vertical landmarks: median dy (card-relative, same frame as FIELD_BOXES)
# measured on the synthetic scans. Real cards print the same form with taller rows, so the ratio
# observed/expected for these labels gives a per-card vertical stretch for the field boxes.
LANDMARK_LABELS = {
    "DATEOFBIRTH": 55.3, "PLACEOFBIRTH": 56.5, "VILLAGE": 103.8, "DISTRICT": 103.9,
    "SPECIALMARKS": 152.8, "DATEOFRENUNCIATION": 155.5, "ORPOLICESTATION": 189.3,
}
# Labels that are recognised (so their text is not mistaken for a landmark) but not used to measure:
# their position varies too much, or their text resembles typed names.
OTHER_LABELS = ["FULLNAME", "FATHERSMOTHERSPLACEOFBIRTH", "CHIEF", "REGISTRATIONDATE", "SEX",
                "IFTHISCARDISFOUNDPLEASERETURNTONEARESTREGISTRATIONOFFICE"]
STRETCH_LIMITS = (0.85, 1.30)   # plausible vertical stretch relative to the synthetic layout
STRETCH_DEADBAND = 0.03         # ignore stretch estimates this close to 1 (measurement noise)

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


def _landmark(text: str) -> str | None:
    """Which printed label (if any) is this OCR token? Requires a clear winner over other labels."""
    from rapidfuzz import fuzz

    w = re.sub(r"[^A-Z]", "", text.upper())
    if len(w) < 5:
        return None
    labels = list(LANDMARK_LABELS) + OTHER_LABELS
    scored = sorted(((fuzz.partial_ratio(w, l) if len(w) <= len(l) else fuzz.partial_ratio(l, w), l)
                     for l in labels), reverse=True)
    (s1, best), (s2, _) = scored[0], scored[1]
    if s1 < 72 or s1 - s2 < 8 or best not in LANDMARK_LABELS:
        return None
    return best


def _vertical_stretch(toks: list[Token], x_left: float, y0: float, scale: float,
                      skip: tuple) -> tuple[float, list[str]]:
    """Estimate how much taller this card's rows are than the calibrated layout, from the
    positions of printed labels relative to the card-number baseline (dy = 0)."""
    ratios, used = [], []
    for t in toks:
        if any(t is s for s in skip):
            continue
        dx, dy = (t.rx - x_left) / scale, (t.ry - y0) / scale
        if not (-30 <= dx <= 380 and 30 <= dy <= 260):
            continue
        label = _landmark(t.text)
        if label is None:
            continue
        r = dy / LANDMARK_LABELS[label]
        if STRETCH_LIMITS[0] <= r <= STRETCH_LIMITS[1]:
            ratios.append(r)
            used.append(label)
    if not ratios:
        return 1.0, []
    stretch = float(np.median(ratios))
    return (1.0 if abs(stretch - 1.0) < STRETCH_DEADBAND else stretch), used


def _read_zone(img: np.ndarray, M: np.ndarray, x0, y0, x1, y1, scale: float = 2.0) -> list[Token]:
    """Crop a zone from the deskewed image, OCR it at 2x, drop printed labels,
    and return tokens in ORIGINAL image coordinates."""
    import cv2

    H, W = img.shape[:2]
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    x1, y1 = min(W, int(x1)), min(H, int(y1))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return []
    crop = ocr_view(img[y0:y1, x0:x1])
    crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    crop = cv2.copyMakeBorder(crop, 12, 12, 12, 12, cv2.BORDER_REPLICATE)
    result, _ = get_engine()(crop, use_cls=False)
    Minv = cv2.invertAffineTransform(M)
    toks = []
    for quad, text, conf in result or []:
        q = (np.array(quad, dtype=float) - 12) / scale + [x0, y0]
        h = float(np.linalg.norm(q[3] - q[0]))
        if h < 7.5 or conf < 0.5:           # printed labels are ~5-6px; typed data is 9px+
            continue
        words = [w for w in str(text).split() if not _is_label(w, float(conf))]
        if not words:
            continue
        q_orig = np.hstack([q, np.ones((4, 1))]) @ Minv.T
        tk = Token(text=" ".join(words), conf=float(conf), quad=q_orig)
        tk.rx, tk.ry = q.mean(0)
        tk.w = float(np.linalg.norm(q[1] - q[0]))
        toks.append(tk)
    return _reading_order(toks)


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
    corrected_from: str | None = None      # OCR text before reference-list correction
    suggestion: str | None = None          # close reference match the officer may accept
    match_score: float | None = None       # similarity behind the correction / suggestion

    def to_dict(self):
        d = {"value": self.value, "confidence": round(self.confidence, 3), "bbox": self.bbox, "raw": self.raw}
        if self.corrected_from:
            d["corrected_from"] = self.corrected_from
        if self.suggestion:
            d["suggestion"] = self.suggestion
        if self.match_score is not None:
            d["match_score"] = self.match_score
        return d


@dataclass
class Extraction:
    fields: dict[str, Field] = field(default_factory=dict)
    tokens: list[Token] = field(default_factory=list)
    skew_deg: float = 0.0
    layout_scale: float = 1.0
    vertical_stretch: float = 1.0
    side: str = "unknown"
    anchored: bool = True
    deskew_matrix: object = None
    deskewed: object = None                 # deskewed BGR image (not serialised)
    forensic_boxes: dict = field(default_factory=dict)   # field -> [x0,y0,x1,y1] in deskewed coords
    warnings: list[str] = field(default_factory=list)

    def value(self, name):
        f = self.fields.get(name)
        return f.value if f else None

    def to_dict(self):
        return {
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
            "skew_deg": round(self.skew_deg, 2),
            "layout_scale": round(self.layout_scale, 3),
            "vertical_stretch": round(self.vertical_stretch, 3),
            "side": self.side,
            "anchored": self.anchored,
            "warnings": self.warnings,
        }


def _bbox(tokens: list[Token]) -> list[int] | None:
    if not tokens:
        return None
    pts = np.vstack([t.quad for t in tokens])
    x0, y0 = pts.min(0)
    x1, y1 = pts.max(0)
    return [int(x0), int(y0), int(math.ceil(x1)), int(math.ceil(y1))]


def _mk(tokens: list[Token], value: str | None, raw: str | None = None) -> Field:
    conf = float(np.mean([t.conf for t in tokens])) if tokens else 0.0
    return Field(value=value, confidence=conf if value else 0.0, bbox=_bbox(tokens),
                 raw=raw if raw is not None else " ".join(t.text for t in tokens))


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
    return f"{int(dd):02d}.{mm}.{yy}"  # invalid dates are kept; validity is checked by the rules


def run_ocr(image: np.ndarray) -> list[Token]:
    result, _ = get_engine()(ocr_view(image), use_cls=False)
    toks = []
    for quad, text, conf in result or []:
        toks.append(Token(text=str(text).strip(), conf=float(conf), quad=np.array(quad, dtype=float)))
    return toks


def extract(image: np.ndarray, tokens: list[Token] | None = None) -> Extraction:
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
    reads, alts = {}, {}
    stretch, landmarks = _vertical_stretch(toks, x_left, y0, ex.layout_scale, (title, card_tok, reg_tok))
    ex.vertical_stretch = stretch
    if stretch != 1.0:
        ex.warnings.append(f"Card rows are {abs(stretch - 1) * 100:.0f}% {'taller' if stretch > 1 else 'shorter'} "
                           f"than the calibrated layout; field zones were adjusted using printed labels "
                           f"({', '.join(sorted(set(landmarks)))}).")
    scaled_boxes = {
        name: (x0 * ex.layout_scale, x1 * ex.layout_scale,
               y_lo * ex.layout_scale * stretch, y_hi * ex.layout_scale * stretch)
        for name, (x0, x1, y_lo, y_hi) in FIELD_BOXES.items()
    }
    for name, (x0, x1, y_lo, y_hi) in scaled_boxes.items():
        full = []
        for t in toks:
            if t is title or t is card_tok or t is reg_tok or t.h < 11.5 or t.conf < 0.5:
                continue
            dx, dy = t.rx - x_left, t.ry - y0
            if x0 <= dx <= x1 and y_lo <= dy <= y_hi:
                words = [w for w in t.text.split() if not _is_label(w, t.conf)]
                if words:
                    full.append(Token(text=" ".join(words), conf=t.conf, quad=t.quad, rx=t.rx, ry=t.ry))
        for ft in full:
            ft.rx, ft.ry = (M @ [ft.cx, ft.cy, 1.0])
        need_crop = name in ALWAYS_CROP or not full or min(t.conf for t in full) < 0.95
        crop = _read_zone(deskewed, M, x_left + x0, y0 + y_lo, x_left + x1, y0 + y_hi) if need_crop else []
        reads[name] = _fuse(full, crop)
        alts[name] = full + crop          # every reading of the zone, for reference-list matching

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

    nm = reads["name"]
    ex.fields["full_name"] = fld("name", _clean_alpha(" ".join(t.text for t in nm)) or None, nm)

    dob = [t for t in reads["dob"] if re.search(r"\d", t.text)]
    dv = _parse_date(_join_line(dob)) if dob else None
    ex.fields["date_of_birth"] = fld("dob", dv, dob)

    sx = [t for t in reads["sex"] if re.sub(r"\W", "", t.text)]
    if sx:
        ch = re.sub(r"\W", "", sx[0].text.upper())[:1]
        ex.fields["sex"] = fld("sex", "F" if ch in ("F", "E", "P") else "M", sx[:1])
    else:
        ex.fields["sex"] = Field(None, 0.0)

    from .gazetteer import canonical, match_district

    def _no_digits(toks_):
        return [t for t in toks_ if not re.search(r"\d", t.text)]

    pob = sorted(_no_digits(reads["pob"]), key=lambda t: t.ry)
    pv = [t for t in pob if not _is_district_token(t.text)]
    pdist = [t for t in pob if _is_district_token(t.text)]
    # Other OCR readings of the same text, tried against the district list in post-correction
    district_alts = {"district": [_clean_alpha(t.text) for t in alts["district"]],
                     "place_of_birth_district": [_clean_alpha(_strip_d(t.text)) for t in _no_digits(alts["pob"])
                                                 if _is_district_token(t.text)]}
    if not pdist and pv:
        # Some cards print the birth district without the "D." prefix: use the place-of-birth line
        # that names a known district in any of its OCR readings (lowest line first, where the
        # district is normally printed).
        def _best(t):
            readings = [t] + [a for a in _no_digits(alts["pob"]) if abs(a.ry - t.ry) < 10]
            return max((match_district(_clean_alpha(a.text)) for a in readings), key=lambda m: m.score)

        hit = next((t for t in reversed(pv) if _best(t).status in ("exact", "corrected")), None)
        if hit is not None:
            pdist = [hit]
            district_alts["place_of_birth_district"] = [_clean_alpha(a.text) for a in _no_digits(alts["pob"])
                                                        if abs(a.ry - hit.ry) < 10]
            if len(pv) > 1:
                pv = [t for t in pv if t is not hit]
    ex.fields["place_of_birth_village"] = fld("pob", _clean_alpha(pv[0].text) if pv else None, pv[:1])
    ex.fields["place_of_birth_district"] = fld("pob", _clean_alpha(_strip_d(pdist[0].text)) if pdist else None, pdist[:1])

    par = reads["parent"]
    ex.fields["parent_place_of_birth"] = fld("parent", _clean_alpha(" ".join(t.text for t in par)) or None, par)

    for key in ("village", "district", "chief"):
        toks_ = reads[key]
        ex.fields[key] = fld(key, _clean_alpha(" ".join(t.text for t in toks_)) or None, toks_)

    rd = [t for t in reads["registration_date"] if re.search(r"\d", t.text)]
    rv = _parse_date(_join_line(rd)) if rd else None
    ex.fields["registration_date"] = fld("rd", rv, rd)

    sp = reads["special"]
    sp_val = _clean_alpha(" ".join(t.text for t in sp)) or None
    if sp_val and sp_val.replace(" ", "").lower() in ("nil", "ni", "nii", "nll"):
        sp_val = "NIL"
    ex.fields["special_marks"] = fld("special", sp_val, sp)

    # District post-correction against the verified district list (OCR slips such as KITWB -> KITWE).
    # High-similarity matches are corrected (the OCR text is kept in corrected_from); weaker matches
    # are only suggested to the officer. Personal names are never corrected.
    for k in ("place_of_birth_district", "district"):
        f = ex.fields.get(k)
        if not (f and f.value):
            continue
        # best match over the shown value and every other OCR reading of the same text
        m = max((match_district(t) for t in [f.value, *district_alts.get(k, [])] if t),
                key=lambda d: d.score)
        if m.status == "exact" and m.district != f.value:
            m.status = "corrected" if canonical(f.value) is None else "exact"
        if m.status == "exact":
            f.value = m.district
        elif m.status == "corrected":
            f.corrected_from, f.value, f.match_score = f.value, m.district, m.score
        elif m.status == "suggested":
            f.suggestion, f.match_score = m.district, m.score
    pp = ex.fields.get("parent_place_of_birth")
    if pp and pp.value:
        m = re.match(r"^(.*?)\s*D\s*\.\s*([A-Z' -]+)$", pp.value)
        if m:
            dm = match_district(m.group(2).strip())
            if dm.status in ("exact", "corrected"):
                corrected = f"{m.group(1).strip()} D.{dm.district}".strip()
                if corrected != pp.value and dm.status == "corrected":
                    pp.corrected_from, pp.match_score = pp.value, dm.score
                pp.value = corrected
            elif dm.status == "suggested":
                pp.suggestion, pp.match_score = dm.district, dm.score

    for k in ("full_name", "date_of_birth", "nrc_number"):
        f = ex.fields[k]
        if f.value and f.confidence < 0.8:
            ex.warnings.append(f"Low OCR confidence on {k.replace('_', ' ')} ({f.confidence:.2f}).")
    return ex

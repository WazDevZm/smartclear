"""Image-forensic features for field-level tamper detection.

For each key field (NRC number, full name, date of birth) we take a tight crop of the
deskewed card and measure properties that genuine typed fields share and edited
fields break:

  * ink colour      — genuine type is neutral black/grey; pasted text is often blue/tinted
  * glyph consistency — per-character height, stroke width, darkness and colour should
                        be uniform in a typed line; a spliced digit or substituted word is not
  * sharpness       — erased / smudged fields lose edge energy
  * background patches — correction patches leave a brighter rectangle behind a glyph
  * legibility      — a recognition-only OCR pass over the crop (low confidence = suspicious)

Every feature is named so the officer UI can show *why* a field scored high.
"""
from __future__ import annotations

import cv2
import numpy as np

FIELDS = ("nrc_number", "full_name", "date_of_birth")

FEATURE_NAMES = [
    "field_nrc", "field_name", "field_dob",
    "ocr_conf", "ocr_len_ratio",
    "text_frac", "contrast", "sharpness", "edge_energy",
    "ink_chroma_mean", "ink_chroma_p95", "ink_blue_p95", "ink_b_mean",
    "blob_count", "blob_h_cv", "blob_h_maxdev", "blob_sw_cv", "blob_sw_maxdev",
    "blob_L_std", "blob_L_maxdev", "blob_chroma_maxdev", "blob_b_maxdev",
    "bg_bright_max", "bg_bright_frac", "bg_std",
]

# Human-readable explanations for the strongest signals
FEATURE_LABELS = {
    "ocr_conf": "Field is hard to read (low OCR confidence)",
    "ocr_len_ratio": "Unexpected number of characters",
    "sharpness": "Field looks smudged or blurred",
    "edge_energy": "Weak character edges (possible erasure)",
    "text_frac": "Unusual amount of ink in field",
    "ink_chroma_mean": "Ink colour differs from typed black",
    "ink_chroma_p95": "Coloured ink present in field",
    "ink_blue_p95": "Blue-tinted characters present",
    "blob_h_maxdev": "A character has a different height",
    "blob_sw_maxdev": "A character has a different stroke weight",
    "blob_L_maxdev": "A character is lighter/darker than the rest",
    "blob_chroma_maxdev": "A character's colour differs from the rest",
    "blob_b_maxdev": "A character is tinted differently",
    "blob_h_cv": "Inconsistent character heights (mixed fonts)",
    "blob_sw_cv": "Inconsistent stroke weights (mixed fonts)",
    "bg_bright_max": "Bright patch behind characters (correction mark)",
    "bg_bright_frac": "Bright patch behind characters (correction mark)",
}

EXPECTED_LEN = {"nrc_number": 11, "date_of_birth": 8, "full_name": 18}


def crop_box(img: np.ndarray, box) -> np.ndarray:
    x0, y0, x1, y1 = [int(v) for v in box]
    return img[max(0, y0):max(0, y1), max(0, x0):max(0, x1)]


def _rec(crop: np.ndarray) -> tuple[str, float]:
    from .extraction import get_engine

    if crop.size == 0 or crop.shape[0] < 6 or crop.shape[1] < 6:
        return "", 0.0
    try:
        res, _ = get_engine()(crop, use_det=False, use_cls=False)
        if res:
            return str(res[0][0]), float(res[0][1])
    except Exception:
        pass
    return "", 0.0


def _robust_dev(vals: np.ndarray) -> float:
    """Largest deviation of any element from the median, in units of the median."""
    if len(vals) < 2:
        return 0.0
    med = np.median(vals)
    return float(np.max(np.abs(vals - med)) / (abs(med) + 1e-6))


def _abs_dev(vals: np.ndarray) -> float:
    if len(vals) < 2:
        return 0.0
    return float(np.max(np.abs(vals - np.median(vals))))


def compute_features(crop: np.ndarray, field: str) -> dict[str, float]:
    f = {k: 0.0 for k in FEATURE_NAMES}
    f["field_nrc"] = float(field == "nrc_number")
    f["field_name"] = float(field == "full_name")
    f["field_dob"] = float(field == "date_of_birth")
    if crop is None or crop.size == 0 or min(crop.shape[:2]) < 6:
        return f

    text, conf = _rec(crop)
    f["ocr_conf"] = conf
    f["ocr_len_ratio"] = len(text.replace(" ", "")) / EXPECTED_LEN[field] if field != "full_name" else \
        min(2.0, len(text.replace(" ", "")) / EXPECTED_LEN[field])

    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
    L, A, B = lab[..., 0], lab[..., 1] - 128, lab[..., 2] - 128
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)

    # Background = text removed by a morphological closing (text is dark on light paper)
    k = max(7, (min(crop.shape[:2]) // 2) | 1)
    bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    diff = bg - gray
    thr = max(25.0, float(np.percentile(diff, 99)) * 0.45)
    mask = (diff > thr).astype(np.uint8)

    f["text_frac"] = float(mask.mean())
    f["contrast"] = float(np.percentile(diff, 99))
    lap = cv2.Laplacian(gray, cv2.CV_32F)
    f["sharpness"] = float(lap.var() / (f["contrast"] ** 2 + 1.0))
    gx, gy = cv2.Sobel(gray, cv2.CV_32F, 1, 0), cv2.Sobel(gray, cv2.CV_32F, 0, 1)
    mag = np.sqrt(gx ** 2 + gy ** 2)
    f["edge_energy"] = float(np.percentile(mag, 98) / (f["contrast"] + 1.0))

    if mask.sum() > 10:
        chroma = np.sqrt(A ** 2 + B ** 2)[mask > 0]
        f["ink_chroma_mean"] = float(chroma.mean())
        f["ink_chroma_p95"] = float(np.percentile(chroma, 95))
        f["ink_blue_p95"] = float(np.percentile(-B[mask > 0], 95))
        f["ink_b_mean"] = float(B[mask > 0].mean())

    # Per-glyph statistics
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
    hs, sws, Ls, cs, bs = [], [], [], [], []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < 8 or h < 5:
            continue
        m = lbl == i
        hs.append(h)
        sws.append(2.0 * float(dist[m].mean()))
        Ls.append(float(L[m].mean()))
        cs.append(float(np.sqrt(A[m] ** 2 + B[m] ** 2).mean()))
        bs.append(float(B[m].mean()))
    f["blob_count"] = float(len(hs))
    if len(hs) >= 2:
        hs_, sws_ = np.array(hs, float), np.array(sws, float)
        f["blob_h_cv"] = float(hs_.std() / (hs_.mean() + 1e-6))
        f["blob_h_maxdev"] = _robust_dev(hs_)
        f["blob_sw_cv"] = float(sws_.std() / (sws_.mean() + 1e-6))
        f["blob_sw_maxdev"] = _robust_dev(sws_)
        f["blob_L_std"] = float(np.std(Ls))
        f["blob_L_maxdev"] = _abs_dev(np.array(Ls))
        f["blob_chroma_maxdev"] = _abs_dev(np.array(cs))
        f["blob_b_maxdev"] = _abs_dev(np.array(bs))

    # Background brightness anomalies (correction patches)
    bgL = cv2.morphologyEx(L, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    med = float(np.median(bgL))
    sm = cv2.blur(bgL, (7, 7))
    f["bg_bright_max"] = float(sm.max() - med)
    f["bg_bright_frac"] = float((bgL > med + 12).mean())
    f["bg_std"] = float(bgL.std())
    return f


def vectorize(feats: dict[str, float]) -> np.ndarray:
    return np.array([feats[k] for k in FEATURE_NAMES], dtype=np.float32)

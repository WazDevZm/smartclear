"""Tests for real-scan handling: page normalisation and the legacy card template.

These use synthetic specimens (no real NRCs in this repository). The legacy
template calibration itself was derived from one real scan and is documented in
NEXT_STEPS.md — treat it as a starting point, not a validated model.
"""
import numpy as np

from smartclear.cards import detect_cards, normalize_page
from smartclear.config import SYNTHETIC_PDF_DIR
from smartclear.document import load_document
from smartclear.extraction import _clean_alpha, _parse_date
from smartclear.verify import parse_date


def test_parse_date_supports_four_digit_years():
    assert _parse_date("13.7.2003") == "13.07.2003"
    assert _parse_date("13/07/2003") == "13.07.2003"
    assert _parse_date("08.04.06") == "08.04.06"          # synthetic style unchanged
    assert _parse_date("08,04,06") == "08.04.06"


def test_verify_parse_date_four_digit():
    from datetime import date
    assert parse_date("13.07.2003") == date(2003, 7, 13)
    assert parse_date("13.7.2003") == date(2003, 7, 13)


def test_clean_alpha_strips_label_phrases():
    assert _clean_alpha("PLACE OF BIRTH CHINGOLA") == "CHINGOLA"
    assert _clean_alpha("FULL NAME PRECIOUS") == "PRECIOUS"
    assert _clean_alpha("DATE OF BIRTH") == ""


def test_detect_cards_on_blank_page():
    blank = np.full((2339, 1654, 3), 255, np.uint8)
    assert detect_cards(blank) == []
    out, info = normalize_page(blank)
    assert info["cards"] == [] and out.shape == blank.shape


def test_synthetic_page_normalisation_is_noop():
    """Synthetic specimens fill the frame; normalisation must not rescale them."""
    p = SYNTHETIC_PDF_DIR / "nrc-syn-0101.pdf"
    img = load_document(p.read_bytes(), p.name)
    out, info = normalize_page(img)
    assert out.shape == img.shape
    assert info["scale"] == 1.0


def test_cards_detected_on_real_like_layout():
    """Two synthetic cards pasted onto a large white page are found as two cards."""
    p = SYNTHETIC_PDF_DIR / "nrc-syn-0101.pdf"
    img = load_document(p.read_bytes(), p.name)
    h, w = img.shape[:2]
    page = np.full((h * 2 + 200, w + 400, 3), 255, np.uint8)
    page[100:100 + h, 200:200 + w] = img
    boxes = detect_cards(page)
    assert len(boxes) == 1                      # the two touching cards merge into one blob
    assert abs(boxes[0][2] - w) < 20
    scaled, info = normalize_page(page)
    assert len(info["cards"]) == 1

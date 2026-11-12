"""Scans at other resolutions than the calibrated ~924 px card width (runs the OCR models)."""
import cv2

import smartclear.cache as cache
from smartclear.config import SYNTHETIC_PDF_DIR
from smartclear.document import load_document
from smartclear.pipeline import process


def _run(scale, monkeypatch):
    monkeypatch.setattr(cache, "load", lambda key: (None, None))
    monkeypatch.setattr(cache, "store", lambda *a, **k: None)
    img = load_document((SYNTHETIC_PDF_DIR / "nrc-syn-0101.pdf").read_bytes(), "x.pdf")
    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    result, _ = process(img)
    return result


def test_high_resolution_scan_is_not_mistaken_for_legacy_layout(monkeypatch):
    result = _run(2.0, monkeypatch)
    fields = {k: v["value"] for k, v in result["extraction"]["fields"].items()}
    assert not any("Different card layout" in w for w in result["extraction"]["warnings"])
    page = result["page"]                                    # brought back to the calibrated size,
    assert page.get("scaled") or page.get("title_scale")     # by card detection or by the title
    assert fields["nrc_number"] == "783849/52/1"
    assert fields["full_name"] == "PRECIOUS MWEEMBA CHISENGA"
    assert fields["date_of_birth"] == "08.04.06"
    assert fields["registration_date"] == "07.05.25"

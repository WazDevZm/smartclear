"""End-to-end extraction on real synthetic scans (runs the OCR models; ~2s per document)."""
from smartclear.config import SYNTHETIC_PDF_DIR
from smartclear.document import load_document
from smartclear.extraction import extract


def run(name):
    p = SYNTHETIC_PDF_DIR / name
    return extract(load_document(p.read_bytes(), p.name))


def test_extracts_key_fields():
    ex = run("nrc-syn-0101.pdf")
    assert ex.value("nrc_number") == "783849/52/1"
    assert ex.value("full_name") == "PRECIOUS MWEEMBA CHISENGA"
    assert ex.value("date_of_birth") == "08.04.06"
    assert ex.value("district") == "KABWE" and ex.value("place_of_birth_district") == "MONZE"


def test_erased_field_reported_missing():
    ex = run("nrc-syn-0177.pdf")       # registration number blurred out
    assert ex.value("nrc_number") is None
    assert ex.value("full_name") == "LUYANDO BANDA NYIRENDA"

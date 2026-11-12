"""District reference list (data/zambia_districts.csv) and OCR post-correction rules."""
from smartclear.extraction import _landmark, _parse_date
from smartclear.gazetteer import canonical, districts, match_district, province


def test_loads_verified_csv():
    assert len(districts()) == 116
    assert province("Mwansabombwe") == "Luapula"
    assert canonical("kapiri") == "KAPIRI MPOSHI"          # alias -> CSV spelling
    assert canonical("Shiwangandu") == "SHIWANG'ANDU"


def test_ocr_slips_are_corrected():
    for ocr, district in [("TMWANSABOBW", "MWANSABOMBWE"), ("CHIBOMB0", "CHIBOMBO"),
                          ("SOLWEZl", "SOLWEZI"), ("T MWANSABOMBWE", "MWANSABOMBWE")]:
        m = match_district(ocr)
        assert (m.district, m.status) == (district, "corrected"), ocr


def test_one_letter_slips_in_short_districts_are_corrected():
    for ocr, district in [("KITWB", "KITWE"), ("XAFUE", "KAFUE"), ("MOSZE", "MONZE"), ("SAMFTA", "SAMFYA")]:
        m = match_district(ocr)
        assert (m.district, m.status) == (district, "corrected"), ocr


def test_weak_matches_are_only_suggested():
    m = match_district("MUKUNSA")                            # ~71%, two+ edits from RUFUNSA
    assert (m.district, m.status) == ("RUFUNSA", "suggested")


def test_village_names_are_not_bent_into_districts():
    for village in ("MALAMA", "MPANSHYA", "NANSANGA", "MUMENA", "LWEKO"):
        assert match_district(village).status in ("none", "suggested"), village


def test_single_digit_day_dates():
    assert _parse_date("8.12.23") == "08.12.23"
    assert _parse_date("25.11.06") == "25.11.06"
    assert _parse_date("081223") == "08.12.23"


def test_label_landmarks():
    assert _landmark("VRLLAGE") == "VILLAGE"
    assert _landmark("ORPOLESTATION") == "ORPOLICESTATION"
    assert _landmark("CHISENGA") is None                     # typed name, not a label

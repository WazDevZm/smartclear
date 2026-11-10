from datetime import date

from smartclear.flags import rule_flags


def codes(fields):
    return {f["code"] for f in rule_flags(fields, {}, today=date(2026, 11, 10))}


BASE = {"nrc_number": "882007/53/1", "full_name": "NCHIMUNYA SINKALA MBEWE", "date_of_birth": "12.06.99",
        "registration_date": "14.08.25", "place_of_birth_district": "LIVINGSTONE", "district": "LIVINGSTONE"}


def test_genuine_card_has_no_flags():
    assert codes(BASE) == set()


def test_district_swap_flagged():
    assert "DISTRICT_INCONSISTENT" in codes({**BASE, "district": "KABWE"})


def test_nrc_code_vs_district():
    assert "NRC_CODE_DISTRICT" in codes({**BASE, "nrc_number": "882007/52/1"})   # 52 = Monze


def test_underage_registration():
    assert "UNDERAGE_REGISTRATION" in codes({**BASE, "date_of_birth": "10.06.52", "registration_date": "11.06.61"})


def test_unreadable_fields():
    assert {"NRC_UNREADABLE", "DOB_UNREADABLE"} <= codes({**BASE, "nrc_number": None, "date_of_birth": None})

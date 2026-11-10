from smartclear.verify import compare_names, parse_date, verify


def test_name_tolerates_order_case_and_typos():
    assert compare_names("MARY BANDA KAPEMBWA", "Kapembwa Mary Banda")["outcome"] == "match"
    assert compare_names("MARY BANDA KAPEMBWA", "MARY BANDA KAPEMBWE")["outcome"] == "match"


def test_missing_middle_name_needs_officer():
    assert compare_names("MARY BANDA KAPEMBWA", "MARY KAPEMBWA")["outcome"] == "partial"


def test_substituted_surname_is_mismatch():
    assert compare_names("CHANDA KAPEMBWA NKONDE", "CHANDA KAPEMBWA ZULU")["outcome"] == "mismatch"


def test_dates_parse_card_and_record_formats():
    assert parse_date("08.04.06").isoformat() == "2006-04-08"
    assert parse_date("11.04.59").isoformat() == "1959-04-11"
    assert parse_date("2006-04-08") == parse_date("08/04/2006")


def test_verify_exact_and_mismatch():
    rec = {"nrc_number": "783849/52/1", "full_name": "PRECIOUS MWEEMBA CHISENGA", "date_of_birth": "2006-04-08"}
    ok = verify({"nrc_number": "783849/52/1", "full_name": "PRECIOUS MWEEMBA CHISENGA", "date_of_birth": "08.04.06"}, rec)
    assert ok["overall"] == "match"
    bad = verify({"nrc_number": "783849/52/1", "full_name": "PRECIOUS MWEEMBA CHISENGA", "date_of_birth": "08.04.07"}, rec)
    assert bad["overall"] == "mismatch" and bad["checks"]["date_of_birth"]["outcome"] == "mismatch"
    unread = verify({"nrc_number": None, "full_name": "PRECIOUS MWEEMBA CHISENGA", "date_of_birth": "08.04.06"}, rec)
    assert unread["overall"] == "review"

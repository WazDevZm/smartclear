import json

from smartclear import ai


def make_case(form_dob="2006-04-08", reg_dob="2006-04-08", reg_outcome="match", flags=(), tamper=0.05):
    name, nrc = "PRECIOUS MWEEMBA CHISENGA", "783849/52/1"
    field = lambda v: {"value": v, "confidence": 0.95}  # noqa: E731
    form_ok = form_dob == "2006-04-08"
    reg_ok = reg_dob == "2006-04-08"
    return {"result": {
        "extraction": {"fields": {"nrc_number": field(nrc), "full_name": field(name), "date_of_birth": field("08.04.06")},
                       "warnings": []},
        "verification": {"overall": "match" if form_ok else "mismatch", "checks": {
            "nrc_number": {"outcome": "match", "extracted": nrc, "record": nrc},
            "full_name": {"outcome": "match", "score": 100, "detail": "Exact match.", "extracted": name, "record": name},
            "date_of_birth": {"outcome": "match" if form_ok else "mismatch", "extracted": "2006-04-08", "record": form_dob}}},
        "registry": {"outcome": reg_outcome, "found": reg_outcome != "not_found", "status": "active", "checks": {
            "nrc_number": {"outcome": "match", "submitted": nrc, "registry": nrc},
            "date_of_birth": {"outcome": "match" if reg_ok else "mismatch", "submitted": "2006-04-08",
                              "registry": reg_dob}} if reg_outcome != "not_found" else {}},
        "flags": [{"code": c, "severity": "high", "title": c, "message": f"NRC {nrc} for {name} on 08.04.06"}
                  for c in flags],
        "tamper": {"date_of_birth": {"probability": tamper, "reasons": []}},
        "risk": {"score": 10, "band": "clear"}}}


def test_facts_contain_no_personal_data():
    blob = json.dumps(ai.case_facts(make_case(form_dob="2007-04-08", flags=["RECORD_MISMATCH"])))
    for secret in ("PRECIOUS", "CHISENGA", "783849", "2006-04-08", "08.04.06"):
        assert secret not in blob
    assert "differs by 1 year" in blob


def test_form_typo_suggests_request_info():
    assert ai.rule_based(ai.case_facts(make_case(form_dob="2007-04-08")))["suggested_action"] == "request_info"


def test_card_disagreeing_with_register_suggests_escalate():
    facts = ai.case_facts(make_case(reg_dob="1996-04-08", reg_outcome="mismatch"))
    assert ai.rule_based(facts)["suggested_action"] == "escalate"


def test_not_in_register_suggests_escalate():
    assert ai.rule_based(ai.case_facts(make_case(reg_outcome="not_found")))["suggested_action"] == "escalate"


def test_clean_case_suggests_approve():
    assert ai.rule_based(ai.case_facts(make_case()))["suggested_action"] == "approve"


def test_falls_back_to_rules_without_llm():
    out = ai.explain(make_case(), use_llm=False)
    assert out["source"] == "rules" and out["suggested_action"] in ai.ACTIONS and out["next_steps"]


def test_parses_fenced_llm_json():
    assert ai._parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert ai._parse_json('Sure! {"a": 2} hope that helps') == {"a": 2}


def test_gemini_call_parses_response_and_sends_no_personal_data(monkeypatch):
    sent = []
    answer = {"headline": "Form has a typo", "explanation": "The card matches the register.", "reasons": [],
              "suggested_action": "request_info", "next_steps": ["Ask the taxpayer."],
              "questions_for_taxpayer": [], "confidence": "medium"}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):  # Gemini's OpenAI-compatible shape, with the JSON fenced as models often do
            return json.dumps({"model": "gemini-test", "choices": [
                {"message": {"content": "```json\n" + json.dumps(answer) + "\n```"}}]}).encode()

    def fake_urlopen(req, timeout):
        sent.append(req)
        return Resp()
    monkeypatch.setattr(ai, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(ai, "GEMINI_MODELS", ["gemini-test"])
    monkeypatch.setattr(ai.urllib.request, "urlopen", fake_urlopen)
    out = ai.explain(make_case(form_dob="2007-04-08", flags=["RECORD_MISMATCH"]))
    assert out["source"] == "ai" and out["model"] == "gemini-test" and out["suggested_action"] == "request_info"
    req = sent[0]
    assert req.full_url.startswith("https://generativelanguage.googleapis.com/")
    assert req.get_header("Authorization") == "Bearer test-key"
    body = req.data.decode()
    for secret in ("PRECIOUS", "MWEEMBA", "CHISENGA", "783849", "2006-04-08", "2007-04-08", "08.04.06"):
        assert secret not in body

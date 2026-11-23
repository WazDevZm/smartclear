import pytest

from smartclear import moha_client, registry


@pytest.fixture(autouse=True)
def sandbox_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "REGISTRY_DB_PATH", tmp_path / "moha.db")
    monkeypatch.setattr(moha_client, "MOHA_API_URL", "")
    registry.seed()


def check(**payload):
    return registry.verify_identity(payload, client="test")


def test_genuine_card_matches_register():
    r = check(nrc_number="882007/53/1", full_name="Nchimunya Sinkala Mbewe", date_of_birth="12.06.99")
    assert r["outcome"] == "match" and r["status"] == "active"


def test_altered_card_disagrees_with_register():
    r = check(nrc_number="882007/53/1", full_name="NCHIMUNYA SINKALA ZULU", date_of_birth="12.06.89")
    assert r["outcome"] == "mismatch"
    assert r["checks"]["date_of_birth"]["outcome"] == "mismatch"


def test_unknown_nrc_is_not_found():
    assert check(nrc_number="999999/99/9", full_name="A B")["outcome"] == "not_found"


def test_unreadable_nrc_falls_back_to_name_and_dob():
    r = check(nrc_number=None, full_name="NCHIMUNYA SINKALA MBEWE", date_of_birth="1999-06-12")
    assert r["found"] and r["matched_by"] == "name_and_date_of_birth"
    assert r["checks"]["nrc_number"]["registry"] == "882007/53/1"


def test_lost_card_raises_status_alert():
    r = check(nrc_number="111111/11/1", full_name="BWALYA MUTALE KAPASA", date_of_birth="14.03.85")
    assert r["outcome"] == "status_alert"
    assert any(f["code"] == "REGISTRY_STATUS" and f["severity"] == "high" for f in moha_client.registry_flags(r))


def test_district_aliases_are_equal():
    r = check(nrc_number="882007/53/1", full_name="NCHIMUNYA SINKALA MBEWE", date_of_birth="12.06.99",
              district="Livingstone")
    assert r["checks"]["district"]["outcome"] == "match"


def test_unreachable_register_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(moha_client, "MOHA_API_URL", "http://127.0.0.1:9")    # nothing listens on port 9
    res = moha_client.lookup({"nrc_number": "882007/53/1"})
    assert res["outcome"] == "unavailable"
    assert [f["code"] for f in moha_client.registry_flags(res)] == ["REGISTRY_UNAVAILABLE"]


def test_http_api_requires_key():
    from fastapi.testclient import TestClient
    client = TestClient(registry.moha_app)
    assert client.post("/verify", json={}).status_code == 401
    ok = client.post("/verify", json={"nrc_number": "882007/53/1"}, headers={"X-API-Key": registry.MOHA_API_KEY})
    assert ok.status_code == 200 and ok.json()["found"]


def test_supabase_backend_reads_nrc_bank(monkeypatch):
    from smartclear import supabase_store
    bank = {"882007/53/1": {"nrc_number": "882007/53/1", "card_number": "Z65535111",
                            "full_name": "NCHIMUNYA SINKALA MBEWE", "date_of_birth": "1999-06-12", "sex": "F",
                            "place_of_birth_district": "LIVINGSTONE", "district": "LIVINGSTONE",
                            "registration_date": "2025-08-14", "status": "active", "updated_at": None}}
    calls = []

    def fake_request(method, path, body=None, prefer=None):
        calls.append((method, path))
        nrc = path.split("nrc_number=eq.")[-1].split("&")[0].replace("%2F", "/")
        return [bank[nrc]] if nrc in bank else []

    monkeypatch.setattr(registry, "REGISTRY_BACKEND", "supabase")
    monkeypatch.setattr(supabase_store, "_request", fake_request)
    assert check(nrc_number="882007/53/1", full_name="Nchimunya Sinkala Mbewe", date_of_birth="12.06.99")["outcome"] == "match"
    assert check(nrc_number="123456/78/9", full_name="X Y")["outcome"] == "not_found"
    assert all(m == "GET" for m, _ in calls) and all("mohais_citizens" in p for _, p in calls)

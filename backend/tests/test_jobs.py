import time

from fastapi.testclient import TestClient

from smartclear import api, jobs


def wait(job_id, owner="officer", timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        job = jobs.get(job_id, owner)
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_job_runs_in_background_and_reports_progress():
    job = jobs.submit("batch", "officer", 2, lambda progress: [progress({"n": i}) for i in range(2)])
    assert job["status"] in ("queued", "running", "done")
    done = wait(job["id"])
    assert done["status"] == "done" and done["done"] == 2 and done["results"] == [{"n": 0}, {"n": 1}]


def test_failed_job_records_error_and_worker_survives():
    def boom(progress):
        raise ValueError("unreadable scan")
    assert "unreadable scan" in wait(jobs.submit("case", "officer", 1, boom)["id"])["error"]
    assert wait(jobs.submit("case", "officer", 1, lambda p: p({"ok": 1}))["id"])["status"] == "done"


def test_jobs_are_private_to_their_owner():
    job = jobs.submit("case", "officer", 1, lambda p: None)
    assert jobs.get(job["id"], "supervisor") is None


def _client(monkeypatch, process, tmp_path):
    from smartclear import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")   # own database: works on a fresh checkout too
    db.init()
    monkeypatch.setattr(api, "_process_item", process)
    c = TestClient(api.app)
    token = c.post("/api/login", json={"username": "officer", "password": "futureminds"}).json()["token"]
    return c, {"Authorization": f"Bearer {token}"}


def test_background_upload_returns_immediately_then_completes(monkeypatch, tmp_path):
    def slow(data, name, tpin, actor):
        time.sleep(0.3)        # stands in for OCR that would outlast a proxy timeout
        return {"filename": name, "id": 42, "ref": "SC-TEST"}
    c, h = _client(monkeypatch, slow, tmp_path)
    t0 = time.time()
    r = c.post("/api/cases", files={"file": ("card.pdf", b"%PDF-1.4")}, data={"background": "true"}, headers=h)
    assert r.status_code == 202 and time.time() - t0 < 0.3
    job_id = r.json()["id"]
    end = time.time() + 5
    while (j := c.get(f"/api/jobs/{job_id}", headers=h).json())["status"] not in ("done", "error") and time.time() < end:
        time.sleep(0.05)
    assert j["status"] == "done" and j["results"][0]["id"] == 42


def test_background_upload_failure_is_reported_on_the_job(monkeypatch, tmp_path):
    c, h = _client(monkeypatch, lambda data, name, tpin, actor: {"filename": name, "error": "Could not process document: bad pdf"}, tmp_path)
    job_id = c.post("/api/cases", files={"file": ("x.pdf", b"x")}, data={"background": "true"}, headers=h).json()["id"]
    end = time.time() + 5
    while (j := c.get(f"/api/jobs/{job_id}", headers=h).json())["status"] not in ("done", "error") and time.time() < end:
        time.sleep(0.05)
    assert j["status"] == "error" and "bad pdf" in j["error"]


def test_background_batch_tracks_each_document(monkeypatch, tmp_path):
    c, h = _client(monkeypatch, lambda data, name, tpin, actor: {"filename": name, "id": 1}, tmp_path)
    files = [("files", (f"c{i}.pdf", b"%PDF")) for i in range(3)]
    r = c.post("/api/batches", files=files, data={"background": "true"}, headers=h)
    assert r.status_code == 202 and r.json()["total"] == 3
    end = time.time() + 5
    while (j := c.get(f"/api/jobs/{r.json()['id']}", headers=h).json())["status"] != "done" and time.time() < end:
        time.sleep(0.05)
    assert j["done"] == 3


def test_unknown_job_is_404(monkeypatch, tmp_path):
    c, h = _client(monkeypatch, lambda *a: {}, tmp_path)
    assert c.get("/api/jobs/nope", headers=h).status_code == 404


def test_ai_respects_total_time_budget(monkeypatch):
    from smartclear import ai
    calls = []

    def slow_urlopen(req, timeout):
        calls.append(timeout)
        time.sleep(0.2)
        raise TimeoutError()
    monkeypatch.setattr(ai, "AI_BUDGET_S", 4.5)
    monkeypatch.setattr(ai, "GEMINI_API_KEY", "test")
    monkeypatch.setattr(ai, "GEMINI_MODELS", ["a", "b", "c"])
    monkeypatch.setattr(ai.urllib.request, "urlopen", slow_urlopen)
    out, meta = ai.call_llm({"x": 1}, {"suggested_action": "approve"})
    assert out is None and all(t <= 4.5 for t in calls)
    assert any("budget" in a.get("error", "") for a in meta["attempts"]) or len(calls) == 3

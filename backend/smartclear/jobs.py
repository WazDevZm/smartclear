"""Background jobs for document processing, so no HTTP request waits on OCR.

Hosting proxies (Hugging Face Spaces, Render, nginx, ...) cut a request after a fixed time and answer 502/504,
even though the server is still working. Reading a card can take tens of seconds on a small CPU, and a batch of
50 far longer, so uploads are queued here and the browser polls ``GET /api/jobs/{id}`` instead.

A single worker by default (``SMARTCLEAR_OCR_WORKERS``): OCR is CPU- and memory-heavy, and running several at once
on a small instance is a common way to get the process killed (which the proxy also reports as 502).
Jobs live in memory: they are short-lived progress records, while results are stored as cases in the database.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=max(1, int(os.environ.get("SMARTCLEAR_OCR_WORKERS", "1"))),
                               thread_name_prefix="smartclear-ocr")
_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_KEEP_S = 6 * 3600


def _public(job: dict) -> dict:
    return {k: v for k, v in job.items() if k != "owner"}


def submit(kind: str, owner: str, total: int, work) -> dict:
    """Queue ``work(progress)``; ``progress(item)`` records one finished item. Returns the job record."""
    job = {"id": uuid.uuid4().hex[:12], "kind": kind, "owner": owner, "status": "queued", "total": total,
           "done": 0, "results": [], "error": None, "created": time.time(), "started": None, "finished": None}
    with _lock:
        cutoff = time.time() - _KEEP_S
        for jid in [j for j, v in _jobs.items() if (v["finished"] or v["created"]) < cutoff]:
            del _jobs[jid]
        _jobs[job["id"]] = job

    def progress(item: dict):
        with _lock:
            job["results"].append(item)
            job["done"] += 1

    def run():
        job["status"], job["started"] = "running", time.time()
        try:
            work(progress)
            job["status"] = "done"
        except Exception as e:      # recorded for the browser; never crashes the worker
            job["status"], job["error"] = "error", f"Could not process document: {e}"
        finally:
            job["finished"] = time.time()

    _executor.submit(run)
    return _public(job)


def get(job_id: str, owner: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        if not job or job["owner"] != owner:
            return None
        out = _public(job)
        out["position"] = sum(1 for j in _jobs.values() if j["status"] == "queued" and j["created"] < job["created"])
        return out

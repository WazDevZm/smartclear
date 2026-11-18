"""SmartClear REST API + static frontend."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db
from .config import FRONTEND_DIST, MODELS_DIR, STORAGE_DIR
from .document import prepare_document_pages
from .pipeline import encode_png, process_pages
from .verify import fmt_nrc

app = FastAPI(title="SmartClear API", version="0.1.0",
              description="ZRA SmartClear — AI-assisted NRC extraction, verification and fraud flagging.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

UPLOADS = STORAGE_DIR / "uploads"
IMAGES = STORAGE_DIR / "images"
for d in (UPLOADS, IMAGES):
    d.mkdir(parents=True, exist_ok=True)

# ---- Auth (pilot-grade: signed bearer tokens; replace with ZRA SSO / AD for deployment)
_secret_file = STORAGE_DIR / ".secret"
if not _secret_file.exists():
    _secret_file.write_text(secrets.token_hex(32))
SECRET = os.environ.get("SMARTCLEAR_SECRET", _secret_file.read_text()).encode()
OFFICERS = {  # demo accounts for the pilot sandbox
    "officer": {"password": "smartclear", "name": "Demo Officer", "role": "Registration Officer", "unit": "TSE"},
    "supervisor": {"password": "smartclear", "name": "Demo Supervisor", "role": "Supervisor", "unit": "Domestic Taxes"},
}


def _sign(user: str) -> str:
    exp = str(int(time.time()) + 12 * 3600)
    sig = hmac.new(SECRET, f"{user}:{exp}".encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{user}:{exp}:{sig}".encode()).decode()


def current_user(authorization: str | None = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Not signed in")
    try:
        user, exp, sig = base64.urlsafe_b64decode(authorization[7:].encode()).decode().split(":")
    except Exception:
        raise HTTPException(401, "Invalid token")
    good = hmac.new(SECRET, f"{user}:{exp}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(good, sig) or int(exp) < time.time() or user not in OFFICERS:
        raise HTTPException(401, "Session expired")
    return {"username": user, **{k: v for k, v in OFFICERS[user].items() if k != "password"}}


@app.on_event("startup")
def _startup():
    db.init()


class Login(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(body: Login):
    o = OFFICERS.get(body.username)
    if not o or not hmac.compare_digest(o["password"], body.password):
        raise HTTPException(401, "Incorrect username or password")
    with db.conn() as c:
        db.audit(c, body.username, "login")
    return {"token": _sign(body.username), "user": {"username": body.username,
                                                    **{k: v for k, v in o.items() if k != "password"}}}


@app.get("/api/health")
def health():
    from .flags import tamper_model

    return {"status": "ok", "tamper_model_loaded": tamper_model() is not None}


@app.get("/api/public/metrics")
def public_metrics():
    """Headline evaluation numbers for the landing page (no personal data)."""
    p = MODELS_DIR / "evaluation.json"
    if not p.exists():
        return {}
    e = json.loads(p.read_text())
    return {"documents": e["dataset"]["documents"],
            "extraction_accuracy": e["extraction"]["key_fields_accuracy"],
            "verification_accuracy": e["verification"]["accuracy"],
            "fraud_recall": e["fraud_flagging"]["recall"], "fraud_precision": e["fraud_flagging"]["precision"],
            "median_seconds": round(e["processing_time_ms"]["median"] / 1000, 1)}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return user


@app.get("/api/stats")
def stats(user=Depends(current_user)):
    with db.conn() as c:
        q = lambda s, *a: c.execute(s, a).fetchone()[0]  # noqa: E731
        bands = {r["risk_band"]: r["n"] for r in c.execute("SELECT risk_band, COUNT(*) n FROM cases GROUP BY risk_band")}
        status = {r["status"]: r["n"] for r in c.execute("SELECT status, COUNT(*) n FROM cases GROUP BY status")}
        flag_counts: dict[str, int] = {}
        for r in c.execute("SELECT result FROM cases"):
            for f in json.loads(r["result"])["flags"]:
                flag_counts[f["title"]] = flag_counts.get(f["title"], 0) + 1
        avg_ms = q("SELECT AVG(json_extract(result,'$.timing_ms.total')) FROM cases") or 0
        return {"total": q("SELECT COUNT(*) FROM cases"), "bands": bands, "status": status,
                "taxpayers": q("SELECT COUNT(*) FROM taxpayers"),
                "top_flags": sorted(flag_counts.items(), key=lambda kv: -kv[1])[:8],
                "avg_processing_ms": round(avg_ms)}


@app.get("/api/cases")
def list_cases(status: str | None = None, band: str | None = None, q: str | None = None,
               user=Depends(current_user)):
    sql = ("SELECT id, ref, filename, tpin, status, risk_score, risk_band, verification, nrc_number, full_name, "
           "date_of_birth, n_flags, created_at, decided_by FROM cases WHERE 1=1")
    args: list = []
    if status:
        sql += " AND status=?"
        args.append(status)
    if band:
        sql += " AND risk_band=?"
        args.append(band)
    if q:
        sql += " AND (full_name LIKE ? OR nrc_number LIKE ? OR ref LIKE ? OR tpin LIKE ?)"
        args += [f"%{q}%"] * 4
    sql += " ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, risk_score DESC, id DESC"
    with db.conn() as c:
        return [dict(r) for r in c.execute(sql, args)]


def _get_case(c, case_id: int) -> dict:
    r = c.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    if not r:
        raise HTTPException(404, "Case not found")
    return db.case_row(r)


@app.get("/api/cases/{case_id}")
def get_case(case_id: int, user=Depends(current_user)):
    with db.conn() as c:
        case = _get_case(c, case_id)
        case["taxpayer"] = db.get_taxpayer(c, tpin=case["tpin"]) if case["tpin"] else None
        case["audit"] = [dict(r) for r in c.execute(
            "SELECT ts, actor, action, detail FROM audit WHERE case_id=? ORDER BY id DESC", (case_id,))]
        db.audit(c, user["username"], "view_case", case_id)
        return case


@app.get("/api/cases/{case_id}/image")
def case_image(case_id: int, token: str | None = None, authorization: str | None = Header(None)):
    current_user(authorization or (f"Bearer {token}" if token else None))
    with db.conn() as c:
        case = _get_case(c, case_id)
    p = Path(case["image_path"])
    if not p.exists():
        raise HTTPException(404, "Image missing")
    return FileResponse(p, media_type="image/png")


RETURNED_FIELDS = (
    "nrc_number", "card_number", "full_name", "date_of_birth", "place_of_birth_village",
    "sex", "village", "district", "chief", "registration_date", "special_marks",
)
RETURNED_FIELD_LABELS = {
    "nrc_number": "NRC number", "card_number": "card number", "full_name": "full name",
    "date_of_birth": "date of birth", "place_of_birth_village": "place of birth",
    "sex": "sex", "village": "village", "district": "district", "chief": "chief",
    "registration_date": "registration date",
}


def _refresh_capture_quality(result: dict) -> None:
    page_cropped = (result.get("preprocessing") or {}).get("page_cropped", [])
    uncropped = [i for i, cropped in enumerate(page_cropped) if not cropped]
    reasons = []
    if uncropped:
        page_details = (result.get("preprocessing") or {}).get("pages", [])
        source_pages = sorted({
            int(page_details[i].get("source_page_index", i)) + 1
            if i < len(page_details) else i + 1
            for i in uncropped
        })
        pages = ", ".join(str(i) for i in source_pages)
        reasons.append(
            f"Could not isolate the full card boundary on page(s) {pages}. Retake with all four card edges visible."
        )
    unreadable, very_low = [], []
    fields = result.get("extraction", {}).get("fields", {})
    for key in RETURNED_FIELDS:
        if key == "special_marks":
            continue
        field = fields.get(key, {})
        if not field.get("value"):
            unreadable.append(RETURNED_FIELD_LABELS[key])
        elif field.get("confidence", 0) < 0.65:
            very_low.append(RETURNED_FIELD_LABELS[key])
    if unreadable:
        reasons.append("Could not read " + ", ".join(unreadable) + ". Retake closer, in focus, with even lighting.")
    if very_low:
        reasons.append("Very low OCR confidence for " + ", ".join(very_low) + ". Retake closer and in focus.")
    result["capture_quality"] = {"retake_recommended": bool(reasons), "reasons": reasons}



def create_case(c, data: bytes, filename: str, tpin: str | None, actor: str, tokens=None, ref=None) -> int:
    images, preprocessing = prepare_document_pages(data, filename)
    record = db.get_taxpayer(c, tpin=tpin) if tpin else None
    # Every isolated card page uses field crops; pages without a reliable card
    # boundary are retained as evidence but explicitly excluded from OCR.
    result, disp, pages = process_pages(
        images, record, tokens, force_crop=True, page_isolated=preprocessing["page_cropped"],
        page_sources=preprocessing["page_sources"],
    )
    result["preprocessing"] = {
        **preprocessing,
        "ocr_input": "grayscale with contrast enhancement",
        "pages": [
            {
                "index": i,
                "source_page_index": page["source_page_index"],
                "card_index": page["card_index"],
                "card_cropped": preprocessing["page_cropped"][i],
                "side": page["side"],
                "rotation_degrees": page["rotation_degrees"],
            }
            for i, page in enumerate(pages)
        ],
    }
    uncropped_pages = [
        i for i, was_cropped in enumerate(preprocessing["page_cropped"]) if not was_cropped
    ]
    if uncropped_pages:
        # OCR confidence alone is not enough when the card was not isolated from the page.
        for field in result["extraction"]["fields"].values():
            page_index = field.get("page_index")
            if (field.get("status") == "accepted" and field.get("raw") != "DEFAULT:NIL"
                    and (page_index is None or page_index in uncropped_pages)):
                field["status"] = "needs_review"
                field["status_reason"] = "The card boundary was not confidently isolated on this page."
        from . import flags as F
        result["flags"].append(F._flag(
            "CARD_BOUNDARY_UNCERTAIN", "medium", "Card boundary needs review",
            "The card could not be confidently isolated. No values were read from this page; request a retake with all four edges visible.",
        ))
        result["risk"] = F.risk(result["flags"], result["verification"], result["tamper"])
    if record is None and not tpin:
        # Fall back to looking the taxpayer up by the extracted NRC number
        nrc = result["extraction"]["fields"]["nrc_number"]["value"]
        record = db.get_taxpayer(c, nrc=fmt_nrc(nrc)) if nrc else None
        if record:
            from .verify import verify
            from . import flags as F

            fields = {k: v["value"] for k, v in result["extraction"]["fields"].items()}
            result["verification"] = verify(fields, record)
            if result["verification"]["overall"] == "mismatch":
                bad = [k for k, v in result["verification"]["checks"].items() if v["outcome"] == "mismatch"]
                result["flags"].append(F._flag("RECORD_MISMATCH", "high", "Doesn't match captured record",
                                               "Mismatch on: " + ", ".join(F.FIELD_LABEL[b] for b in bad) + ".",
                                               bad[0]))
            result["risk"] = F.risk(result["flags"], result["verification"], result["tamper"])
            tpin = record["tpin"]
    # Duplicate check: same NRC number already presented with different details
    nrc = result["extraction"]["fields"]["nrc_number"]["value"]
    if nrc:
        dup = c.execute("SELECT ref, full_name, date_of_birth FROM cases WHERE nrc_number=?", (nrc,)).fetchall()
        name = result["extraction"]["fields"]["full_name"]["value"]
        others = [d for d in dup if d["full_name"] != name]
        if others:
            from . import flags as F

            result["flags"].insert(0, F._flag("DUPLICATE_NRC", "high", "NRC number seen with different details",
                                              f"NRC {nrc} was already presented as {others[0]['full_name']} "
                                              f"(case {others[0]['ref']}).", "nrc_number"))
            result["risk"] = F.risk(result["flags"], result["verification"], result["tamper"])
    _refresh_capture_quality(result)

    # Keep the response focused on the requested NRC fields.
    result["extraction"]["fields"] = {
        key: result["extraction"]["fields"][key]
        for key in RETURNED_FIELDS if key in result["extraction"]["fields"]
    }
    result["extraction"]["crop_boxes"] = {
        key: box for key, box in result["extraction"].get("crop_boxes", {}).items()
        if key in RETURNED_FIELDS
    }
    result["forensic_boxes"] = {
        key: box for key, box in result.get("forensic_boxes", {}).items() if key in RETURNED_FIELDS
    }
    result["flags"] = [
        flag for flag in result["flags"]
        if not flag.get("field") or flag.get("field") in RETURNED_FIELDS
    ]
    result["tamper"] = {
        key: value for key, value in result.get("tamper", {}).items() if key in RETURNED_FIELDS
    }
    from . import flags as F
    result["risk"] = F.risk(result["flags"], result["verification"], result["tamper"])

    ref = ref or f"SC-{uuid.uuid4().hex[:8].upper()}"
    img_path = IMAGES / f"{ref}.png"
    img_path.write_bytes(encode_png(disp))
    src_path = UPLOADS / f"{ref}{Path(filename).suffix.lower() or '.bin'}"
    src_path.write_bytes(data)
    f = result["extraction"]["fields"]
    cur = c.execute(
        "INSERT INTO cases(ref, filename, tpin, status, risk_score, risk_band, verification, nrc_number, full_name, "
        "date_of_birth, n_flags, result, image_path, source_path, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ref, filename, tpin, "pending", result["risk"]["score"], result["risk"]["band"],
         result["verification"]["overall"], f["nrc_number"]["value"], f["full_name"]["value"],
         f["date_of_birth"]["value"], len(result["flags"]), json.dumps(result), str(img_path), str(src_path),
         db.now(), db.now()))
    db.audit(c, actor, "submit_document", cur.lastrowid,
             {"filename": filename, "risk": result["risk"], "verification": result["verification"]["overall"]})
    return cur.lastrowid


@app.post("/api/cases")
async def upload(file: UploadFile = File(...), tpin: str | None = Form(None), user=Depends(current_user)):
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 15 MB)")
    try:
        with db.conn() as c:
            cid = create_case(c, data, file.filename or "upload", tpin or None, user["username"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(422, f"Could not process document: {e}")
    return get_case(cid, user)


class Review(BaseModel):
    action: str          # approve | reject | escalate | request_info
    note: str | None = None


STATUS = {"approve": "approved", "reject": "rejected", "escalate": "escalated", "request_info": "info_requested"}


@app.post("/api/cases/{case_id}/review")
def review(case_id: int, body: Review, user=Depends(current_user)):
    if body.action not in STATUS:
        raise HTTPException(400, "Unknown action")
    if body.action in ("reject", "escalate") and not (body.note or "").strip():
        raise HTTPException(400, "A note is required when rejecting or escalating")
    with db.conn() as c:
        _get_case(c, case_id)
        c.execute("UPDATE cases SET status=?, decided_by=?, decision_note=?, updated_at=? WHERE id=?",
                  (STATUS[body.action], user["name"], body.note, db.now(), case_id))
        db.audit(c, user["username"], f"review:{body.action}", case_id, {"note": body.note})
    return get_case(case_id, user)


@app.get("/api/taxpayers")
def taxpayers(q: str | None = None, user=Depends(current_user)):
    with db.conn() as c:
        if q:
            rows = c.execute("SELECT * FROM taxpayers WHERE full_name LIKE ? OR nrc_number LIKE ? OR tpin LIKE ? "
                             "LIMIT 50", (f"%{q}%",) * 3)
        else:
            rows = c.execute("SELECT * FROM taxpayers ORDER BY tpin LIMIT 200")
        return [dict(r) for r in rows]


@app.get("/api/evaluation")
def evaluation(user=Depends(current_user)):
    out = {}
    for name in ("evaluation.json", "tamper_metrics.json"):
        p = MODELS_DIR / name
        if p.exists():
            d = json.loads(p.read_text())
            d.pop("oof_scores", None)
            out[name.replace(".json", "")] = d
    return out


@app.get("/api/audit")
def audit_log(user=Depends(current_user)):
    with db.conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 200")]


# ---- Frontend (built SPA)
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        f = FRONTEND_DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    def root():
        return Response("SmartClear API running. Build the frontend (cd frontend && npm run build) to serve the UI.",
                        media_type="text/plain")

---
title: SmartClear — AI NRC Verification for ZRA
emoji: 🛡️
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---
# SmartClear — AI NRC Verification for ZRA

> this is the SA team

SmartClear is a working prototype for the **ZRA AI Unit's "Strengthening Identity Verification in Taxpayer
Registration" challenge**. It runs the *extract → verify → flag → officer review* workflow from our technical
proposal, end to end and locally:

```
Scanned NRC ─▶ AI/OCR extraction ─▶ Record verification ─▶ Anomaly / fraud flags ─▶ Officer review
   (PDF)        NRC no., name, DOB     vs captured record     rules + tamper model     approve / reject / escalate
```

SmartClear supports officers and does not replace them. A flag means "look closer". It is never an automated fraud decision, and records are never changed automatically.

## Quick start

Requirements: Python 3.11–3.12, Node 18+.

```bash
./run.sh                 # first run: venv, deps, frontend build, seed DB, evaluate, then serve
open http://localhost:8000
```

Sign in with **officer / futureminds** (or **supervisor / futureminds**).

`./run.sh --retrain` rebuilds the OCR cache, retrains the tamper model and re-runs the evaluation.

Frontend dev with hot reload: start the API (`cd backend && ../.venv/bin/uvicorn smartclear.api:app --reload`),
then run `cd frontend && npm run dev` and open http://localhost:5173. Vite proxies `/api` to the API.

Offline use: delete `storage/ocr_cache/` to force fresh OCR on repeat uploads (results are otherwise cached by content hash).

Tests: `cd backend && ../.venv/bin/python -m pytest -q`

## Results on the synthetic set (100 NRCs, 33 labelled fraudulent)

| Brief success measure | Result | How it is measured |
|---|---|---|
| Extraction accuracy (NRC no., name, DOB) | **100%** (300/300 legible fields) | vs manually verified reading, `data/facilitator_ground_truth.csv` |
| Extraction under perturbation | **100%** (20 docs) | rotation ±3°, scale ±5%, shift, noise, JPEG q70 |
| Verification accuracy | **100%** (66 match / 7 review / 27 mismatch) | vs expected outcome per synthetic record scenario |
| Fraud-flagging recall | **100%** (33/33) | district swaps 11/11, underage 8/8, visual tampers 17/17 |
| Fraud-flagging precision | **94.3%** (2 false alarms) | tamper scores are 5-fold, document-grouped, out-of-fold |
| Tamper model, synthetic-only training | recall 100%, ROC-AUC 1.0 | trained on generated forgeries only, scored on the real tampered cards |
| Processing time | ~1.0 s median per document | laptop CPU, no GPU, no cloud |

Full report: `models/evaluation.json` and the **Model performance** page in the app.
**Read the caveats in [NEXT_STEPS.md](NEXT_STEPS.md#honest-caveats) before quoting these numbers.**

## How it works on real scans (one-sample result, read carefully)

The code handles a genuine legacy-issue scan (both sides on one page, supplied by the team) without crashing and extracts:
card number and registration date exactly (conf 0.98–0.99), sex exactly (0.76),
the name with a small OCR corruption (0.89), and unreadable DOB / perforated NRC number —
correctly flagged rather than guessed. Village and districts read approximately, at low confidence.
Three tamper flags fired; the tamper model is not validated on real cards and is shown as indicative only.

So: on real scans, expect exact reads on the bold printed fields (card no., registration date), imperfect reads on the faint dotted print (name, village, districts — low confidence, officer checks), and no reads of dot-perforated numbers. Every case must be reviewed by an officer; nothing here replaces verification. Run `backend/scripts/evaluate_real.py --truth truth.json your-scan.pdf` inside the sandbox (real scans are git-ignored in `data/real/`).

## How it works

### 1. Extraction: `backend/smartclear/extraction.py`, `backend/smartclear/cards.py`
* Real scans are normalised first: card regions are detected on the page (`cards.detect_cards`) and the page is scaled so the card matches the calibrated 924 px card width. Tighter-cropped or single-card scans pass through unchanged.
* When no card is detected on the page, the page is resized so the printed "REGISTRATION CARD" title has its calibrated width (high-resolution scans are shrunk; low-resolution scans get a 2× retry when the title cannot be read at all).
* The printed-layout variant is detected from where its labels sit. The taller "legacy green" issue gets its own zone calibration (`FIELD_BOXES_LEGACY`) and an honesty warning on every case.
* **RapidOCR** (PaddleOCR PP-OCR detection and recognition models on ONNX Runtime) runs fully on-premise.
* Every PDF page is cropped and OCR'd independently. Pages are classified as card front or back; front-side fields and the back-side NRC number are then merged with their page coordinates preserved. Unknown pages are not used to fill fields.
* A clearly dominant quadrilateral card is cropped and perspective-corrected; if boundaries are ambiguous, the page is kept intact and the case warns officers to review nearby stamps or handwriting.
* Pages without a readable horizontal card anchor are checked at quarter-turn rotations. Unknown layouts are still not mapped to new field positions automatically.
* OCR uses a grayscale, contrast-normalized view. The uploaded original and its color pixels remain unchanged for storage and forensic analysis.
* Pass 1: full-page OCR finds anchors (the "NATIONAL REGISTRATION CARD" title, the card number and the registration number) and estimates skew from the text-box angles.
* The page is deskewed and a card-relative coordinate frame is scaled from the printed title, so field zones adapt to different scan sizes.
* On the standard layout, field zones also adapt to each card's row spacing: printed labels such as VILLAGE, SPECIAL MARKS and the footer are found and used to measure how much taller or shorter the rows are than the calibrated layout.
* Pass 2: each field zone is cropped and re-read at 2× (2.8× for the legacy card; the name field on legacy cards additionally gets a CLAHE contrast pass). The two passes are **fused** by keeping the most confident read for each position, which recovers words the full-page detector clips at printed lines.
* Printed form labels are removed by glyph height plus fuzzy matching, weighted by OCR confidence; multi-word label phrases are also stripped deterministically.
* Dates may use 1- or 2-digit days, 2- or 4-digit years and `.`/`/`/`-` separators.
* District fields are matched to the verified list of Zambia's 116 districts in `data/zambia_districts.csv` (`gazetteer.py`). Every OCR reading of the field is tried:
  * 85% similarity or more, or a single wrong letter that points to only one district: **corrected**. The case view shows the original reading.
  * 70–85%: the OCR value is kept and the district is shown as a **suggestion** for the officer.
  * The thresholds are `DISTRICT_AUTO_CORRECT` and `DISTRICT_SUGGEST` in `config.py`. Personal names, villages and chiefs are never auto-corrected.
* The perforated (dot-matrix) registration number found on genuine old-issue NRCs is **not** machine-readable with this OCR stack; the system reports the number as unreadable rather than guessing. An officer must transcribe it.

### Performance: `backend/smartclear/pipeline.py`, `cards.py`, `cache.py`
* The two card sides on one page are processed **in parallel** (multi-card pages detect, crop, OCR and extract each card concurrently, then merge).
* Zone re-reads are **batched into a single OCR call** per document instead of one engine call per zone.
* A **content-hash cache** (`storage/ocr_cache/`) makes re-verifying an identical scan effectively instant (~0.3s); editing the extraction code or retraining the tamper model invalidates stale entries automatically.
* Measured on a real legacy-issue scan (CPU, 4 cores): ~29s first pass, ~0.3s cached — vs ~69s before.

### 2. Verification: `backend/smartclear/verify.py`
* NRC number and DOB use **exact** matching after normalisation. DOB accepts dd.mm.yy, ISO, dd/mm/yyyy and other formats.
* Names are normalised and matched with token alignment:
  * different order, case or a 1-character typo → **match**
  * missing middle name → **partial**, for the officer to decide
  * any wholly different name → **mismatch**
* Erased fields give **unreadable**. The system never guesses.

### 3. Flagging: `backend/smartclear/flags.py`
Explainable rules:

| Code | Check |
|---|---|
| `NRC_CODE_DISTRICT` | NRC district code (e.g. `/52/` = Monze) disagrees with the place-of-birth district (reference table in `models/reference.json`) |
| `DISTRICT_INCONSISTENT` | Place-of-birth district ≠ district field |
| `UNDERAGE_REGISTRATION` | Card issued before age 16 |
| `*_UNREADABLE`, `DOB_INVALID`, `DOB_FUTURE`, `REG_BEFORE_BIRTH` | Missing, invalid or impossible values |
| `DUPLICATE_NRC` | Same NRC number previously presented with a different name |
| `RECORD_MISMATCH` | Verification failed |
| `TAMPER_SUSPECTED` | Trained model (below), with plain-language reasons |

**Tamper model** (`forensics.py`, `synth.py`, `scripts/train_tamper.py`): a random forest over 25 named image-forensic features per key field. The features cover ink colour and blueness, per-glyph height, stroke-weight, darkness and colour consistency, sharpness and edge energy, bright correction patches, and recognition-only OCR legibility.

It is trained on **~1,400 synthetic forgeries** made by a generator that reproduces the four alteration techniques seen in the labelled set:
* digit correction patches
* spliced digits in a different font or ink
* substituted surnames
* blur and erasure

Benign augmentations (JPEG, noise, brightness, defocus) are applied to both genuine and forged samples, so "any processing = tamper" can't be learned as a shortcut.

**Risk score (0–100)** combines the rule severities, the tamper probabilities and the verification outcome into three bands:
* **clear**: below 30
* **review**: 30–69
* **high**: 70 and above

### 4. Ground-truth check: Ministry of Home Affairs registry (`registry.py`, `moha_client.py`)
* A sandbox stand-in for the national NRC register, in its own database (`storage/moha_registry.db`) and served as a
  separate app at `/moha/api/v1` behind an `X-API-Key` (`POST /verify`, `GET /citizens/{nrc}`, `GET /stats`).
* Every case sends its extracted NRC number, name, date of birth, sex, card number and district to `/verify` and gets
  per-field match / mismatch results plus the card's status (active, reported lost, replaced, revoked, deceased).
  Disagreements raise `REGISTRY_*` flags and the risk score. If the register can't be reached, the case is still
  created with a "verify manually" warning.
* `run.sh` sets `MOHA_API_URL`, so the server calls the registry over HTTP like an external service. Without it
  (scripts, tests, Docker) the call is made in-process through the same contract.
* **Supabase NRC bank (optional):** set `SUPABASE_URL`, `SUPABASE_SECRET_KEY` and `REGISTRY_BACKEND=supabase` to
  read citizens from the `mohais_citizens` table instead of the local SQLite copy. Load it once with
  `scripts/seed_supabase_registry.py` (upserts by NRC number, safe to re-run). Default is `sqlite`.
* Seeded from the facilitators' ground truth. For altered cards the register keeps the original identity.
  `scripts/evaluate_registry.py` measures it (the **Model performance** page shows the result);
  `scripts/registry_backfill.py` upgrades an existing database.

### 5. AI assistant (`ai.py`)
* Explains each case's results in plain language and suggests one next step (approve, ask for information,
  escalate, reject), with questions the officer could ask the taxpayer.
* **Human in the loop:** it only suggests. The officer decides, and the audit log records the suggestion and whether
  the officer followed it.
* **Privacy:** the model receives an anonymised summary (what differs and by how much, flag types, tamper reasons).
  Names, NRC numbers and dates of birth are never sent.
* Uses OpenRouter (`OPENROUTER_API_KEY` and a comma-separated `OPENROUTER_MODEL` fallback list in `.env`). Without
  a key, or if every model fails, a rule-based explainer returns the same structure. API:
  `POST /api/cases/{id}/explain` (`?refresh=true` to regenerate).

### 6. Officer app: `frontend/` (React, Vite, Tailwind)
* Landing page
* Sign-in
* Dashboard with SVG charts: verification outcomes donut, risk distribution, 14-day throughput, decisions funnel, flags breakdown
* Risk-sorted review queue with pagination (10/25/50/100 rows)
* Case view: the document with evidence overlays, card vs record side by side, flags with reasons, per-field tamper scores, decision buttons with keyboard shortcuts (1–4) and an audit trail
* Upload and verify, plus **batch verification** (up to 50 scans per submission, one case each)
* Taxpayer records (paginated)
* Model performance
* Audit log with CSV export (paginated)

Every submission, view and decision is written to the audit table.

## Repository layout

```
backend/smartclear/   config, document loading, extraction, gazetteer, verify, forensics, synth, flags, pipeline, db, api
backend/scripts/      build_cache.py · train_tamper.py · seed.py · evaluate.py
backend/tests/        pytest suite (verification, rules, live extraction)
data/                 see data/README.md for what each folder is and where it came from
  facilitator_nrc_pdfs/            the 100 synthetic NRC PDFs supplied by the challenge facilitators
  facilitator_ground_truth.csv     verified field values + fraud labels for those PDFs
  synthetic_taxpayer_records.csv   synthetic "captured records", one labelled test scenario per card
  zambia_districts.csv             verified district list (district, province, district code)
  real_nrc/                        real scans + labels.csv for scripts/evaluate_real.py; git-ignored, never commit
models/               tamper_model.joblib · reference.json · tamper_metrics.json · evaluation.json
frontend/             officer web app (built into frontend/dist and served by FastAPI)
storage/              runtime only (SQLite DB, uploads, rendered images, OCR cache); git-ignored
```

## API (all under `/api`, bearer token from `POST /api/login`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/login` | Officer sign-in → token |
| POST | `/cases` | Upload a PDF/image (+ optional `tpin`) → full pipeline result |
| GET | `/cases`, `/cases/{id}` | Queue (filters: `status`, `band`, `q`) and case detail |
| GET | `/cases/{id}/image` | Deskewed document image |
| POST | `/cases/{id}/review` | `approve` · `reject` · `escalate` · `request_info` (+ note) |
| GET | `/stats`, `/evaluation`, `/taxpayers`, `/audit` | Dashboard, metrics, records, audit log |

Interactive docs: http://localhost:8000/docs

## Deploying to Hugging Face Spaces

The repo is Space-ready (see `Dockerfile`, port 7860). The Space serves the built officer UI **and** `/api` from one process; the demo database is seeded at image build time (synthetic NRCs only — never upload real ones to a public Space).

1. Create a free account at huggingface.co → **New Space** → name it (e.g. `smartclear`) → SDK **Docker** → visibility **Public** (demo) or **Private** (controlled access).
2. In Space **Settings**, choose **Link GitHub repository**, pick `WazDevZm/smartclear`, branch `master` — pushes to `master` now auto-rebuild and redeploy.
3. Wait for the build (~5–10 min), open the Space URL, sign in with **officer / futureminds**.
4. Re-seed the demo DB at any time by rebuilding the Space (or deleting `storage/smartclear.db` — it is baked in at build).

> Or push directly to the Space's git remote instead of linking GitHub. Note: a public Space is public — synthetic data only; real NRCs belong in ZRA's controlled sandbox, not on a public URL.

## Data handling
* Development used **synthetic** NRCs plus a few genuine team-supplied scans (used to develop the page normalisation, the legacy-template zones and the row-spacing adjustment; the scans are not in this repository). Nothing leaves the machine, and no cloud OCR or LLM is called.
* The uploaded source file is stored unchanged; preprocessing crops clear card regions, reads every PDF page, and creates a grayscale evidence preview.
* Real ZRA documents should be processed only inside ZRA's controlled sandbox. See NEXT_STEPS.md.

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

Sign in with **officer / smartclear** (or **supervisor / smartclear**).

`./run.sh --retrain` rebuilds the OCR cache, retrains the tamper model and re-runs the evaluation.

Frontend dev with hot reload: start the API (`cd backend && ../.venv/bin/uvicorn smartclear.api:app --reload`),
then run `cd frontend && npm run dev` and open http://localhost:5173. Vite proxies `/api` to the API.

Tests: `cd backend && ../.venv/bin/python -m pytest -q`

## Results on the synthetic set (100 NRCs, 33 labelled fraudulent)

| Brief success measure | Result | How it is measured |
|---|---|---|
| Extraction accuracy (NRC no., name, DOB) | **100%** (300/300 legible fields) | vs manually verified reading, `data/ground_truth.csv` |
| Extraction under perturbation | **100%** (20 docs) | rotation ±3°, scale ±5%, shift, noise, JPEG q70 |
| Verification accuracy | **100%** (66 match / 7 review / 27 mismatch) | vs expected outcome per synthetic record scenario |
| Fraud-flagging recall | **100%** (33/33) | district swaps 11/11, underage 8/8, visual tampers 17/17 |
| Fraud-flagging precision | **94.3%** (2 false alarms) | tamper scores are 5-fold, document-grouped, out-of-fold |
| Tamper model, synthetic-only training | recall 100%, ROC-AUC 1.0 | trained on generated forgeries only, scored on the real tampered cards |
| Processing time | ~1.0 s median per document | laptop CPU, no GPU, no cloud |

Full report: `models/evaluation.json` and the **Model performance** page in the app.
**Read the caveats in [NEXT_STEPS.md](NEXT_STEPS.md#honest-caveats) before quoting these numbers.**

## How it works

### 1. Extraction: `backend/smartclear/extraction.py`
* **RapidOCR** (PaddleOCR PP-OCR detection and recognition models on ONNX Runtime) runs fully on-premise.
* Every PDF page is cropped and OCR'd independently. Pages are classified as card front or back; front-side fields and the back-side NRC number are then merged with their page coordinates preserved. Unknown pages are not used to fill fields.
* A clearly dominant quadrilateral card is cropped and perspective-corrected; if boundaries are ambiguous, the page is kept intact and the case warns officers to review nearby stamps or handwriting.
* Pages without a readable horizontal card anchor are checked at quarter-turn rotations. Unknown layouts are still not mapped to new field positions automatically.
* OCR uses a grayscale, contrast-normalized view. The uploaded original and its color pixels remain unchanged for storage and forensic analysis.
* Pass 1: OCR finds anchors (the "REGISTRATION CARD" title, the card number and the registration number) and estimates skew from the text-box angles.
* The page is deskewed and a card-relative coordinate frame is scaled from the printed title, so field zones adapt to different scan sizes.
* Pass 2: each field zone is cropped and re-read at 2×. The two passes are **fused** by keeping the most confident read for each position, which recovers words the full-page detector clips at printed lines.
* Printed form labels are removed by glyph height plus fuzzy matching, weighted by OCR confidence.
* District fields are snapped to a gazetteer of Zambia's 116 districts (`gazetteer.py`). Personal names are never auto-corrected.

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

### 4. Officer app: `frontend/` (React, Vite, Tailwind)
* Landing page
* Sign-in
* Dashboard
* Risk-sorted review queue
* Case view: the document with evidence overlays, card vs record side by side, flags with reasons, per-field tamper scores, decision buttons and an audit trail
* Upload and verify
* Taxpayer records
* Model performance
* Audit log

Every submission, view and decision is written to the audit table.

## Repository layout

```
backend/smartclear/   config, document loading, extraction, gazetteer, verify, forensics, synth, flags, pipeline, db, api
backend/scripts/      build_cache.py · train_tamper.py · seed.py · evaluate.py
backend/tests/        pytest suite (verification, rules, live extraction)
data/synthetic_nrc/   the 100 synthetic NRC PDFs supplied for the challenge
data/ground_truth.csv     manually verified field values + fraud labels (type, tampered field, technique)
data/taxpayer_records.csv synthetic "captured records" with a labelled test scenario per record
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

## Data handling
* All development used **synthetic** NRCs only. Nothing leaves the machine, and no cloud OCR or LLM is called.
* The uploaded source file is stored unchanged; preprocessing crops clear card regions, reads every PDF page, and creates a grayscale evidence preview.
* Real ZRA documents should be processed only inside ZRA's controlled sandbox. See NEXT_STEPS.md.

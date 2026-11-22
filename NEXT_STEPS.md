# SmartClear: next steps for the team

The prototype runs end to end on the synthetic set. This file covers three things: what is **done**, what the numbers do **not** prove yet, and the remaining work by role. The roles follow our proposal.

## Done

- [x] Extract → verify → flag → review pipeline, running locally (`./run.sh`)
- [x] AI/OCR extraction of all 13 NRC fields, with confidence and evidence boxes. Two-pass fused OCR, deskew, gazetteer correction.
- [x] Verification: exact NRC/DOB, tolerant name matching with match, partial and mismatch outcomes
- [x] Explainable rules:
  - NRC district code vs district
  - district consistency
  - underage registration
  - impossible dates
  - unreadable fields
  - duplicate NRC
- [x] Trained field-level tamper model, plus the synthetic forgery generator used to train it
- [x] Evaluation harness for the brief's three success measures, plus a robustness test (`scripts/evaluate.py`)
- [x] Officer web app: queue, case review with evidence, decisions, audit trail, metrics page, landing page
- [x] Performance: multi-card pages processed in parallel + batched zone OCR + content-hash cache (~0.3s re-verify)
- [x] Batch verification page, paginated lists (queue / records / audit) with rows-per-page selector, audit CSV export, dashboard charts, keyboard decision shortcuts
- [x] Unit and end-to-end tests (`pytest`, 18 passing)

## Honest caveats

Please read these before presenting results:

1. **Small, single-template dataset.** The 100 cards come from one generator with one layout. The extraction zones were calibrated on these same cards, so 100% here is a ceiling, not a forecast. Real scans (phone photos, glare, old laminated cards, folds) will score lower.
2. **We created the labels.** `facilitator_ground_truth.csv` comes from visually inspecting the synthetic set:
   - 17 visual tampers
   - 11 district inconsistencies
   - 8 underage registrations

   The rule-based labels (district, underage) are partly defined by the rules that catch them. Treat ZRA's own labelled fake-NRC set as the real test.

3. **The forgery generator mimics the techniques we observed.** The tamper model may miss forgery styles it has never seen, for example a high-quality reprint or photo substitution. The photo is not analysed yet.
4. **The captured taxpayer records are synthetic.** ZRA is still identifying the real records source, so verification accuracy measures our matching logic against scenarios we designed.
5. **The district-code table was learned from 26 codes seen in genuine cards.** It must be replaced with the official NRB code table.
6. **Pilot-grade auth.** Demo accounts are hard-coded in `api.py`, and tokens are HMAC-signed bearer tokens.
7. **Preprocessing is still a heuristic.** Pages are processed independently, clear quadrilateral cards are perspective-corrected, and unreadable orientations are checked at quarter turns. These behaviors and side classification still need evaluation on representative scans. Ambiguous crops are left uncropped; the tamper model is still trained on synthetic cards and may over-flag genuine originals.

10. **One real scan has been run through the pipeline.** The numbers in README are from that single legacy-issue scan: bold print reads exactly (card no., registration date), faint dotted print reads approximately with low confidence (name, village, districts), and the dot-perforated registration number is unreadable by RapidOCR — reported as unreadable, not guessed. The legacy template zones (`FIELD_BOXES_LEGACY`) and the layout-stretch detection are calibrated on this one card. Do not quote a real-world accuracy from it; label a representative sample and report per-field accuracy with confidence intervals.

## Remaining work by role

### Data Science Lead

- [ ] Agree the **baseline protocol** with ZRA (time per document, error rate and backlog under the manual process). This is a brief requirement. The `processing_time_ms` and audit timestamps already give the SmartClear side.
- [ ] Hand-label a representative sample of **real** NRCs inside the ZRA sandbox (field values and genuine/fake), then run `scripts/evaluate.py` on it. Report per-field accuracy and confidence intervals, not single numbers.
- [ ] Tune thresholds on real data: `TAMPER_FIELD_THRESHOLD`, `NAME_MATCH_THRESHOLD`, `NAME_REVIEW_THRESHOLD`, and the risk bands in `flags.risk()`. Plot precision against recall and pick the operating point with ZRA. Missing a fraud likely costs more than an extra review.
- [ ] Replace `models/reference.json` with the official NRB district-code table and extend `gazetteer.py` if needed.
- [ ] Check the name matcher on real Zambian name variants: clan names, hyphenation, transliteration and initials.

### AI Lead

- [x] **Generalise extraction beyond the synthetic template (first pass, a few real scans).** Pages are normalised so detected cards sit at the calibrated width, multi-card pages no longer break the anchors, and the taller "legacy green" layout is auto-detected and calibrated (`cards.py`, `FIELD_BOXES_LEGACY`). On the standard layout, zones stretch to each card's row spacing measured from printed labels. Contrast-enhanced re-read of the name field; deterministic label-phrase stripping; dates with 4-digit years; districts matched to the verified list. Test on a wider set of real scans — especially phone photos (glare, perspective), which this does not yet handle.
- [ ] Re-calibrate the legacy zones on more real cards and learn them (e.g. a key-value layout model) instead of hand-tuning; the current legacy calibration is one card wide.
- [ ] **Benchmark OCR on held-out, labelled cards.** Compare current vs. alternative preprocessing, field crops/layouts, and OCR engines across damaged text and real scan conditions (phone photos, blur, glare, rotation, low resolution, compression, stamps, and handwriting). Report per-field accuracy, character errors, wrong-field assignments, unreadable-field hallucinations/false blanks, review rate, and processing time; keep tuning data separate.
- [ ] Retrain the tamper model on ZRA's **labelled fake-NRC set**. Keep the document-grouped CV in `train_tamper.py`, and add new forgery techniques to `synth.py` as they are discovered.
- [ ] Add a **photo and portrait check**: replaced photo, face-region tamper, and an optional face match against a captured selfie.
- [ ] Add document-level forensics: JPEG ghost / error-level analysis, copy-move detection, and checks on security features such as the coat-of-arms region and thumbprint area.
- [ ] Optional: compare against a vision-LLM extractor running on-premise, on accuracy, latency and cost.

### Back End Development

- [ ] Connect to ZRA's **captured registration records** (read-only API or DB view) in place of the `taxpayers` table, and match by TPIN.
- [ ] Replace demo auth with **ZRA SSO / Active Directory**, with role-based permissions (officer vs supervisor approvals for escalations).
- [ ] Move from SQLite to ZRA's database (Postgres or SQL Server). Encrypt uploads at rest and add a retention and deletion policy for NRC images.
- [ ] Containerise with a Dockerfile and docker-compose for the ZRA sandbox. Add structured logging, health checks and a batch endpoint for back-processing the 2,000–6,000 scanned NRCs.
- [ ] Make the audit log tamper-evident (append-only, hash-chained) and add an export.

### Front End & UI/UX

- [ ] Run usability sessions with TSE and Domestic Taxes officers, then iterate on the case view: wording of flags, layout at the counter, and keyboard shortcuts for approve and reject.
- [x] Batch upload: `/api/batches` + batch verification page (up to 50 scans per submission; one case each, risk-ordered into the queue).
- [ ] A supervisor queue for escalations, and a timing view comparing manual and SmartClear handling.
- [ ] Accessibility pass (contrast, focus states, screen reader labels) and a light theme for bright offices.
- [ ] Keep the "flags support judgement" message visible in every view, as a governance requirement.

## Measuring on real cards

Real NRCs are personal data. Keep them only in `data/real_nrc/`, which git ignores.

1. Put scans in `data/real_nrc/` (PDF or image; front, or front and back).
2. Run `.venv\Scripts\python.exe backend\scripts\evaluate_real.py` (add `--dir data/real` for that folder). The first run creates `labels.csv`. To just look at one scan's fields, pass the file path instead.
3. Have a person fill in the values printed on each card. Write `EMPTY` for a field that is blank on the card, and leave a cell empty to skip scoring it.
4. Run the script again. It prints per-field accuracy with 95% intervals, the character error rate, and whether each error was a blank, a wrong value, or an invented value.

Collect 30–50 cards across card versions and scan conditions before tuning anything. One card is not enough to choose OCR preprocessing.

## Useful commands

```bash
./run.sh                                   # set up and start
./run.sh --retrain                         # rebuild OCR cache, retrain model, reseed, re-evaluate
.venv/bin/python backend/scripts/evaluate.py      # regenerate models/evaluation.json
cd backend && ../.venv/bin/python -m pytest -q    # tests
```

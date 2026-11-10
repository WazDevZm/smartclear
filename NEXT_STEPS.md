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
- [x] Unit and end-to-end tests (`pytest`, 12 passing)

## Honest caveats
Please read these before presenting results:
1. **Small, single-template dataset.** The 100 cards come from one generator with one layout. The extraction zones were calibrated on these same cards, so 100% here is a ceiling, not a forecast. Real scans (phone photos, glare, old laminated cards, folds) will score lower.
2. **We created the labels.** `ground_truth.csv` comes from visually inspecting the synthetic set:
   - 17 visual tampers
   - 11 district inconsistencies
   - 8 underage registrations

   The rule-based labels (district, underage) are partly defined by the rules that catch them. Treat ZRA's own labelled fake-NRC set as the real test.
3. **The forgery generator mimics the techniques we observed.** The tamper model may miss forgery styles it has never seen, for example a high-quality reprint or photo substitution. The photo is not analysed yet.
4. **The captured taxpayer records are synthetic.** ZRA is still identifying the real records source, so verification accuracy measures our matching logic against scenarios we designed.
5. **The district-code table was learned from 26 codes seen in genuine cards.** It must be replaced with the official NRB code table.
6. **Pilot-grade auth.** Demo accounts are hard-coded in `api.py`, and tokens are HMAC-signed bearer tokens.

## Remaining work by role

### Data Science Lead
- [ ] Agree the **baseline protocol** with ZRA (time per document, error rate and backlog under the manual process). This is a brief requirement. The `processing_time_ms` and audit timestamps already give the SmartClear side.
- [ ] Hand-label a representative sample of **real** NRCs inside the ZRA sandbox (field values and genuine/fake), then run `scripts/evaluate.py` on it. Report per-field accuracy and confidence intervals, not single numbers.
- [ ] Tune thresholds on real data: `TAMPER_FIELD_THRESHOLD`, `NAME_MATCH_THRESHOLD`, `NAME_REVIEW_THRESHOLD`, and the risk bands in `flags.risk()`. Plot precision against recall and pick the operating point with ZRA. Missing a fraud likely costs more than an extra review.
- [ ] Replace `models/reference.json` with the official NRB district-code table and extend `gazetteer.py` if needed.
- [ ] Check the name matcher on real Zambian name variants: clan names, hyphenation, transliteration and initials.

### AI Lead
- [ ] **Generalise extraction beyond the synthetic template.** Add a card detector or perspective correction for phone photos, plus a fallback for when the anchors are not found (currently `anchored=False` and the layout fields are empty). Test on real scan quality.
- [ ] Re-calibrate `FIELD_BOXES` and `REG_OFFSET` in `extraction.py` on real cards, or learn them, e.g. with a small key-value layout model.
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
- [ ] Add batch upload, a supervisor queue for escalations, and a timing view comparing manual and SmartClear handling.
- [ ] Accessibility pass (contrast, focus states, screen reader labels) and a light theme for bright offices.
- [ ] Keep the "flags support judgement" message visible in every view, as a governance requirement.

### Business & Research Lead
- [ ] Map the current manual workflow and confirm where SmartClear sits (at the counter vs back office).
- [ ] Finalise data-handling requirements with ZRA: DPIA, access controls, sandbox rules, and who may see real NRC images.
- [ ] Define the **decision-gate criteria** for continue, redesign or stop (relevance, usability, data quality), as in the brief.
- [ ] Write up the limitations (above) and the replication path: passports, customs.
- [ ] Prepare the showcase demo script using the seeded cases:
  - SC-0101 (district swap)
  - SC-0105 (patched NRC digit)
  - SC-0152 (substituted surname)
  - SC-0139 (registered at age 9)
  - SC-0177 (erased NRC number)

## Suggested timeline (remaining pilot)
| Weeks | Focus |
|---|---|
| 1–2 | Sandbox deployment (Docker), real-records connection, baseline protocol agreed, real sample labelled |
| 3–5 | Extraction generalisation on real scans; tamper model retrained on ZRA's fake-NRC set; threshold tuning |
| 6–8 | Officer usability testing and UI iteration; SSO and audit hardening |
| 9–10 | Final evaluation against manual baseline, limitations write-up, showcase |

## Useful commands
```bash
./run.sh                                   # set up and start
./run.sh --retrain                         # rebuild OCR cache, retrain model, reseed, re-evaluate
.venv/bin/python backend/scripts/evaluate.py      # regenerate models/evaluation.json
cd backend && ../.venv/bin/python -m pytest -q    # tests
```

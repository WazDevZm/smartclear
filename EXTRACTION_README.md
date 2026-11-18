# SmartClear extraction: making field reading accurate on real NRCs

This document is the plan for taking the NRC field extractor from "accurate on the synthetic set" to "accurate on real scans." It is a set of steps to follow, not a status report. For overall project status, see [NEXT_STEPS.md](NEXT_STEPS.md). For the known problems list, see [tomakeitbetter.md](tomakeitbetter.md).

## 1. The problem

The extractor in [backend/smartclear/extraction.py](backend/smartclear/extraction.py) assumes one card layout:

- `ZONES`, `FIELD_BOXES`, `COL_DIVIDER`, `DOB_MAX_DX`, `SEX_MIN_DX` and `REG_OFFSET` are pixel offsets measured from the printed anchors ("REGISTRATION CARD" title and the card-number line).
- `REFERENCE_TITLE_WIDTH` is the title width measured on the synthetic training scans.
- When the anchors are not found, the card is marked `anchored=False` and the layout fields come back empty.

These values were calibrated on the 100 synthetic cards. The reported 100% extraction accuracy is a ceiling on the data the zones were tuned against. It does not predict performance on real scans, where card versions, print, scan offsets, glare, folds and stamps all vary.

The OCR engine (RapidOCR, pretrained PP-OCR models) is not the first thing to fix. When a crop is correct, it reads reasonably well. Most failures are expected to come from wrong crops, wrong zones, or blank fields.

## 2. Principles

1. **Measure on real labelled cards before changing anything.** Tuning constants against synthetic cards makes the synthetic score go up and real-card performance harder to predict.
2. **Abstain instead of guessing.** A blank that goes to human review is acceptable. A wrong value that is accepted is the failure that matters for a fraud-screening tool.
3. **Keep held-out data held out.** Cards used to tune zones or thresholds must not be used to report final accuracy.
4. **Report per field, with uncertainty.** Use accuracy with confidence intervals per field, not a single number.
5. **Keep all processing on ZRA infrastructure.** NRC images and extracted values are personal data.

## 3. Step 1: Get a small real labelled set

**Goal:** roughly 50 to 100 real scans, each hand-labelled. Nothing else will move the numbers as much.

Work with ZRA inside the sandbox to label the scans. Each card needs:

- `doc_id`
- card version (if known, otherwise `unknown`)
- side (front or back)
- image quality notes (blur, glare, fold, stamp, handwriting, rotation)
- the true value for each of the 13 fields, or `UNREADABLE` where a human cannot read the field either

Store the labels in a CSV in the same shape as [data/ground_truth.csv](data/ground_truth.csv), so `evaluate.py` can read them without changes. Keep the real images and labels out of git.

Split the set before any tuning, and keep the held-out part held out:

- **Tuning set** (about 40%): used to find card versions, zone offsets and thresholds.
- **Held-out set** (about 60%): run once per release to report accuracy. Never tune against it.

## 4. Step 2: Sort the errors into buckets before changing code

`scripts/evaluate.py` already writes per-field errors to `models/evaluation.json`, including `raw`, `bbox` and `confidence`. Run it on the real labelled set:

```bash
.venv/bin/python backend/scripts/evaluate.py
```

Then use `backend/scripts/build_error_set.py` to create review crops in `storage/error_review/`. Look at the crops, and tag each error with one bucket:

| Bucket | Meaning | Fix lives in |
|---|---|---|
| **Routing** | Wrong page or side was used, or the card was not found | Side classification, card crop, orientation checks |
| **Zone** | Right card, but the text came from the wrong field or box | `FIELD_BOXES`, `ZONES`, card version map |
| **Character** | Field located correctly, characters misread (for example `O` vs `0`) | OCR model, `DIGIT_FIX` and `ALPHA_FIX`, fine-tuning |
| **Unreadable** | Blank, low confidence, or unreadable by a human | Abstention thresholds, human review path |

Each bucket needs a different fix. Only the **Character** bucket is an OCR problem. Record the bucket counts per field; that table decides what to do next.

## 5. Step 3: Make the system abstain instead of guessing

Do this before changing OCR.

- **Identify the card version** from printed anchors. Keep a version registry: each version has its own anchors, field boxes and reference width.
- **Validate each version's field map** on labelled examples from that version before it is used.
- **Send unmatched cards to review.** If the anchors are not found or no version matches, do not fill layout fields from the synthetic map. Mark the card as needing review.
- **Gate fields on agreement.** `_fuse` already combines two OCR passes. Accept a field only when the passes agree or confidence is above a threshold. Otherwise mark it unreadable and route it to review.
- **Track "wrong values accepted" as the main safety metric.** Report it separately from extraction accuracy, and drive it down first. A blank that gets reviewed costs an officer a few seconds; a wrong value that is accepted can pass a forged or mistyped record through.

## 6. Step 4: Fix zones per card version

For each version with enough labelled examples:

1. Measure zone errors for that version only.
2. Adjust that version's field boxes. Do not change the shared map for other versions.
3. Re-run evaluation on the held-out set for that version.

Where anchors are unreliable, consider learning field positions from labelled examples (for example, a small key-value layout model) instead of hand-measuring offsets.

## 7. Step 5: Fix OCR last, and only for the character-misread bucket

Only start here if the **Character** bucket is large and the **Zone** and **Routing** buckets are small. Fine-tuning cannot fix a wrong crop or a wrong field.

Options, in order of cost:

1. **Better preprocessing for the crop** (contrast, binarisation choice, scale). Measure on the same held-out set.
2. **Compare OCR engines** on the same field crops. Report per-field accuracy, character errors and processing time.
3. **Fine-tune the PP-OCR recognition model** on labelled field crops from the tuning set. A few thousand labelled crops is usually enough for a recognition fine-tune. Evaluate on the held-out set only.

## 8. Step 6: Use a second opinion for uncertain fields

For fields that still fail the agreement gate after steps 3 to 5, use one of these:

- **Agreement between the two OCR passes** already in `_fuse`, as described in step 3.
- **An on-premise vision model**, consulted only on low-confidence fields. Compare its accuracy, latency and cost against the current pipeline on the held-out set.

If the second reader and the OCR disagree, route the field to human review. Do not pick one automatically. Keep all processing on ZRA infrastructure given the data sensitivity; no cloud OCR or vision service is used.

## 9. Reporting

Each evaluation release should report:

- per-field accuracy on the held-out set, with confidence intervals
- error bucket counts per field
- wrong values accepted (safety metric)
- review rate (share of fields and cards sent to a human)
- processing time per card

Keep each report tied to the model and label versions used.

## 10. Commands

```bash
./run.sh                                              # set up and start
./run.sh --retrain                                    # rebuild OCR cache, retrain tamper model, reseed, re-evaluate
.venv/bin/python backend/scripts/evaluate.py          # regenerate models/evaluation.json
.venv/bin/python backend/scripts/build_error_set.py   # review crops in storage/error_review/
cd backend && ../.venv/bin/python -m pytest -q        # tests
```

## 11. Definition of done

Extraction is ready to rely on for a given card version when:

- the held-out set for that version has been evaluated once, with per-field results and intervals reported
- the wrong-values-accepted rate is below the threshold agreed with ZRA
- cards that cannot be matched to a validated version go to review, not to layout guesses
- the review rate is acceptable to ZRA operations

Thresholds are set with ZRA, not chosen by the engineering team alone.

## Open questions

- Which card versions exist in the ZRA population, and how many genuine cards of each version can be labelled?
- What wrong-value rate does ZRA accept, and what review rate can operations handle?
- Can labelled real images be used in the sandbox, and under what retention rules?

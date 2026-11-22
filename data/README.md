# Data folders

Two kinds of synthetic NRC data live here. Keep them apart: they come from different sources
and are used for different things. None of it is real personal data.

## From the challenge facilitators (in git)

| Path | What it is | Used by |
|---|---|---|
| `facilitator_nrc_pdfs/` | The 100 synthetic NRC scans (PDF) supplied with the ZRA challenge, `nrc-syn-0101` to `nrc-syn-0200` | The app's demo cases (`seed.py`), evaluation, tests |
| `facilitator_ground_truth.csv` | Verified field values for each of those PDFs, plus fraud labels (`is_fraud`, `fraud_types`, `tampered_field`, `tamper_technique`) | Evaluation, tamper-model training, `seed.py` |

## Made by the team

| Path | In git? | What it is | Used by |
|---|---|---|---|
| `synthetic_taxpayer_records.csv` | yes | Synthetic "captured taxpayer records", one per facilitator card, each with a labelled test scenario (exact, typo, different person, ...). Written by `backend/scripts/seed.py` from the ground truth | Record verification in the app and evaluation |
| `zambia_districts.csv` | yes | Verified list of Zambia's districts (district, province, district code) | District correction (`gazetteer.py`) |
| `generated_nrc_cards_v5/` | no (local) | 120 fictional cards from our own generator (`generate_nrc_v5.py` inside), each as a clean render plus a flatbed scan, phone photo or photocopy, with per-field text and boxes in `labels.json` | Source for the OCR field crops |
| `generated_ocr_field_crops/` | no (local) | One image per printed field, cut from `generated_nrc_cards_v5/`, with its text in `train.txt` / `val.txt` / `test.txt`. Split by card, so no card is in two splits | Fine-tuning the ONNX text reader (`ocr-text-extraction` and `onnx_model` branches) |
| `generated_nrc_cards_v5_zips/` | no (local) | The same generated set packaged as zip files for sharing | Sharing / restoring `generated_nrc_cards_v5/` |

## Real cards

`real_nrc/` is reserved for real scans and their labels (`labels.csv`), used by
`backend/scripts/evaluate_real.py`. It is git-ignored. Never commit real NRC images.

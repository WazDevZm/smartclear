"""Central paths and tunables for SmartClear."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"
STORAGE_DIR = ROOT / "storage"          # uploaded docs, rendered images, crops
DB_PATH = STORAGE_DIR / "smartclear.db"
FRONTEND_DIST = ROOT / "frontend" / "dist"

# Source synthetic dataset supplied with the challenge (sibling folder of the project)
SYNTHETIC_PDF_DIR = DATA_DIR / "facilitator_nrc_pdfs"         # the 100 synthetic NRC PDFs supplied by the facilitators
GROUND_TRUTH_CSV = DATA_DIR / "facilitator_ground_truth.csv"     # verified field values + fraud labels for those PDFs
TAXPAYER_RECORDS_CSV = DATA_DIR / "synthetic_taxpayer_records.csv"  # synthetic "captured records" (written by seed.py)

DISTRICTS_CSV = DATA_DIR / "zambia_districts.csv"   # verified district list (DISTRICT, PROVINCE, DIST_CODE)

# District post-correction: fuzzy similarity (0-100) between OCR text and a known district
DISTRICT_AUTO_CORRECT = 85     # at or above: replace with the canonical district (raw OCR kept)
DISTRICT_SUGGEST = 70          # at or above (but below auto): keep OCR value, offer the district to the officer

TAMPER_MODEL_PATH = MODELS_DIR / "tamper_model.joblib"
REFERENCE_PATH = MODELS_DIR / "reference.json"   # district-code table learned from genuine specimens

# Verification thresholds
NAME_MATCH_THRESHOLD = 90      # token-sort similarity (0-100) to count as a name match
NAME_REVIEW_THRESHOLD = 75     # between review and match -> "partial" (officer decides)

# Fraud / risk thresholds
TAMPER_FIELD_THRESHOLD = 0.5   # per-field tamper probability that raises a flag
MIN_REGISTRATION_AGE = 16      # NRCs are issued from age 16 in Zambia
OCR_LOW_CONFIDENCE = 0.80

for d in (STORAGE_DIR, MODELS_DIR, DATA_DIR):
    d.mkdir(parents=True, exist_ok=True)

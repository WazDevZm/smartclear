"""Central paths and tunables for SmartClear."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"
STORAGE_DIR = ROOT / "storage"          # uploaded docs, rendered images, crops
DB_PATH = STORAGE_DIR / "smartclear.db"
FRONTEND_DIST = ROOT / "frontend" / "dist"

# Source synthetic dataset supplied with the challenge (sibling folder of the project)
SYNTHETIC_PDF_DIR = DATA_DIR / "synthetic_nrc"

# Fine-tuned PP-OCRv4 English text recognizer (ocr_training/), used for the text-reading step.
OCR_REC_MODEL_PATH = MODELS_DIR / "ocr" / "nrc_rec.onnx"
OCR_REC_KEYS_PATH = MODELS_DIR / "ocr" / "nrc_rec_keys.txt"
REFERENCE_PATH = MODELS_DIR / "reference.json"   # district-code table learned from genuine specimens

# Verification thresholds
NAME_MATCH_THRESHOLD = 90      # token-sort similarity (0-100) to count as a name match
NAME_REVIEW_THRESHOLD = 75     # between review and match -> "partial" (officer decides)

# Fraud / risk thresholds
MIN_REGISTRATION_AGE = 16      # NRCs are issued from age 16 in Zambia
OCR_LOW_CONFIDENCE = 0.80

for d in (STORAGE_DIR, MODELS_DIR, DATA_DIR):
    d.mkdir(parents=True, exist_ok=True)

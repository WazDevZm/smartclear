"""Central paths and tunables for SmartClear."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_env(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines); real environment variables take precedence."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env(ROOT / ".env")
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"
# uploaded docs, rendered images, crops, DB. SMARTCLEAR_STORAGE_DIR (relative to the project root)
# lets two copies of the app run side by side, e.g. one per text reader, without sharing cases.
STORAGE_DIR = ROOT / os.environ.get("SMARTCLEAR_STORAGE_DIR", "storage")
DB_PATH = STORAGE_DIR / "smartclear.db"
REGISTRY_DB_PATH = STORAGE_DIR / "moha_registry.db"   # sandbox Ministry of Home Affairs register (separate system)
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

# Text recognizer used for reading fields. Detection always uses the stock PP-OCR detector.
#   stock: RapidOCR's bundled PP-OCRv4 recognizer (default, unchanged behaviour)
#   onnx:  PP-OCRv4 English recognizer fine-tuned on synthetic NRC field crops (models/ocr/)
# Choose with the SMARTCLEAR_OCR_READER environment variable.
OCR_READERS = ("stock", "onnx")
OCR_REC_MODEL_PATH = MODELS_DIR / "ocr" / "nrc_rec.onnx"
OCR_REC_KEYS_PATH = MODELS_DIR / "ocr" / "nrc_rec_keys.txt"


def ocr_reader() -> str:
    """The text recognizer selected by SMARTCLEAR_OCR_READER ('stock' when unset)."""
    reader = os.environ.get("SMARTCLEAR_OCR_READER", "stock").strip().lower() or "stock"
    if reader not in OCR_READERS:
        raise ValueError(f"SMARTCLEAR_OCR_READER must be one of {OCR_READERS}, got {reader!r}")
    return reader
REFERENCE_PATH = MODELS_DIR / "reference.json"   # district-code table learned from genuine specimens

# Verification thresholds
NAME_MATCH_THRESHOLD = 90      # token-sort similarity (0-100) to count as a name match
NAME_REVIEW_THRESHOLD = 75     # between review and match -> "partial" (officer decides)

# Fraud / risk thresholds
TAMPER_FIELD_THRESHOLD = 0.5   # per-field tamper probability that raises a flag
MIN_REGISTRATION_AGE = 16      # NRCs are issued from age 16 in Zambia
OCR_LOW_CONFIDENCE = 0.80

# Ministry of Home Affairs ground-truth registry. Unset URL = call the registry in-process (scripts, tests);
# set it (run.sh does) to send extracted data over HTTP, exactly as to a real external service.
MOHA_API_URL = os.environ.get("MOHA_API_URL", "").rstrip("/")
MOHA_API_KEY = os.environ.get("MOHA_API_KEY", "moha-sandbox-key-change-me")
MOHA_TIMEOUT_S = float(os.environ.get("MOHA_TIMEOUT_S", "8"))
# Where the registry's NRC bank lives: "sqlite" (local copy, default) or "supabase" (mohais_citizens table).
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")
SUPABASE_TIMEOUT_S = float(os.environ.get("SUPABASE_TIMEOUT_S", "8"))
REGISTRY_BACKEND = os.environ.get("REGISTRY_BACKEND", "sqlite").lower()

# AI explanation layer (OpenRouter, OpenAI-compatible). Without a key, a deterministic rule-based explainer is used.
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
# Free models, fastest reliable first (benchmarked 2026-11-23 on a real case; see docs). Rate-limited ones fail fast.
OPENROUTER_MODELS = [m.strip() for m in os.environ.get(
    "OPENROUTER_MODEL", "particle-ai/particle-1:free,nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free,dots-studio/dots-3-note-preview:free,nvidia/nemotron-3-ultra-550b-a55b:free,nvidia/nemotron-3.5-super-vl:free").split(",") if m.strip()]
AI_TIMEOUT_S = float(os.environ.get("AI_TIMEOUT_S", "20"))      # per model attempt
# Total time across all model attempts before the rule-based explainer answers instead. Keeps the request well
# under hosting proxies' timeouts (which otherwise surface as 502/504).
AI_BUDGET_S = float(os.environ.get("AI_BUDGET_S", "25"))

for d in (STORAGE_DIR, MODELS_DIR, DATA_DIR):
    d.mkdir(parents=True, exist_ok=True)

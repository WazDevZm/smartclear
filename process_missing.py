import csv, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path('backend').resolve()))
from smartclear import db, config
from smartclear.api import create_case
from smartclear.config import STORAGE_DIR, SYNTHETIC_PDF_DIR

CACHE = STORAGE_DIR / "cache" / "docs"
# load records
by_doc = {}
with open('data/taxpayer_records.csv') as fh:
    for r in csv.DictReader(fh):
        by_doc[r['source_doc']] = r

pdfs = [Path('data/synthetic_nrc')/f'nrc-syn-{i:04d}.pdf' for i in range(196,201)]
db.init()
with db.conn() as c:
    for p in pdfs:
        js = CACHE / f"{p.stem.upper()}.json"
        tokens = json.loads(js.read_text())["tokens"] if js.exists() else None
        cid = create_case(c, p.read_bytes(), p.name, by_doc[p.name]["tpin"], "system:seed", tokens=tokens,
                          ref=f"SC-{p.stem[-4:]}")
        row = c.execute("SELECT risk_band, verification, n_flags FROM cases WHERE id=?", (cid,)).fetchone()
        print(f"{p.name}: {dict(row)}", flush=True)
print("done")

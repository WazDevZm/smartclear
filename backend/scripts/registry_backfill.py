"""Re-seed the MoHA sandbox registry and run the registry check on every existing case (no OCR needed).

Use after upgrading an existing database: ``.venv/bin/python backend/scripts/registry_backfill.py``
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smartclear import db, moha_client, registry  # noqa: E402

if __name__ == "__main__":
    print(f"MoHA registry: {registry.seed()} citizens")
    outcomes = Counter()
    with db.conn() as c:
        for row in c.execute("SELECT id, result FROM cases").fetchall():
            result = moha_client.apply(json.loads(row["result"]))
            result.pop("ai", None)
            c.execute("UPDATE cases SET result=?, risk_score=?, risk_band=?, n_flags=? WHERE id=?",
                      (json.dumps(result), result["risk"]["score"], result["risk"]["band"], len(result["flags"]),
                       row["id"]))
            outcomes[result["registry"]["outcome"]] += 1
    print("registry outcomes:", dict(outcomes))

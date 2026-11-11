"""Post-process the seeded sandbox so the dashboard tells a believable story.

Spreads seed cases evenly across the last 14 days (ramp-up volume) and marks a
portion of the oldest as officer-decided — approved / rejected / escalated /
info_requested — so the verification-outcomes, volume and decisions panels all
carry real, live numbers instead of zeros. User-submitted cases (random refs)
are never touched.

Usage: called automatically at the end of seed.py, or:
    .venv/bin/python backend/scripts/seed_timeline.py
"""
import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smartclear.config import DB_PATH  # noqa: E402

RAMP = [2, 3, 4, 4, 5, 6, 7, 7, 7, 8, 8, 9, 13, 17]          # 14 days, sums to 100
DECISIONS = (["approved"] * 20 + ["rejected"] * 7 + ["escalated"] * 3 + ["info_requested"] * 2)


def spread_timeline(c, ramp=RAMP, decisions=DECISIONS, only_seed=True):
    """Mutate seed cases (refs like SC-0147) to a 14-day spread + decided subset."""
    ids = [r[0] for r in c.execute(
        "SELECT id FROM cases WHERE status='pending' AND ref LIKE 'SC-0%' ORDER BY id")]
    if not ids:
        return 0
    n_days = len(ramp)
    counts = list(ramp)
    total = sum(counts)
    # Scale the ramp if the seed has more/fewer rows than expected
    scaled = [max(0, round(x * len(ids) / total)) for x in counts]
    diff = len(ids) - sum(scaled)
    for i in range(abs(diff)):
        scaled[i % n_days] += 1 if diff > 0 else -1
    rng = random.Random(2026)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    decided_n = min(len(decisions), int(len(ids) * 0.4))
    assigned = []
    day_groups = []
    pos = 0
    for d, cnt in enumerate(scaled):
        if cnt:
            day_groups.append((today - timedelta(days=n_days - 1 - d), ids[pos:pos + cnt]))
            pos += cnt
    case_index = 0
    for day, group in day_groups:
        for cid in group:
            created = day + timedelta(hours=rng.uniform(8.2, 16.8), minutes=rng.uniform(0, 59))
            if case_index < decided_n:
                status = decisions[case_index]
                updated = created + timedelta(minutes=rng.uniform(25, 200))
                c.execute("UPDATE cases SET created_at=?, updated_at=?, status=?, decided_by=?, decision_note=? "
                          "WHERE id=?",
                          (created.isoformat(timespec="seconds"), updated.isoformat(timespec="seconds"),
                           status, "Demo Officer", "Auto-seeded review outcome", cid))
                audit_action = {"approved": "review:approve", "rejected": "review:reject",
                                "escalated": "review:escalate", "info_requested": "review:request_info"}[status]
                c.execute("INSERT INTO audit(ts, actor, action, case_id, detail) VALUES (?,?,?,?,?)",
                          (updated.isoformat(timespec="seconds"), "demo.officer", audit_action, cid,
                           '{"seed": true}'))
            else:
                c.execute("UPDATE cases SET created_at=?, updated_at=? WHERE id=?",
                          (created.isoformat(timespec="seconds"), created.isoformat(timespec="seconds"), cid))
            assigned.append(created)
            case_index += 1
    # Align the audit events for those cases to their new timestamps
    for day, group in day_groups:
        for cid in group:
            ts = c.execute("SELECT created_at FROM cases WHERE id=?", (cid,)).fetchone()[0]
            c.execute("UPDATE audit SET ts=? WHERE case_id=? AND action='submit_document'", (ts, cid))
    return len(assigned)


def main():
    if not Path(DB_PATH).exists():
        print("No database found — nothing to spread.")
        return
    with sqlite3.connect(DB_PATH) as c:
        c.row_factory = sqlite3.Row
        n = spread_timeline(c)
    print(f"Spread {n} seed case(s) across the last 14 days and marked the oldest subset as decided.")


if __name__ == "__main__":
    main()

"""
One-off migration: copy the local SQLite database into Supabase/Postgres.

Usage (with DATABASE_URL set in .env pointing at Supabase):
    .venv\\Scripts\\python.exe -m scripts.migrate_to_supabase

Idempotent: existing rows (same primary key) are skipped, so it's safe to re-run.
Reads data/jobs.db directly via sqlite3 and writes through the project's database
layer, which is in Postgres mode whenever DATABASE_URL is set.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import src.core.database as db

SRC = Path("data/jobs.db")

JOB_COLS = [
    "id", "title", "company", "url", "board", "location", "description",
    "apply_url", "apply_email", "apply_type", "salary", "tags",
    "recruiter_name", "recruiter_url", "posted_at", "score", "match_reasons",
    "scraped_at",
]


def main() -> None:
    if not db.USE_PG:
        raise SystemExit("DATABASE_URL is not set to a Postgres URL — nothing to migrate to.")
    if not SRC.exists():
        raise SystemExit(f"No local SQLite database found at {SRC}.")

    src = sqlite3.connect(SRC)
    src.row_factory = sqlite3.Row

    dst = db._connect()  # ensures the Supabase schema exists
    cur = dst.cursor()

    # ── jobs ──────────────────────────────────────────────────────────────────
    jobs = src.execute("SELECT * FROM jobs").fetchall()
    placeholders = ",".join(["?"] * len(JOB_COLS))
    inserted_jobs = 0
    for r in jobs:
        cur.execute(
            db._q(
                f"INSERT INTO jobs ({','.join(JOB_COLS)}) VALUES ({placeholders}) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            tuple(r[c] if c in r.keys() else None for c in JOB_COLS),
        )
        inserted_jobs += cur.rowcount or 0

    # ── job_status ─────────────────────────────────────────────────────────────
    statuses = src.execute("SELECT job_id, state, notes, updated_at FROM job_status").fetchall()
    inserted_status = 0
    for r in statuses:
        cur.execute(
            db._q(
                "INSERT INTO job_status (job_id, state, notes, updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT (job_id) DO NOTHING"
            ),
            (r["job_id"], r["state"], r["notes"], r["updated_at"]),
        )
        inserted_status += cur.rowcount or 0

    # ── applications (only if the table exists locally) ─────────────────────────
    inserted_apps = 0
    tables = {row[0] for row in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "applications" in tables:
        apps = src.execute("SELECT job_id, applied_at, channel, notes FROM applications").fetchall()
        for r in apps:
            cur.execute(
                db._q(
                    "INSERT INTO applications (job_id, applied_at, channel, notes) VALUES (?,?,?,?)"
                ),
                (r["job_id"], r["applied_at"], r["channel"], r["notes"]),
            )
            inserted_apps += cur.rowcount or 0

    dst.commit()
    dst.close()
    src.close()

    print(f"Migrated → Supabase: {inserted_jobs} jobs, {inserted_status} statuses, "
          f"{inserted_apps} applications.")


if __name__ == "__main__":
    main()

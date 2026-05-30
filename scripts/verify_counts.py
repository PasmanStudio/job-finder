"""Quick verification: compare local SQLite row counts vs Supabase."""
from __future__ import annotations
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import src.core.database as db

# ── Local SQLite ─────────────────────────────────────────────────────────────
local = sqlite3.connect(Path("data/jobs.db"))
tables = {r[0] for r in local.execute("SELECT name FROM sqlite_master WHERE type='table'")}
local_jobs = local.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
local_status = local.execute("SELECT COUNT(*) FROM job_status").fetchone()[0]
local_apps = local.execute("SELECT COUNT(*) FROM applications").fetchone()[0] if "applications" in tables else 0
local.close()

print(f"LOCAL    → jobs={local_jobs:4d}, job_status={local_status:4d}, applications={local_apps:4d}")

# ── Supabase ─────────────────────────────────────────────────────────────────
if not db.USE_PG:
    print("DATABASE_URL not pointing to Postgres — skipping Supabase check.")
else:
    import psycopg
    conn = psycopg.connect(db.DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM jobs")
    pg_jobs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM job_status")
    pg_status = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM applications")
    pg_apps = cur.fetchone()[0]
    conn.close()
    print(f"SUPABASE → jobs={pg_jobs:4d}, job_status={pg_status:4d}, applications={pg_apps:4d}")
    print()
    ok = local_jobs == pg_jobs and local_status == pg_status and local_apps == pg_apps
    print("STATUS: OK — counts match" if ok else "STATUS: MISMATCH — re-run migrate_to_supabase.py")

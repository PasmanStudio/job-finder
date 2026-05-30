"""
Database layer — works against either SQLite (local dev) or Postgres/Supabase
(production), chosen automatically from the DATABASE_URL environment variable.

  • DATABASE_URL set (postgres://...)  → Supabase Postgres
  • DATABASE_URL unset                 → local file data/jobs.db (SQLite)

The public functions have identical signatures in both modes, so app.py and
main.py never need to know which backend is active.

Tables:
  jobs           — all scraped job listings (kept forever, even if the posting
                   later goes offline — this is our application history archive)
  job_status     — current application state per job (new/saved/applied/...)
  applications   — append-only log: one row each time you apply, with date,
                   channel and notes. Lets us count applications per company.
"""
from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.core.models import Job

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_PG = DATABASE_URL.startswith("postgres")

if USE_PG:
    import psycopg2
    import psycopg2.extras
else:
    import sqlite3

# Only used in SQLite mode. Patchable in tests.
DB_PATH = Path("data/jobs.db")


def _ddl() -> list[str]:
    """Schema statements, tweaked per backend (autoincrement syntax differs)."""
    serial = "SERIAL PRIMARY KEY" if USE_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"
    return [
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id           TEXT PRIMARY KEY,
            title        TEXT NOT NULL,
            company      TEXT NOT NULL,
            url          TEXT NOT NULL,
            board        TEXT NOT NULL,
            location     TEXT DEFAULT 'Remote',
            description  TEXT DEFAULT '',
            apply_url    TEXT DEFAULT '',
            apply_email  TEXT,
            apply_type   TEXT DEFAULT '',
            salary       TEXT DEFAULT '',
            tags         TEXT DEFAULT '[]',
            recruiter_name TEXT DEFAULT '',
            recruiter_url  TEXT DEFAULT '',
            posted_at    TEXT DEFAULT '',
            score        INTEGER DEFAULT 0,
            match_reasons TEXT DEFAULT '[]',
            scraped_at   TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS job_status (
            job_id       TEXT PRIMARY KEY REFERENCES jobs(id),
            state        TEXT NOT NULL DEFAULT 'new',
            notes        TEXT DEFAULT '',
            updated_at   TEXT NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS applications (
            id           {serial},
            job_id       TEXT NOT NULL REFERENCES jobs(id),
            applied_at   TEXT NOT NULL,
            channel      TEXT DEFAULT '',
            notes        TEXT DEFAULT ''
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_applications_job ON applications(job_id)",
    ]


def _q(sql: str) -> str:
    """Translate '?' placeholders to '%s' when talking to Postgres."""
    return sql.replace("?", "%s") if USE_PG else sql


def _ensure_schema(conn) -> None:
    cur = conn.cursor()
    for stmt in _ddl():
        cur.execute(stmt)
    # SQLite-only: backfill columns added after the first schema version.
    if not USE_PG:
        existing = {row[1] for row in cur.execute("PRAGMA table_info(jobs)")}
        for col, ddl in (
            ("score", "ALTER TABLE jobs ADD COLUMN score INTEGER DEFAULT 0"),
            ("match_reasons", "ALTER TABLE jobs ADD COLUMN match_reasons TEXT DEFAULT '[]'"),
        ):
            if col not in existing:
                cur.execute(ddl)
    conn.commit()


def _connect():
    if USE_PG:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_jobs(jobs: list[Job]) -> list[Job]:
    """Insert new jobs. Returns only the ones that were truly new (not seen before)."""
    conn = _connect()
    new_jobs: list[Job] = []
    now = _now()
    try:
        cur = conn.cursor()
        for job in jobs:
            cur.execute(_q("SELECT id FROM jobs WHERE id = ?"), (job.id,))
            if cur.fetchone() is None:
                cur.execute(
                    _q(
                        """
                        INSERT INTO jobs
                          (id, title, company, url, board, location, description,
                           apply_url, apply_email, apply_type, salary, tags,
                           recruiter_name, recruiter_url, posted_at,
                           score, match_reasons, scraped_at)
                        VALUES
                          (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """
                    ),
                    (
                        job.id, job.title, job.company, job.url, job.board,
                        job.location, job.description, job.apply_url,
                        job.apply_email, job.apply_type, job.salary,
                        json.dumps(job.tags), job.recruiter_name,
                        job.recruiter_url, job.posted_at,
                        job.score, json.dumps(job.match_reasons), now,
                    ),
                )
                cur.execute(
                    _q("INSERT INTO job_status (job_id, state, updated_at) VALUES (?,?,?)"),
                    (job.id, "new", now),
                )
                new_jobs.append(job)
        conn.commit()
    finally:
        conn.close()
    return new_jobs


def rescore_all(config: dict) -> int:
    """
    Recompute score + match_reasons for every job already in the DB.

    Useful after tweaking the `scoring:` weights, or to backfill rows inserted
    before scoring existed. Returns the number of rows updated.
    """
    from src.core.scoring import score_job  # local import avoids a cycle

    conn = _connect()
    updated = 0
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, title, company, url, board, description, salary FROM jobs")
        rows = [dict(r) for r in cur.fetchall()]
        for row in rows:
            job = Job(
                id=row["id"], title=row["title"], company=row["company"],
                url=row["url"], board=row["board"],
                description=row["description"] or "", salary=row["salary"] or "",
            )
            score, reasons = score_job(job, config)
            cur.execute(
                _q("UPDATE jobs SET score = ?, match_reasons = ? WHERE id = ?"),
                (score, json.dumps(reasons), row["id"]),
            )
            updated += 1
        conn.commit()
    finally:
        conn.close()
    return updated


# ── Application state ───────────────────────────────────────────────────────────

def set_status(job_id: str, state: str, notes: Optional[str] = None) -> None:
    """Update the current application state for a job (keeps existing notes if None)."""
    conn = _connect()
    now = _now()
    try:
        cur = conn.cursor()
        if notes is None:
            cur.execute(
                _q(
                    "INSERT INTO job_status (job_id, state, updated_at) VALUES (?,?,?) "
                    "ON CONFLICT(job_id) DO UPDATE SET state=excluded.state, updated_at=excluded.updated_at"
                ),
                (job_id, state, now),
            )
        else:
            cur.execute(
                _q(
                    "INSERT INTO job_status (job_id, state, notes, updated_at) VALUES (?,?,?,?) "
                    "ON CONFLICT(job_id) DO UPDATE SET state=excluded.state, notes=excluded.notes, updated_at=excluded.updated_at"
                ),
                (job_id, state, notes, now),
            )
        conn.commit()
    finally:
        conn.close()


def set_notes(job_id: str, notes: str) -> None:
    """Update only the notes for a job, leaving its state untouched."""
    conn = _connect()
    now = _now()
    try:
        cur = conn.cursor()
        cur.execute(
            _q(
                "INSERT INTO job_status (job_id, state, notes, updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(job_id) DO UPDATE SET notes=excluded.notes, updated_at=excluded.updated_at"
            ),
            (job_id, "new", notes, now),
        )
        conn.commit()
    finally:
        conn.close()


# ── Applications log ────────────────────────────────────────────────────────────

def log_application(job_id: str, channel: str = "", notes: str = "",
                    applied_at: Optional[str] = None) -> None:
    """
    Record that you applied to a job. Appends a row (you can apply more than once),
    and moves the job's current state to 'applied'.
    """
    conn = _connect()
    now = _now()
    try:
        cur = conn.cursor()
        cur.execute(
            _q("INSERT INTO applications (job_id, applied_at, channel, notes) VALUES (?,?,?,?)"),
            (job_id, applied_at or now, channel, notes),
        )
        cur.execute(
            _q(
                "INSERT INTO job_status (job_id, state, updated_at) VALUES (?,?,?) "
                "ON CONFLICT(job_id) DO UPDATE SET state='applied', updated_at=excluded.updated_at"
            ),
            (job_id, "applied", now),
        )
        conn.commit()
    finally:
        conn.close()


def get_applications(job_id: str) -> list[dict]:
    """All application events for one job, most recent first."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            _q("SELECT applied_at, channel, notes FROM applications WHERE job_id = ? ORDER BY applied_at DESC"),
            (job_id,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def application_counts() -> dict[str, int]:
    """Map of job_id -> number of times applied (for badges in lists)."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT job_id, COUNT(*) AS cnt FROM applications GROUP BY job_id")
        return {row["job_id"]: row["cnt"] for row in cur.fetchall()}
    finally:
        conn.close()


def get_company_applications() -> list[dict]:
    """
    One row per company you've applied to: how many times in total, when last,
    and the list of individual applications (each with the job title + date +
    channel) so the dashboard can show full per-company history.
    """
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT j.company AS company,
                   j.id      AS job_id,
                   j.title   AS title,
                   j.url     AS url,
                   a.applied_at AS applied_at,
                   a.channel AS channel,
                   a.notes   AS notes
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            ORDER BY LOWER(j.company), a.applied_at DESC
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    grouped: dict[str, dict] = {}
    for r in rows:
        company = r["company"] or "—"
        g = grouped.setdefault(
            company, {"company": company, "count": 0, "last_applied": "", "events": []}
        )
        g["count"] += 1
        g["last_applied"] = max(g["last_applied"], r["applied_at"] or "")
        g["events"].append(r)
    return sorted(grouped.values(), key=lambda g: g["count"], reverse=True)


# ── Reads ───────────────────────────────────────────────────────────────────────

def get_jobs_by_state(state: str) -> list[dict]:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            _q(
                """
                SELECT j.*, s.state, s.notes, s.updated_at AS status_updated_at
                FROM jobs j
                JOIN job_status s ON j.id = s.job_id
                WHERE s.state = ?
                ORDER BY j.score DESC, j.scraped_at DESC
                """
            ),
            (state,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_all_jobs() -> list[dict]:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT j.*, s.state, s.notes, s.updated_at AS status_updated_at
            FROM jobs j
            JOIN job_status s ON j.id = s.job_id
            ORDER BY j.score DESC, j.scraped_at DESC
            """
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_stats() -> dict:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT state, COUNT(*) as cnt FROM job_status GROUP BY state")
        return {row["state"]: row["cnt"] for row in cur.fetchall()}
    finally:
        conn.close()


def job_ids_seen() -> set[str]:
    """Return all job IDs already in the database (for dedup without loading full rows)."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM jobs")
        return {row["id"] for row in cur.fetchall()}
    finally:
        conn.close()

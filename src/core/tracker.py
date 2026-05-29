"""
Job tracker — persists seen jobs to data/seen_jobs.json so the scraper never
re-applies to the same listing across runs.
"""
from __future__ import annotations

import json
import hashlib
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from src.core.models import Job


DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "seen_jobs.json"


def _job_key(job: Job) -> str:
    """Stable key: hash of (board + url) so URL changes don't re-trigger."""
    raw = f"{job.board}:{job.url}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def load_seen() -> dict:
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_seen(seen: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2)


def filter_new(jobs: Iterable[Job], retention_days: int = 90) -> list[Job]:
    """
    Returns only jobs that have NOT been seen before.
    Also prunes entries older than retention_days from the seen store.
    """
    seen = load_seen()
    cutoff = (datetime.utcnow() - timedelta(days=retention_days)).isoformat() if retention_days > 0 else None

    # Prune old entries
    if cutoff:
        seen = {k: v for k, v in seen.items() if v.get("seen_at", "") >= cutoff}

    new_jobs: list[Job] = []
    for job in jobs:
        key = _job_key(job)
        if key not in seen:
            new_jobs.append(job)

    return new_jobs


def mark_seen(jobs: Iterable[Job]) -> None:
    """Persist jobs as seen so they are skipped next run."""
    seen = load_seen()
    now = datetime.utcnow().isoformat()
    for job in jobs:
        key = _job_key(job)
        seen[key] = {
            "title": job.title,
            "company": job.company,
            "url": job.url,
            "board": job.board,
            "seen_at": now,
        }
    save_seen(seen)

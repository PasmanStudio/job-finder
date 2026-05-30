"""
CV-based relevance scoring (no LLM).

Each job is scored 0–100 by matching its title + description against weighted
keyword groups defined under the `scoring:` section of search_config.yaml.
Those groups encode Carolina's profile (senior product/UX-UI designer with
fintech, design-systems and B2B/enterprise background).

The matched high-value keywords are returned as human-readable reasons so the
dashboard can show *why* a job ranked where it did.
"""
from __future__ import annotations

from src.core.models import Job

# Keyword groups whose matches are surfaced as "why this matched" reasons.
_REASON_GROUPS = ("strong", "skills", "seniority")


def _group(cfg: dict, name: str) -> tuple[int, list[str]]:
    g = cfg.get(name, {}) or {}
    return int(g.get("weight", 0)), [k.lower() for k in g.get("keywords", [])]


def score_job(job: Job, config: dict) -> tuple[int, list[str]]:
    """Return (score 0-100, reasons) for a single job given the loaded config."""
    cfg = config.get("scoring", {}) or {}
    if not cfg:
        return 0, []

    # Title matches count double — the title is the strongest relevance signal.
    title = job.title.lower()
    text = f"{job.title} {job.description}".lower()

    total = 0
    reasons: list[str] = []

    for name in ("strong", "skills", "seniority", "region", "mode"):
        weight, keywords = _group(cfg, name)
        if not weight:
            continue
        for kw in keywords:
            if kw in text:
                total += weight * (2 if kw in title else 1)
                if name in _REASON_GROUPS:
                    reasons.append(kw)

    if job.salary:
        total += int(cfg.get("salary_bonus", 0))

    score = max(0, min(100, total))
    # De-duplicate reasons preserving order, keep the most relevant handful.
    seen: set[str] = set()
    unique_reasons = [r for r in reasons if not (r in seen or seen.add(r))]
    return score, unique_reasons[:6]


def score_jobs(jobs: list[Job], config: dict) -> list[Job]:
    """Annotate every job in-place with its score + match reasons. Returns the list."""
    for job in jobs:
        job.score, job.match_reasons = score_job(job, config)
    return jobs

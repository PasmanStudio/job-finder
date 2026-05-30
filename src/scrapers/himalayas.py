"""
Himalayas scraper — public JSON API, remote-only jobs with good salary data.
Endpoint: https://himalayas.app/jobs/api

NOTE (verified 2026): the free endpoint only returns the ~20 most-recent jobs and
ignores the `search` / `category` / `offset` params (totalCount is huge but the
payload caps at ~20). So this is a low-yield source — some runs legitimately
return 0 design roles. We keep whatever matches the search keywords among the
recent listings rather than failing.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Sequence

import requests

from src.core.models import Job
from src.scrapers.base import BaseScraper

_API_URL = "https://himalayas.app/jobs/api"
_HEADERS = {"User-Agent": "Mozilla/5.0 (job-scraper)", "Accept": "application/json"}


def _salary(item: dict) -> str:
    lo, hi = item.get("minSalary"), item.get("maxSalary")
    cur = item.get("currency", "") or ""
    if lo and hi:
        return f"{lo:,}–{hi:,} {cur}".strip()
    if lo:
        return f"from {lo:,} {cur}".strip()
    return ""


def _posted(ts) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
    except Exception:
        return ""


class HimalayasScraper(BaseScraper):
    name = "himalayas"

    def scrape(self) -> Sequence[Job]:
        board_cfg = self.config.get("boards", {}).get("himalayas", {})
        if not board_cfg.get("enabled", True):
            return []

        try:
            resp = requests.get(
                _API_URL,
                params={"limit": 100},
                headers=_HEADERS,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"  [himalayas] error: {exc}")
            return []

        jobs: list[Job] = []
        seen: set[str] = set()

        for item in data.get("jobs", []):
            title = html.unescape(item.get("title", "") or "").strip()
            company = html.unescape(item.get("companyName", "") or "").strip()
            url = item.get("applicationLink", "") or item.get("guid", "") or ""
            if not title or not url or url in seen:
                continue
            seen.add(url)

            locs = item.get("locationRestrictions") or []
            location = ", ".join(locs) if locs else "Remote"

            job = Job(
                id=f"himalayas:{item.get('guid', url)}",
                title=title,
                company=company,
                url=url,
                apply_url=url,
                board=self.name,
                location=location,
                description=html.unescape(item.get("description", "") or "")[:3000],
                salary=_salary(item),
                tags=(item.get("categories", []) or []) + ["remote"],
                apply_type="external",
                posted_at=_posted(item.get("pubDate")),
            )
            if self._matches(job):
                jobs.append(job)

        print(f"  [himalayas] {len(jobs)} matching jobs found")
        return jobs

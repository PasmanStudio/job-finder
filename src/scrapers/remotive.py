"""
Remotive scraper — public JSON API, remote-only jobs.
Docs: https://remotive.com/api/remote-jobs

We pull the whole "design" category and filter against the search keywords.
"""
from __future__ import annotations

import html
from typing import Sequence

import requests

from src.core.models import Job
from src.scrapers.base import BaseScraper

_API_URL = "https://remotive.com/api/remote-jobs"
_HEADERS = {"User-Agent": "Mozilla/5.0 (job-scraper)", "Accept": "application/json"}


class RemotiveScraper(BaseScraper):
    name = "remotive"

    def scrape(self) -> Sequence[Job]:
        board_cfg = self.config.get("boards", {}).get("remotive", {})
        if not board_cfg.get("enabled", True):
            return []

        try:
            resp = requests.get(
                _API_URL,
                params={"category": "design", "limit": 200},
                headers=_HEADERS,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"  [remotive] error: {exc}")
            return []

        jobs: list[Job] = []
        for item in data.get("jobs", []):
            title = html.unescape(item.get("title", "") or "").strip()
            company = html.unescape(item.get("company_name", "") or "").strip()
            url = item.get("url", "") or ""
            if not title or not url:
                continue

            job = Job(
                id=f"remotive:{item.get('id', url)}",
                title=title,
                company=company,
                url=url,
                apply_url=url,
                board=self.name,
                location=item.get("candidate_required_location", "Remote") or "Remote",
                description=html.unescape(item.get("description", "") or "")[:3000],
                salary=item.get("salary", "") or "",
                tags=(item.get("tags", []) or []) + ["remote"],
                apply_type="external",
                posted_at=(item.get("publication_date", "") or "")[:10],
            )
            if self._matches(job):
                jobs.append(job)

        print(f"  [remotive] {len(jobs)} matching jobs found")
        return jobs

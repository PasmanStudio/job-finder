"""
Himalayas scraper — public JSON API, remote-only jobs with good salary data.
Endpoint: https://himalayas.app/jobs/api

We page through recent listings and keep the ones in the Design category that
match the search keywords.
"""
from __future__ import annotations

import html
import time
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

        jobs: list[Job] = []
        seen: set[str] = set()
        # Page through the most recent listings.
        for offset in range(0, 200, 100):
            try:
                resp = requests.get(
                    _API_URL,
                    params={"limit": 100, "offset": offset},
                    headers=_HEADERS,
                    timeout=20,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                print(f"  [himalayas] offset={offset} error: {exc}")
                break

            items = data.get("jobs", [])
            if not items:
                break

            for item in items:
                categories = [c.lower() for c in (item.get("categories") or [])]
                if "design" not in categories:
                    continue

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

            if len(items) < 100:
                break
            time.sleep(0.5)

        print(f"  [himalayas] {len(jobs)} matching jobs found")
        return jobs

"""
RemoteOK scraper — uses the public JSON API.
Docs: https://remoteok.com/api
"""
from __future__ import annotations

import html
import time
from typing import Sequence

import requests

from src.core.models import Job
from src.scrapers.base import BaseScraper


_API_URL = "https://remoteok.com/api"
_DESIGN_TAGS = ["designer", "design", "ux", "ui", "product-designer"]

# User-Agent is required — RemoteOK returns 403 for default Python UA
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (job-scraper/1.0; +https://github.com/mtotaro/job-scraper)"
}


class RemoteOKScraper(BaseScraper):
    name = "remoteok"

    def scrape(self) -> Sequence[Job]:
        board_cfg = self.config.get("boards", {}).get("remoteok", {})
        if not board_cfg.get("enabled", True):
            return []

        tags = board_cfg.get("tags", _DESIGN_TAGS)
        jobs: list[Job] = []

        for tag in tags:
            url = f"{_API_URL}?tags={tag}"
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=15)
                resp.raise_for_status()
                resp.encoding = "utf-8"  # RemoteOK sends UTF-8 but may omit charset header
                data = resp.json()
            except Exception as exc:
                print(f"  RemoteOK error for tag={tag}: {exc}")
                time.sleep(2)
                continue

            # First item is metadata, skip it
            for item in data[1:]:
                if not isinstance(item, dict):
                    continue
                job = Job(
                    id=str(item.get("id", "")),
                    title=html.unescape(item.get("position", "")),
                    company=html.unescape(item.get("company", "")),
                    url=item.get("url", ""),
                    apply_url=item.get("apply_url", item.get("url", "")),
                    board=self.name,
                    location=item.get("location", "Remote"),
                    description=html.unescape(item.get("description", "")),
                    tags=item.get("tags", []),
                    posted_at=item.get("date", ""),
                )
                if self._matches(job):
                    jobs.append(job)

            time.sleep(1)  # be polite between requests

        # Deduplicate within this run by URL
        seen_urls: set[str] = set()
        unique: list[Job] = []
        for j in jobs:
            if j.url not in seen_urls:
                seen_urls.add(j.url)
                unique.append(j)

        print(f"  RemoteOK: {len(unique)} matching jobs found")
        return unique

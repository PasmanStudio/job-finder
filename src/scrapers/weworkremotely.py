"""
We Work Remotely scraper — uses the public RSS feed for the Design category.
Feed URL: https://weworkremotely.com/categories/remote-design-jobs.rss
"""
from __future__ import annotations

import re
from html import unescape
from typing import Sequence

import feedparser

from src.core.models import Job
from src.scrapers.base import BaseScraper


_FEED_URL = "https://weworkremotely.com/categories/remote-design-jobs.rss"

# Simple regex to extract a mailto: address from description HTML
_EMAIL_RE = re.compile(r"mailto:([a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9.\-]+)")


class WeWorkRemotelyScraper(BaseScraper):
    name = "weworkremotely"

    def scrape(self) -> Sequence[Job]:
        board_cfg = self.config.get("boards", {}).get("weworkremotely", {})
        if not board_cfg.get("enabled", True):
            return []

        feed = feedparser.parse(_FEED_URL)
        jobs: list[Job] = []

        for entry in feed.entries:
            title_raw = entry.get("title", "")
            # Format: "CompanyName: Job Title"
            if ": " in title_raw:
                company, title = title_raw.split(": ", 1)
            else:
                company = ""
                title = title_raw

            description = unescape(entry.get("summary", ""))
            url = entry.get("link", "")
            posted_at = entry.get("published", "")

            apply_email = None
            match = _EMAIL_RE.search(description)
            if match:
                apply_email = match.group(1)

            job = Job(
                id=entry.get("id", url),
                title=title.strip(),
                company=company.strip(),
                url=url,
                apply_url=url,
                board=self.name,
                location="Remote",
                description=description,
                apply_email=apply_email,
                posted_at=posted_at,
            )
            if self._matches(job):
                jobs.append(job)

        print(f"  WeWorkRemotely: {len(jobs)} matching jobs found")
        return jobs

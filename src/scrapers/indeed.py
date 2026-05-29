"""
Indeed scraper — HTTP-based scraping with BeautifulSoup.

⚠️  IMPORTANT: Indeed's ToS prohibits scraping. This scraper uses public
search results pages only (no login), and respects rate limits.
It is DISABLED by default. Enable in search_config.yaml if desired.
"""
from __future__ import annotations

import hashlib
import re
import time
from typing import Sequence
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

from src.core.models import Job
from src.scrapers.base import BaseScraper


_BASE_URL = "https://www.indeed.com"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class IndeedScraper(BaseScraper):
    name = "indeed"

    def scrape(self) -> Sequence[Job]:
        board_cfg = self.config.get("boards", {}).get("indeed", {})
        if not board_cfg.get("enabled", False):
            return []

        max_results = board_cfg.get("max_results", 25)
        jobs: list[Job] = []

        search_queries = self.keywords[:3] if self.keywords else ["UX designer remote"]

        for query in search_queries:
            params = urlencode({"q": query, "l": "Remote", "remotejob": "032b3046-06a3-4876-8dfd-474eb5e7ed11"})
            url = f"{_BASE_URL}/jobs?{params}"

            try:
                resp = requests.get(url, headers=_HEADERS, timeout=15)
                resp.raise_for_status()
            except Exception as exc:
                print(f"  Indeed error for query='{query}': {exc}")
                time.sleep(3)
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select("a.tapItem, div.job_seen_beacon")

            for card in cards[:max_results]:
                try:
                    title_el = card.select_one("h2.jobTitle span[title], h2.jobTitle span")
                    company_el = card.select_one("span.companyName, [data-testid='company-name']")
                    link_el = card.select_one("a[href*='/pagead/'], a[href*='/rc/clk'], a[id^='job_']")

                    title = title_el.get_text(strip=True) if title_el else ""
                    company = company_el.get_text(strip=True) if company_el else ""

                    if not title:
                        continue

                    href = link_el["href"] if link_el else ""
                    job_url = urljoin(_BASE_URL, href) if href else url
                    job_id = hashlib.sha256(job_url.encode()).hexdigest()[:16]

                    job = Job(
                        id=job_id,
                        title=title,
                        company=company,
                        url=job_url,
                        apply_url=job_url,
                        board=self.name,
                        location="Remote",
                    )
                    if self._matches(job):
                        jobs.append(job)
                except Exception:
                    continue

            time.sleep(2)

        print(f"  Indeed: {len(jobs)} matching jobs found")
        return jobs

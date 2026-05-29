"""
Wellfound (AngelList) scraper — scrapes public job search pages.
Disabled by default. Requires Playwright for JS-rendered content.
"""
from __future__ import annotations

import hashlib
import time
from typing import Sequence

from src.core.models import Job
from src.scrapers.base import BaseScraper

try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False


class WellfoundScraper(BaseScraper):
    name = "wellfound"

    def scrape(self) -> Sequence[Job]:
        board_cfg = self.config.get("boards", {}).get("wellfound", {})
        if not board_cfg.get("enabled", False):
            return []

        if not _PLAYWRIGHT_AVAILABLE:
            print("  Wellfound: playwright not installed, skipping.")
            return []

        jobs: list[Job] = []
        base_url = "https://wellfound.com/jobs?role=Designer&remote=true"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page.goto(base_url, timeout=30000)
            time.sleep(3)

            cards = page.query_selector_all("[class*='JobListingCard']")
            for card in cards:
                try:
                    title_el = card.query_selector("a[class*='title'], h2")
                    company_el = card.query_selector("[class*='company'], [class*='startup']")
                    link_el = card.query_selector("a[href*='/jobs/']")

                    title = title_el.inner_text().strip() if title_el else ""
                    company = company_el.inner_text().strip() if company_el else ""
                    href = link_el.get_attribute("href") if link_el else ""
                    url = f"https://wellfound.com{href}" if href and not href.startswith("http") else href

                    if not title or not url:
                        continue

                    job_id = hashlib.sha256(url.encode()).hexdigest()[:16]
                    job = Job(
                        id=job_id,
                        title=title,
                        company=company,
                        url=url,
                        apply_url=url,
                        board=self.name,
                        location="Remote",
                    )
                    if self._matches(job):
                        jobs.append(job)
                except Exception:
                    continue

            browser.close()

        print(f"  Wellfound: {len(jobs)} matching jobs found")
        return jobs

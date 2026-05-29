"""
LinkedIn scraper — uses Playwright to search job listings.

⚠️  IMPORTANT WARNINGS:
  1. LinkedIn's Terms of Service prohibit automated scraping.
  2. This module ONLY collects job listing URLs — it does NOT auto-apply.
  3. Use at your own risk. LinkedIn can block the account used.
  4. Requires LINKEDIN_EMAIL and LINKEDIN_PASSWORD GitHub Secrets.

This scraper is DISABLED by default in search_config.yaml.
Enable it by setting boards.linkedin.enabled = true.
"""
from __future__ import annotations

import os
import time
from typing import Sequence

from src.core.models import Job
from src.scrapers.base import BaseScraper

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False


_BASE_URL = "https://www.linkedin.com"


class LinkedInScraper(BaseScraper):
    name = "linkedin"

    def scrape(self) -> Sequence[Job]:
        board_cfg = self.config.get("boards", {}).get("linkedin", {})
        if not board_cfg.get("enabled", False):
            return []

        if not _PLAYWRIGHT_AVAILABLE:
            print("  LinkedIn: playwright not installed, skipping.")
            return []

        email = os.environ.get("LINKEDIN_EMAIL", "")
        password = os.environ.get("LINKEDIN_PASSWORD", "")
        if not email or not password:
            print("  LinkedIn: LINKEDIN_EMAIL / LINKEDIN_PASSWORD not set, skipping.")
            return []

        max_results = board_cfg.get("max_results", 25)
        jobs: list[Job] = []
        keywords = " OR ".join(f'"{kw}"' for kw in self.keywords[:4]) if self.keywords else "UX designer"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = context.new_page()

            try:
                # Login
                page.goto(f"{_BASE_URL}/login", timeout=30000)
                page.fill("#username", email)
                page.fill("#password", password)
                page.click('[data-litms-control-urn="login-submit"]')
                page.wait_for_url("**/feed/**", timeout=20000)
            except PWTimeout:
                print("  LinkedIn: login timed out, skipping.")
                browser.close()
                return []

            # Search jobs
            search_url = (
                f"{_BASE_URL}/jobs/search/?keywords={keywords.replace(' ', '%20')}"
                f"&f_WT=2"  # remote filter
            )
            page.goto(search_url, timeout=30000)
            time.sleep(2)

            cards = page.query_selector_all(".job-card-container__link")
            for card in cards[:max_results]:
                try:
                    href = card.get_attribute("href") or ""
                    title_el = card.query_selector(".job-card-list__title")
                    company_el = card.query_selector(".job-card-container__company-name")
                    title = title_el.inner_text().strip() if title_el else ""
                    company = company_el.inner_text().strip() if company_el else ""
                    url = href if href.startswith("http") else f"{_BASE_URL}{href}"

                    if not title:
                        continue

                    job = Job(
                        id=url,
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

        print(f"  LinkedIn: {len(jobs)} matching jobs found")
        return jobs

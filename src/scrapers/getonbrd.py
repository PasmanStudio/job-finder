"""
GetOnBoard scraper — Argentina's main tech job board.
Uses the public REST API: https://www.getonbrd.com/api/v0/
"""
from __future__ import annotations

import hashlib
import re
import time

import requests

from src.core.models import Job
from src.scrapers.base import BaseScraper

API_BASE = "https://www.getonbrd.com/api/v0"
HEADERS = {"Accept": "application/json", "User-Agent": "JobScrapper/2.0"}

SEARCH_QUERIES = [
    "UX designer",
    "UI designer",
    "product designer",
    "UX UI",
    "diseñador UX",
]

JUNIOR_SIGNALS = re.compile(
    r"\bjunior\b|\bjr\.?\b|\bentry.?level\b|\brecién recibido\b", re.IGNORECASE
)


def _job_id(url: str) -> str:
    return hashlib.sha256(f"getonbrd:{url}".encode()).hexdigest()[:16]


class GetOnBrdScraper(BaseScraper):
    name = "getonbrd"

    def scrape(self) -> list[Job]:
        jobs: list[Job] = []
        seen: set[str] = set()

        for query in SEARCH_QUERIES:
            try:
                resp = requests.get(
                    f"{API_BASE}/search/jobs",
                    params={"q": query, "per_page": 20},
                    headers=HEADERS,
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                print(f"  [getonbrd] '{query}' → error: {exc}")
                continue

            items = data.get("data", [])
            for item in items:
                attrs = item.get("attributes", {})
                title = attrs.get("title", "").strip()
                company_data = item.get("relationships", {}).get("company", {}).get("data", {})
                company = attrs.get("company_name", "") or str(company_data.get("id", "Unknown"))

                # Build URL
                job_id_raw = item.get("id", "")
                url = f"https://www.getonbrd.com/jobs/{job_id_raw}"

                if not title or url in seen:
                    continue
                seen.add(url)

                if JUNIOR_SIGNALS.search(title):
                    continue
                if not self._matches(Job(id="", title=title, company=company, url=url, board="getonbrd")):
                    continue

                description = attrs.get("description", "") or ""
                location = attrs.get("modality", "Remote")
                salary_min = attrs.get("min_salary", "")
                salary_max = attrs.get("max_salary", "")
                salary = ""
                if salary_min or salary_max:
                    salary = f"{salary_min}–{salary_max} USD/mo" if salary_max else f"from {salary_min} USD/mo"

                apply_url = attrs.get("apply_url") or url

                jobs.append(Job(
                    id=_job_id(url),
                    title=title,
                    company=company,
                    url=url,
                    board="getonbrd",
                    location=location or "Argentina",
                    description=description[:3000],
                    apply_url=apply_url,
                    apply_type="ats" if "apply_url" in attrs else "external",
                    salary=salary,
                    posted_at=attrs.get("published_at", "")[:10] if attrs.get("published_at") else "",
                ))

            time.sleep(0.5)

        print(f"  [getonbrd] {len(jobs)} jobs found")
        return jobs

"""
GetOnBoard scraper — Argentina/LatAm's main tech job board.
Uses the public REST API: https://www.getonbrd.com/api/v0/

Notes on the API (verified May 2026):
  • /search/jobs requires the `query` param (NOT `q`) — `q` returns HTTP 422.
  • Search results carry the company only as a relationship id. The company
    *name* is not exposed: `expand=company` 500s and the /jobs/{id} detail
    endpoint 401s. So we leave company blank ("—"); title/url/score are still
    useful and the apply link works.
"""
from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timezone

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


def _posted(value) -> str:
    """`published_at` is a Unix timestamp (int); normalise to YYYY-MM-DD."""
    if not value:
        return ""
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc).date().isoformat()
        except Exception:
            return ""
    return str(value)[:10]


class GetOnBrdScraper(BaseScraper):
    name = "getonbrd"

    def scrape(self) -> list[Job]:
        jobs: list[Job] = []
        seen: set[str] = set()

        for query in SEARCH_QUERIES:
            try:
                resp = requests.get(
                    f"{API_BASE}/search/jobs",
                    params={"query": query, "per_page": 20},
                    headers=HEADERS,
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                print(f"  [getonbrd] '{query}' → error: {exc}")
                continue

            for item in data.get("data", []):
                attrs = item.get("attributes", {})
                title = (attrs.get("title") or "").strip()

                slug = item.get("id", "")
                url = f"https://www.getonbrd.com/jobs/{slug}"

                if not title or url in seen:
                    continue
                seen.add(url)

                if JUNIOR_SIGNALS.search(title):
                    continue
                if not self._matches(Job(id="", title=title, company="", url=url, board="getonbrd")):
                    continue

                is_remote = bool(attrs.get("remote"))
                countries = attrs.get("countries") or []
                country = ", ".join(countries) if isinstance(countries, list) else str(countries or "")
                if is_remote:
                    location = f"Remote ({country})" if country and country.lower() != "remote" else "Remote"
                else:
                    location = country or "Argentina"

                tags = []
                if is_remote:
                    tags.append("remote")
                if "argentin" in f"{country} {attrs.get('remote_zone', '')}".lower():
                    tags.append("local")

                salary_min = attrs.get("min_salary", "")
                salary_max = attrs.get("max_salary", "")
                salary = ""
                if salary_min or salary_max:
                    salary = f"{salary_min}–{salary_max} USD/mo" if salary_max else f"from {salary_min} USD/mo"

                jobs.append(Job(
                    id=_job_id(url),
                    title=title,
                    company="—",
                    url=url,
                    board="getonbrd",
                    location=location,
                    description=(attrs.get("description", "") or "")[:3000],
                    apply_url=url,
                    apply_type="external",
                    salary=salary,
                    tags=tags,
                    posted_at=_posted(attrs.get("published_at")),
                ))

            time.sleep(0.5)

        print(f"  [getonbrd] {len(jobs)} jobs found")
        return jobs

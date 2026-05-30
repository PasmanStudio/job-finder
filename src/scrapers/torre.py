"""
Torre.ai scraper — LatAm-first talent platform with a public opportunities
search endpoint. Strong for Argentina / remote roles.

Endpoint: POST https://search.torre.co/opportunities/_search
Body:     {"skill/role": {"text": "<term>", "experience": "potential-to-develop"}}
"""
from __future__ import annotations

import time
from typing import Sequence

import requests

from src.core.models import Job
from src.scrapers.base import BaseScraper

_SEARCH_URL = "https://search.torre.co/opportunities/_search"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (job-scraper)",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

_SEARCH_TERMS = [
    "product designer",
    "ux designer",
    "ui designer",
    "ux/ui designer",
    "diseñador de producto",
    "diseñador ux",
]


def _company(item: dict) -> str:
    orgs = item.get("organizations") or []
    if orgs and isinstance(orgs, list):
        return str(orgs[0].get("name", "") or "")
    return ""


def _salary(item: dict) -> str:
    comp = (item.get("compensation") or {}).get("data") or {}
    lo, hi = comp.get("minAmount"), comp.get("maxAmount")
    cur = comp.get("currency", "") or ""
    per = comp.get("periodicity", "") or ""
    if lo and hi:
        return f"{lo:,.0f}–{hi:,.0f} {cur}/{per}".strip("/ ")
    if lo:
        return f"from {lo:,.0f} {cur}/{per}".strip("/ ")
    return ""


class TorreScraper(BaseScraper):
    name = "torre"

    def scrape(self) -> Sequence[Job]:
        board_cfg = self.config.get("boards", {}).get("torre", {})
        if not board_cfg.get("enabled", True):
            return []

        jobs: list[Job] = []
        seen: set[str] = set()

        for term in _SEARCH_TERMS:
            body = {"skill/role": {"text": term, "experience": "potential-to-develop"}}
            try:
                resp = requests.post(
                    f"{_SEARCH_URL}?size=30&offset=0&aggregate=false",
                    headers=_HEADERS,
                    json=body,
                    timeout=20,
                )
                resp.raise_for_status()
                results = resp.json().get("results", [])
            except Exception as exc:
                print(f"  [torre] {term!r} error: {exc}")
                continue

            for item in results:
                opp_id = str(item.get("id", "") or "")
                title = str(item.get("objective", "") or "").strip()
                if not opp_id or not title or opp_id in seen:
                    continue
                seen.add(opp_id)

                url = f"https://torre.co/jobs/{opp_id}"
                is_remote = bool(item.get("remote"))
                locs = item.get("locations") or []
                location = "Remote" if is_remote else (", ".join(str(l) for l in locs) or "—")

                tags = ["remote"] if is_remote else []
                # Geographic categorisation consistent with the rest of the app.
                loc_blob = " ".join(str(l).lower() for l in locs)
                if "argentin" in loc_blob:
                    tags.append("local")

                job = Job(
                    id=f"torre:{opp_id}",
                    title=title,
                    company=_company(item),
                    url=url,
                    apply_url=url,
                    board=self.name,
                    location=location,
                    description=str(item.get("tagline", "") or "")[:3000],
                    salary=_salary(item),
                    tags=tags,
                    apply_type="external",
                    posted_at=str(item.get("created", "") or "")[:10],
                )
                if self._matches(job):
                    jobs.append(job)

            time.sleep(1)

        print(f"  [torre] {len(jobs)} matching jobs found")
        return jobs

"""
JobSpy-backed scraper — replaces custom LinkedIn/Indeed scrapers.

Calls python-jobspy to search LinkedIn, Indeed, Glassdoor, and Google Jobs
in a single batched request. Supports li_at cookie for authenticated LinkedIn access.

Required env vars:
  LI_AT_COOKIE   — optional; LinkedIn li_at session cookie for full access
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from datetime import date
from typing import Optional

from src.core.models import Job

# JobSpy is imported lazily so the rest of the app works even without it
try:
    from jobspy import scrape_jobs
    _JOBSPY_AVAILABLE = True
except ImportError:
    _JOBSPY_AVAILABLE = False


name = "jobspy"

# ── keyword searches to run ────────────────────────────────────────────────────
SEARCH_TERMS = [
    "UX designer",
    "product designer",
    "UX/UI designer",
    "graphic designer",
    "diseñador UX",
]

# (location, country_indeed, is_remote, category)
# category is stored as a tag on each job: "remote" | "local" | "relocation"
# Kept lean (5 entries) to avoid 300+ searches — cities covered by country-level queries.
LOCATIONS = [
    # ── trabajar desde Argentina ──────────────────────────────
    ("Remote",         "Argentina",    True,  "remote"),
    ("Argentina",      "Argentina",    False, "local"),
    # ── relocalización Europa (ciudadanía europea) ────────────
    ("Spain",          "Spain",        False, "relocation"),
    ("Netherlands",    "Netherlands",  False, "relocation"),
    ("United Kingdom", "UK",           False, "relocation"),
]

# Glassdoor removed — fails with Argentina/Buenos Aires locations
SITES = ["linkedin", "indeed", "google"]

JUNIOR_SIGNALS = re.compile(
    r"\bjunior\b|\bjr\.?\b|\bentry.?level\b|\brecién recibido\b|\bsin experiencia\b",
    re.IGNORECASE,
)
SENIOR_SIGNALS = re.compile(
    r"\bsenior\b|\bsr\.?\b|\bprincipal\b|\blead\b|\bstaff\b|\bsemi.?senior\b|\bssr\.?\b",
    re.IGNORECASE,
)
EXCLUDE_TITLES = re.compile(
    r"\bfrontend\b|\bfront.end\b|\bfront end\b|\bdeveloper\b|\bengineer\b"
    r"|\bmarketing manager\b"
    r"|\bsales\b|\baccountant\b|\bcontador\b"
    r"|\bproyectista\b|\banalista\b|\bgerente\b|\bmanager\b"
    r"|\bproduct manager\b|\bproduct lead\b|\bproduct owner\b"
    r"|\bcontent creator\b|\bcommunity manager\b|\bcopywriter\b"
    r"|\bintern\b|\binternship\b|\bpasante\b|\bassistant\b"
    # becas / pasantías en múltiples idiomas
    r"|\bbeca\b|\btrainee\b|\bwerkstudent\b|\bpraktikum\b|\bpraktikant\b"
    r"|\bstage\b|\balternant\b|\baprendiz\b|\bgraduate\b|\bthesis\b"
    # diseño NO digital
    r"|\bmec[áa]nic[oa]\b|\bcatia\b|\baeron[áa]ut\b|\bindustrial\b"
    r"|\bmoda\b|\bfashion\b|\bcocina\b|\bkitchen\b|\binterior\b"
    r"|\beditorial\b|\bpreimpresor\b|\bcat[áa]logo\b|\bimpres\w+\b"
    r"|\btextil\b|\bindumentaria\b|\barquitectura\b|\barchitect\b"
    # otros roles no design
    r"|\blead\.?\s*net\b|\btechnical lead\b|\btech lead\b",
    re.IGNORECASE,
)

# Title must contain at least one of these to be considered a design role
DESIGN_TITLE_REQUIRED = re.compile(
    r"\bux\b|\bui\b|\bdesign\b|\bdiseg\w+\b|\bdise\w+\b|\bcreativ\w+\b"
    r"|\bexperience\b|\binteraction\b|\bvisual\b|\bmultimedia\b|\bbranding\b",
    re.IGNORECASE,
)


def _job_id(board: str, url: str) -> str:
    return hashlib.sha256(f"{board}:{url}".encode()).hexdigest()[:16]


def _apply_type(row) -> str:
    job_url = str(row.get("job_url_direct") or "")
    if "easy_apply" in str(row.get("job_url") or "").lower():
        return "easy_apply"
    if row.get("emails"):
        return "email"
    if any(x in job_url for x in ["greenhouse.io", "lever.co", "workday", "taleo", "icims"]):
        return "ats"
    return "external"


def _parse_posted(row) -> str:
    val = row.get("date_posted")
    if val is None:
        return ""
    if isinstance(val, date):
        return val.isoformat()
    return str(val)


def _seniority(title: str, description: str) -> str:
    text = f"{title} {description[:300]}"
    if JUNIOR_SIGNALS.search(text):
        return "junior"
    if SENIOR_SIGNALS.search(text):
        return "senior"
    return "mid"


def scrape(config: dict) -> list[Job]:
    if not _JOBSPY_AVAILABLE:
        print("  [jobspy] python-jobspy not installed — skipping")
        return []

    li_at = os.getenv("LI_AT_COOKIE") or ""
    hours_old = config.get("jobspy", {}).get("hours_old", 72)
    results_per_search = config.get("jobspy", {}).get("results_per_search", 30)

    jobs: list[Job] = []
    seen_keys: set[str] = set()

    for term in SEARCH_TERMS:
        for location, country, is_remote, category in LOCATIONS:
            # For "Remote" searches, don't pass country_indeed — it causes
            # invalid country resolution (e.g. "dominican republic") internally
            indeed_kwargs = {} if is_remote else {"country_indeed": country}
            try:
                df = scrape_jobs(
                    site_name=SITES,
                    search_term=term,
                    location=location,
                    hours_old=hours_old,
                    results_wanted=results_per_search,
                    is_remote=is_remote,
                    linkedin_fetch_description=bool(li_at),
                    linkedin_company_ids=None,
                    **indeed_kwargs,
                    **({"linkedin_li_at": li_at} if li_at else {}),
                )
            except Exception as exc:
                print(f"  [jobspy] {term!r} / {location} → error: {exc}")
                continue

            for _, row in df.iterrows():
                title = str(row.get("title") or "").strip()
                company = str(row.get("company") or "").strip()
                url = str(row.get("job_url") or "").strip()
                description = str(row.get("description") or "")

                if not title or not url or url == "nan":
                    continue
                if EXCLUDE_TITLES.search(title):
                    continue
                if not DESIGN_TITLE_REQUIRED.search(title):
                    continue
                if _seniority(title, description) == "junior":
                    continue

                # dedup by company + normalized title
                key = f"{company.lower()}:{title.lower()}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                board = str(row.get("site") or "jobspy")
                loc = str(row.get("location") or location)
                salary = str(row.get("min_amount") or "")
                if salary and row.get("max_amount"):
                    salary = f"{salary}–{row['max_amount']} {row.get('currency','')}"

                emails = row.get("emails")
                apply_email: Optional[str] = None
                if emails:
                    if isinstance(emails, list) and emails:
                        apply_email = emails[0]
                    elif isinstance(emails, str):
                        apply_email = emails

                apply_url_raw = str(row.get("job_url_direct") or "")
                apply_url = apply_url_raw if (apply_url_raw and apply_url_raw != "nan") else url

                # tag: remote | local | relocation
                job_tags = [category]
                if is_remote:
                    job_tags.append("remote")

                job = Job(
                    id=_job_id(board, url),
                    title=title,
                    company=company,
                    url=url,
                    board=board,
                    location=loc,
                    description=description[:3000],
                    apply_url=apply_url,
                    apply_email=apply_email,
                    apply_type=_apply_type(row),
                    salary=salary,
                    tags=job_tags,
                    recruiter_name=str(row.get("company_linkedin_url") or ""),
                    recruiter_url="",
                    posted_at=_parse_posted(row),
                )
                jobs.append(job)

            # small delay between searches to avoid rate-limiting
            time.sleep(1)

    print(f"  [jobspy] {len(jobs)} jobs found across all searches")
    return jobs

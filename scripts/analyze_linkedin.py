"""
Quick LinkedIn analysis script — no login required.
Uses LinkedIn's public guest jobs API.

Usage:
    .\.venv\Scripts\python.exe scripts/analyze_linkedin.py
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ─── Config ─────────────────────────────────────────────────────────────────

SEARCHES = [
    # English — Argentina
    {"keywords": "UX designer",          "location": "Argentina"},
    {"keywords": "UI designer",           "location": "Argentina"},
    {"keywords": "product designer",      "location": "Argentina"},
    {"keywords": "UX UI designer",        "location": "Argentina"},
    {"keywords": "graphic designer",      "location": "Argentina"},
    {"keywords": "UX designer",           "location": "Buenos Aires"},
    {"keywords": "product designer",      "location": "Buenos Aires"},
    # Spanish — Argentina
    {"keywords": "diseñador UX",          "location": "Argentina"},
    {"keywords": "diseñador UI",          "location": "Argentina"},
    {"keywords": "diseñador de producto", "location": "Argentina"},
    {"keywords": "diseño UX UI",          "location": "Argentina"},
    {"keywords": "diseñador gráfico",     "location": "Argentina"},
    # Remote / contractor worldwide
    {"keywords": "UX designer",           "location": "Remote"},
    {"keywords": "product designer",      "location": "Remote"},
    {"keywords": "UX UI designer",        "location": "Remote"},
]

MAX_PER_SEARCH = 25   # LinkedIn guest API returns up to 25 per page

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ─── Data model ─────────────────────────────────────────────────────────────

@dataclass
class LIJob:
    id: str
    title: str
    company: str
    location: str
    url: str
    listed_at: str = ""
    description: str = ""
    keywords_found: list[str] = field(default_factory=list)


# ─── Fetch ───────────────────────────────────────────────────────────────────

def fetch_jobs(keywords: str, location: str, start: int = 0) -> list[LIJob]:
    url = (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        f"?keywords={requests.utils.quote(keywords)}"
        f"&location={requests.utils.quote(location)}"
        f"&f_TPR=r604800"    # posted in last 7 days
        f"&start={start}"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ⚠️  Request failed ({keywords} / {location}): {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    jobs = []
    for card in soup.find_all("li"):
        try:
            job_id = card.find("div", {"data-entity-urn": True})
            if not job_id:
                continue
            urn = job_id["data-entity-urn"]
            jid = urn.split(":")[-1]

            title_el = card.find("h3", class_=re.compile(r"base-search-card__title"))
            company_el = card.find("h4", class_=re.compile(r"base-search-card__subtitle"))
            location_el = card.find("span", class_=re.compile(r"job-search-card__location"))
            time_el = card.find("time")
            link_el = card.find("a", class_=re.compile(r"base-card__full-link"))

            jobs.append(LIJob(
                id=jid,
                title=title_el.get_text(strip=True) if title_el else "N/A",
                company=company_el.get_text(strip=True) if company_el else "N/A",
                location=location_el.get_text(strip=True) if location_el else location,
                url=link_el["href"].split("?")[0] if link_el else "",
                listed_at=time_el.get("datetime", "") if time_el else "",
            ))
        except Exception:
            continue

    return jobs


def fetch_description(job_id: str) -> str:
    """Fetch the first 800 chars of the job description from the public detail page."""
    url = f"https://www.linkedin.com/jobs/view/{job_id}/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        desc_el = soup.find("div", class_=re.compile(r"show-more-less-html__markup"))
        if desc_el:
            text = desc_el.get_text(separator=" ", strip=True)
            return text[:800]
    except Exception:
        pass
    return ""


# ─── Keyword analysis ────────────────────────────────────────────────────────

INTEREST_KEYWORDS = [
    "figma", "sketch", "prototyp", "wireframe", "user research",
    "usability", "design system", "agile", "scrum", "remote",
    "contractor", "freelance", "part-time", "senior", "lead",
    "argentina", "latam", "latin america", "buenos aires",
    "english", "inglés", "bilingual",
]

# Titles containing these → skip entirely
EXCLUDE_TITLE_KEYWORDS = [
    # Dev / engineering
    "front end developer", "frontend developer", "software engineer",
    "desarrollador", "developer", "android", "ios developer",
    # Business / non-design
    "accountant", "sales", "marketing manager", "data scientist",
    "analista funcional", "analista de sistemas", "business analyst",
    # Pure non-digital visual (not UX)
    "marketing visual", "motion designer", "video editor", "animator",
    "visual designer",          # only when NOT combined with UX/UI
    # Writing / content
    "content design", "content designer", "copywriter",
    # Physical product design (not digital UX)
    "hardgoods", "footwear", "apparel", "furniture",
    # Graduate / intern (caught by JUNIOR_SIGNALS already but belt+suspenders)
    "graduate ux",
]

# Titles OR description containing these → mark as junior, filter out
JUNIOR_SIGNALS = [
    r"\bjr\b", r"\bjunior\b", r"\bentry.?level\b", r"\bentry level\b",
    r"\btrainee\b", r"\bintern\b", r"\bpasante\b",
    r"\bpráctica\b", r"\bpractice\b", r"\bgraduate\b",
]

# Titles containing these → preferred (semi-sr to sr)
SENIOR_SIGNALS = [
    r"\bsenior\b", r"\bsr\.?\b", r"\bsemi.?senior\b", r"\bssr\b",
    r"\blead\b", r"\bstaff\b", r"\bprincipal\b", r"\bmanager\b",
    r"\bmid\b", r"\bmiddle\b", r"\bpleno\b",
]

def analyze_keywords(text: str) -> list[str]:
    text_lower = text.lower()
    return [kw for kw in INTEREST_KEYWORDS if kw in text_lower]


def is_junior(title: str, description: str = "") -> bool:
    t = title.lower()
    if any(re.search(p, t) for p in JUNIOR_SIGNALS):
        return True
    # Also catch "entry-level" / "junior" buried in description but not title
    desc_lower = description.lower()
    early_desc = desc_lower[:300]  # only check first 300 chars to avoid false positives
    return any(re.search(p, early_desc) for p in JUNIOR_SIGNALS)


def seniority_score(title: str) -> int:
    """Higher = more senior. Used for sorting."""
    t = title.lower()
    return sum(1 for p in SENIOR_SIGNALS if re.search(p, t))


_LOCATION_SUFFIX = re.compile(
    r"\s*[-–]\s*(remote|latin america|latam|argentina|buenos aires"
    r"|rosario|córdoba|cordoba|salta|mendoza|remote.*latam.*).*",
    re.IGNORECASE,
)

def _dedup_key(job: "LIJob") -> tuple[str, str]:
    """(company, normalized_title) — collapses same job posted in multiple cities."""
    company = job.company.lower().strip()
    title = _LOCATION_SUFFIX.sub("", job.title).lower().strip()
    # also strip trailing city/country in parentheses
    title = re.sub(r"\s*\(.*\)\s*$", "", title).strip()
    return (company, title)


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    all_jobs: dict[str, LIJob] = {}           # deduplicate by id
    dedup_titles: dict[tuple, str] = {}        # (company, title) → first id seen

    print("=" * 70)
    print("  LinkedIn Job Analysis — Argentina + Remote")
    print("  Semi-Sr to Sr filter ON | Spanish keywords ON")
    print("  (no login, no state saved, no email)")
    print("=" * 70)

    for s in SEARCHES:
        kw, loc = s["keywords"], s["location"]
        print(f"\n🔍 '{kw}' in '{loc}'...")
        batch = fetch_jobs(kw, loc)
        new = [j for j in batch if j.id not in all_jobs]
        for j in new:
            all_jobs[j.id] = j
        print(f"   Found {len(batch)} listings, {len(new)} new (deduped by id)")
        time.sleep(2)

    print(f"\n📋 Total unique jobs: {len(all_jobs)}")
    print("   Fetching descriptions (may take ~30s)...\n")

    jobs_list = list(all_jobs.values())

    # Fetch descriptions with rate limiting
    for i, job in enumerate(jobs_list):
        if job.id:
            job.description = fetch_description(job.id)
            job.keywords_found = analyze_keywords(job.title + " " + job.description)
        if (i + 1) % 5 == 0:
            print(f"   ... {i+1}/{len(jobs_list)} done")
            time.sleep(1)

    # --- Company+title deduplication ---
    seen_title_keys: dict[tuple, str] = {}
    title_deduped: list[LIJob] = []
    for job in jobs_list:
        key = _dedup_key(job)
        if key not in seen_title_keys:
            seen_title_keys[key] = job.id
            title_deduped.append(job)
        # else: same job in another city — skip
    collapsed = len(jobs_list) - len(title_deduped)
    if collapsed:
        print(f"   (collapsed {collapsed} duplicate same-job-different-city postings)")

    # ── Filter: exclude non-UX roles and juniors ──────────────────────────────
    def is_design_job(job: LIJob) -> bool:
        title_lower = job.title.lower()
        return not any(excl in title_lower for excl in EXCLUDE_TITLE_KEYWORDS)

    filtered = [j for j in title_deduped if is_design_job(j)]
    non_design = len(title_deduped) - len(filtered)
    if non_design:
        print(f"   (filtered out {non_design} non-UX/product-design titles)")

    juniors = [j for j in filtered if is_junior(j.title, j.description)]
    filtered = [j for j in filtered if not is_junior(j.title, j.description)]
    if juniors:
        print(f"   (filtered out {len(juniors)} junior/entry-level roles)")
        for j in juniors:
            print(f"     ↳ skipped: {j.title} @ {j.company}")

    # ── Sort: seniority first, then keyword richness ───────────────────────────
    filtered.sort(key=lambda j: (seniority_score(j.title), len(j.keywords_found)), reverse=True)

    # ── Print results ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"  RESULTS — {len(filtered)} design jobs")
    print("=" * 70)

    for i, job in enumerate(filtered, 1):
        print(f"\n{'─'*70}")
        print(f"  #{i:02d}  {job.title}")
        print(f"       Company : {job.company}")
        print(f"       Location: {job.location}")
        print(f"       Posted  : {job.listed_at or 'N/A'}")
        print(f"       Link    : {job.url}")
        if job.keywords_found:
            print(f"       Tags    : {', '.join(job.keywords_found)}")
        if job.description:
            # Wrap description at 66 chars
            desc = job.description[:500]
            lines = [desc[i:i+66] for i in range(0, len(desc), 66)]
            print(f"       Desc    : {lines[0]}")
            for line in lines[1:3]:
                print(f"                 {line}")
            if len(lines) > 3:
                print(f"                 ...")

    # ── Summary stats ─────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("  SUMMARY")
    print(f"{'='*70}")

    argentina_jobs = [j for j in filtered if "argentina" in j.location.lower()
                      or "buenos aires" in j.location.lower()]
    remote_jobs = [j for j in filtered if "remote" in j.location.lower()
                   or "remote" in j.description.lower()]
    with_figma = [j for j in filtered if "figma" in j.keywords_found]
    senior_roles = [j for j in filtered if "senior" in j.title.lower() or "lead" in j.title.lower()]

    print(f"  🇦🇷 Argentina-based    : {len(argentina_jobs)}")
    print(f"  🌎 Mentions remote     : {len(remote_jobs)}")
    print(f"  🎨 Mentions Figma      : {len(with_figma)}")
    print(f"  ⭐ Senior/Lead roles   : {len(senior_roles)}")

    if argentina_jobs:
        print(f"\n  Argentina jobs:")
        for j in argentina_jobs:
            print(f"    • {j.title} @ {j.company} — {j.location}")

    print()


if __name__ == "__main__":
    main()


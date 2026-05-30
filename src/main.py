"""
Main entry point for the job scraper.

Usage:
  python -m src.main                  # run all enabled scrapers, save to DB
  python -m src.main --dry-run        # don't persist to DB, don't send email
  python -m src.main --boards remoteok weworkremotely getonbrd
  python -m src.main --boards jobspy
"""
from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()  # loads .env file if present (local dev)

from src.core.config import load as load_config
from src.core.database import upsert_jobs, rescore_all
from src.core.emailer import send_summary
from src.core.scoring import score_jobs
from src.scrapers import ALL_SCRAPERS
import src.scrapers.jobspy_scraper as jobspy_scraper


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Job Scraper")
    parser.add_argument("--dry-run", action="store_true", help="Do not persist state or send email")
    parser.add_argument("--boards", nargs="*", help="Only run specified boards (e.g. remoteok weworkremotely jobspy)")
    parser.add_argument("--rescore", action="store_true", help="Recompute scores for all jobs in the DB and exit")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    email_prefix = config.get("email", {}).get("subject_prefix", "[JobScraper]")

    if args.rescore:
        n = rescore_all(config)
        print(f"Rescored {n} jobs in the DB.")
        return

    active_boards = {b.lower() for b in args.boards} if args.boards else None

    all_jobs = []

    # ── BaseScraper-based scrapers ─────────────────────────────────────────────
    for ScraperClass in ALL_SCRAPERS:
        if active_boards and ScraperClass.name not in active_boards:
            continue
        print(f"Scraping {ScraperClass.name}...")
        scraper = ScraperClass(config)
        try:
            jobs = scraper.scrape()
            all_jobs.extend(jobs)
        except Exception as exc:
            print(f"  {ScraperClass.name} failed: {exc}")

    # ── JobSpy (LinkedIn / Indeed / Glassdoor / Google) ───────────────────────
    jobspy_enabled = config.get("jobspy", {}).get("enabled", True)
    run_jobspy = jobspy_enabled and (active_boards is None or "jobspy" in active_boards)
    if run_jobspy:
        print("Scraping via JobSpy (LinkedIn / Indeed / Glassdoor / Google)...")
        try:
            jobs = jobspy_scraper.scrape(config)
            all_jobs.extend(jobs)
        except Exception as exc:
            print(f"  JobSpy failed: {exc}")

    print(f"\nTotal raw results: {len(all_jobs)}")

    # Score every job against the CV profile and rank best-first.
    score_jobs(all_jobs, config)
    all_jobs.sort(key=lambda j: j.score, reverse=True)

    if args.dry_run:
        for i, job in enumerate(all_jobs[:20], 1):
            print(f"  {i:3d}. [{job.score:3d}] [{job.board}] {job.title} @ {job.company}")
        print("\nDry-run: nothing saved.")
        return

    new_jobs = upsert_jobs(all_jobs)
    print(f"New jobs saved to DB: {len(new_jobs)}")

    for i, job in enumerate(new_jobs, 1):
        print(f"  {i:3d}. [{job.board}] {job.title} @ {job.company} — {job.apply_url}")

    try:
        send_summary(new_jobs, prefix=email_prefix)
    except Exception as exc:
        print(f"  Email failed (configure Gmail App Password in .env): {exc}")


if __name__ == "__main__":
    main()

"""
Main entry point for the job scraper.

Usage:
  python -m src.main                  # run all enabled scrapers
  python -m src.main --dry-run        # don't mark jobs as seen / don't send email
  python -m src.main --boards remoteok weworkremotely
"""
from __future__ import annotations

import argparse
import sys

from src.core.config import load as load_config
from src.core.tracker import filter_new, mark_seen
from src.core.emailer import send_summary
from src.scrapers import ALL_SCRAPERS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Job Scraper")
    parser.add_argument("--dry-run", action="store_true", help="Do not persist state or send email")
    parser.add_argument("--boards", nargs="*", help="Only run specified boards (e.g. remoteok weworkremotely)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    retention = config.get("deduplication", {}).get("retention_days", 90)
    email_prefix = config.get("email", {}).get("subject_prefix", "[JobScraper]")

    active_boards = {b.lower() for b in args.boards} if args.boards else None

    all_jobs = []
    for ScraperClass in ALL_SCRAPERS:
        if active_boards and ScraperClass.name not in active_boards:
            continue
        print(f"🔍 Running {ScraperClass.name} scraper...")
        scraper = ScraperClass(config)
        try:
            jobs = scraper.scrape()
            all_jobs.extend(jobs)
        except Exception as exc:
            print(f"  ❌ {ScraperClass.name} failed: {exc}")

    print(f"\n📋 Total raw results: {len(all_jobs)}")

    new_jobs = filter_new(all_jobs, retention_days=retention)
    print(f"✨ New (unseen) jobs: {len(new_jobs)}")

    for i, job in enumerate(new_jobs, 1):
        print(f"  {i:3d}. [{job.board}] {job.title} @ {job.company} — {job.apply_url}")

    if args.dry_run:
        print("\n⚡ Dry-run mode: state not saved, email not sent.")
        return

    if new_jobs:
        mark_seen(new_jobs)
        print("\n💾 Seen-jobs store updated.")

    send_summary(new_jobs, prefix=email_prefix)


if __name__ == "__main__":
    main()

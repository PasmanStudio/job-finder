"""Base scraper interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from src.core.models import Job


class BaseScraper(ABC):
    name: str = "base"

    def __init__(self, config: dict):
        self.config = config
        self.keywords: list[str] = config.get("search", {}).get("keywords", [])
        self.excluded: list[str] = config.get("search", {}).get("excluded_keywords", [])

    @abstractmethod
    def scrape(self) -> Sequence[Job]:
        """Fetch and return job listings from this board."""

    def _matches(self, job: Job) -> bool:
        """Return True if the job matches search criteria."""
        text = f"{job.title} {job.description}".lower()

        # Must match at least one keyword
        if self.keywords and not any(kw.lower() in text for kw in self.keywords):
            return False

        # Must not contain excluded keywords in the title
        title_lower = job.title.lower()
        if any(ex.lower() in title_lower for ex in self.excluded):
            return False

        return True

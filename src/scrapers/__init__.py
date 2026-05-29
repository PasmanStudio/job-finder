from src.scrapers.base import BaseScraper
from src.scrapers.remoteok import RemoteOKScraper
from src.scrapers.weworkremotely import WeWorkRemotelyScraper
from src.scrapers.linkedin import LinkedInScraper
from src.scrapers.indeed import IndeedScraper
from src.scrapers.wellfound import WellfoundScraper

ALL_SCRAPERS: list[type[BaseScraper]] = [
    RemoteOKScraper,
    WeWorkRemotelyScraper,
    LinkedInScraper,
    IndeedScraper,
    WellfoundScraper,
]

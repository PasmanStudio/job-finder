from src.scrapers.base import BaseScraper
from src.scrapers.remoteok import RemoteOKScraper
from src.scrapers.weworkremotely import WeWorkRemotelyScraper
from src.scrapers.getonbrd import GetOnBrdScraper
from src.scrapers.remotive import RemotiveScraper
from src.scrapers.himalayas import HimalayasScraper
from src.scrapers.torre import TorreScraper

ALL_SCRAPERS: list[type[BaseScraper]] = [
    RemoteOKScraper,
    WeWorkRemotelyScraper,
    GetOnBrdScraper,
    RemotiveScraper,
    HimalayasScraper,
    TorreScraper,
]

"""Tests for individual scrapers."""
from src.nerajob.scrapers.arbeitnow import ArbeitnowScraper
from src.nerajob.scrapers.jooble import JoobleScraper
from src.nerajob.scrapers.greenhouse import GreenhouseScraper

def test_arbeitnow_scraper():
    s = ArbeitnowScraper()
    assert s.user_agent == "NeraJob-Scraper/1.0"

def test_jooble_scraper_no_key():
    s = JoobleScraper()
    jobs = s.search_jobs("developer", region="us")
    assert len(jobs) == 3  # Sample data
    assert all('id' in j for j in jobs)

def test_greenhouse_scraper_empty():
    s = GreenhouseScraper()
    jobs = s.search_jobs(company="")  # No company -> empty
    assert jobs == []

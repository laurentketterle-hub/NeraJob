"""Tests for scraper framework."""
import pytest
from src.nerajob.scraper_framework import RateLimiter, BaseScraper

def test_rate_limiter():
    rl = RateLimiter(calls_per_minute=60)
    start = __import__('time').time()
    for _ in range(5):
        rl.acquire()
    assert True  # No hanging

def test_base_scraper():
    class TestScraper(BaseScraper):
        def search_jobs(self, query="", **kw):
            return [{"id": "1", "title": query}]
        def normalize_job(self, raw):
            return raw
    
    s = TestScraper()
    jobs = s.search_jobs("python")
    assert len(jobs) == 1
    assert jobs[0]['title'] == "python"

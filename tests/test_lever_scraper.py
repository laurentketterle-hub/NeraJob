"""Tests for the Lever scraper."""
from nerajob.scrapers.lever import LeverScraper


def test_lever_scraper_filters_python_roles():
    jobs = LeverScraper().search(query="python", limit=10)
    assert jobs
    for j in jobs:
        assert "python" in f"{j.title} {j.description} {' '.join(j.tags)}".lower()

def test_lever_scraper_respects_limit():
    jobs = LeverScraper().search(query="", limit=1)
    assert len(jobs) <= 1

def test_lever_scraper_ids_stable():
    a = LeverScraper().search(query="", limit=5)
    b = LeverScraper().search(query="", limit=5)
    assert [j.id for j in a] == [j.id for j in b]

def test_lever_scraper_no_match_returns_empty():
    jobs = LeverScraper().search(query="zzzznotexistkeyword", limit=10)
    assert jobs == []

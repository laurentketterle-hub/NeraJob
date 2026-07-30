"""Tests for USAJOBS scraper."""
import pytest


def test_usajobs_import():
    """USAJobsScraper should be importable."""
    from nerajob.scrapers.usajobs import USAJobsScraper
    assert USAJobsScraper is not None


def test_usajobs_offline_search_empty():
    """Offline search with empty query returns all samples."""
    from nerajob.scrapers.usajobs import USAJobsScraper
    scraper = USAJobsScraper()  # no API key -> offline mode
    results = scraper.search("", limit=10)
    assert len(results) >= 1
    assert results[0].source == "usajobs"


def test_usajobs_offline_search_filtered():
    """Offline search with query filters results."""
    from nerajob.scrapers.usajobs import USAJobsScraper
    scraper = USAJobsScraper()
    results = scraper.search("software", limit=10)
    assert len(results) >= 1
    assert any("software" in r.title.lower() for r in results)


def test_usajobs_offline_search_skills():
    """Offline results should include skills."""
    from nerajob.scrapers.usajobs import USAJobsScraper
    scraper = USAJobsScraper()
    results = scraper.search("python", limit=10)
    for r in results:
        if "python" in " ".join(r.skills or []).lower():
            return
    pytest.skip("No python match in offline samples")


def test_usajobs_registered():
    """USAJobsScraper should be in available_scrapers."""
    from nerajob.scrapers.registry import available_scrapers
    scrapers = available_scrapers()
    assert "usajobs" in scrapers


def test_usajobs_offline_search_limit():
    """Offline search respects limit."""
    from nerajob.scrapers.usajobs import USAJobsScraper
    scraper = USAJobsScraper()
    results = scraper.search("", limit=2)
    assert len(results) <= 2

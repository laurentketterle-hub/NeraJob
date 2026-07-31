"""Tests for USAJOBS scraper (NeraJob #8)."""

import pytest

from nerajob.scrapers.usajobs import USAJobsScraper


class TestUSAJobsScraper:
    def test_name(self):
        scraper = USAJobsScraper()
        assert scraper.name == "usajobs"

    def test_offline_by_default(self):
        scraper = USAJobsScraper()
        assert scraper._offline() is True

    def test_search_returns_results(self):
        scraper = USAJobsScraper()
        results = scraper.search("python")
        assert len(results) > 0
        assert all(r.source == "usajobs" for r in results)

    def test_search_query_filter(self):
        scraper = USAJobsScraper()
        results = scraper.search("Data Scientist")
        assert len(results) >= 1
        assert any("Data Scientist" in r.title for r in results)

    def test_search_query_no_match(self):
        scraper = USAJobsScraper()
        results = scraper.search("zzz_nonexistent_query_xyz")
        assert len(results) == 0

    def test_search_location_filter(self):
        scraper = USAJobsScraper()
        results = scraper.search("", location="Remote")
        assert len(results) > 0
        assert all("remote" in r.location.lower() for r in results)

    def test_search_limit(self):
        scraper = USAJobsScraper()
        results = scraper.search("", limit=2)
        assert len(results) <= 2

    def test_offline_fixtures_have_all_jobs(self):
        scraper = USAJobsScraper()
        results = scraper.search("", limit=100)
        assert len(results) == 5

    def test_result_structure(self):
        scraper = USAJobsScraper()
        results = scraper.search("IT")
        assert len(results) > 0
        job = results[0]
        assert job.id.startswith("usajobs-")
        assert job.source == "usajobs"
        assert len(job.title) > 0
        assert len(job.company) > 0
        assert len(job.url) > 0
        assert "federal" in job.tags
        assert "us-government" in job.tags

    def test_salary_present(self):
        scraper = USAJobsScraper()
        results = scraper.search("IT")
        assert len(results) > 0
        assert results[0].salary != ""

    def test_offline_force_via_env(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_USAJOBS_API_KEY", "fake-key")
        monkeypatch.setenv("NERAJOB_USAJOBS_EMAIL", "test@example.com")
        monkeypatch.setenv("NERAJOB_USAJOBS_OFFLINE", "1")
        scraper = USAJobsScraper()
        assert scraper._offline() is True

    def test_offline_no_credentials(self, monkeypatch):
        monkeypatch.delenv("NERAJOB_USAJOBS_API_KEY", raising=False)
        monkeypatch.delenv("NERAJOB_USAJOBS_EMAIL", raising=False)
        scraper = USAJobsScraper()
        assert scraper._offline() is True

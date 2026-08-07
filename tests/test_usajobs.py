"""Tests for USAJOBS scraper."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from nerajob.scrapers.usajobs import _OFFLINE, UsajobsScraper


class TestUsajobsScraper:
    def test_name(self):
        scraper = UsajobsScraper()
        assert scraper.name == "usajobs"

    def test_offline_returns_fixtures_without_api_key(self):
        scraper = UsajobsScraper()
        results = scraper.search("python")
        assert len(results) > 0
        for r in results:
            assert r.source == "usajobs"
            assert r.title
            assert r.company
            assert r.url.startswith("https://")

    def test_offline_filters_by_query(self):
        scraper = UsajobsScraper()
        results = scraper.search("Data Scientist")
        assert len(results) >= 1
        titles = [r.title.lower() for r in results]
        assert any("data scientist" in t for t in titles)

    def test_offline_filters_by_location(self):
        scraper = UsajobsScraper()
        results = scraper.search("", location="Washington")
        assert len(results) >= 1
        assert any("washington" in r.location.lower() for r in results)

    def test_offline_respects_limit(self):
        scraper = UsajobsScraper()
        results = scraper.search("", limit=3)
        assert len(results) <= 3

    def test_offline_no_match_returns_empty(self):
        scraper = UsajobsScraper()
        results = scraper.search("XYZZY_NONEXISTENT_QUERY")
        assert len(results) == 0

    def test_offline_env_var_forces_offline(self):
        scraper = UsajobsScraper()
        with patch.dict(os.environ, {"NERAJOB_USAJOBS_OFFLINE": "1"}):
            results = scraper.search("IT Specialist", location="Washington")
            assert len(results) >= 1
            assert any("specialist" in r.title.lower() for r in results)

    def test_offline_env_var_true_is_recognized(self):
        scraper = UsajobsScraper()
        for val in ("1", "true", "yes"):
            with patch.dict(os.environ, {"NERAJOB_USAJOBS_OFFLINE": val}):
                results = scraper.search("python", limit=2)
                assert len(results) > 0
                assert all(r.source == "usajobs" for r in results)

    def test_live_api_graceful_fallback_on_connection_error(self):
        """When API key is set but network fails, fall back to offline."""
        scraper = UsajobsScraper()
        with patch.dict(os.environ, {"NERAJOB_USAJOBS_API_KEY": "fake-key-123", "NERAJOB_USAJOBS_EMAIL": "test@example.com"}, clear=False):
            with patch("nerajob.scrapers.usajobs.httpx.Client.get", side_effect=Exception("Connection refused")):
                results = scraper.search("python", limit=3)
                assert len(results) > 0
                assert all(r.source == "usajobs" for r in results)

    def test_live_api_graceful_fallback_on_http_error(self):
        scraper = UsajobsScraper()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 500")
        with patch.dict(os.environ, {"NERAJOB_USAJOBS_API_KEY": "fake-key-123"}, clear=False):
            with patch("nerajob.scrapers.usajobs.httpx.Client.get", return_value=mock_response):
                results = scraper.search("Engineer", limit=2)
                assert len(results) > 0

    def test_empty_query_returns_first_n_fixtures(self):
        scraper = UsajobsScraper()
        results = scraper.search("", limit=3)
        assert len(results) == 3
        for r in results:
            assert r.source == "usajobs"

    def test_tags_present(self):
        scraper = UsajobsScraper()
        results = scraper.search("Security", location="Arlington")
        assert len(results) >= 1
        for r in results:
            assert isinstance(r.tags, list)

    def test_offline_has_enough_fixtures(self):
        """Offline fixtures should have at least 5 entries for demo coverage."""
        assert len(_OFFLINE) >= 5

    def test_remote_detection(self):
        scraper = UsajobsScraper()
        results = scraper.search("", limit=20)
        remote_jobs = [r for r in results if r.remote]
        assert len(remote_jobs) > 0
        for r in remote_jobs:
            assert "remote" in r.location.lower() or r.remote

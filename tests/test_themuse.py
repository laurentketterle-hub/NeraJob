"""Tests for The Muse scraper — offline data, mocked HTTP, pagination."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from nerajob.scrapers.themuse import TheMuseScraper
from nerajob.models import JobPosting


# ── offline sample data tests ───────────────────────────────────────────────

class TestTheMuseOffline:
    def test_search_returns_jobs(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_THEMUSE_OFFLINE", "1")
        jobs = TheMuseScraper().search(query="", limit=10)
        assert len(jobs) >= 3
        assert all(isinstance(j, JobPosting) for j in jobs)

    def test_source_is_themuse(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_THEMUSE_OFFLINE", "1")
        jobs = TheMuseScraper().search(query="", limit=5)
        assert all(j.source == "themuse" for j in jobs)

    def test_python_keyword_filter(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_THEMUSE_OFFLINE", "1")
        jobs = TheMuseScraper().search(query="python", limit=10)
        assert len(jobs) >= 2
        for j in jobs:
            hay = f"{j.title} {j.description} {' '.join(j.tags)}".lower()
            assert "python" in hay

    def test_kubernetes_keyword_filter(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_THEMUSE_OFFLINE", "1")
        jobs = TheMuseScraper().search(query="kubernetes", limit=10)
        assert len(jobs) >= 1
        for j in jobs:
            hay = f"{j.title} {j.description} {' '.join(j.tags)}".lower()
            assert "kubernetes" in hay or "sre" in hay

    def test_respects_limit(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_THEMUSE_OFFLINE", "1")
        jobs = TheMuseScraper().search(query="", limit=2)
        assert len(jobs) <= 2
        assert len(jobs) >= 1

    def test_limit_zero_returns_empty(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_THEMUSE_OFFLINE", "1")
        jobs = TheMuseScraper().search(query="", limit=0)
        assert jobs == []

    def test_ids_are_stable(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_THEMUSE_OFFLINE", "1")
        a = TheMuseScraper().search(query="", limit=10)
        b = TheMuseScraper().search(query="", limit=10)
        assert [j.id for j in a] == [j.id for j in b]

    def test_ids_are_unique(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_THEMUSE_OFFLINE", "1")
        jobs = TheMuseScraper().search(query="", limit=10)
        ids = [j.id for j in jobs]
        assert len(ids) == len(set(ids))

    def test_no_match_returns_empty(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_THEMUSE_OFFLINE", "1")
        jobs = TheMuseScraper().search(query="zzzznotexistkeyword", limit=10)
        assert jobs == []

    def test_location_filter(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_THEMUSE_OFFLINE", "1")
        jobs = TheMuseScraper().search(query="", location="Remote", limit=10)
        assert len(jobs) >= 1
        for j in jobs:
            assert "remote" in j.location.lower()

    def test_san_francisco_location_filter(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_THEMUSE_OFFLINE", "1")
        jobs = TheMuseScraper().search(
            query="", location="San Francisco", limit=10
        )
        for j in jobs:
            assert "san francisco" in j.location.lower()

    def test_tags_exist(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_THEMUSE_OFFLINE", "1")
        jobs = TheMuseScraper().search(query="", limit=10)
        for j in jobs:
            assert isinstance(j.tags, list)

    def test_remote_detection(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_THEMUSE_OFFLINE", "1")
        jobs = TheMuseScraper().search(query="", limit=10)
        remote_jobs = [j for j in jobs if j.remote]
        assert len(remote_jobs) >= 1


# ── mocked HTTP tests ───────────────────────────────────────────────────────

_MUSE_PAGE_1 = {
    "page_count": 2,
    "page": 1,
    "results": [
        {
            "id": 1001,
            "name": "Python Developer",
            "company": {"name": "Tech Corp"},
            "locations": [{"name": "Remote"}],
            "categories": [
                {"name": "Engineering"},
                {"name": "Software Development"},
            ],
            "contents": "<p>Build Python APIs and services</p>",
            "refs": {"landing_page": "https://www.themuse.com/jobs/1001"},
        },
        {
            "id": 1002,
            "name": "Frontend Engineer",
            "company": {"name": "WebStudio"},
            "locations": [{"name": "New York, NY"}],
            "categories": [
                {"name": "Engineering"},
                {"name": "Frontend"},
            ],
            "contents": "<p>React and TypeScript development</p>",
            "refs": {"landing_page": "https://www.themuse.com/jobs/1002"},
        },
    ],
}

_MUSE_PAGE_2 = {
    "page_count": 2,
    "page": 2,
    "results": [
        {
            "id": 1003,
            "name": "Data Scientist",
            "company": {"name": "DataFlow Inc"},
            "locations": [{"name": "Remote"}],
            "categories": [
                {"name": "Data Science"},
                {"name": "Machine Learning"},
            ],
            "contents": "<p>Python, pandas, scikit-learn</p>",
            "refs": {"landing_page": "https://www.themuse.com/jobs/1003"},
        },
    ],
}


class TestTheMuseMockedHTTP:
    """Tests using mocked HTTP responses — no real network calls."""

    @pytest.fixture(autouse=True)
    def _clear_env(self, monkeypatch):
        monkeypatch.delenv("NERAJOB_THEMUSE_OFFLINE", raising=False)

    def _make_response(self, payload, status=200, headers=None):
        resp = MagicMock()
        resp.status_code = status
        resp.headers = headers or {"Content-Type": "application/json"}
        resp.json.return_value = payload
        resp.raise_for_status = MagicMock()
        return resp

    def test_single_page_results(self):
        scraper = TheMuseScraper()
        with patch.object(
            scraper, "search", wraps=scraper.search
        ) as wrapped:
            # Use offline mode for this test
            pass

        with patch("nerajob.scrapers.themuse.httpx.Client") as mock_client:
            client_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = client_instance
            client_instance.get.return_value = self._make_response(_MUSE_PAGE_1)

            jobs = TheMuseScraper().search(query="", limit=5)
            assert len(jobs) == 2
            assert jobs[0].title == "Python Developer"
            assert jobs[1].title == "Frontend Engineer"

    def test_python_query_filter(self):
        with patch("nerajob.scrapers.themuse.httpx.Client") as mock_client:
            client_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = client_instance
            client_instance.get.return_value = self._make_response(_MUSE_PAGE_1)

            jobs = TheMuseScraper().search(query="python", limit=10)
            assert len(jobs) == 1
            assert "python" in jobs[0].title.lower()

    def test_location_filter(self):
        with patch("nerajob.scrapers.themuse.httpx.Client") as mock_client:
            client_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = client_instance
            client_instance.get.return_value = self._make_response(_MUSE_PAGE_1)

            jobs = TheMuseScraper().search(query="", location="Remote", limit=10)
            assert len(jobs) == 1
            assert "remote" in jobs[0].location.lower()

    def test_multi_page_pagination(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_THEMUSE_OFFLINE", "1")
        # Use offline for reliability; pagination with live API is tested below
        jobs = TheMuseScraper().search(query="", limit=10)
        # Offline has 5 entries, limit=10 returns all
        assert len(jobs) == 5

    def test_limit_across_pages(self):
        """When limit > page size, we should fetch multiple pages."""
        with patch("nerajob.scrapers.themuse.httpx.Client") as mock_client:
            client_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = client_instance
            client_instance.get.side_effect = [
                self._make_response(_MUSE_PAGE_1),
                self._make_response(_MUSE_PAGE_2),
            ]

            jobs = TheMuseScraper().search(query="", limit=30)
            assert len(jobs) == 3  # 2 + 1 across two pages

    def test_api_error_falls_back_to_offline(self, monkeypatch):
        with patch("nerajob.scrapers.themuse.httpx.Client") as mock_client:
            client_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = client_instance
            client_instance.get.side_effect = Exception("Connection refused")

            jobs = TheMuseScraper().search(query="python", limit=5)
            assert len(jobs) >= 2
            assert all(j.source == "themuse" for j in jobs)

    def test_empty_results_falls_back_to_offline(self):
        with patch("nerajob.scrapers.themuse.httpx.Client") as mock_client:
            client_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = client_instance
            client_instance.get.return_value = self._make_response(
                {"page_count": 1, "page": 1, "results": []}
            )

            jobs = TheMuseScraper().search(query="python", limit=5)
            assert len(jobs) >= 2  # fallback to offline

    def test_company_name_extraction(self):
        with patch("nerajob.scrapers.themuse.httpx.Client") as mock_client:
            client_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = client_instance
            client_instance.get.return_value = self._make_response(_MUSE_PAGE_1)

            jobs = TheMuseScraper().search(query="", limit=5)
            assert jobs[0].company == "Tech Corp"
            assert jobs[1].company == "WebStudio"

    def test_tags_from_categories(self):
        with patch("nerajob.scrapers.themuse.httpx.Client") as mock_client:
            client_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = client_instance
            client_instance.get.return_value = self._make_response(_MUSE_PAGE_1)

            jobs = TheMuseScraper().search(query="", limit=5)
            assert "engineering" in jobs[0].tags
            assert "software development" in jobs[0].tags

    def test_url_extraction(self):
        with patch("nerajob.scrapers.themuse.httpx.Client") as mock_client:
            client_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = client_instance
            client_instance.get.return_value = self._make_response(_MUSE_PAGE_1)

            jobs = TheMuseScraper().search(query="", limit=5)
            assert jobs[0].url == "https://www.themuse.com/jobs/1001"


# ── registry integration ──────────────────────────────────────────────────

def test_themuse_registered():
    from nerajob.scrapers.registry import available_scrapers, get_scraper
    assert "themuse" in available_scrapers()
    s = get_scraper("themuse")
    assert isinstance(s, TheMuseScraper)

"""Tests for the Lever scraper — offline sample data and multi-board support."""
from __future__ import annotations

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from nerajob.scrapers.lever import LeverScraper, _parse_board_names, _strip_html
from nerajob.models import JobPosting


# ── board-name parsing ─────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", []),
        (None, []),
        ("  ", []),
        ("netflix", ["netflix"]),
        ("netflix,spotify", ["netflix", "spotify"]),
        ("netflix; spotify", ["netflix", "spotify"]),
        ("Netflix,SPOTIFY", ["netflix", "spotify"]),
        ("netflix,spotify,netflix", ["netflix", "spotify"]),  # dedup
        ("invalid name!", []),  # rejected by regex
        ("netflix,invalid name!,spotify", ["netflix", "spotify"]),
        ("  netflix , , spotify  ", ["netflix", "spotify"]),
    ],
)
def test_parse_board_names(raw, expected):
    assert _parse_board_names(raw) == expected


# ── HTML stripping ─────────────────────────────────────────────────────────

def test_strip_html_removes_tags():
    assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_strip_html_plain_text():
    assert _strip_html("Just plain text") == "Just plain text"


def test_strip_html_collapses_whitespace():
    assert _strip_html("<p>  Lots   of   space  </p>") == "Lots of space"


# ── offline sample data (no board env set) ─────────────────────────────────

class TestLeverOffline:
    """Tests against the enriched sample data (no board configured)."""

    def test_search_returns_jobs(self):
        jobs = LeverScraper().search(query="", limit=20)
        assert len(jobs) >= 3
        assert all(isinstance(j, JobPosting) for j in jobs)

    def test_source_is_lever(self):
        jobs = LeverScraper().search(query="", limit=5)
        assert all(j.source == "lever" for j in jobs)

    def test_python_keyword_filter(self):
        jobs = LeverScraper().search(query="python", limit=10)
        assert len(jobs) >= 2
        for j in jobs:
            hay = f"{j.title} {j.description} {' '.join(j.tags)}".lower()
            assert "python" in hay

    def test_frontend_keyword_filter(self):
        jobs = LeverScraper().search(query="frontend", limit=10)
        assert len(jobs) >= 1
        for j in jobs:
            hay = f"{j.title} {j.description} {' '.join(j.tags)}".lower()
            assert "frontend" in hay or "react" in hay

    def test_respects_limit(self):
        jobs = LeverScraper().search(query="", limit=2)
        assert len(jobs) <= 2
        assert len(jobs) >= 1

    def test_limit_zero_returns_empty(self):
        jobs = LeverScraper().search(query="", limit=0)
        assert jobs == []

    def test_ids_are_stable(self):
        a = LeverScraper().search(query="", limit=10)
        b = LeverScraper().search(query="", limit=10)
        assert [j.id for j in a] == [j.id for j in b]

    def test_ids_are_unique(self):
        jobs = LeverScraper().search(query="", limit=10)
        ids = [j.id for j in jobs]
        assert len(ids) == len(set(ids))

    def test_no_match_returns_empty(self):
        jobs = LeverScraper().search(query="zzzznotexistkeyword", limit=10)
        assert jobs == []

    def test_tags_exist(self):
        jobs = LeverScraper().search(query="", limit=10)
        for j in jobs:
            assert isinstance(j.tags, list)

    def test_remote_detection(self):
        jobs = LeverScraper().search(query="", limit=10)
        remote_jobs = [j for j in jobs if j.remote]
        non_remote = [j for j in jobs if not j.remote]
        assert len(remote_jobs) >= 1
        # San Francisco should not be remote
        if non_remote:
            assert any("san francisco" in j.location.lower() for j in non_remote)

    def test_location_filter(self):
        jobs = LeverScraper().search(query="", location="Remote", limit=10)
        assert len(jobs) >= 1
        for j in jobs:
            assert "remote" in j.location.lower()


# ── live API mocks ─────────────────────────────────────────────────────────

LEVER_API_RESPONSE = [
    {
        "id": "live-1",
        "text": "API Backend Dev",
        "description": "<p>Build Python APIs</p>",
        "categories": {
            "location": "Remote",
            "team": "Platform",
            "commitment": "Full-time",
        },
        "hostedUrl": "https://jobs.lever.co/testcorp/live-1",
    },
    {
        "id": "live-2",
        "text": "Frontend Lead",
        "description": "<p>Lead React team</p>",
        "categories": {
            "location": "Berlin, Germany",
            "team": "Product",
            "commitment": "Full-time",
        },
        "hostedUrl": "https://jobs.lever.co/testcorp/live-2",
    },
]


class TestLeverMockedHTTP:
    """Tests using mocked HTTP responses — no real network calls."""

    def test_single_board_fetch(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_LEVER_BOARD", "testcorp")

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(LEVER_API_RESPONSE).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("nerajob.scrapers.lever.urlopen", return_value=mock_response):
            scraper = LeverScraper()
            jobs = scraper.search(query="", limit=10)
            assert len(jobs) == 2
            assert jobs[0].title == "API Backend Dev"
            assert jobs[1].title == "Frontend Lead"

    def test_single_board_with_query(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_LEVER_BOARD", "testcorp")

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(LEVER_API_RESPONSE).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("nerajob.scrapers.lever.urlopen", return_value=mock_response):
            scraper = LeverScraper()
            jobs = scraper.search(query="python", limit=10)
            assert len(jobs) == 1
            assert "api" in jobs[0].title.lower()

    def test_multi_board_fetch(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_LEVER_BOARD", "boardA,boardB")

        def make_response(data):
            m = MagicMock()
            m.read.return_value = json.dumps(data).encode()
            m.__enter__ = MagicMock(return_value=m)
            m.__exit__ = MagicMock(return_value=False)
            return m

        resp_a = make_response(
            [{"id": "a1", "text": "Job A1", "categories": {}, "hostedUrl": "https://jobs.lever.co/boardA/a1"}]
        )
        resp_b = make_response(
            [{"id": "b1", "text": "Job B1", "categories": {}, "hostedUrl": "https://jobs.lever.co/boardB/b1"}]
        )

        with patch("nerajob.scrapers.lever.urlopen", side_effect=[resp_a, resp_b]):
            with patch("nerajob.scrapers.lever.time.sleep", return_value=None):  # skip delay
                scraper = LeverScraper()
                jobs = scraper.search(query="", limit=20)
                assert len(jobs) == 2

    def test_board_fetch_http_error_graceful(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_LEVER_BOARD", "badboard")

        from urllib.error import HTTPError

        with patch("nerajob.scrapers.lever.urlopen", side_effect=HTTPError(
            "http://fake", 404, "Not Found", {}, None
        )):
            scraper = LeverScraper()
            jobs = scraper.search(query="python", limit=10)
            assert jobs == []

    def test_board_constructor_override_env(self, monkeypatch):
        """board_name passed to constructor overrides env var."""
        monkeypatch.setenv("NERAJOB_LEVER_BOARD", "envboard")

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(LEVER_API_RESPONSE).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("nerajob.scrapers.lever.urlopen", return_value=mock_response):
            scraper = LeverScraper(board_name="overridecorp")
            jobs = scraper.search(query="", limit=10)
            assert len(jobs) == 2

    def test_company_extracted_from_url(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_LEVER_BOARD", "cool-company")

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            [{"id": "x1", "text": "Dev", "categories": {}, "hostedUrl": "https://jobs.lever.co/cool-company/x1"}]
        ).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("nerajob.scrapers.lever.urlopen", return_value=mock_response):
            scraper = LeverScraper()
            jobs = scraper.search(query="", limit=10)
            assert len(jobs) == 1
            assert jobs[0].company == "Cool Company"


# ── registry integration ──────────────────────────────────────────────────

def test_lever_registered():
    from nerajob.scrapers.registry import available_scrapers, get_scraper
    assert "lever" in available_scrapers()
    s = get_scraper("lever")
    assert isinstance(s, LeverScraper)

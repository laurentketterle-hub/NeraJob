"""Tests for USAJOBS scraper (NeraJob #8).

Enhanced test suite absorbing patterns from PR#130:
- Pagination tests (multi-page)
- Rate limiting tests (respects min interval)
- Error handling tests (retry, network failure, graceful degradation)
- Edge cases (empty query, large limit, invalid credentials)
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from nerajob.scrapers.usajobs import USAJobsScraper, RateLimiter, _MAX_RETRIES


# ── Helper: create a mock API response page ──────────────────────────────


def _mock_page(items: list[dict], total: int | None = None) -> dict:
    """Build a USAJOBS SearchResult-shaped dict."""
    search_items = []
    for item in items:
        search_items.append({"MatchedObjectDescriptor": item})
    result: dict = {
        "SearchResult": {
            "SearchResultItems": search_items,
        },
    }
    if total is not None:
        result["SearchResult"]["SearchResultCountAll"] = total
    return result


def _mock_job(i: int, title: str = "Software Engineer") -> dict:
    return {
        "PositionTitle": f"{title} {i}",
        "OrganizationName": f"Agency {i}",
        "PositionURI": f"https://www.usajobs.gov/job/{1000 + i}",
        "PositionLocation": [{"LocationName": f"City {i}, ST"}],
        "QualificationSummary": f"Qualification summary for job {i}.",
        "PositionRemuneration": [
            {
                "MinimumRange": str(80000 + i * 1000),
                "MaximumRange": str(120000 + i * 1000),
                "RateIntervalCode": "PA",
            }
        ],
    }


# ══════════════════════════════════════════════════════════════════════════
# RateLimiter
# ══════════════════════════════════════════════════════════════════════════


class TestRateLimiter:
    def test_first_call_no_wait(self):
        rl = RateLimiter(min_interval_s=999.0)  # huge interval
        start = time.monotonic()
        rl.wait()
        elapsed = time.monotonic() - start
        # First call should NOT wait (no prior call)
        assert elapsed < 1.0

    def test_second_call_waits(self):
        rl = RateLimiter(min_interval_s=0.3)
        rl.wait()  # first call
        start = time.monotonic()
        rl.wait()  # second call — should wait ~0.3s
        elapsed = time.monotonic() - start
        assert elapsed >= 0.25  # allow small timing variance


# ══════════════════════════════════════════════════════════════════════════
# USAJobsScraper — offline mode
# ══════════════════════════════════════════════════════════════════════════


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

    def test_offline_fixtures_count(self):
        scraper = USAJobsScraper()
        results = scraper.search("", limit=100)
        assert len(results) == len(scraper.OFFLINE_JOBS)

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

    def test_limit_clamped(self):
        """Extremely large limit is clamped to 10_000."""
        scraper = USAJobsScraper()
        results = scraper.search("", limit=99_999)
        # Should not crash; returns at most OFFLINE_JOBS count
        assert len(results) <= len(scraper.OFFLINE_JOBS)

    def test_zero_limit(self):
        scraper = USAJobsScraper()
        results = scraper.search("IT", limit=0)
        assert len(results) == 0

    def test_negative_limit_clamped_to_zero(self):
        scraper = USAJobsScraper()
        results = scraper.search("IT", limit=-5)
        assert len(results) == 0


# ══════════════════════════════════════════════════════════════════════════
# USAJobsScraper — live mode (mocked HTTP)
# ══════════════════════════════════════════════════════════════════════════


class TestUSAJobsScraperLive:
    """Tests that mock httpx to exercise the live API path."""

    @pytest.fixture
    def live_scraper(self, monkeypatch):
        monkeypatch.setenv("NERAJOB_USAJOBS_API_KEY", "test-key")
        monkeypatch.setenv("NERAJOB_USAJOBS_EMAIL", "test@example.com")
        # Speed up rate limiter for tests
        monkeypatch.setenv("NERAJOB_USAJOBS_RATE_LIMIT", "0.0")
        monkeypatch.setenv("NERAJOB_USAJOBS_MAX_RETRIES", "3")
        return USAJobsScraper()

    def test_live_single_page(self, live_scraper):
        """Single-page fetch with fewer results than limit."""
        jobs = [_mock_job(i) for i in range(5)]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _mock_page(jobs, total=5)
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            results = live_scraper.search("engineer", limit=10)

        assert len(results) == 5
        assert all(r.source == "usajobs" for r in results)
        assert results[0].title == "Software Engineer 0"

    def test_live_multi_page_pagination(self, live_scraper):
        """Multi-page: fetch 50 results spread across multiple API pages."""
        # Page 1 returns 30 results, total=50
        # Page 2 returns 20 results, total=50
        jobs_page1 = [_mock_job(i) for i in range(30)]
        jobs_page2 = [_mock_job(i, title="Data Analyst") for i in range(20)]

        response1 = MagicMock()
        response1.status_code = 200
        response1.json.return_value = _mock_page(jobs_page1, total=50)
        response1.raise_for_status = MagicMock()

        response2 = MagicMock()
        response2.status_code = 200
        response2.json.return_value = _mock_page(jobs_page2, total=50)
        response2.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.get.side_effect = [response1, response2]
            mock_client_cls.return_value = mock_client

            results = live_scraper.search("engineer", limit=50)

        assert len(results) == 50
        # Should have called get() twice (page 1 and page 2)
        assert mock_client.get.call_count == 2

    def test_live_stops_at_limit(self, live_scraper):
        """When the first page already fills the limit, no 2nd call."""
        jobs = [_mock_job(i) for i in range(30)]
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = _mock_page(jobs, total=999)
        response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.get.return_value = response
            mock_client_cls.return_value = mock_client

            results = live_scraper.search("engineer", limit=5)

        assert len(results) == 5
        assert mock_client.get.call_count == 1  # only one page

    def test_live_empty_first_page(self, live_scraper):
        """API returns zero results on first page."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = _mock_page([], total=0)
        response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.get.return_value = response
            mock_client_cls.return_value = mock_client

            results = live_scraper.search("nonexistent", limit=20)

        assert len(results) == 0

    def test_live_retry_on_503_then_succeed(self, live_scraper):
        """First call returns 503, retry succeeds."""
        jobs = [_mock_job(0)]
        fail_response = MagicMock()
        fail_response.status_code = 503
        fail_response.raise_for_status.side_effect = Exception("503")

        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.json.return_value = _mock_page(jobs, total=1)
        ok_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.get.side_effect = [fail_response, ok_response]
            mock_client_cls.return_value = mock_client

            results = live_scraper.search("engineer", limit=5)

        assert len(results) == 1
        assert mock_client.get.call_count == 2  # original + retry

    def test_live_retry_exhausted_falls_back(self, live_scraper):
        """All retries fail → graceful degradation to offline fixtures."""
        fail_response = MagicMock()
        fail_response.status_code = 503
        fail_response.raise_for_status.side_effect = Exception("503")

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            # Fail on every call (3 retries = 3 calls with our current logic's page-level retry)
            mock_client.get.return_value = fail_response
            mock_client_cls.return_value = mock_client

            results = live_scraper.search("IT", limit=3)

        # Should fall back to offline fixtures filtered by "IT"
        assert len(results) >= 1
        assert results[0].source == "usajobs"

    def test_live_httpx_timeout_fallback(self, live_scraper):
        """Network timeout triggers offline fallback."""
        import httpx

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.get.side_effect = httpx.TimeoutException("timeout")
            mock_client_cls.return_value = mock_client

            results = live_scraper.search("Cybersecurity", limit=5)

        assert len(results) >= 1
        assert results[0].source == "usajobs"

    def test_live_rate_limiter_called(self, live_scraper):
        """Rate limiter.wait() is invoked between pages."""
        jobs = [_mock_job(i) for i in range(5)]
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = _mock_page(jobs, total=5)
        response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.get.return_value = response
            mock_client_cls.return_value = mock_client

            with patch.object(live_scraper._rate_limiter, "wait") as mock_wait:
                live_scraper.search("engineer", limit=5)

            # wait() should be called at least once (for the single page fetch)
            assert mock_wait.call_count >= 1

    def test_live_location_param_passed(self, live_scraper):
        """Location parameter is forwarded to the API."""
        jobs = [_mock_job(0)]
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = _mock_page(jobs, total=1)
        response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.get.return_value = response
            mock_client_cls.return_value = mock_client

            live_scraper.search("dev", location="Remote")

        call_args = mock_client.get.call_args
        params = call_args[1]["params"] if call_args and "params" in call_args[1] else {}
        assert params.get("LocationName") == "Remote"

    def test_live_malformed_json_fallback(self, live_scraper):
        """API returns 200 but with unparseable JSON."""
        response = MagicMock()
        response.status_code = 200
        response.json.side_effect = ValueError("Bad JSON")
        response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.get.return_value = response
            mock_client_cls.return_value = mock_client

            results = live_scraper.search("IT", limit=5)

        # Should fall back to offline
        assert len(results) >= 1
        assert results[0].source == "usajobs"

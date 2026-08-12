"""Tests for the USAJOBS official Search API adapter.

Run with: pytest tests/test_usajobs.py  (or python -m unittest)

These tests are fully offline: live HTTP is mocked with ``unittest.mock`` and
the "no credentials" path exercises the deterministic offline fixtures.

Bounty: https://github.com/mergeos-bounties/NeraJob/issues/8
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from nerajob.scrapers.registry import available_scrapers, get_scraper
from nerajob.scrapers.usajobs import USAJobsScraper

# A realistic slice of the USAJOBS /api/search response envelope.
SAMPLE_PAYLOAD = {
    "LanguageCode": "EN",
    "SearchResult": {
        "SearchResultCount": 1,
        "SearchResultCountAll": 1,
        "SearchResultItems": [
            {
                "MatchedObjectId": "123456789",
                "MatchedObjectDescriptor": {
                    "PositionTitle": "Software Engineer",
                    "PositionURI": "https://www.usajobs.gov/GetJob/ViewDetails/123456789",
                    "PositionLocation": [
                        {"LocationName": "Washington, District of Columbia"}
                    ],
                    "OrganizationName": "National Aeronautics and Space Administration",
                    "DepartmentName": "National Aeronautics and Space Administration",
                    "QualificationSummary": "Build mission software in Python.",
                    "PositionRemuneration": [
                        {"MinimumRange": "85000", "MaximumRange": "120000", "RateIntervalCode": "PA"}
                    ],
                    "JobCategory": [{"Name": "Information Technology Management", "Code": "2210"}],
                    "PositionOfferingType": [{"Name": "Permanent", "Code": "15317"}],
                },
            }
        ],
    },
}


def _fake_response(payload: dict) -> mock.Mock:
    resp = mock.Mock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


class USAJobsRegistrationTests(unittest.TestCase):
    def test_registered(self) -> None:
        self.assertIn("usajobs", available_scrapers())
        scraper = get_scraper("usajobs")
        self.assertIsInstance(scraper, USAJobsScraper)
        self.assertEqual(scraper.name, "usajobs")


class USAJobsOfflineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scraper = USAJobsScraper()

    def test_offline_when_forced(self) -> None:
        with mock.patch.dict(os.environ, {"NERAJOB_USAJOBS_OFFLINE": "1"}):
            jobs = self.scraper.search(query="python", limit=5)
        self.assertTrue(jobs)
        self.assertTrue(all(j.source == "usajobs" for j in jobs))

    def test_offline_when_no_api_key(self) -> None:
        with mock.patch.dict(os.environ, {"USAJOBS_API_KEY": ""}):
            jobs = self.scraper.search(query="python", limit=5)
        self.assertTrue(jobs, "Should fall back to offline fixtures without a key")

    def test_offline_no_query_returns_all(self) -> None:
        with mock.patch.dict(os.environ, {"USAJOBS_API_KEY": ""}):
            jobs = self.scraper.search(query="", limit=20)
        self.assertGreaterEqual(len(jobs), 3)

    def test_offline_query_filter(self) -> None:
        with mock.patch.dict(os.environ, {"USAJOBS_API_KEY": ""}):
            jobs = self.scraper.search(query="cybersecurity", limit=20)
        self.assertTrue(jobs)
        self.assertTrue(any("cybersecurity" in j.title.lower() for j in jobs))

    def test_offline_location_filter(self) -> None:
        with mock.patch.dict(os.environ, {"USAJOBS_API_KEY": ""}):
            jobs = self.scraper.search(query="", location="Denver", limit=20)
        self.assertTrue(jobs)
        self.assertTrue(any("denver" in j.location.lower() for j in jobs))

    def test_offline_respects_limit(self) -> None:
        with mock.patch.dict(os.environ, {"USAJOBS_API_KEY": ""}):
            jobs = self.scraper.search(query="", limit=2)
        self.assertLessEqual(len(jobs), 2)


class USAJobsLiveMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scraper = USAJobsScraper()

    def _patch_live(self, payload: dict) -> tuple:
        env = mock.patch.dict(
            os.environ,
            {"USAJOBS_API_KEY": "test-key", "USAJOBS_EMAIL": "dev@example.com"},
        )
        client_patch = mock.patch("nerajob.scrapers.usajobs.httpx.Client")
        return env, client_patch

    def test_live_maps_fields(self) -> None:
        env, client_patch = self._patch_live(SAMPLE_PAYLOAD)
        with env:
            with client_patch as client_cls:
                client = client_cls.return_value.__enter__.return_value
                client.get.return_value = _fake_response(SAMPLE_PAYLOAD)
                jobs = self.scraper.search(query="engineer", limit=5)

        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job.source, "usajobs")
        self.assertEqual(job.title, "Software Engineer")
        self.assertEqual(job.company, "National Aeronautics and Space Administration")
        self.assertIn("Washington", job.location)
        self.assertEqual(job.url, "https://www.usajobs.gov/GetJob/ViewDetails/123456789")
        self.assertEqual(job.salary, "$85,000 - $120,000 PA")
        self.assertIn("information technology management", job.tags)
        self.assertIn("permanent", job.tags)
        self.assertIn("python", job.description.lower())

    def test_live_sends_required_headers_and_params(self) -> None:
        env, client_patch = self._patch_live(SAMPLE_PAYLOAD)
        with env:
            with client_patch as client_cls:
                client = client_cls.return_value.__enter__.return_value
                client.get.return_value = _fake_response(SAMPLE_PAYLOAD)
                self.scraper.search(query="python", location="Remote", limit=10)

        # httpx.Client(...) is constructed with the required headers.
        _, kwargs = client_cls.call_args
        headers = kwargs["headers"]
        self.assertEqual(headers["Host"], "data.usajobs.gov")
        self.assertEqual(headers["Authorization-Key"], "test-key")
        self.assertEqual(headers["User-Agent"], "dev@example.com")

        # client.get(...) receives Keyword / LocationName / ResultsPerPage.
        _, get_kwargs = client.get.call_args
        self.assertEqual(get_kwargs["params"]["Keyword"], "python")
        self.assertEqual(get_kwargs["params"]["LocationName"], "Remote")
        self.assertEqual(get_kwargs["params"]["ResultsPerPage"], 10)

    def test_live_network_error_falls_back_offline(self) -> None:
        env, client_patch = self._patch_live(SAMPLE_PAYLOAD)
        with env:
            with client_patch as client_cls:
                client = client_cls.return_value.__enter__.return_value
                client.get.side_effect = OSError("connection refused")
                jobs = self.scraper.search(query="python", limit=5)

        self.assertTrue(jobs, "Should degrade gracefully to offline fixtures")
        self.assertTrue(all(j.source == "usajobs" for j in jobs))


if __name__ == "__main__":
    unittest.main()

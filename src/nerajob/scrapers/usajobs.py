"""USAJOBS official API adapter for NeraJob.

USAJOBS is the US federal government's official job board.
API docs: https://developer.usajobs.gov/
Rate limit: 1,000 requests/hour with API key.

Bounty: https://github.com/mergeos-bounties/NeraJob/issues/8

Enhancements (absorbed from PR#130 patterns):
- Multi-page pagination (API supports up to 500 pages of 200 results each)
- Rate limiting with adaptive backoff (max 1,000 req/h = ~3.6s/req floor)
- Retry logic with exponential backoff (3 attempts, 1s → 2s → 4s)
- Graceful degradation on network/API errors → offline fallback
- Comprehensive error handling for all failure modes (429, 503, timeout, JSON parse)
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any

import httpx

from nerajob.config import http_timeout, user_agent
from nerajob.models import JobPosting
from nerajob.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# ── Rate limiting constants ──────────────────────────────────────────────
# USAJOBS allows 1,000 requests/hour → floor of 3.6 seconds between requests.
# We use a slightly conservative 4.0s to stay safely under the limit.
_RATE_LIMIT_FLOOR_S = float(os.getenv("NERAJOB_USAJOBS_RATE_LIMIT", "4.0"))
_MAX_RETRIES = int(os.getenv("NERAJOB_USAJOBS_MAX_RETRIES", "3"))
_RETRY_BACKOFF_BASE_S = 1.0  # doubles each retry: 1s → 2s → 4s
_HTTP_STATUS_RETRYABLE = {429, 500, 502, 503, 504}
_MAX_RESULTS_PER_PAGE = 200  # USAJOBS API max per page
_MAX_PAGES = int(os.getenv("NERAJOB_USAJOBS_MAX_PAGES", "25"))  # safety cap


class RateLimiter:
    """Simple token-bucket-inspired rate limiter for USAJOBS API calls."""

    def __init__(self, min_interval_s: float = _RATE_LIMIT_FLOOR_S):
        self._min_interval = min_interval_s
        self._last_call: float | None = None

    def wait(self) -> None:
        """Block until the minimum interval has elapsed since the last call."""
        now = time.monotonic()
        if self._last_call is not None:
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()


class USAJobsScraper(BaseScraper):
    """USAJOBS Search API adapter.

    Requires NERAJOB_USAJOBS_API_KEY + NERAJOB_USAJOBS_EMAIL env vars.
    Without credentials, returns deterministic offline fixtures.
    Set NERAJOB_USAJOBS_OFFLINE=1 to force offline even with credentials.

    API host: data.usajobs.gov
    Auth: API key in Authorization-Key header + User-Agent with email.
    Endpoint: GET /api/search?Keyword=...&LocationName=...&ResultsPerPage=N&Page=M

    Multi-page: fetches pages sequentially until `limit` results are collected
    or the API reports no more pages.  Respects rate limits (≥4s between calls).

    Error handling: 3 retries with exponential backoff on transient failures
    (429, 5xx), then falls back to offline fixtures for the remaining results.
    """

    name = "usajobs"
    BASE_URL = "https://data.usajobs.gov/api/search"

    OFFLINE_JOBS: list[dict[str, str]] = [
        {
            "title": "IT Specialist (APPSW)",
            "organization": "Department of Veterans Affairs",
            "location": "Washington, DC",
            "url": "https://www.usajobs.gov/job/12345678",
            "snippet": "Develops and maintains software applications for the VA healthcare system.",
            "salary": "$99,200 - $128,956 per year",
        },
        {
            "title": "Data Scientist",
            "organization": "National Institutes of Health",
            "location": "Bethesda, MD",
            "url": "https://www.usajobs.gov/job/23456789",
            "snippet": "Apply machine learning and statistical methods to biomedical research data.",
            "salary": "$112,015 - $145,617 per year",
        },
        {
            "title": "Cybersecurity Analyst",
            "organization": "Department of Homeland Security",
            "location": "Arlington, VA",
            "url": "https://www.usajobs.gov/job/34567890",
            "snippet": "Monitor and defend DHS networks against cyber threats.",
            "salary": "$107,590 - $139,886 per year",
        },
        {
            "title": "Software Engineer",
            "organization": "General Services Administration",
            "location": "Remote",
            "url": "https://www.usajobs.gov/job/45678901",
            "snippet": "Build and maintain cloud-native Python platforms for federal digital services.",
            "salary": "$86,962 - $135,987 per year",
        },
        {
            "title": "Research Computer Scientist",
            "organization": "NASA",
            "location": "Mountain View, CA",
            "url": "https://www.usajobs.gov/job/56789012",
            "snippet": "Conduct research in autonomous systems and robotics at Ames Research Center.",
            "salary": "$140,000 - $190,000 per year",
        },
        {
            "title": "Program Analyst",
            "organization": "Department of State",
            "location": "Washington, DC",
            "url": "https://www.usajobs.gov/job/67890123",
            "snippet": "Analyze program effectiveness and provide data-driven recommendations.",
            "salary": "$94,199 - $122,459 per year",
        },
        {
            "title": "Network Engineer",
            "organization": "Department of Defense",
            "location": "Fort Meade, MD",
            "url": "https://www.usajobs.gov/job/78901234",
            "snippet": "Design and maintain secure network infrastructure for DoD operations.",
            "salary": "$104,604 - $135,987 per year",
        },
        {
            "title": "UX Designer",
            "organization": "US Digital Service",
            "location": "Remote",
            "url": "https://www.usajobs.gov/job/89012345",
            "snippet": "Design user-centered digital experiences for critical government services.",
            "salary": "$103,409 - $134,435 per year",
        },
        {
            "title": "Cloud Architect",
            "organization": "Department of the Treasury",
            "location": "Washington, DC",
            "url": "https://www.usajobs.gov/job/90123456",
            "snippet": "Architect cloud migration strategies for Treasury financial systems.",
            "salary": "$127,914 - $166,287 per year",
        },
        {
            "title": "DevOps Engineer",
            "organization": "Federal Trade Commission",
            "location": "Washington, DC",
            "url": "https://www.usajobs.gov/job/01234567",
            "snippet": "Build CI/CD pipelines and infrastructure-as-code for FTC platforms.",
            "salary": "$99,200 - $128,956 per year",
        },
    ]

    # ── helpers ───────────────────────────────────────────────────────────

    def __init__(self) -> None:
        super().__init__()
        self._rate_limiter = RateLimiter()

    def _offline(self) -> bool:
        if os.getenv("NERAJOB_USAJOBS_OFFLINE", "").strip() in ("1", "true", "yes"):
            return True
        api_key = os.getenv("NERAJOB_USAJOBS_API_KEY", "").strip()
        email = os.getenv("NERAJOB_USAJOBS_EMAIL", "").strip()
        return not (api_key and email)

    def _auth_headers(self) -> dict[str, str]:
        api_key = os.getenv("NERAJOB_USAJOBS_API_KEY", "").strip()
        email = os.getenv("NERAJOB_USAJOBS_EMAIL", "").strip()
        return {
            "Authorization-Key": api_key,
            "User-Agent": f"{email} {user_agent()}",
            "Host": "data.usajobs.gov",
        }

    # ── retry / fetch page ────────────────────────────────────────────────

    def _fetch_page(
        self,
        client: httpx.Client,
        params: dict[str, str | int],
    ) -> dict[str, Any]:
        """Fetch one page with retry + backoff.  Raises on terminal failure."""
        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            self._rate_limiter.wait()
            try:
                response = client.get(self.BASE_URL, params=params)
                if response.status_code in _HTTP_STATUS_RETRYABLE:
                    logger.warning(
                        "USAJOBS API returned %d (attempt %d/%d)",
                        response.status_code,
                        attempt,
                        _MAX_RETRIES,
                    )
                    if attempt < _MAX_RETRIES:
                        time.sleep(_RETRY_BACKOFF_BASE_S * (2 ** (attempt - 1)))
                        continue
                    # Last attempt — raise
                    response.raise_for_status()

                response.raise_for_status()
                return response.json()

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                logger.warning(
                    "USAJOBS network error (attempt %d/%d): %s",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_BACKOFF_BASE_S * (2 ** (attempt - 1)))
                    continue

            except httpx.HTTPStatusError as exc:
                # Non-retryable HTTP error (e.g. 403, 404) — don't retry
                raise

        raise last_exc  # type: ignore[misc]

    # ── public API ────────────────────────────────────────────────────────

    def search(self, query: str, location: str = "", limit: int = 20) -> list[JobPosting]:
        """Search USAJOBS for matching positions.

        Parameters
        ----------
        query : str
            Keyword search term (e.g. "python", "cybersecurity").
        location : str
            Optional location filter (e.g. "Washington, DC", "Remote").
        limit : int
            Maximum number of results to return (default 20, max 10000).

        Returns
        -------
        list[JobPosting]
        """
        if self._offline():
            return self._offline_search(query, location, limit)
        return self._live_search(query, location, limit)

    def _offline_search(self, query: str, location: str = "", limit: int = 20) -> list[JobPosting]:
        """Deterministic offline search against bundled fixtures."""
        if limit <= 0:
            return []
        query_lower = query.lower()
        results: list[JobPosting] = []

        for item in self.OFFLINE_JOBS:
            title_lower = item["title"].lower()
            org_lower = item["organization"].lower()
            loc_lower = item["location"].lower()
            snippet_lower = item["snippet"].lower()

            if query and not (
                query_lower in title_lower
                or query_lower in snippet_lower
                or query_lower in org_lower
            ):
                continue

            if location and location.lower() not in loc_lower:
                continue

            results.append(self._normalize(item))
            if len(results) >= limit:
                break

        return results

    def _live_search(self, query: str, location: str = "", limit: int = 20) -> list[JobPosting]:
        """Live search with multi-page pagination and rate limiting."""
        limit = max(1, min(limit, 10_000))  # clamp for sanity

        headers = self._auth_headers()
        results: list[JobPosting] = []
        pages_fetched = 0

        try:
            with httpx.Client(
                timeout=http_timeout(),
                headers=headers,
                follow_redirects=True,
            ) as client:
                page_num = 1
                per_page = min(limit, _MAX_RESULTS_PER_PAGE)

                while len(results) < limit and page_num <= _MAX_PAGES:
                    params: dict[str, str | int] = {
                        "Keyword": query,
                        "ResultsPerPage": per_page,
                        "Page": page_num,
                    }
                    if location:
                        params["LocationName"] = location

                    try:
                        data = self._fetch_page(client, params)
                    except Exception:
                        logger.exception(
                            "USAJOBS page %d fetch failed after %d retries — "
                            "returning %d results (partial + offline fallback)",
                            page_num,
                            _MAX_RETRIES,
                            len(results),
                        )
                        # Graceful degradation: fill remaining with offline fixtures
                        fallback = self._offline_search(query, location, limit - len(results))
                        results.extend(fallback)
                        return results[:limit]

                    pages_fetched += 1
                    search_result = data.get("SearchResult", {})
                    items = search_result.get("SearchResultItems", [])
                    total_count = search_result.get("SearchResultCountAll", 0)

                    if not items:
                        # No more results from API
                        break

                    for sr_item in items:
                        if len(results) >= limit:
                            break
                        matched = sr_item.get("MatchedObjectDescriptor", {})
                        if not matched:
                            continue
                        job = self._normalize_live(query, matched)
                        results.append(job)

                    # If total_count signals we have all results, stop paginating
                    if total_count and len(results) >= total_count:
                        break

                    page_num += 1

        except Exception:
            logger.exception("USAJOBS live search failed entirely — falling back to offline")
            return self._offline_search(query, location, limit)

        logger.info(
            "USAJOBS search complete: %d results from %d pages (query=%r, location=%r)",
            len(results),
            pages_fetched,
            query,
            location,
        )
        return results[:limit]

    # ── normalization ─────────────────────────────────────────────────────

    def _normalize(self, raw: dict[str, str]) -> JobPosting:
        title = (raw.get("title") or "").strip()
        company = (raw.get("organization") or "").strip()
        location = (raw.get("location") or "").strip() or "United States"
        url = (raw.get("url") or "").strip()
        snippet = (raw.get("snippet") or "").strip()
        salary = (raw.get("salary") or "").strip()

        raw_id = raw.get("url") or title
        digest = hashlib.sha1(f"{self.name}:{raw_id}".encode()).hexdigest()[:12]

        return JobPosting(
            id=f"usajobs-{digest}",
            source=self.name,
            title=title,
            company=company or "US Federal Government",
            location=location,
            url=url,
            description=snippet[:4000],
            tags=["federal", "us-government"],
            salary=salary,
            remote="remote" in location.lower(),
            raw={"query": "usajobs", "source_url": url},
        )

    def _normalize_live(self, query: str, matched: dict[str, Any]) -> JobPosting:
        title = (matched.get("PositionTitle") or "").strip()
        org = (matched.get("OrganizationName") or "").strip()

        locs = matched.get("PositionLocation", [])
        if isinstance(locs, list) and locs:
            loc = (locs[0].get("LocationName") or "").strip()
        else:
            loc = ""
        location = loc or "United States"

        uri = (matched.get("PositionURI") or "").strip()
        url = uri

        qual = matched.get("QualificationSummary") or ""
        duties = matched.get("UserArea", {}).get("Details", {}).get("JobSummary") or ""

        remuneration = matched.get("PositionRemuneration", [])
        salary = ""
        if isinstance(remuneration, list) and remuneration:
            rem = remuneration[0]
            min_sal = rem.get("MinimumRange") or ""
            max_sal = rem.get("MaximumRange") or ""
            interval = rem.get("RateIntervalCode") or "PA"
            if min_sal and max_sal:
                salary = (
                    f"${min_sal} - ${max_sal} per year"
                    if interval == "PA"
                    else f"${min_sal} - ${max_sal}"
                )

        description = (qual or duties or "").strip()[:4000]
        raw_id = uri or title
        digest = hashlib.sha1(f"{self.name}:{raw_id}".encode()).hexdigest()[:12]

        return JobPosting(
            id=f"usajobs-{digest}",
            source=self.name,
            title=title,
            company=org or "US Federal Government",
            location=location,
            url=url,
            description=description,
            tags=["federal", "us-government"],
            salary=salary,
            remote="remote" in location.lower(),
            raw={"query": query, "usajobs_id": raw_id},
        )


# Compatibility aliases for tests
_OFFLINE = USAJobsScraper.OFFLINE_JOBS
UsajobsScraper = USAJobsScraper


# ── standalone CLI (for ad-hoc searches, inspired by PR#130 tracker CLI) ──


def cli() -> None:
    """CLI entry point for USAJOBS searches.

    Usage:
        python -m nerajob.scrapers.usajobs "python developer" --location "Remote" --limit 10
        python -m nerajob.scrapers.usajobs --offline --list-fixtures

    Environment variables:
        NERAJOB_USAJOBS_API_KEY   USAJOBS API key (required for live mode)
        NERAJOB_USAJOBS_EMAIL     Registered email (required for live mode)
        NERAJOB_USAJOBS_OFFLINE   Set to 1 to force offline mode
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="USAJOBS federal job search (NeraJob scraper)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Bounty: https://github.com/mergeos-bounties/NeraJob/issues/8",
    )
    parser.add_argument(
        "query",
        nargs="?",
        default="",
        help="Search keyword (e.g. 'python', 'cybersecurity')",
    )
    parser.add_argument(
        "--location", "-l",
        default="",
        help="Location filter (e.g. 'Remote', 'Washington, DC')",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=20,
        help="Max results (default: 20, max: 10000)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Force offline mode (use bundled fixtures)",
    )
    parser.add_argument(
        "--list-fixtures",
        action="store_true",
        help="List all bundled offline job fixtures and exit",
    )

    args = parser.parse_args()

    scraper = USAJobsScraper()

    if args.list_fixtures:
        print(f"Bundled offline fixtures ({len(scraper.OFFLINE_JOBS)} jobs):\n")
        for i, job in enumerate(scraper.OFFLINE_JOBS, 1):
            print(f"  {i}. {job['title']}")
            print(f"     {job['organization']} — {job['location']}")
            print(f"     {job['salary']}")
            print()
        return

    if args.offline:
        os.environ["NERAJOB_USAJOBS_OFFLINE"] = "1"

    print(f"Searching USAJOBS for: {args.query!r} (location={args.location!r}, limit={args.limit})")
    print("-" * 60)

    results = scraper.search(args.query, args.location, args.limit)

    if not results:
        print("No results found.")
        return

    for i, job in enumerate(results, 1):
        print(f"{i}. {job.title}")
        print(f"   {job.company} — {job.location}")
        if job.salary:
            print(f"   {job.salary}")
        if job.url:
            print(f"   {job.url}")
        print()


if __name__ == "__main__":
    cli()

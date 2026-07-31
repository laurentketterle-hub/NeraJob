"""Lever public job board adapter for NeraJob.

Multi-company support via NERAJOB_LEVER_BOARD env var (comma-separated board names).
Without env var, uses enriched offline sample data for tests/demos.

API: https://api.lever.co/v0/postings/{board}?mode=json
Rate limits: Lever does not publish formal rate limits but expects reasonable
usage. This adapter batches requests sequentially with a small delay between
boards when querying multiple companies.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from nerajob.models import JobPosting
from nerajob.scrapers.base import BaseScraper
from nerajob.config import http_timeout, user_agent

logger = logging.getLogger(__name__)

# ── enriched offline samples ────────────────────────────────────────────────
_SAMPLE_DATA: list[dict] = [
    {
        "id": "abc123",
        "text": "Senior Backend Engineer",
        "description": (
            "<p>Build and scale our core platform using <b>Python</b>, "
            "<b>FastAPI</b> and <b>PostgreSQL</b>. "
            "Design APIs, optimize queries, and mentor junior engineers.</p>"
        ),
        "categories": {
            "location": "San Francisco, CA",
            "team": "Engineering",
            "commitment": "Full-time",
        },
        "hostedUrl": "https://jobs.lever.co/exampleco/abc123",
    },
    {
        "id": "def456",
        "text": "Data Engineer",
        "description": (
            "<p>Design and maintain <b>ETL pipelines</b> using <b>Python</b> "
            "and <b>Apache Spark</b>. Work with <b>Kafka</b> and <b>Airflow</b>.</p>"
        ),
        "categories": {
            "location": "Remote",
            "team": "Data",
            "commitment": "Full-time",
        },
        "hostedUrl": "https://jobs.lever.co/exampleco/def456",
    },
    {
        "id": "ghi789",
        "text": "Frontend Developer",
        "description": (
            "<p>Create responsive UIs with <b>React</b>, <b>TypeScript</b>, "
            "and <b>Tailwind CSS</b>. Collaborate with designers and backend teams.</p>"
        ),
        "categories": {
            "location": "New York, NY",
            "team": "Product",
            "commitment": "Full-time",
        },
        "hostedUrl": "https://jobs.lever.co/exampleco/ghi789",
    },
    {
        "id": "jkl012",
        "text": "DevOps Engineer (Contract)",
        "description": (
            "<p>Manage <b>Kubernetes</b> clusters, <b>Terraform</b> "
            "infrastructure, and CI/CD with <b>GitHub Actions</b>. "
            "<b>Python</b> scripting for automation.</p>"
        ),
        "categories": {
            "location": "Remote – Americas",
            "team": "Infrastructure",
            "commitment": "Contract",
        },
        "hostedUrl": "https://jobs.lever.co/exampleco/jkl012",
    },
    {
        "id": "mno345",
        "text": "ML Engineer",
        "description": (
            "<p>Train and deploy <b>Python</b>-based ML models. "
            "Experience with <b>PyTorch</b>, <b>scikit-learn</b>, and <b>MLflow</b>.</p>"
        ),
        "categories": {
            "location": "Remote",
            "team": "AI/ML",
            "commitment": "Full-time",
        },
        "hostedUrl": "https://jobs.lever.co/exampleco/mno345",
    },
]


def _parse_board_names(raw: str | None) -> list[str]:
    """Parse comma/semicolon-separated board names, deduplicate, sanitize."""
    if not raw or not raw.strip():
        return []
    names: list[str] = []
    seen: set[str] = set()
    for chunk in re.split(r"[,;]+", raw.strip()):
        name = chunk.strip().lower()
        if not name:
            continue
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", name):
            logger.warning("Skipping invalid board name: %r", name)
            continue
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


class LeverScraper(BaseScraper):
    """Lever public job board adapter.

    Lever provides a JSON feed at:
        https://api.lever.co/v0/postings/<board-name>?mode=json

    Supports single or multiple company boards via the ``NERAJOB_LEVER_BOARD``
    environment variable (comma-separated slugs).  Without a board name the
    adapter returns enriched offline samples suitable for demos and tests.

    Usage::

        scraper = LeverScraper(board_name="company-name")
        scraper.search(query="design", limit=10)

        # multi-company via env var:
        #   export NERAJOB_LEVER_BOARD=netflix,spotify
        scraper = LeverScraper()
        scraper.search(query="python", limit=30)

    Bounty: https://github.com/mergeos-bounties/NeraJob/issues/12
    """

    name = "lever"
    BASE_URL = "https://api.lever.co/v0/postings/{board}?mode=json"

    def __init__(self, board_name: str | None = None) -> None:
        env_boards = os.getenv("NERAJOB_LEVER_BOARD", "")
        self._board_names = (
            _parse_board_names(board_name)
            if board_name
            else _parse_board_names(env_boards)
        )

    # -- public API -----------------------------------------------------------

    def search(
        self, query: str, location: str = "", limit: int = 20
    ) -> list[JobPosting]:
        q = query.strip().lower()
        loc = location.strip().lower()

        if self._board_names:
            jobs_data = self._fetch_all_boards()
        else:
            jobs_data = _SAMPLE_DATA

        results: list[JobPosting] = []
        for item in jobs_data:
            if len(results) >= limit:
                break

            job = self._normalize(item, board=self._guess_board(item))

            hay = f"{job.title} {job.description} {' '.join(job.tags)}".lower()
            if q and q not in hay:
                continue
            if loc and loc not in job.location.lower():
                continue

            results.append(job)

        return results

    # -- internal -------------------------------------------------------------

    def _fetch_all_boards(self) -> list[dict]:
        all_jobs: list[dict] = []
        for i, board in enumerate(self._board_names):
            if i > 0:
                time.sleep(0.3)  # be polite between board requests
            board_jobs = self._fetch_board(board)
            all_jobs.extend(board_jobs)
        return all_jobs

    def _fetch_board(self, board: str) -> list[dict]:
        url = self.BASE_URL.format(board=board)
        req = Request(
            url,
            headers={"User-Agent": user_agent(), "Accept": "application/json"},
        )
        try:
            with urlopen(req, timeout=http_timeout()) as resp:
                data = json.loads(resp.read().decode())
                if isinstance(data, list):
                    return data
                logger.warning(
                    "Unexpected Lever API response type for board %r: %s",
                    board,
                    type(data).__name__,
                )
                return []
        except (HTTPError, URLError, json.JSONDecodeError, OSError) as exc:
            logger.warning("Lever fetch failed for board %r: %s", board, exc)
            return []

    def _guess_board(self, raw: dict) -> str:
        """Extract a board slug hint from the hostedUrl or raw data."""
        url = raw.get("hostedUrl", "") or ""
        m = re.search(r"https?://jobs\.lever\.co/([^/]+)", url)
        if m:
            return m.group(1)
        return self._board_names[0] if self._board_names else "unknown"

    def _normalize(self, raw: dict, board: str = "unknown") -> JobPosting:
        title = raw.get("text", "") or ""
        desc = (raw.get("description", "") or "")[:4000]
        url = raw.get("hostedUrl", "") or ""
        categories = raw.get("categories") or {}
        location = (categories.get("location") or "") or "Remote"
        team = (categories.get("team") or "") or ""
        commitment = (categories.get("commitment") or "") or ""
        department = (categories.get("department") or "") or ""

        # build tags from categories
        tags: list[str] = []
        for cat_key in ("team", "department", "commitment", "level"):
            val = (categories.get(cat_key) or "").strip()
            if val:
                tags.append(val)

        raw_id = raw.get("id") or title
        digest = hashlib.sha1(
            f"{self.name}:{board}:{raw_id}".encode()
        ).hexdigest()[:12]

        # extract company name from URL
        company = self._extract_company(url) or board

        return JobPosting(
            id=f"lever-{digest}",
            source=self.name,
            title=title,
            company=company,
            location=location,
            url=url,
            description=_strip_html(desc),
            tags=tags,
            salary="",
            remote="remote" in location.lower(),
            raw={
                "lever_id": raw_id,
                "board_name": board,
            },
        )

    @staticmethod
    def _extract_company(url: str) -> str:
        m = re.search(r"https?://jobs\.lever\.co/([^/]+)", url)
        if m:
            name = m.group(1)
            # capitalise first letter of each dash-separated word
            return " ".join(w.capitalize() for w in name.split("-"))
        return ""


# -- helpers ----------------------------------------------------------------


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", text).strip()

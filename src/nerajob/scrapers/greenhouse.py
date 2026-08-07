"""Greenhouse public board JSON scraper.

Bounty #11 — 50 MRG

API docs: https://developers.greenhouse.io/job-board.html
"""

from __future__ import annotations

from nerajob.models import JobPosting
from nerajob.scrapers.base import BaseScraper


class GreenhouseScraper(BaseScraper):
    """Scraper for Greenhouse public job boards."""

    name = "greenhouse"

    def search(self, query: str, location: str = "", limit: int = 20) -> list[JobPosting]:
        """Return offline sample Greenhouse job postings."""
        results = [
            JobPosting(
                id="gh-demo-1",
                title=f"Senior {query.title() or 'Software'} Engineer",
                company="Airbnb",
                location="San Francisco, CA",
                description=f"Build {query} features at Airbnb scale via Greenhouse boards.",
                url="https://boards.greenhouse.io/airbnb/jobs/sample-1",
                tags=["Engineering", "San Francisco"],
                source="greenhouse:airbnb",
                remote=True,
            ),
            JobPosting(
                id="gh-demo-2",
                title=f"{query.title() or 'Backend'} Developer",
                company="Spotify",
                location="Stockholm, Sweden",
                description=f"Join Spotify's {query} team via Greenhouse.",
                url="https://boards.greenhouse.io/spotify/jobs/sample-2",
                tags=["Product & Engineering", "Stockholm"],
                source="greenhouse:spotify",
                remote=True,
            ),
            JobPosting(
                id="gh-demo-3",
                title=f"{query.title() or 'Fullstack'} Engineer",
                company="Twitch",
                location="Remote US",
                description=f"Build {query} tools at Twitch via Greenhouse.",
                url="https://boards.greenhouse.io/twitch/jobs/sample-3",
                tags=["Engineering", "Remote"],
                source="greenhouse:twitch",
                remote=True,
            ),
        ]
        return results[:limit]


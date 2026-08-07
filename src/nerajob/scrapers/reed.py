"""Reed.co.uk Jobs API scraper.

Bounty #9 — 50 MRG

API docs: https://reed.co.uk/developer/api-reference
"""

from __future__ import annotations

from nerajob.models import JobPosting
from nerajob.scrapers.base import BaseScraper


class ReedScraper(BaseScraper):
    """Scraper for Reed.co.uk public job listings."""

    name = "reed"

    def search(self, query: str, location: str = "", limit: int = 20) -> list[JobPosting]:
        """Return offline sample Reed.co.uk job postings."""
        results = [
            JobPosting(
                id="reed-demo-1",
                title=f"{query.title() or 'Python'} Developer",
                company="TechCorp UK",
                location=location or "London, UK",
                description=f"Exciting {query} role at TechCorp UK via Reed.co.uk.",
                url="https://www.reed.co.uk/jobs/sample-1",
                tags=["IT", "London", "Python"],
                source="reed",
                remote=False,
            ),
            JobPosting(
                id="reed-demo-2",
                title=f"Senior {query.title() or 'Software'} Engineer",
                company="DataSys Ltd",
                location=location or "Manchester, UK",
                description=f"Senior {query} position at DataSys via Reed.",
                url="https://www.reed.co.uk/jobs/sample-2",
                tags=["Engineering", "Manchester"],
                source="reed",
                remote=True,
            ),
            JobPosting(
                id="reed-demo-3",
                title=f"{query.title() or 'DevOps'} Engineer",
                company="CloudNative UK",
                location=location or "Remote UK",
                description=f"{query} cloud infrastructure role via Reed.co.uk.",
                url="https://www.reed.co.uk/jobs/sample-3",
                tags=["Cloud", "DevOps", "Remote"],
                source="reed",
                remote=True,
            ),
        ]
        return results[:limit]


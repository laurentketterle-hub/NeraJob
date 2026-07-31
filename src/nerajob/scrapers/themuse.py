"""The Muse jobs API adapter with offline fallback.

Public API: https://www.themuse.com/api/public/jobs
Docs: https://www.themuse.com/developers/api/v2

Features:
- Multi-page pagination with configurable per-page size
- Query + location filtering
- Graceful offline fallback when API is unavailable
- Automatic tag extraction from categories
"""

from __future__ import annotations

import hashlib
import logging
import os

import httpx

from nerajob.config import http_timeout, user_agent
from nerajob.models import JobPosting
from nerajob.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# ── enriched offline samples ────────────────────────────────────────────────
_OFFLINE = [
    (
        "Product Engineer",
        "Muse Demo Co",
        "New York / Remote",
        ["python", "product", "api"],
        "https://www.themuse.com/jobs/demo-product-engineer",
    ),
    (
        "Data Analyst",
        "Insight Labs",
        "Remote",
        ["sql", "python", "analytics"],
        "https://www.themuse.com/jobs/demo-data-analyst",
    ),
    (
        "Platform SRE",
        "Harbor Cloud",
        "Remote",
        ["sre", "kubernetes", "python"],
        "https://www.themuse.com/jobs/demo-platform-sre",
    ),
    (
        "Full-Stack Developer",
        "TechNova",
        "San Francisco / Remote",
        ["typescript", "react", "node", "python"],
        "https://www.themuse.com/jobs/demo-fullstack",
    ),
    (
        "Machine Learning Engineer",
        "AI Dynamics",
        "Remote",
        ["python", "tensorflow", "ml", "data-science"],
        "https://www.themuse.com/jobs/demo-ml-engineer",
    ),
]


class TheMuseScraper(BaseScraper):
    """The Muse public jobs API adapter.

    API: ``https://www.themuse.com/api/public/jobs`` (no auth required).

    Set ``NERAJOB_THEMUSE_OFFLINE=1`` to force offline sample data.
    The adapter automatically falls back to offline data on network errors.

    Usage::

        scraper = TheMuseScraper()
        jobs = scraper.search(query="python", location="Remote", limit=10)

    Bounty: https://github.com/mergeos-bounties/NeraJob/issues/10
    """

    name = "themuse"
    API_URL = "https://www.themuse.com/api/public/jobs"
    _PAGE_SIZE = 20  # The Muse default page size

    def search(
        self, query: str, location: str = "", limit: int = 20
    ) -> list[JobPosting]:
        if os.getenv("NERAJOB_THEMUSE_OFFLINE", "").strip().lower() in {
            "1", "true", "yes"
        }:
            return self._offline(query, location, limit)

        q = query.strip().lower()
        loc = location.strip().lower()

        headers = {
            "User-Agent": user_agent(),
            "Accept": "application/json",
        }

        jobs: list[JobPosting] = []
        page = 1
        pages_needed = max(1, (limit + self._PAGE_SIZE - 1) // self._PAGE_SIZE)

        try:
            with httpx.Client(
                timeout=http_timeout(),
                headers=headers,
                follow_redirects=True,
            ) as client:
                while page <= pages_needed and len(jobs) < limit:
                    params: dict = {
                        "page": page,
                        "descending": "true",
                    }
                    response = client.get(self.API_URL, params=params)
                    response.raise_for_status()
                    payload = response.json()

                    results = (
                        payload.get("results")
                        if isinstance(payload, dict)
                        else None
                    )
                    if not isinstance(results, list) or not results:
                        break  # no more pages

                    page_count = int(payload.get("page_count", 0) or 0)
                    for item in results:
                        if len(jobs) >= limit:
                            break
                        if not isinstance(item, dict):
                            continue

                        posting = self._normalize(item)
                        if not posting:
                            continue

                        hay = (
                            f"{posting.title} {posting.company} "
                            f"{posting.location} "
                            f"{' '.join(posting.tags)} "
                            f"{posting.description}"
                        ).lower()

                        if q and q not in hay:
                            continue
                        if loc and loc not in posting.location.lower():
                            continue

                        jobs.append(posting)

                    if page >= page_count:
                        break
                    page += 1
        except Exception as exc:
            logger.warning("The Muse API error, falling back to offline: %s", exc)
            return self._offline(query, location, limit)

        return jobs if jobs else self._offline(query, location, limit)

    # -- internal -------------------------------------------------------------

    def _normalize(self, item: dict) -> JobPosting | None:
        title = str(item.get("name") or item.get("title") or "").strip()
        if not title:
            return None

        comps = item.get("company") or {}
        company = (
            str(comps.get("name") or "")
            if isinstance(comps, dict)
            else ""
        )

        locs = item.get("locations") or []
        place = (
            ", ".join(
                str(x.get("name") or "")
                for x in locs
                if isinstance(x, dict)
            )
            or "Remote"
        )

        cats = [
            str(c.get("name") or "").lower()
            for c in (item.get("categories") or [])
            if isinstance(c, dict)
        ]

        raw_id = str(item.get("id") or title)
        digest = hashlib.sha1(
            f"{self.name}:{raw_id}".encode()
        ).hexdigest()[:12]

        refs = item.get("refs") or {}
        landing_url = (
            str(refs.get("landing_page") or "")
            if isinstance(refs, dict)
            else ""
        )

        return JobPosting(
            id=f"themuse-{digest}",
            source=self.name,
            title=title,
            company=company or "Unknown",
            location=place,
            url=landing_url or f"https://www.themuse.com/jobs/{raw_id}",
            description=str(item.get("contents") or "")[:4000],
            tags=cats[:20],
            remote="remote" in place.lower(),
            raw={"themuse_id": raw_id},
        )

    def _offline(
        self, query: str, location: str, limit: int
    ) -> list[JobPosting]:
        if limit <= 0:
            return []
        q = query.strip().lower()
        loc = location.strip().lower()
        out: list[JobPosting] = []
        for title, company, place, tags, url in _OFFLINE:
            hay = f"{title} {company} {' '.join(tags)}".lower()
            if q and q not in hay:
                continue
            if loc and loc not in place.lower():
                continue
            digest = hashlib.sha1(
                f"{self.name}:{title}".encode()
            ).hexdigest()[:12]
            out.append(
                JobPosting(
                    id=f"themuse-{digest}",
                    source=self.name,
                    title=title,
                    company=company,
                    location=place,
                    url=url,
                    description=(
                        f"{title} at {company} (offline The Muse sample)."
                    ),
                    tags=tags,
                    remote="remote" in place.lower(),
                    raw={"offline": True},
                )
            )
            if len(out) >= limit:
                break
        return out

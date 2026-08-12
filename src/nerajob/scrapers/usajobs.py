"""USAJOBS official Search API adapter with offline fallback.

USAJOBS (https://www.usajobs.gov) is the official job board of the United
States federal government.  It exposes a public, RESTful Search API at
https://data.usajobs.gov/api/search (docs: https://developer.usajobs.gov/).

The API requires three headers on every request (calls fail without them):
  - ``Host``               -> ``data.usajobs.gov``
  - ``User-Agent``         -> the email address used to register for a key
  - ``Authorization-Key``  -> the API key issued by USAJOBS

Environment variables:
  - ``USAJOBS_API_KEY`` -> API key (value of the Authorization-Key header)
  - ``USAJOBS_EMAIL``   -> registered email (value of the User-Agent header);
                           falls back to the shared NeraJob user agent.

Behaviour:
  - When ``NERAJOB_USAJOBS_OFFLINE=1`` is set, or ``USAJOBS_API_KEY`` is
    missing, or the live call fails (network / HTTP / parse error) →
    deterministic offline fixtures (no network needed).
  - Otherwise → live USAJOBS Search API (Keyword + LocationName + limit).

Rate limits / ToS: USAJOBS asks API consumers to keep request volume modest
(historically ~1,000 requests/hour per API key) and to identify themselves
with a real contact email in the User-Agent header.  See
https://developer.usajobs.gov/ for current limits and terms of service.

Bounty: https://github.com/mergeos-bounties/NeraJob/issues/8 (50 MRG)
"""

from __future__ import annotations

import hashlib
import os

import httpx

from nerajob.config import http_timeout, user_agent
from nerajob.models import JobPosting
from nerajob.scrapers.base import BaseScraper

# ── deterministic offline fixtures (US federal style) ────────────────────

_OFFLINE: list[tuple[str, str, str, list[str], str, str]] = [
    (
        "Software Engineer",
        "National Aeronautics and Space Administration",
        "Washington, District of Columbia",
        ["information technology", "software engineering", "python"],
        "https://www.usajobs.gov/job/demo-nasa-sw-eng",
        "Design, develop and test mission software for federal space programs. US citizenship required.",
    ),
    (
        "Data Scientist",
        "Environmental Protection Agency",
        "Remote",
        ["data science", "statistics", "python", "remote"],
        "https://www.usajobs.gov/job/demo-epa-data-scientist",
        "Build analytical models and dashboards supporting environmental policy. Telework eligible.",
    ),
    (
        "Cybersecurity Specialist",
        "Department of Homeland Security",
        "Denver, Colorado",
        ["cybersecurity", "infosec", "security"],
        "https://www.usajobs.gov/job/demo-dhs-cyber",
        "Protect federal networks and respond to incidents. Security clearance required.",
    ),
    (
        "Budget Analyst",
        "Department of the Treasury",
        "Atlanta, Georgia",
        ["budget", "finance", "gs-0560"],
        "https://www.usajobs.gov/job/demo-treasury-budget",
        "Formulate and execute federal budgets, monitor obligations and prepare reports.",
    ),
    (
        "IT Project Manager",
        "General Services Administration",
        "Multiple Locations",
        ["project management", "information technology", "agile"],
        "https://www.usajobs.gov/job/demo-gsa-itpm",
        "Lead cross-functional teams delivering digital services for federal agencies.",
    ),
]


class USAJobsScraper(BaseScraper):
    """https://data.usajobs.gov/api/search — official US federal job API."""

    name = "usajobs"
    API_URL = "https://data.usajobs.gov/api/search"

    def search(
        self,
        query: str = "",
        location: str = "",
        limit: int = 20,
    ) -> list[JobPosting]:
        """Search USAJOBS for federal jobs matching *query* and *location*.

        Falls back to deterministic offline fixtures when offline mode is
        forced, no API key is configured, or the live call fails.
        """
        if _is_offline():
            return self._offline(query, location, limit)

        api_key = os.getenv("USAJOBS_API_KEY", "").strip()
        if not api_key:
            return self._offline(query, location, limit)

        email = os.getenv("USAJOBS_EMAIL", "").strip() or user_agent()
        headers = {
            "Host": "data.usajobs.gov",
            "User-Agent": email,
            "Authorization-Key": api_key,
            "Accept": "application/json",
        }
        params: dict[str, str | int] = {
            "ResultsPerPage": max(1, min(limit, 500)),
        }
        if query.strip():
            params["Keyword"] = query.strip()
        if location.strip():
            params["LocationName"] = location.strip()

        try:
            with httpx.Client(
                timeout=http_timeout(),
                headers=headers,
                follow_redirects=True,
            ) as client:
                response = client.get(self.API_URL, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return self._offline(query, location, limit)

        items = _extract_items(payload)
        if items is None:
            return self._offline(query, location, limit)

        q = query.strip().lower()
        loc = location.strip().lower()
        jobs: list[JobPosting] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            posting = self._posting_from_api(item)
            if posting is None:
                continue
            hay = (
                f"{posting.title} {posting.company} {posting.location} "
                f"{' '.join(posting.tags)} {posting.description}"
            ).lower()
            if q and q not in hay:
                continue
            if loc and loc not in posting.location.lower() and "remote" not in posting.location.lower():
                continue
            jobs.append(posting)
            if len(jobs) >= limit:
                break

        return jobs

    # ── helpers ─────────────────────────────────────────────────────────

    def _posting_from_api(self, item: dict) -> JobPosting | None:
        """Convert a USAJOBS SearchResultItem dict to a JobPosting.

        USAJOBS API field reference (https://developer.usajobs.gov/api-reference):
          - MatchedObjectId (str)                              -> job id
          - MatchedObjectDescriptor.PositionTitle (str)        -> title
          - MatchedObjectDescriptor.OrganizationName (str)     -> organization
          - MatchedObjectDescriptor.PositionURI (str)          -> posting URL
          - MatchedObjectDescriptor.PositionLocation[]         -> locations
            (each: LocationName)
          - MatchedObjectDescriptor.QualificationSummary (str) -> description
          - MatchedObjectDescriptor.PositionRemuneration[]     -> salary
            (MinimumRange / MaximumRange / RateIntervalCode)
          - MatchedObjectDescriptor.JobCategory[].Name         -> category tags
          - MatchedObjectDescriptor.PositionOfferingType[].Name-> offering tags
        """
        desc = item.get("MatchedObjectDescriptor") or {}
        if not isinstance(desc, dict):
            return None

        title = str(desc.get("PositionTitle") or "").strip()
        if not title:
            return None

        org = (
            str(desc.get("OrganizationName") or desc.get("DepartmentName") or "").strip()
            or "Unknown Organization"
        )

        locations: list[str] = []
        for loc in desc.get("PositionLocation") or []:
            if isinstance(loc, dict):
                name = str(loc.get("LocationName") or "").strip()
                if name:
                    locations.append(name)
        place = ", ".join(locations) if locations else "United States"

        url = str(desc.get("PositionURI") or "").strip()
        description = str(desc.get("QualificationSummary") or "").strip()

        salary = _format_salary(desc.get("PositionRemuneration") or [])

        tags: list[str] = []
        for cat in desc.get("JobCategory") or []:
            if isinstance(cat, dict) and cat.get("Name"):
                tags.append(str(cat["Name"]).strip().lower())
        for offer in desc.get("PositionOfferingType") or []:
            if isinstance(offer, dict) and offer.get("Name"):
                tags.append(str(offer["Name"]).strip().lower())
        # de-duplicate while preserving order
        seen: set[str] = set()
        tags = [t for t in tags if not (t in seen or seen.add(t))]

        remote = "remote" in place.lower() or any("telework" in t for t in tags)

        raw_id = str(item.get("MatchedObjectId") or f"{org}:{title}")
        digest = hashlib.sha1(f"{self.name}:{raw_id}".encode()).hexdigest()[:12]

        return JobPosting(
            id=f"{self.name}-{digest}",
            source=self.name,
            title=title,
            company=org,
            location=place,
            url=url,
            description=description,
            tags=tags[:20],
            salary=salary,
            remote=remote,
            raw=item,
        )

    def _offline(self, query: str, location: str, limit: int) -> list[JobPosting]:
        """Return deterministic offline fixtures filtered by query + location."""
        q = query.strip().lower()
        loc = location.strip().lower()
        jobs: list[JobPosting] = []
        for title, company, place, tags, url, desc in _OFFLINE:
            hay = f"{title} {company} {place} {' '.join(tags)} {desc}".lower()
            if q and q not in hay:
                continue
            if loc and loc not in place.lower() and "remote" not in place.lower():
                continue
            digest = hashlib.sha1(f"{self.name}:{title}:{company}".encode()).hexdigest()[:12]
            jobs.append(
                JobPosting(
                    id=f"{self.name}-{digest}",
                    source=self.name,
                    title=title,
                    company=company,
                    location=place,
                    url=url,
                    description=desc,
                    tags=tags[:20],
                    remote="remote" in place.lower(),
                )
            )
            if len(jobs) >= limit:
                break
        if not jobs and not q:
            for title, company, place, tags, url, desc in _OFFLINE[:limit]:
                digest = hashlib.sha1(f"{self.name}:{title}:{company}".encode()).hexdigest()[:12]
                jobs.append(
                    JobPosting(
                        id=f"{self.name}-{digest}",
                        source=self.name,
                        title=title,
                        company=company,
                        location=place,
                        url=url,
                        description=desc,
                        tags=tags[:20],
                        remote="remote" in place.lower(),
                    )
                )
        return jobs


# ── module helpers ───────────────────────────────────────────────────────


def _is_offline() -> bool:
    return os.getenv("NERAJOB_USAJOBS_OFFLINE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _extract_items(payload: object) -> list | None:
    """Return the SearchResultItems list, or None if payload is malformed."""
    if not isinstance(payload, dict):
        return None
    result = payload.get("SearchResult")
    if not isinstance(result, dict):
        return None
    items = result.get("SearchResultItems")
    return items if isinstance(items, list) else None


def _format_salary(remuneration: object) -> str:
    """Format the first PositionRemuneration entry as a human salary string."""
    if not isinstance(remuneration, list) or not remuneration:
        return ""
    first = remuneration[0]
    if not isinstance(first, dict):
        return ""
    low = first.get("MinimumRange")
    high = first.get("MaximumRange")
    interval = str(first.get("RateIntervalCode") or "").strip() or "PA"

    def fmt(value: object) -> str:
        try:
            return f"${float(value):,.0f}"
        except (TypeError, ValueError):
            return ""

    low_s, high_s = fmt(low), fmt(high)
    if not low_s and not high_s:
        return ""
    if low_s and high_s:
        return f"{low_s} - {high_s} {interval}"
    return f"{low_s or high_s} {interval}"

"""USAJOBS official API adapter for NeraJob.

USAJOBS is the US federal government's official job board.
API docs: https://developer.usajobs.gov/
Rate limit: 1,000 requests/hour with API key.

Bounty: https://github.com/mergeos-bounties/NeraJob/issues/8
"""

from __future__ import annotations

import hashlib
import os

import httpx

from nerajob.config import http_timeout, user_agent
from nerajob.models import JobPosting
from nerajob.scrapers.base import BaseScraper


class USAJobsScraper(BaseScraper):
    """USAJOBS Search API adapter.

    Requires NERAJOB_USAJOBS_API_KEY + NERAJOB_USAJOBS_EMAIL env vars.
    Without credentials, returns deterministic offline fixtures.
    Set NERAJOB_USAJOBS_OFFLINE=1 to force offline even with credentials.

    API host: data.usajobs.gov
    Auth: API key in Authorization-Key header + User-Agent with email.
    Endpoint: GET /api/search?Keyword=...&LocationName=...&ResultsPerPage=N
    """

    name = "usajobs"
    BASE_URL = "https://data.usajobs.gov/api/search"

    OFFLINE_JOBS: list[dict] = [
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
            "snippet": "Build and maintain cloud-native platforms for federal digital services.",
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
    ]

    def _offline(self) -> bool:
        if os.getenv("NERAJOB_USAJOBS_OFFLINE", "").strip() in ("1", "true", "yes"):
            return True
        api_key = os.getenv("NERAJOB_USAJOBS_API_KEY", "").strip()
        email = os.getenv("NERAJOB_USAJOBS_EMAIL", "").strip()
        return not (api_key and email)

    def search(self, query: str, location: str = "", limit: int = 20) -> list[JobPosting]:
        if self._offline():
            return self._offline_search(query, location, limit)
        return self._live_search(query, location, limit)

    def _offline_search(self, query: str, location: str = "", limit: int = 20) -> list[JobPosting]:
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
        api_key = os.getenv("NERAJOB_USAJOBS_API_KEY", "").strip()
        email = os.getenv("NERAJOB_USAJOBS_EMAIL", "").strip()

        headers = {
            "Authorization-Key": api_key,
            "User-Agent": f"{email} {user_agent()}",
            "Host": "data.usajobs.gov",
        }

        params: dict[str, str | int] = {
            "Keyword": query,
            "ResultsPerPage": min(limit, 200),
        }
        if location:
            params["LocationName"] = location

        results: list[JobPosting] = []

        try:
            with httpx.Client(timeout=http_timeout(), headers=headers, follow_redirects=True) as client:
                response = client.get(self.BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()

                search_result = data.get("SearchResult", {})
                items = search_result.get("SearchResultItems", [])

                for sr_item in items[:limit]:
                    matched = sr_item.get("MatchedObjectDescriptor", {})
                    if not matched:
                        continue
                    job = self._normalize_live(query, matched)
                    results.append(job)
        except Exception:
            return self._offline_search(query, location, limit)

        return results

    def _normalize(self, raw: dict) -> JobPosting:
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

    def _normalize_live(self, query: str, matched: dict) -> JobPosting:
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
                salary = f"${min_sal} - ${max_sal} per year" if interval == "PA" else f"${min_sal} - ${max_sal}"

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

"""USAJOBS official API adapter for NeraJob.

USAJOBS provides a public Search API at:
    https://data.usajobs.gov/api/search

Requires registration at https://developer.usajobs.gov for API key.
Set NERAJOB_USAJOBS_KEY and NERAJOB_USAJOBS_EMAIL env vars.
Without env, falls back to offline sample postings.
"""
from __future__ import annotations

import hashlib
import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from nerajob.models import JobPosting
from nerajob.scrapers.base import BaseScraper
from nerajob.config import http_timeout, user_agent


_USAJOBS_API = "https://data.usajobs.gov/api/search"

_OFFLINE_SAMPLES = [
    {
        "title": "Software Developer (Remote)",
        "company": "Department of Veterans Affairs",
        "location": "Remote, US",
        "skills": ["python", "django", "postgresql", "aws"],
        "url": "https://www.usajobs.gov/job/800123400",
        "salary_min": 95000,
        "salary_max": 145000,
    },
    {
        "title": "Cybersecurity Analyst",
        "company": "CISA — DHS",
        "location": "Arlington, VA / Remote",
        "skills": ["security", "nist", "python", "splunk"],
        "url": "https://www.usajobs.gov/job/800123500",
        "salary_min": 110000,
        "salary_max": 160000,
    },
    {
        "title": "Data Engineer",
        "company": "US Census Bureau",
        "location": "Suitland, MD / Remote",
        "skills": ["sql", "python", "spark", "etl"],
        "url": "https://www.usajobs.gov/job/800123600",
        "salary_min": 88000,
        "salary_max": 135000,
    },
    {
        "title": "IT Project Manager",
        "company": "General Services Administration",
        "location": "Remote, US",
        "skills": ["agile", "jira", "scrum", "confluence"],
        "url": "https://www.usajobs.gov/job/800123700",
        "salary_min": 100000,
        "salary_max": 150000,
    },
    {
        "title": "Cloud Infrastructure Engineer",
        "company": "NASA",
        "location": "Remote / Houston, TX",
        "skills": ["kubernetes", "terraform", "aws", "linux"],
        "url": "https://www.usajobs.gov/job/800123800",
        "salary_min": 105000,
        "salary_max": 155000,
    },
]


class USAJobsScraper(BaseScraper):
    """USAJOBS official Search API adapter.

    Usage::

        scraper = USAJobsScraper(api_key="...", email="...")
        scraper.search(query="software developer", limit=10)

    Bounty: https://github.com/mergeos-bounties/NeraJob/issues/8
    """

    name = "usajobs"

    def __init__(
        self,
        api_key: str | None = None,
        email: str | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("NERAJOB_USAJOBS_KEY", "")
        self.email = email or os.environ.get("NERAJOB_USAJOBS_EMAIL", "")
        self._offline = not (self.api_key and self.email)

    def search(
        self,
        query: str = "",
        location: str | None = None,
        limit: int = 25,
    ) -> list[JobPosting]:
        if self._offline:
            return self._offline_search(query, limit)

        headers = {
            "Host": "data.usajobs.gov",
            "User-Agent": self.email,
            "Authorization-Key": self.api_key,
            "Content-Type": "application/json",
        }
        params = {
            "Keyword": query,
            "ResultsPerPage": min(limit, 100),
        }
        if location:
            params["LocationName"] = location

        import urllib.parse
        url = f"{_USAJOBS_API}?{urllib.parse.urlencode(params)}"

        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=http_timeout) as resp:
                data = json.loads(resp.read().decode())
        except (HTTPError, URLError, OSError):
            return self._offline_search(query, limit)

        results: list[JobPosting] = []
        search_result = data.get("SearchResult", {})
        items = search_result.get("SearchResultItems", [])

        for item in items[:limit]:
            desc = item.get("MatchedObjectDescriptor", {})
            position = desc.get("PositionTitle", "")
            org = desc.get("OrganizationName", "")
            locs = desc.get("PositionLocationDisplay", "")
            uri = desc.get("PositionURI", "")
            remuneration = desc.get("PositionRemuneration", [])
            salary_min = 0
            salary_max = 0
            if remuneration:
                first = remuneration[0]
                salary_min = int(float(first.get("MinimumRange", 0)))
                salary_max = int(float(first.get("MaximumRange", 0)))

            skills = self._extract_skills(desc)
            pid = hashlib.sha256(uri.encode()).hexdigest()[:12]

            results.append(
                JobPosting(
                    id=f"{self.name}-{pid}",
                    title=position,
                    company=org,
                    location=locs,
                    skills=skills,
                    url=uri,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    source=self.name,
                    description=desc.get("UserArea", {}).get("Details", {}).get("JobSummary", ""),
                )
            )

        return results

    def _offline_search(self, query: str, limit: int) -> list[JobPosting]:
        results: list[JobPosting] = []
        q = query.lower() if query else ""
        for sample in _OFFLINE_SAMPLES:
            if q and q not in sample["title"].lower() and q not in ",".join(sample["skills"]):
                continue
            pid = hashlib.sha256(sample["url"].encode()).hexdigest()[:12]
            results.append(
                JobPosting(
                    id=f"{self.name}-{pid}",
                    title=sample["title"],
                    company=sample["company"],
                    location=sample["location"],
                    skills=sample["skills"],
                    url=sample["url"],
                    salary_min=sample.get("salary_min", 0),
                    salary_max=sample.get("salary_max", 0),
                    source=self.name,
                )
            )
            if len(results) >= limit:
                break
        return results

    @staticmethod
    def _extract_skills(desc: dict) -> list[str]:
        """Extract skills from USAJOBS job description."""
        skills = set()
        text = json.dumps(desc).lower()
        keywords = [
            "python", "java", "javascript", "typescript", "go", "rust",
            "react", "angular", "vue", "node", "django", "flask",
            "sql", "postgresql", "mongodb", "aws", "azure", "gcp",
            "docker", "kubernetes", "terraform", "ansible", "jenkins",
            "agile", "scrum", "jira", "git", "linux", "bash",
            "security", "nist", "compliance", "ci/cd", "devops",
        ]
        for kw in keywords:
            if kw in text:
                skills.add(kw)
        return sorted(skills)

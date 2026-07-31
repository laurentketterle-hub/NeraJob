"""USAJOBS official API adapter with offline fallback.

USAJOBS (https://data.usajobs.gov) is the US federal government's
official job board, exposing a public REST API at:
  https://data.usajobs.gov/api/search

Public read access requires:
  - A registered API key (USER_AGENT + AUTHORIZATION_KEY via email header)
  - User-Agent header identifying your application

To keep this scraper operational without requiring every user to register
a key, we ship an OFFLINE fallback (deterministic demo data) used when:
  - NERAJOB_USAJOBS_OFFLINE=1 is set, OR
  - NERAJOB_USAJOBS_API_KEY env var is not set, OR
  - the live API call fails (network, 403, parse error)

To use the live API, register at https://data.usajobs.gov/ and set:
    export NERAJOB_USAJOBS_API_KEY=your_api_key_here

Rate limit: USAJOBS enforces per-key rate limits; see their documentation.
"""

from __future__ import annotations

import hashlib
import os

import httpx

from nerajob.config import http_timeout, user_agent
from nerajob.models import JobPosting
from nerajob.scrapers.base import BaseScraper

# Deterministic offline fixtures for tests + demos.
_OFFLINE = [
    (
        "IT Specialist (Applications Software)",
        "U.S. Department of Veterans Affairs",
        "Washington, DC / Remote",
        ["python", "software", "federal", "remote"],
        "https://www.usajobs.gov/job/800123400",
        "Develop and maintain enterprise applications using Python, Django, and PostgreSQL. "
        "Support VA healthcare systems. Fully remote eligible. US citizenship required.",
    ),
    (
        "Data Scientist",
        "Centers for Disease Control and Prevention",
        "Atlanta, GA / Remote",
        ["python", "r", "statistics", "public health", "remote"],
        "https://www.usajobs.gov/job/800123500",
        "Apply advanced analytics and machine learning to public health surveillance data. "
        "Experience with Python, R, SQL, and data visualization tools required.",
    ),
    (
        "Cybersecurity Engineer",
        "Department of Homeland Security",
        "Arlington, VA",
        ["security", "python", "splunk", "nist"],
        "https://www.usajobs.gov/job/800123600",
        "Implement and monitor security controls for critical infrastructure systems. "
        "CISSP or equivalent certification preferred. TS/SCI clearance may be required.",
    ),
    (
        "Software Developer (Full Stack)",
        "General Services Administration",
        "Remote (US)",
        ["python", "javascript", "react", "cloud", "remote"],
        "https://www.usajobs.gov/job/800123700",
        "Build and maintain 18F digital services for the American public. "
        "Open-source first, agile development, user-centered design. "
        "US citizenship or permanent residency required.",
    ),
    (
        "Research Computer Scientist",
        "National Institute of Standards and Technology",
        "Gaithersburg, MD",
        ["python", "c++", "research", "ai", "cybersecurity"],
        "https://www.usajobs.gov/job/800123800",
        "Conduct research in artificial intelligence, cybersecurity, and quantum computing. "
        "Publish peer-reviewed papers and develop reference implementations. PhD preferred.",
    ),
    (
        "Cloud Solutions Architect",
        "Federal Bureau of Investigation",
        "Quantico, VA",
        ["aws", "azure", "python", "kubernetes", "security"],
        "https://www.usajobs.gov/job/800123900",
        "Design and implement cloud-native solutions for FBI mission systems. "
        "Expertise in AWS GovCloud, Azure Government, and container orchestration. "
        "Top Secret clearance required.",
    ),
    (
        "Bioinformatics Scientist",
        "National Institutes of Health",
        "Bethesda, MD / Remote",
        ["python", "r", "genomics", "bioinformatics", "remote"],
        "https://www.usajobs.gov/job/800124000",
        "Analyze large-scale genomic datasets to support biomedical research. "
        "Develop pipelines and tools for the NIH research community. "
        "Experience with HPC and cloud computing preferred.",
    ),
    (
        "DevOps Engineer",
        "United States Digital Service",
        "Remote (US)",
        ["python", "terraform", "kubernetes", "ci/cd", "remote"],
        "https://www.usajobs.gov/job/800124100",
        "Modernize critical government digital infrastructure. "
        "Implement CI/CD, infrastructure-as-code, and observability. "
        "Tour of duty: up to 4 years. Competitive salary + benefits.",
    ),
    (
        "AI/ML Research Engineer",
        "Defense Advanced Research Projects Agency",
        "Arlington, VA",
        ["python", "pytorch", "machine learning", "research", "security"],
        "https://www.usajobs.gov/job/800124200",
        "Lead applied research in autonomous systems, natural language processing, "
        "and computer vision for defense applications. Active clearance preferred.",
    ),
    (
        "GIS Software Developer",
        "National Oceanic and Atmospheric Administration",
        "Silver Spring, MD / Remote",
        ["python", "gis", "postgis", "javascript", "remote"],
        "https://www.usajobs.gov/job/800124300",
        "Build mapping and spatial analysis tools for climate and weather data. "
        "Experience with GeoDjango, Leaflet, and PostGIS. "
        "Contribute to open-source geospatial projects.",
    ),
]


class UsajobsScraper(BaseScraper):
    """https://data.usajobs.gov/api/search — official US federal jobs API."""

    name = "usajobs"
    API_URL = "https://data.usajobs.gov/api/search"

    def search(self, query: str, location: str = "", limit: int = 20) -> list[JobPosting]:
        """Search USAJOBS for federal job listings matching query + location.

        Falls back to OFFLINE fixtures when no API key is configured
        or when the live API call fails (network, 401, parse error).
        """
        if os.getenv("NERAJOB_USAJOBS_OFFLINE", "").strip().lower() in {"1", "true", "yes"}:
            return self._offline(query, location, limit)

        api_key = os.getenv("NERAJOB_USAJOBS_API_KEY", "").strip()
        if not api_key:
            return self._offline(query, location, limit)

        ua = os.getenv("NERAJOB_USAJOBS_USER_AGENT", "").strip() or user_agent()
        headers = {
            "User-Agent": ua,
            "Host": "data.usajobs.gov",
            "Authorization-Key": api_key,
            "Accept": "application/json",
        }

        params: dict[str, str | int] = {
            "ResultsPerPage": max(1, min(limit, 25)),
        }
        keyword_parts = []
        if query.strip():
            keyword_parts.append(query.strip())
        if location.strip():
            keyword_parts.append(location.strip())
        if keyword_parts:
            params["Keyword"] = " ".join(keyword_parts)
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

        results = (
            payload.get("SearchResult", {})
            .get("SearchResultItems", [])
            if isinstance(payload, dict)
            else []
        )
        if not isinstance(results, list):
            return self._offline(query, location, limit)

        jobs: list[JobPosting] = []
        q = query.strip().lower()
        loc = location.strip().lower()
        for item in results:
            if not isinstance(item, dict):
                continue
            posting = self._posting_from_api(item)
            if posting is None:
                continue
            hay = (
                f"{posting.title} {posting.company} "
                f"{posting.location} {' '.join(posting.tags)} "
                f"{posting.description}"
            ).lower()
            if q and q not in hay:
                continue
            if loc and loc not in posting.location.lower() and "remote" not in posting.location.lower():
                continue
            jobs.append(posting)
            if len(jobs) >= limit:
                break
        return jobs

    def _posting_from_api(self, item: dict) -> JobPosting | None:
        """Convert a USAJOBS SearchResultItem dict to a JobPosting.

        API field reference:
          - MatchedObjectId (str)
          - MatchedObjectDescriptor.PositionTitle (str)
          - MatchedObjectDescriptor.OrganizationName (str)
          - MatchedObjectDescriptor.PositionLocationDisplay (str)
          - MatchedObjectDescriptor.PositionURI (str)
          - MatchedObjectDescriptor.UserArea.Details.JobSummary (str)
          - MatchedObjectDescriptor.UserArea.Details.Keyword (list[str])
          - MatchedObjectDescriptor.PositionRemuneration (list[dict])
          - MatchedObjectDescriptor.PositionOfferingType (list[dict])
        """
        desc = item.get("MatchedObjectDescriptor", item)
        if not isinstance(desc, dict):
            return None

        title = str(desc.get("PositionTitle") or "").strip()
        if not title:
            return None

        company = str(desc.get("OrganizationName") or desc.get("DepartmentName") or "US Federal Government").strip()

        locations = desc.get("PositionLocationDisplay") or ""
        if isinstance(locations, list):
            locations = ", ".join(str(loc) for loc in locations)
        location = str(locations).strip() or "Remote"

        url = str(
            desc.get("PositionURI")
            or desc.get("ApplyURI")
            or item.get("MatchedObjectId", "")
        ).strip()

        description = ""
        user_area = desc.get("UserArea") or {}
        details = user_area.get("Details") if isinstance(user_area, dict) else {}
        if isinstance(details, dict):
            description = str(details.get("JobSummary") or details.get("MajorDuties") or "").strip()
        if not description:
            description = str(desc.get("QualificationSummary") or desc.get("JobSummary") or "").strip()

        # Extract keywords/tags
        keywords = details.get("Keyword") if isinstance(details, dict) else None
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        elif not isinstance(keywords, list):
            keywords = []

        # Add PositionOfferingType as tags
        offering_types = desc.get("PositionOfferingType") or []
        if isinstance(offering_types, list):
            for ot in offering_types:
                if isinstance(ot, dict):
                    ot_name = str(ot.get("Name") or "").strip()
                    if ot_name:
                        keywords.append(ot_name.lower())

        # Add remuneration info
        salary = ""
        remunerations = desc.get("PositionRemuneration") or []
        if isinstance(remunerations, list):
            for rem in remunerations:
                if isinstance(rem, dict):
                    min_r = rem.get("MinimumRange") or ""
                    max_r = rem.get("MaximumRange") or ""
                    interval = rem.get("RateIntervalCode") or ""
                    if min_r or max_r:
                        salary = f"{min_r}-{max_r} {interval}".strip()

        tags = sorted({str(t).strip().lower() for t in keywords if t})

        remote = "remote" in location.lower() or any(
            "remote" in str(ot.get("Name", "")).lower()
            for ot in (offering_types if isinstance(offering_types, list) else [])
            if isinstance(ot, dict)
        )

        raw_id = item.get("MatchedObjectId") or str(item.get("id", ""))
        posting_id = (
            f"{self.name}-{raw_id}"
            if raw_id
            else f"{self.name}-{hashlib.sha1(f'{title}:{company}:{url}'.encode()).hexdigest()[:12]}"
        )

        return JobPosting(
            id=posting_id,
            source=self.name,
            title=title,
            company=company,
            location=location,
            url=url,
            description=description,
            tags=tags,
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
                    tags=tags,
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
                        tags=tags,
                        remote="remote" in place.lower(),
                    )
                )
        return jobs

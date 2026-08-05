"""Scraper for landingjobs - public API with offline fallback."""

from __future__ import annotations

import hashlib
import os

import httpx

from nerajob.config import http_timeout, user_agent
from nerajob.models import JobPosting
from nerajob.scrapers.base import BaseScraper

_OFFLINE_KEY = "NERAJOB_LANDINGJOBS_OFFLINE"
_OFFLINE_JOBS = [
        ('Python Backend Developer', 'TechStar', 'Lisbon, Portugal', ['python', 'django', 'postgresql'], 'https://landing.jobs/jobs/py'),
        ('React Frontend Engineer', 'WebCo', 'Porto, Portugal', ['react', 'typescript'], 'https://landing.jobs/jobs/react'),
    ]


class LandingjobsScraper(BaseScraper):
    """Public landingjobs job board adapter."""

    name = "landingjobs"
    API_URL = "https://landing.jobs/api/v1/jobs"

    def search(self, query: str, location: str = "", limit: int = 20) -> list[JobPosting]:
        if os.getenv(_OFFLINE_KEY, "").strip() in ("1", "true", "yes"):
            return self._offline_search(query, location, limit)

        headers = {"User-Agent": user_agent(), "Accept": "application/json"}
        try:
            with httpx.Client(timeout=http_timeout(), headers=headers, follow_redirects=True) as client:
                response = client.get(self.API_URL)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return self._offline_search(query, location, limit)

        return self._parse(payload, query, location, limit)

    def _parse(self, payload, query, location, limit):
        if not isinstance(payload, (list, dict)):
            return self._offline_search(query, location, limit)

        items = payload if isinstance(payload, list) else payload.get("jobs", payload.get("data", []))
        if not isinstance(items, list):
            return self._offline_search(query, location, limit)

        q = query.strip().lower()
        loc = location.strip().lower()
        jobs = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("position") or "").strip()
            company = str(item.get("company") or item.get("company_name") or "").strip()
            if not title:
                continue
            tags = [str(t).lower() for t in (item.get("tags") or item.get("skills") or []) if t]
            hay = title.lower() + " " + company.lower() + " " + " ".join(tags)
            if q and q not in hay:
                continue
            if loc and loc not in str(item.get("location", "")).lower():
                continue
            job_loc = str(item.get("location") or "Remote")
            url = str(item.get("url") or item.get("apply_url") or item.get("link") or "")
            raw_id = str(item.get("id") or item.get("slug") or hash(title + company))
            digest = hashlib.sha1((self.name + ":" + raw_id).encode()).hexdigest()[:12]

            jobs.append(JobPosting(
                id=f"landingjobs-{digest}",
                source=self.name,
                title=title,
                company=company or "Unknown",
                location=job_loc or "Remote",
                url=url,
                description=str(item.get("description") or "")[:4000],
                tags=tags[:20],
                salary=str(item.get("salary") or ""),
                remote=True,
                raw={landingjobs_id: raw_id},
            ))
            if len(jobs) >= limit:
                break
        return jobs if jobs else self._offline_search(query, location, limit)

    def _offline_search(self, query, location, limit):
        q = query.strip().lower()
        loc = location.strip().lower()
        jobs = []
        for title, company, job_loc, tags, url in _OFFLINE_JOBS:
            if q and q not in (title + " " + " ".join(tags)).lower():
                continue
            if loc and loc not in job_loc.lower():
                continue
            digest = hashlib.sha1(("offline-" + title + "-" + company).encode()).hexdigest()[:12]
            jobs.append(JobPosting(
                id=f"landingjobs-offline-{digest}",
                source=self.name,
                title=title,
                company=company,
                location=job_loc,
                url=url,
                description=f"Offline fixture for {title} at {company}",
                tags=list(tags),
                salary="",
                remote=True,
                raw={"offline": True},
            ))
            if len(jobs) >= limit:
                break
        return jobs

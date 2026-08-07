"""Himalayas.app public remote jobs API scraper.

Bounty #5 — [25 MRG] Scraper: Himalayas.app public remote jobs API.
"""
import json
import time
from dataclasses import dataclass, field
from typing import Optional

import requests


HIMALAYAS_API = "https://himalayas.app/api/jobs"


@dataclass
class Job:
    """A remote job listing from Himalayas."""
    id: str
    title: str
    company: str = ""
    location: str = "Remote"
    url: str = ""
    description: str = ""
    salary: str = ""
    tags: list[str] = field(default_factory=list)
    posted_at: str = ""

    @classmethod
    def from_api(cls, data: dict) -> "Job":
        return cls(
            id=str(data.get("id", data.get("slug", ""))),
            title=data.get("title", ""),
            company=data.get("company", {}).get("name", data.get("company_name", "")),
            location=data.get("location", "Remote"),
            url=data.get("url", data.get("apply_url", "")),
            description=data.get("description", "")[:500],
            salary=data.get("salary", data.get("compensation", "")),
            tags=data.get("tags", data.get("categories", [])),
            posted_at=data.get("created_at", data.get("posted_at", "")),
        )


class HimalayasScraper:
    """Scrape remote jobs from Himalayas.app public API."""

    BASE = "https://himalayas.app/api"

    def __init__(self, timeout: int = 15):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "NeraJob/1.0 (bounty-scraper)",
            "Accept": "application/json",
        })
        self.timeout = timeout

    def search(self, query: str = "", limit: int = 50, page: int = 1) -> list[Job]:
        """Search remote jobs."""
        params = {"q": query, "limit": limit, "page": page}
        try:
            resp = self.session.get(f"{self.BASE}/jobs", params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("jobs", data.get("results", data if isinstance(data, list) else []))
            return [Job.from_api(item) for item in results]
        except Exception as e:
            print(f"[HimalayasScraper] Error: {e}")
            return []

    def search_all(self, query: str = "", max_pages: int = 5) -> list[Job]:
        """Search across multiple pages."""
        all_jobs = []
        for page in range(1, max_pages + 1):
            jobs = self.search(query=query, page=page)
            if not jobs:
                break
            all_jobs.extend(jobs)
            time.sleep(0.5)
        return all_jobs

    def get_job(self, job_id: str) -> Optional[dict]:
        """Get detailed job info by ID."""
        try:
            resp = self.session.get(f"{self.BASE}/jobs/{job_id}", timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None


__all__ = ["HimalayasScraper", "Job"]

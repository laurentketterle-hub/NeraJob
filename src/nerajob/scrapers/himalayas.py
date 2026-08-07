"""Himalayas.app public remote jobs API adapter (with offline sample fallback).

Himalayas (https://himalayas.app) is a remote job board with a free,
public REST API at https://himalayas.app/jobs/api/. No authentication
is required. The API supports offset/limit pagination (totalCount
in the response indicates how many items are available).

To keep this scraper operational without a live network dependency,
we ship an OFFLINE fallback (deterministic demo data) used when:
  - NERAJOB_HIMALAYAS_OFFLINE=1 is set, OR
  - the live API call fails (network, parse error)
"""

from __future__ import annotations

import hashlib
import os

import httpx

from nerajob.config import http_timeout, user_agent
from nerajob.models import JobPosting
from nerajob.scrapers.base import BaseScraper

_OFFLINE = [
    (
        "Senior Python Backend Engineer",
        "Himalayas Demo Labs",
        "Remote (Worldwide)",
        ["python", "fastapi", "postgresql", "remote"],
        "https://himalayas.app/companies/demo-labs/jobs/python-backend",
        "Design and build resilient backend services in Python. Work on APIs, data pipelines, and async job queues.",
    ),
    (
        "Full-Stack Engineer (React + Node)",
        "RemoteCraft",
        "Remote (Americas)",
        ["javascript", "react", "nodejs", "typescript", "remote"],
        "https://himalayas.app/companies/remotecraft/jobs/fullstack",
        "Join a 12-person product team building developer tooling. Own features end-to-end.",
    ),
    (
        "DevOps Engineer",
        "Cloudward",
        "Remote (Europe)",
        ["kubernetes", "terraform", "aws", "docker", "remote"],
        "https://himalayas.app/companies/cloudward/jobs/devops",
        "Own the platform: CI/CD, observability, infra-as-code. Strong AWS and K8s background required.",
    ),
    (
        "ML Engineer",
        "Visionary AI",
        "Remote (Worldwide)",
        ["python", "pytorch", "mlops", "tensorflow", "remote"],
        "https://himalayas.app/companies/visionary-ai/jobs/ml-engineer",
        "Train and ship production ML models for vision systems. End-to-end ownership from data pipeline to deployment.",
    ),
    (
        "Security Engineer (AppSec)",
        "Shield Stack",
        "Remote (Worldwide)",
        ["security", "python", "appsec", "remote"],
        "https://himalayas.app/companies/shield-stack/jobs/security",
        "Lead application security for a fintech platform. Threat modeling, SAST and DAST tooling, secure code review.",
    ),
]


class HimalayasScraper(BaseScraper):
    """https://himalayas.app/jobs/api/ - free public remote jobs API."""
    name = "himalayas"
    API_URL = "https://himalayas.app/jobs/api/"

    def search(self, query: str, location: str = "", limit: int = 20) -> list[JobPosting]:
        headers = {"User-Agent": user_agent(), "Accept": "application/json"}
        offline_mode = os.environ.get("NERAJOB_HIMALAYAS_OFFLINE", "0") == "1"
        jobs: list[JobPosting] = []
        seen = set()

        if offline_mode:
            return self._offline_search(query, limit)

        try:
            offset = 0
            while len(jobs) < limit and offset < 1000:
                url = f"{self.API_URL}?limit=50&offset={offset}"
                with httpx.Client(timeout=http_timeout(), headers=headers, follow_redirects=True) as client:
                    response = client.get(url)
                    response.raise_for_status()
                    payload = response.json()
                items = payload.get("jobs", [])
                total = payload.get("totalCount", 0)
                if not items:
                    break
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    title = str(item.get("title") or "").strip()
                    company = str(item.get("companyName") or item.get("company") or "").strip()
                    if not title:
                        continue
                    tags_raw = item.get("categories") or item.get("tags") or []
                    tags = [str(t).lower() for t in tags_raw if t]
                    loc_str = "; ".join(filter(None, [
                        str(item.get("location") or ""),
                        str(item.get("locationNames") or ""),
                    ])) or "Remote"
                    url_str = str(item.get("applicationURL") or item.get("url") or "")
                    if not url_str:
                        url_str = f"https://himalayas.app/jobs/{item.get('id', '')}"
                    raw_id = str(item.get("id", ""))
                    if raw_id in seen:
                        continue
                    seen.add(raw_id)
                    desc = str(item.get("excerpt") or item.get("description") or "")[:4000]
                    digest = hashlib.sha1(f"{self.name}:{raw_id}".encode()).hexdigest()[:12]
                    jobs.append(JobPosting(
                        id=f"himalayas-{digest}",
                        source=self.name,
                        title=title,
                        company=company or "Unknown",
                        location=loc_str,
                        url=url_str,
                        description=desc,
                        tags=tags[:20],
                        salary=str(item.get("salary") or ""),
                        remote=True,
                        raw={"himalayas_id": raw_id},
                    ))
                    if len(jobs) >= limit:
                        break
                if len(items) < 50 or offset + 50 >= total:
                    break
                offset += 50
        except Exception:
            return self._offline_search(query, limit)
        return jobs

    def _offline_search(self, query: str, limit: int) -> list[JobPosting]:
        q = query.strip().lower()
        results: list[JobPosting] = []
        for title, company, location, tags, url, desc in _OFFLINE:
            hay = f"{title} {company} {' '.join(tags)} {desc}".lower()
            if q and q not in hay:
                continue
            digest = hashlib.sha1(f"{self.name}:{title}:{company}".encode()).hexdigest()[:12]
            results.append(JobPosting(
                id=f"himalayas-offline-{digest}",
                source=self.name,
                title=title,
                company=company,
                location=location,
                url=url,
                description=desc,
                tags=tags,
                remote=True,
                raw={"himalayas_offline": True},
            ))
            if len(results) >= limit:
                break
        return results

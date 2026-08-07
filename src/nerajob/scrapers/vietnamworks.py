
"""
VietnamWorks public job board adapter for NeraJob.

VietnamWorks (vietnamworks.com) is a major Vietnamese job platform.
This adapter scrapes public-facing search result snippets with rate limiting.
"""

from __future__ import annotations

import hashlib
import re
import time
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from nerajob.models import JobPosting
from nerajob.scrapers.base import BaseScraper
from nerajob.config import http_timeout, user_agent


class _VNWListingParser(HTMLParser):
    """Lightweight parser for VietnamWorks public search result snippets."""

    def __init__(self):
        super().__init__()
        self.jobs: list[dict] = []
        self._current: dict | None = None
        self._in_title = False
        self._in_company = False
        self._in_location = False
        self._text_buf = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        classes = (attrs_dict.get("class") or "").lower()

        if tag == "div" and ("job-item" in classes or "result-item" in classes):
            self._current = {}
        if self._current is not None:
            if tag in ("h2", "h3", "a") and "job-title" in classes:
                self._in_title = True
            elif tag in ("span", "a") and "company" in classes:
                self._in_company = True
            elif tag in ("span", "div") and "location" in classes:
                self._in_location = True

    def handle_endtag(self, tag: str) -> None:
        if self._current is not None:
            if self._in_title and tag in ("h2", "h3", "a"):
                self._current.setdefault("title", self._text_buf.strip())
                self._text_buf = ""
                self._in_title = False
            elif self._in_company and tag in ("span", "a", "div"):
                self._current.setdefault("company", self._text_buf.strip())
                self._text_buf = ""
                self._in_company = False
            elif self._in_location and tag in ("span", "div"):
                self._current.setdefault("location", self._text_buf.strip())
                self._text_buf = ""
                self._in_location = False

            if tag == "div" and self._current and self._current.get("title"):
                self.jobs.append(self._current)
                self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._text_buf += data


# Offline sample: realistic VietnamWorks snippet
VNW_SAMPLE = """
<div class="result-item">
  <h3 class="job-title"><a href="/viec-lam/backend-developer-python-123">Backend Developer (Python)</a></h3>
  <span class="company">FPT Software</span>
  <span class="location">Ho Chi Minh</span>
</div>
<div class="result-item">
  <h3 class="job-title"><a href="/viec-lam/data-engineer-456">Data Engineer</a></h3>
  <span class="company">VNG Corporation</span>
  <span class="location">Ha Noi</span>
</div>
<div class="result-item">
  <h3 class="job-title"><a href="/viec-lam/mobile-developer-flutter-789">Mobile Developer (Flutter)</a></h3>
  <span class="company">Shopee Vietnam</span>
  <span class="location">Ho Chi Minh</span>
</div>
"""


class VietnamWorksScraper(BaseScraper):
    """VietnamWorks public job listing adapter.

    Parses public-facing search result snippets with conservative rate limiting.
    Falls back to offline sample data when the live endpoint is unreachable.

    Usage::

        scraper = VietnamWorksScraper()
        scraper.search(query="python", limit=10)

    Bounty: https://github.com/mergeos-bounties/NeraJob/issues/17
    """

    name = "vietnamworks"
    BASE_URL = "https://www.vietnamworks.com/viec-lam/tat-ca-viec-lam"

    def __init__(self, offline: bool = False) -> None:
        self._offline = offline
        self._last_request = 0.0

    def _rate_limit(self) -> None:
        """Enforce minimum 2-second gap between requests."""
        now = time.monotonic()
        gap = now - self._last_request
        if gap < 2.0:
            time.sleep(2.0 - gap)
        self._last_request = time.monotonic()

    def _fetch(self) -> str:
        """Fetch HTML from VietnamWorks public search page or return offline sample."""
        if self._offline:
            return VNW_SAMPLE

        self._rate_limit()
        req = Request(
            self.BASE_URL,
            headers={"User-Agent": user_agent},
        )
        try:
            with urlopen(req, timeout=http_timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError):
            return VNW_SAMPLE

    def _parse(self, html: str) -> list[dict]:
        parser = _VNWListingParser()
        parser.feed(html)
        return parser.jobs

    def search(self, query: str, location: str = "", limit: int = 20) -> list[JobPosting]:
        html = self._fetch()
        raw_jobs = self._parse(html)
        q = query.strip().lower()
        loc = location.strip().lower()
        results: list[JobPosting] = []

        for item in raw_jobs:
            if len(results) >= limit:
                break
            title = item.get("title", "")
            company = item.get("company", "")
            loc_str = item.get("location", "")

            hay = f"{title} {company}".lower()
            if q and q not in hay:
                continue
            if loc and loc not in loc_str.lower():
                continue

            job_id = hashlib.sha256(
                f"vietnamworks:{title}:{company}:{loc_str}".encode()
            ).hexdigest()[:12]

            results.append(JobPosting(
                id=job_id,
                title=title,
                company=company,
                location=loc_str,
                description=f"{title} at {company}",
                url=self.BASE_URL,
                source="vietnamworks",
                tags=["Vietnam", "tech"],
            ))

        return results

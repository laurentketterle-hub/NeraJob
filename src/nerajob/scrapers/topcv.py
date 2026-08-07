"""
TopCV.vn public job board adapter for NeraJob.

TopCV (topcv.vn) is a leading Vietnamese job platform.
This adapter scrapes public-facing listing pages with rate limiting.
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


class _TopCVListingParser(HTMLParser):
    """Lightweight parser for TopCV public listing page snippets."""

    def __init__(self):
        super().__init__()
        self.jobs: list[dict] = []
        self._current: dict | None = None
        self._in_title = False
        self._in_company = False
        self._in_location = False
        self._in_salary = False
        self._text_buf = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        classes = (attrs_dict.get("class") or "").lower()

        if tag == "div" and "job-item" in classes:
            self._current = {}
        if self._current is not None:
            if tag in ("h2", "h3") and "title" in classes:
                self._in_title = True
            elif tag in ("a", "span") and "company" in classes:
                self._in_company = True
            elif tag in ("span", "div") and ("location" in classes or "address" in classes):
                self._in_location = True
            elif tag in ("span", "div") and "salary" in classes:
                self._in_salary = True

    def handle_endtag(self, tag: str) -> None:
        if self._current is not None:
            if self._in_title and tag in ("h2", "h3", "a"):
                self._current["title"] = self._text_buf.strip()
                self._text_buf = ""
                self._in_title = False
            elif self._in_company and tag in ("a", "span", "div"):
                self._current.setdefault("company", self._text_buf.strip())
                self._text_buf = ""
                self._in_company = False
            elif self._in_location and tag in ("span", "div", "p"):
                self._current.setdefault("location", self._text_buf.strip())
                self._text_buf = ""
                self._in_location = False
            elif self._in_salary and tag in ("span", "div"):
                self._current.setdefault("salary", self._text_buf.strip())
                self._text_buf = ""
                self._in_salary = False

            if tag == "div" and self._current and self._current.get("title"):
                self.jobs.append(self._current)
                self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._text_buf += data


# Offline sample: realistic TopCV snippet
TOPCV_SAMPLE = """
<div class="job-item">
  <h3 class="title"><a href="/viec-lam/backend-developer-python-123">Backend Developer (Python)</a></h3>
  <span class="company">FPT Software</span>
  <span class="location">Ho Chi Minh</span>
  <span class="salary">Up to $2000</span>
</div>
<div class="job-item">
  <h3 class="title"><a href="/viec-lam/frontend-developer-reactjs-456">Frontend Developer (ReactJS)</a></h3>
  <span class="company">VNG Corporation</span>
  <span class="location">Ha Noi</span>
  <span class="salary">$1500 - $2500</span>
</div>
"""


class TopCVScraper(BaseScraper):
    """TopCV.vn public job listing adapter.

    Parses public-facing listing snippets with conservative rate limiting.
    Falls back to offline sample data when the live endpoint is unreachable.

    Usage::

        scraper = TopCVScraper()
        scraper.search(query="python", limit=10)

    Bounty: https://github.com/mergeos-bounties/NeraJob/issues/17
    """

    name = "topcv"
    BASE_URL = "https://www.topcv.vn/viec-lam-it"

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
        """Fetch HTML from TopCV public listing page or return offline sample."""
        if self._offline:
            return TOPCV_SAMPLE

        self._rate_limit()
        req = Request(
            self.BASE_URL,
            headers={"User-Agent": user_agent},
        )
        try:
            with urlopen(req, timeout=http_timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError):
            return TOPCV_SAMPLE

    def _parse(self, html: str) -> list[dict]:
        parser = _TopCVListingParser()
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
            salary = item.get("salary", "")

            hay = f"{title} {company}".lower()
            if q and q not in hay:
                continue
            if loc and loc not in loc_str.lower():
                continue

            job_id = hashlib.sha256(
                f"topcv:{title}:{company}:{loc_str}".encode()
            ).hexdigest()[:12]

            results.append(JobPosting(
                id=job_id,
                title=title,
                company=company,
                location=loc_str,
                description=f"{title} at {company} — {salary}" if salary else f"{title} at {company}",
                url=self.BASE_URL,
                source="topcv",
                tags=[salary] if salary else [],
            ))

        return results

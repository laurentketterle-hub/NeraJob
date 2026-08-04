"""Tests for multi-source deduplication (Issue #19)."""
from __future__ import annotations

from nerajob.models import JobPosting


def _make_job(title: str, company: str, url: str = "", source: str = "sample", idx: int = 0) -> JobPosting:
    return JobPosting(
        id=f"test-{idx}-{title.lower().replace(' ','-')}",
        title=title,
        company=company,
        url=url,
        source=source,
        location="Remote",
        description="Test job",
    )


def _dedupe_url_first(jobs: list[JobPosting]) -> list[JobPosting]:
    """URL-first dedup: prefer first occurrence, then title+company fallback."""
    # Phase 1: URL dedup
    seen_urls: set[str] = set()
    url_deduped: list[JobPosting] = []
    for job in jobs:
        url_key = (job.url or "").strip().lower()
        if url_key and url_key in seen_urls:
            continue
        if url_key:
            seen_urls.add(url_key)
        url_deduped.append(job)

    # Phase 2: Title+Company dedup
    seen_tc: set[str] = set()
    deduped: list[JobPosting] = []
    for job in url_deduped:
        tc_key = f"{job.title.strip().lower()}|{job.company.strip().lower()}"
        if tc_key in seen_tc:
            continue
        seen_tc.add(tc_key)
        deduped.append(job)
    return deduped


def test_dedupe_identical_urls() -> None:
    """Jobs with identical URLs should be deduplicated."""
    jobs = [
        _make_job("Python Dev", "Acme", "https://example.com/job/1", idx=1),
        _make_job("Python Dev", "Acme", "https://example.com/job/1", idx=2),
    ]
    result = _dedupe_url_first(jobs)
    assert len(result) == 1


def test_dedupe_identical_title_company_no_url() -> None:
    """Jobs with same title+company but no URL should be deduplicated."""
    jobs = [
        _make_job("Python Dev", "Acme", "", idx=1),
        _make_job("Python Dev", "Acme", "", idx=2),
    ]
    result = _dedupe_url_first(jobs)
    assert len(result) == 1


def test_dedupe_different_urls_same_title_company() -> None:
    """Jobs with different URLs but same title+company: URL pass keeps both, TC pass drops second."""
    jobs = [
        _make_job("Python Dev", "Acme", "https://a.com/job/1", idx=1),
        _make_job("Python Dev", "Acme", "https://b.com/job/1", idx=2),
    ]
    result = _dedupe_url_first(jobs)
    # URL pass keeps both (different URLs), TC pass drops second (same title+company)
    assert len(result) == 1


def test_dedupe_different_jobs_kept() -> None:
    """Different jobs should all be kept."""
    jobs = [
        _make_job("Python Dev", "Acme", "https://a.com/1", idx=1),
        _make_job("Frontend Dev", "Beta", "https://b.com/2", idx=2),
        _make_job("Data Scientist", "Gamma", "https://c.com/3", idx=3),
    ]
    result = _dedupe_url_first(jobs)
    assert len(result) == 3


def test_dedupe_case_insensitive() -> None:
    """Dedup should be case-insensitive for titles and companies."""
    jobs = [
        _make_job("python dev", "ACME", "https://example.com/job/1", idx=1),
        _make_job("Python Dev", "acme", "https://example.com/job/1", idx=2),
    ]
    result = _dedupe_url_first(jobs)
    assert len(result) == 1


def test_dedupe_empty_input() -> None:
    """Empty input should return empty list."""
    result = _dedupe_url_first([])
    assert result == []


def test_dedupe_keeps_first_occurrence() -> None:
    """When deduplicating, the first occurrence should be kept."""
    jobs = [
        _make_job("Python Dev", "Acme", "https://example.com/1", "adzuna", idx=1),
        _make_job("Python Dev", "Acme", "https://example.com/1", "reed", idx=2),
    ]
    result = _dedupe_url_first(jobs)
    assert len(result) == 1
    assert result[0].source == "adzuna"  # first source kept


def test_dedupe_empty_urls_fallback_to_title_company() -> None:
    """When URLs are empty, fall back to title+company dedup."""
    jobs = [
        _make_job("Python Dev", "Acme", "", idx=1),
        _make_job("Python Dev", "Acme", "", idx=2),
        _make_job("Frontend Dev", "Beta", ""),
    ]
    result = _dedupe_url_first(jobs)
    assert len(result) == 2  # Python Dev x2 deduped to 1 + Frontend Dev

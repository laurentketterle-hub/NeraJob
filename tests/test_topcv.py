"""Tests for TopCV.vn scraper."""

from nerajob.scrapers.topcv import TopCVScraper, TOPCV_SAMPLE, _TopCVListingParser


class TestTopCVListingParser:
    """Unit tests for the HTML parser."""

    def test_parse_sample(self):
        parser = _TopCVListingParser()
        parser.feed(TOPCV_SAMPLE)
        jobs = parser.jobs
        assert len(jobs) == 2, f"Expected 2 jobs, got {len(jobs)}"
        assert jobs[0]["title"] == "Backend Developer (Python)"
        assert jobs[0]["company"] == "FPT Software"
        assert "Ho Chi Minh" in jobs[0]["location"]
        assert jobs[1]["title"] == "Frontend Developer (ReactJS)"
        assert jobs[1]["company"] == "VNG Corporation"

    def test_parse_empty(self):
        parser = _TopCVListingParser()
        parser.feed("<html><body></body></html>")
        assert parser.jobs == []


class TestTopCVScraper:
    """Integration tests for the TopCV scraper."""

    def test_name(self):
        scraper = TopCVScraper(offline=True)
        assert scraper.name == "topcv"

    def test_search_offline_finds_python(self):
        scraper = TopCVScraper(offline=True)
        results = scraper.search(query="python", limit=10)
        assert len(results) >= 1, f"Expected at least 1 result, got {len(results)}"
        assert any("python" in r.title.lower() for r in results)

    def test_search_offline_finds_frontend(self):
        scraper = TopCVScraper(offline=True)
        results = scraper.search(query="frontend", limit=10)
        assert len(results) >= 1
        assert results[0].source == "topcv"

    def test_search_no_match(self):
        scraper = TopCVScraper(offline=True)
        results = scraper.search(query="zzz_no_match_xxx", limit=10)
        assert len(results) == 0

    def test_search_location_filter(self):
        scraper = TopCVScraper(offline=True)
        results = scraper.search(query="", location="Ha Noi", limit=10)
        assert len(results) >= 1
        assert any("Ha Noi" in r.location for r in results)

    def test_search_limit(self):
        scraper = TopCVScraper(offline=True)
        results = scraper.search(query="", limit=1)
        assert len(results) <= 1

    def test_job_posting_fields(self):
        scraper = TopCVScraper(offline=True)
        results = scraper.search(query="backend", limit=1)
        assert len(results) == 1
        job = results[0]
        assert job.title
        assert job.company
        assert job.source == "topcv"
        assert len(job.id) == 12

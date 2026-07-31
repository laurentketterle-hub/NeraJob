"""Tests for VietnamWorks scraper."""

from nerajob.scrapers.vietnamworks import VietnamWorksScraper, VNW_SAMPLE, _VNWListingParser


class TestVNWListingParser:
    """Unit tests for the HTML parser."""

    def test_parse_sample(self):
        parser = _VNWListingParser()
        parser.feed(VNW_SAMPLE)
        jobs = parser.jobs
        assert len(jobs) == 3, f"Expected 3 jobs, got {len(jobs)}"
        assert jobs[0]["title"] == "Backend Developer (Python)"
        assert jobs[0]["company"] == "FPT Software"
        assert "Ho Chi Minh" in jobs[0]["location"]
        assert jobs[2]["title"] == "Mobile Developer (Flutter)"

    def test_parse_empty(self):
        parser = _VNWListingParser()
        parser.feed("<html><body></body></html>")
        assert parser.jobs == []


class TestVietnamWorksScraper:
    """Integration tests for the VietnamWorks scraper."""

    def test_name(self):
        scraper = VietnamWorksScraper(offline=True)
        assert scraper.name == "vietnamworks"

    def test_search_offline_finds_python(self):
        scraper = VietnamWorksScraper(offline=True)
        results = scraper.search(query="python", limit=10)
        assert len(results) >= 1
        assert any("python" in r.title.lower() for r in results)

    def test_search_offline_finds_data(self):
        scraper = VietnamWorksScraper(offline=True)
        results = scraper.search(query="data", limit=10)
        assert len(results) >= 1
        assert results[0].source == "vietnamworks"

    def test_search_no_match(self):
        scraper = VietnamWorksScraper(offline=True)
        results = scraper.search(query="zzz_no_match_xxx", limit=10)
        assert len(results) == 0

    def test_search_location_filter(self):
        scraper = VietnamWorksScraper(offline=True)
        results = scraper.search(query="", location="Ha Noi", limit=10)
        assert len(results) >= 1
        assert any("Ha Noi" in r.location for r in results)

    def test_search_limit(self):
        scraper = VietnamWorksScraper(offline=True)
        results = scraper.search(query="", limit=2)
        assert len(results) <= 2

    def test_job_posting_fields(self):
        scraper = VietnamWorksScraper(offline=True)
        results = scraper.search(query="mobile", limit=1)
        assert len(results) == 1
        job = results[0]
        assert job.title
        assert job.company
        assert job.source == "vietnamworks"
        assert len(job.id) == 12
        assert "Vietnam" in job.tags

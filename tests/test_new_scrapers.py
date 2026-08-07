"""Tests for the 5 new scrapers added in issue #22."""

from nerajob.scrapers.registry import available_scrapers, get_scraper


def test_landingjobs_registered():
    assert "landingjobs" in available_scrapers()


def test_landingjobs_offline(monkeypatch):
    monkeypatch.setenv("NERAJOB_LANDINGJOBS_OFFLINE", "1")
    jobs = get_scraper("landingjobs").search("python", limit=5)
    assert jobs
    assert all(j.source == "landingjobs" for j in jobs)


def test_nodesk_registered():
    assert "nodesk" in available_scrapers()


def test_nodesk_offline(monkeypatch):
    monkeypatch.setenv("NERAJOB_NODESK_OFFLINE", "1")
    jobs = get_scraper("nodesk").search("go", limit=5)
    assert jobs
    assert all(j.source == "nodesk" for j in jobs)


def test_jobspresso_registered():
    assert "jobspresso" in available_scrapers()


def test_jobspresso_offline(monkeypatch):
    monkeypatch.setenv("NERAJOB_JOBSPRESSO_OFFLINE", "1")
    jobs = get_scraper("jobspresso").search("", limit=5)
    assert jobs
    assert all(j.source == "jobspresso" for j in jobs)


def test_euremote_registered():
    assert "euremote" in available_scrapers()


def test_euremote_offline(monkeypatch):
    monkeypatch.setenv("NERAJOB_EUREMOTE_OFFLINE", "1")
    jobs = get_scraper("euremote").search("java", limit=5)
    assert jobs
    assert all(j.source == "euremote" for j in jobs)


def test_wr_programming_registered():
    assert "wr_programming" in available_scrapers()


def test_wr_programming_offline(monkeypatch):
    monkeypatch.setenv("NERAJOB_WR_PROGRAMMING_OFFLINE", "1")
    jobs = get_scraper("wr_programming").search("", limit=5)
    assert jobs
    assert all(j.source == "wr_programming" for j in jobs)


def test_query_filtering_works(monkeypatch):
    monkeypatch.setenv("NERAJOB_LANDINGJOBS_OFFLINE", "1")
    jobs = get_scraper("landingjobs").search("python", limit=5)
    assert len(jobs) >= 1
    titles = [j.title.lower() for j in jobs]
    assert any("python" in t for t in titles)

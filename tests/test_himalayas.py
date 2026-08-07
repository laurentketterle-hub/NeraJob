"""Tests for Himalayas scraper (live + offline)."""
from __future__ import annotations

from nerajob.scrapers.himalayas import HimalayasScraper


def test_himalayas_name():
    s = HimalayasScraper()
    assert s.name == "himalayas"


def test_himalayas_offline_no_query():
    s = HimalayasScraper()
    results = s._offline_search("", 10)
    assert len(results) > 0
    for r in results:
        assert r.source == "himalayas"
        assert r.title
        assert r.company
        assert r.remote is True


def test_himalayas_offline_query_match():
    s = HimalayasScraper()
    results = s._offline_search("python", 5)
    assert len(results) > 0
    for r in results:
        assert "python" in r.title.lower() or "python" in r.description.lower()


def test_himalayas_offline_query_no_match():
    s = HimalayasScraper()
    results = s._offline_search("zzzzznonexistent", 5)
    assert results == []


def test_himalayas_offline_limit():
    s = HimalayasScraper()
    results = s._offline_search("", 2)
    assert len(results) <= 2


def test_himalayas_offline_structure():
    s = HimalayasScraper()
    results = s._offline_search("", 1)
    assert len(results) == 1
    r = results[0]
    assert r.id
    assert r.title
    assert r.company
    assert r.location
    assert r.tags
    assert r.description

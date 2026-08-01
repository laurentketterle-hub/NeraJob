"""Arbeitnow + EU/EURES-oriented remote listings scraper."""
from ..scraper_framework import BaseScraper
from typing import List, Dict, Any

ARBEITNOW_API = "https://www.arbeitnow.com/api/job-board-api"

class ArbeitnowScraper(BaseScraper):
    """Scraper for Arbeitnow job board (EU remote jobs)."""
    
    def __init__(self):
        super().__init__(calls_per_minute=20)
    
    def search_jobs(self, query: str = "", location: str = "remote", **kwargs) -> List[Dict[str, Any]]:
        """Fetch jobs from Arbeitnow API."""
        url = ARBEITNOW_API
        if location:
            url += f"?location={location}"
        data = self.fetch(url)
        if not data or 'data' not in data:
            return []
        return [self.normalize_job(j) for j in data['data']]
    
    def normalize_job(self, raw: Dict) -> Dict[str, Any]:
        return {
            'id': f"arbeitnow-{raw.get('slug', '')}",
            'title': raw.get('title', ''),
            'company': raw.get('company_name', ''),
            'location': ' / '.join(raw.get('location', ['Remote'])),
            'description': raw.get('description', ''),
            'url': raw.get('url', ''),
            'remote': True,
            'source': 'arbeitnow',
            'tags': raw.get('tags', []),
            'posted_at': raw.get('created_at', ''),
            'type': raw.get('job_types', ['Full-time']),
            'category': raw.get('category', ''),
        }

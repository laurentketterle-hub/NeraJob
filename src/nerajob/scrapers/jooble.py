"""Jooble API multi-region search scraper."""
from ..scraper_framework import BaseScraper
from typing import List, Dict, Any

JOOBLE_API = "https://jooble.org/api/"

class JoobleScraper(BaseScraper):
    """Scraper for Jooble job search API (multi-region)."""
    
    def __init__(self, api_key: str = None):
        super().__init__(calls_per_minute=10)
        self.api_key = api_key
        self.regions = {
            'us': 'United States', 'uk': 'United Kingdom',
            'de': 'Germany', 'fr': 'France', 'vn': 'Vietnam',
            'sg': 'Singapore', 'jp': 'Japan', 'au': 'Australia'
        }
    
    def search_jobs(self, query: str = "", region: str = "us", **kwargs) -> List[Dict[str, Any]]:
        """Search jobs on Jooble for a region."""
        if not self.api_key:
            # Return sample data for testing without API key
            return [{
                'id': f'jooble-{region}-sample-{i}',
                'title': f'Sample Jooble Job {i} in {self.regions.get(region, region)}',
                'company': 'Sample Company',
                'location': self.regions.get(region, region),
                'description': f'Sample job description for {query}',
                'url': f'https://jooble.org/jobs/{query}',
                'source': 'jooble',
                'tags': [query, region, 'sample'],
                'posted_at': '2024-01-01',
            } for i in range(3)]
        
        url = f"{JOOBLE_API}{self.api_key}"
        payload = {"keywords": query, "location": region}
        data = self.fetch(url, headers={'Content-Type': 'application/json'})
        if not data or 'jobs' not in data:
            return []
        return [self.normalize_job(j) for j in data['jobs']]
    
    def normalize_job(self, raw: Dict) -> Dict[str, Any]:
        return {
            'id': f"jooble-{raw.get('id', '')}",
            'title': raw.get('title', ''),
            'company': raw.get('company', ''),
            'location': raw.get('location', ''),
            'description': raw.get('snippet', ''),
            'url': raw.get('link', ''),
            'source': 'jooble',
            'tags': [],
            'posted_at': raw.get('updated', ''),
            'salary': raw.get('salary', ''),
        }

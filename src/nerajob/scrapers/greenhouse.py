"""Greenhouse public board JSON scraper."""
from ..scraper_framework import BaseScraper
from typing import List, Dict, Any

class GreenhouseScraper(BaseScraper):
    """Scraper for Greenhouse public job boards."""
    
    def __init__(self):
        super().__init__(calls_per_minute=15)
    
    def search_jobs(self, company: str = "", query: str = "", **kwargs) -> List[Dict[str, Any]]:
        """Fetch jobs from a Greenhouse company board."""
        if not company:
            return []
        
        url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
        params = "?content=true"
        if query:
            params += f"&q={query}"
        
        data = self.fetch(url + params)
        if not data or 'jobs' not in data:
            return []
        return [self.normalize_job(j) for j in data['jobs']]
    
    def normalize_job(self, raw: Dict) -> Dict[str, Any]:
        return {
            'id': f"greenhouse-{raw.get('id', '')}",
            'title': raw.get('title', ''),
            'company': raw.get('company_name', ''),
            'location': raw.get('location', {}).get('name', ''),
            'description': raw.get('content', ''),
            'url': raw.get('absolute_url', ''),
            'source': 'greenhouse',
            'tags': [d.get('name', '') for d in raw.get('departments', [])],
            'posted_at': raw.get('updated_at', ''),
            'type': raw.get('employment_type', 'Full-time'),
        }

"""Shared scraper framework with HTTP client, retries, rate limiting."""
import time
import json
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

class RateLimiter:
    """Token-bucket rate limiter."""
    def __init__(self, calls_per_minute: int = 30):
        self.rate = calls_per_minute / 60.0
        self.tokens = calls_per_minute
        self.max_tokens = calls_per_minute
        self.last_refill = time.time()
    
    def acquire(self):
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.rate)
        self.last_refill = now
        if self.tokens < 1:
            wait = (1 - self.tokens) / self.rate
            time.sleep(wait)
            self.tokens = 0
        else:
            self.tokens -= 1

class BaseScraper(ABC):
    """Base scraper with HTTP client, retries, and rate limiting."""
    
    def __init__(self, user_agent: str = "NeraJob-Scraper/1.0", calls_per_minute: int = 30):
        self.user_agent = user_agent
        self.limiter = RateLimiter(calls_per_minute)
        self.max_retries = 3
    
    def fetch(self, url: str, headers: Dict = None) -> Optional[Dict]:
        """Fetch JSON data from URL with retries and rate limiting."""
        req_headers = {'User-Agent': self.user_agent, 'Accept': 'application/json'}
        if headers:
            req_headers.update(headers)
        
        for attempt in range(self.max_retries):
            try:
                self.limiter.acquire()
                req = urllib.request.Request(url, headers=req_headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode('utf-8'))
            except urllib.error.HTTPError as e:
                if e.code == 429:  # Rate limited
                    time.sleep(2 ** attempt)
                    continue
                return None
            except Exception:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    return None
        return None
    
    @abstractmethod
    def search_jobs(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """Search for jobs matching query."""
        pass
    
    @abstractmethod
    def normalize_job(self, raw_job: Dict) -> Dict[str, Any]:
        """Normalize a raw job posting to NeraJob format."""
        pass
    
    def normalize_jobs(self, raw_jobs: List[Dict]) -> List[Dict[str, Any]]:
        return [self.normalize_job(j) for j in raw_jobs if j]

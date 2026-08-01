"""Match score: rank jobs vs profile skills/tags."""
from typing import List, Dict, Any

def score_job_match(profile: Dict[str, Any], job: Dict[str, Any]) -> float:
    """Calculate a match score between a profile and a job posting.
    
    Args:
        profile: Dict with 'skills', 'tags', 'title', 'experience' keys
        job: Dict with 'title', 'description', 'skills', 'tags' keys
    
    Returns:
        Match score from 0.0 to 1.0
    """
    score = 0.0
    weights = {'skills': 0.40, 'tags': 0.25, 'title': 0.20, 'experience': 0.15}
    
    profile_skills = set(s.lower() for s in profile.get('skills', []))
    job_skills = set(s.lower() for s in job.get('skills', []))
    if profile_skills and job_skills:
        overlap = len(profile_skills & job_skills)
        score += weights['skills'] * (overlap / max(len(job_skills), 1))
    
    profile_tags = set(t.lower() for t in profile.get('tags', []))
    job_tags = set(t.lower() for t in job.get('tags', []))
    if profile_tags and job_tags:
        overlap = len(profile_tags & job_tags)
        score += weights['tags'] * (overlap / max(len(job_tags), 1))
    
    # Title similarity (simple word overlap)
    profile_title = profile.get('title', '').lower().split()
    job_title = job.get('title', '').lower().split()
    if profile_title and job_title:
        overlap = len(set(profile_title) & set(job_title))
        score += weights['title'] * (overlap / max(len(job_title), 1))
    
    # Experience match (basic)
    prof_exp = profile.get('experience', 0)
    job_exp = job.get('required_experience', 0)
    if job_exp > 0:
        exp_ratio = min(prof_exp / job_exp, 2.0) / 2.0
        score += weights['experience'] * exp_ratio
    
    return min(score, 1.0)

def rank_jobs(profile: Dict[str, Any], jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rank a list of jobs by match score against a profile."""
    scored = []
    for job in jobs:
        s = score_job_match(profile, job)
        scored.append({**job, 'match_score': round(s, 3)})
    return sorted(scored, key=lambda j: j['match_score'], reverse=True)

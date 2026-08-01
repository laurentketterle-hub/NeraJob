"""Tests for match score."""
from src.nerajob.match_score import score_job_match, rank_jobs

def test_exact_match():
    profile = {"skills": ["python", "django"], "tags": ["backend"], "title": "Python Developer", "experience": 5}
    job = {"title": "Python Developer", "skills": ["python", "django"], "tags": ["backend"], "required_experience": 5}
    score = score_job_match(profile, job)
    assert score > 0.8

def test_no_match():
    profile = {"skills": ["python"], "tags": [], "title": "Dev", "experience": 1}
    job = {"title": "Doctor", "skills": ["medicine"], "tags": ["healthcare"], "required_experience": 10}
    score = score_job_match(profile, job)
    assert score < 0.3

def test_rank_jobs():
    profile = {"skills": ["python", "react"], "tags": ["frontend"], "title": "Developer", "experience": 3}
    jobs = [
        {"title": "React Dev", "skills": ["react", "typescript"], "tags": ["frontend"], "required_experience": 3},
        {"title": "Data Scientist", "skills": ["python", "ml"], "tags": ["data"], "required_experience": 5},
        {"title": "Chef", "skills": ["cooking"], "tags": ["culinary"], "required_experience": 2},
    ]
    ranked = rank_jobs(profile, jobs)
    assert ranked[0]['title'] == "React Dev" or ranked[0]['title'] == "Data Scientist"

#!/usr/bin/env python3
"""Demo: nerajob match --resume-file --jobs-file offline matching.
Matches resumes to jobs using local JSON files instead of live API."""

import json, argparse, sys
from pathlib import Path

def load_json(path):
    """Load a JSON file with error handling."""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(1)

def match_skills(resume_skills, job_skills):
    """Calculate skill match score."""
    if not job_skills:
        return 0.0
    resume_set = set(s.lower() for s in resume_skills)
    job_set = set(s.lower() for s in job_skills)
    matches = resume_set & job_set
    return len(matches) / len(job_set)

def match_resume_to_jobs(resume, jobs):
    """Score a single resume against all jobs."""
    results = []
    resume_skills = resume.get("skills", [])
    for job in jobs:
        score = match_skills(resume_skills, job.get("required_skills", []))
        results.append({
            "job_id": job.get("id", "unknown"),
            "job_title": job.get("title", "Untitled"),
            "company": job.get("company", "Unknown"),
            "match_score": round(score, 2),
            "matched_skills": [s for s in job.get("required_skills", [])
                              if s.lower() in (rs.lower() for rs in resume_skills)]
        })
    results.sort(key=lambda x: x["match_score"], reverse=True)
    return results

def main():
    parser = argparse.ArgumentParser(description="Match resumes to jobs offline")
    parser.add_argument("--resume-file", required=True, help="Path to resume JSON file")
    parser.add_argument("--jobs-file", required=True, help="Path to jobs JSON file")
    parser.add_argument("--top", type=int, default=5, help="Show top N matches (default: 5)")
    parser.add_argument("--output", "-o", help="Output file for results (JSON)")
    args = parser.parse_args()

    resume = load_json(args.resume_file)
    jobs_data = load_json(args.jobs_file)
    
    # Support both {"jobs": [...]} and [...] formats
    if isinstance(jobs_data, dict):
        jobs = jobs_data.get("jobs", [])
    elif isinstance(jobs_data, list):
        jobs = jobs_data
    else:
        print("Error: jobs file must be a list or object with 'jobs' key", file=sys.stderr)
        sys.exit(1)
    
    print(f"Loaded resume: {resume.get('name', 'Unknown')}")
    print(f"Loaded {len(jobs)} job listings")
    print(f"\nTop {min(args.top, len(jobs))} matches:")
    print("-" * 60)
    
    matches = match_resume_to_jobs(resume, jobs)
    
    for i, m in enumerate(matches[:args.top]):
        stars = "\u2605" * int(m["match_score"] * 5) if m["match_score"] > 0 else "No match"
        print(f"{i+1}. {m['job_title']} @ {m['company']}")
        print(f"   Score: {m['match_score']:.0%} {stars}")
        if m["matched_skills"]:
            print(f"   Skills: {', '.join(m['matched_skills'])}")
        print()
    
    if args.output:
        output_data = {
            "resume": resume.get("name", "Unknown"),
            "total_jobs": len(jobs),
            "top_matches": matches[:args.top]
        }
        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"Results saved to {args.output}")

if __name__ == "__main__":
    main()

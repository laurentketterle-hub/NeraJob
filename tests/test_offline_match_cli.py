"""Tests for offline CLI match with --resume-file, --jobs-file, and --demo.

Covers the top-level `nerajob match` command (and existing `nerajob jobs match`).
"""

import json
import subprocess as sp
import sys
from pathlib import Path

from nerajob.match import match_score
from nerajob.models import JobPosting, Profile

# Use the same Python that pytest runs under so `nerajob` is importable
_PYTHON = sys.executable

# ---------------------------------------------------------------------------
# unit tests — matching logic
# ---------------------------------------------------------------------------


def test_offline_match_python_profile_vs_frontend_jobs():
    profile = Profile(
        headline="Python Backend Engineer",
        location="Remote",
        skills=["Python", "FastAPI", "PostgreSQL"],
    )
    job = JobPosting(
        id="fe_01",
        source="sample",
        title="Senior Frontend Engineer",
        company="WebCo",
        location="Remote",
        description="",
        tags=["react", "typescript", "next.js"],
        remote=True,
    )
    score = match_score(profile, job)
    # Python backend profile should not score high on frontend role
    assert score["score"] < 50 or len(score["skill_hits"]) == 0


def test_offline_match_devops_profile_vs_devops_jobs():
    profile = Profile(
        headline="DevOps Engineer",
        location="Remote",
        skills=["Kubernetes", "Terraform", "AWS", "Docker"],
    )
    job = JobPosting(
        id="devops_01",
        source="sample",
        title="Senior DevOps Engineer",
        company="CloudScale",
        location="Remote",
        description="",
        tags=["kubernetes", "terraform", "aws", "ci/cd"],
        remote=True,
    )
    score = match_score(profile, job)
    assert score["score"] >= 50
    assert score["band"] in ("medium", "strong")


def test_offline_match_with_sample_fixtures():
    profile = Profile(
        headline="Python Backend Engineer",
        location="Remote",
        skills=["Python", "FastAPI", "PostgreSQL", "Docker"],
    )

    jobs_path = (
        Path(__file__).parent.parent / "data" / "samples" / "jobs_python_remote.json"
    )
    jobs_data = json.loads(jobs_path.read_text(encoding="utf-8"))
    jobs = [JobPosting(**j) for j in jobs_data]

    from nerajob.match import rank_jobs

    ranked = rank_jobs(profile, jobs, top_k=3)
    assert len(ranked) == 3
    top = ranked[0]
    assert "python" in str(top.get("skill_hits", [])).lower() or top["score"] > 0


# ---------------------------------------------------------------------------
# integration tests — existing `nerajob jobs match` subcommand
# ---------------------------------------------------------------------------


def test_jobs_match_with_files(tmp_path: Path) -> None:
    """Test `nerajob jobs match --resume-file --jobs-file` works end-to-end."""
    profile = Profile(
        full_name="Test User",
        headline="Python Backend Engineer",
        location="Remote",
        skills=["Python", "FastAPI", "PostgreSQL"],
    )
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(profile.model_dump_json(), encoding="utf-8")

    jobs = [
        JobPosting(
            id="j1",
            source="fixture",
            title="Python Backend Engineer",
            company="TestCo",
            location="Remote",
            description="FastAPI and PostgreSQL experience required",
            tags=["python", "fastapi", "postgres"],
            remote=True,
        ),
        JobPosting(
            id="j2",
            source="fixture",
            title="Rust Systems Engineer",
            company="TestCo",
            location="Remote",
            description="Systems programming in Rust",
            tags=["rust", "systems"],
            remote=True,
        ),
    ]
    jobs_path = tmp_path / "jobs.json"
    jobs_path.write_text(
        json.dumps([j.model_dump() for j in jobs]), encoding="utf-8"
    )

    result = sp.run(
        [
            _PYTHON,
            "-m",
            "nerajob",
            "jobs",
            "match",
            "--resume-file",
            str(profile_path),
            "--jobs-file",
            str(jobs_path),
            "--top",
            "2",
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0
    assert "Python Backend" in result.stdout
    assert "TestCo" in result.stdout


# ---------------------------------------------------------------------------
# integration tests — top-level `nerajob match` command
# ---------------------------------------------------------------------------


def test_top_level_match_with_files(tmp_path: Path) -> None:
    """Top-level `nerajob match --resume-file --jobs-file` works."""
    profile = Profile(
        full_name="Test User",
        headline="Python Backend Engineer",
        location="Remote",
        skills=["Python", "FastAPI", "PostgreSQL"],
    )
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(profile.model_dump_json(), encoding="utf-8")

    jobs = [
        JobPosting(
            id="j1",
            source="fixture",
            title="Python Backend Engineer",
            company="TestCo",
            location="Remote",
            description="FastAPI and PostgreSQL experience required",
            tags=["python", "fastapi", "postgres"],
            remote=True,
        ),
        JobPosting(
            id="j2",
            source="fixture",
            title="Rust Systems Engineer",
            company="TestCo",
            location="Remote",
            description="Systems programming in Rust",
            tags=["rust", "systems"],
            remote=True,
        ),
    ]
    jobs_path = tmp_path / "jobs.json"
    jobs_path.write_text(
        json.dumps([j.model_dump() for j in jobs]), encoding="utf-8"
    )

    result = sp.run(
        [
            _PYTHON,
            "-m",
            "nerajob",
            "match",
            "--resume-file",
            str(profile_path),
            "--jobs-file",
            str(jobs_path),
            "--top",
            "2",
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0
    assert "Python Backend" in result.stdout
    assert "TestCo" in result.stdout


def test_top_level_match_demo_flag() -> None:
    """Top-level `nerajob match --demo` runs successfully with bundled fixtures."""
    result = sp.run(
        [_PYTHON, "-m", "nerajob", "match", "--demo", "--top", "3"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "Job matches" in result.stdout
    assert "Senior Python" in result.stdout
    assert "Band breakdown" in result.stdout
    # Should rank the Python backend job highest for a Python profile
    assert "strong" in result.stdout


def test_top_level_match_demo_with_custom_weights() -> None:
    """--demo mode respects --skill-weight, --title-weight, --location-weight."""
    result = sp.run(
        [
            _PYTHON, "-m", "nerajob", "match",
            "--demo", "--top", "3",
            "--skill-weight", "80",
            "--title-weight", "10",
            "--location-weight", "5",
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0
    assert "Job matches" in result.stdout


# ---------------------------------------------------------------------------
# error cases — top-level `nerajob match`
# ---------------------------------------------------------------------------


def test_top_level_match_missing_both_files(tmp_path: Path) -> None:
    """If no flags and no stored profile, top-level match exits gracefully."""
    result = sp.run(
        [_PYTHON, "-m", "nerajob", "match"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    # Should fail because no stored profile in CI
    assert result.returncode != 0


def test_top_level_match_only_resume_file(tmp_path: Path) -> None:
    """Requires both --resume-file AND --jobs-file together."""
    profile = Profile(headline="Tester", skills=["Python"])
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(profile.model_dump_json(), encoding="utf-8")

    result = sp.run(
        [_PYTHON, "-m", "nerajob", "match", "--resume-file", str(profile_path)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode != 0
    assert "Both --resume-file AND --jobs-file" in result.stdout


def test_top_level_match_only_jobs_file(tmp_path: Path) -> None:
    """Requires both --resume-file AND --jobs-file together."""
    jobs = [{"id": "j1", "source": "fixture", "title": "Test", "company": "Co"}]
    jobs_path = tmp_path / "jobs.json"
    jobs_path.write_text(json.dumps(jobs), encoding="utf-8")

    result = sp.run(
        [_PYTHON, "-m", "nerajob", "match", "--jobs-file", str(jobs_path)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode != 0
    assert "Both --resume-file AND --jobs-file" in result.stdout


def test_top_level_match_invalid_resume_json(tmp_path: Path) -> None:
    """Graceful error on malformed resume JSON."""
    bad_profile = tmp_path / "bad_profile.json"
    bad_profile.write_text("not valid json", encoding="utf-8")

    jobs = [{"id": "j1", "source": "fixture", "title": "Test", "company": "Co"}]
    jobs_path = tmp_path / "jobs.json"
    jobs_path.write_text(json.dumps(jobs), encoding="utf-8")

    result = sp.run(
        [
            _PYTHON, "-m", "nerajob", "match",
            "--resume-file", str(bad_profile),
            "--jobs-file", str(jobs_path),
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode != 0
    assert "Invalid resume file" in result.stdout


def test_top_level_match_invalid_jobs_json(tmp_path: Path) -> None:
    """Graceful error on malformed jobs JSON."""
    profile = Profile(headline="Tester", skills=["Python"])
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(profile.model_dump_json(), encoding="utf-8")

    bad_jobs = tmp_path / "bad_jobs.json"
    bad_jobs.write_text("[{invalid json]]", encoding="utf-8")

    result = sp.run(
        [
            _PYTHON, "-m", "nerajob", "match",
            "--resume-file", str(profile_path),
            "--jobs-file", str(bad_jobs),
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode != 0
    assert "Invalid jobs file" in result.stdout


def test_top_level_match_jobs_not_array(tmp_path: Path) -> None:
    """Jobs file must be a JSON array, not an object."""
    profile = Profile(headline="Tester", skills=["Python"])
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(profile.model_dump_json(), encoding="utf-8")

    obj_jobs = tmp_path / "obj_jobs.json"
    obj_jobs.write_text('{"key": "not an array"}', encoding="utf-8")

    result = sp.run(
        [
            _PYTHON, "-m", "nerajob", "match",
            "--resume-file", str(profile_path),
            "--jobs-file", str(obj_jobs),
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode != 0
    assert "JSON array" in result.stdout


def test_top_level_match_demo_ranks_senior_python_first() -> None:
    """Python-heavy profile should rank the Python backend role highest."""
    result = sp.run(
        [_PYTHON, "-m", "nerajob", "match", "--demo", "--top", "6"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    # The Senior Python Backend Engineer should appear before the Rust or Frontend roles
    sr_py_line = next((i for i, line in enumerate(lines) if "Senior Python" in line), None)
    rust_line = next((i for i, line in enumerate(lines) if "Rust" in line and "Systems" in line), None)
    frontend_line = next((i for i, line in enumerate(lines) if "Frontend" in line), None)
    assert sr_py_line is not None, "Should rank Senior Python job"
    if rust_line is not None:
        assert sr_py_line < rust_line, "Python role should rank above Rust role"
    if frontend_line is not None:
        assert sr_py_line < frontend_line, "Python role should rank above Frontend role"

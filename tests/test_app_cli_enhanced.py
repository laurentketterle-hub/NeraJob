"""Tests for application tracker CLI commands — app stats, app list filtering."""
import pytest
from typer.testing import CliRunner

from nerajob.cli import app
from nerajob.models import ApplicationPackage
from nerajob.storage import save_application, load_applications

runner = CliRunner()


class TestAppListFiltering:
    """Test app list with --status and --sort-by options."""

    def _setup_apps(self, tmp_path, monkeypatch):
        import nerajob.storage as s
        apps_dir = tmp_path / "applications"
        monkeypatch.setattr(s, "APPLICATIONS_DIR", apps_dir)
        save_application(ApplicationPackage(job_id="a1", status="draft"))
        save_application(ApplicationPackage(job_id="a2", status="applied"))
        save_application(ApplicationPackage(job_id="a3", status="applied"))
        save_application(ApplicationPackage(job_id="a4", status="interview"))
        save_application(ApplicationPackage(job_id="a5", status="offer"))

    def test_list_all(self, tmp_path, monkeypatch):
        self._setup_apps(tmp_path, monkeypatch)
        result = runner.invoke(app, ["app", "list"])
        assert result.exit_code == 0
        assert "a1" in result.stdout
        assert "a5" in result.stdout

    def test_list_filter_by_status(self, tmp_path, monkeypatch):
        self._setup_apps(tmp_path, monkeypatch)
        result = runner.invoke(app, ["app", "list", "--status", "applied"])
        assert result.exit_code == 0
        assert "applied" in result.stdout
        assert "a2" in result.stdout
        assert "a3" in result.stdout
        assert "a5" not in result.stdout  # offer

    def test_list_filter_empty_status(self, tmp_path, monkeypatch):
        self._setup_apps(tmp_path, monkeypatch)
        result = runner.invoke(app, ["app", "list", "--status", "accepted"])
        assert result.exit_code == 0
        assert "No applications with status" in result.stdout

    def test_list_invalid_status(self, tmp_path, monkeypatch):
        self._setup_apps(tmp_path, monkeypatch)
        result = runner.invoke(app, ["app", "list", "--status", "invalid"])
        assert result.exit_code == 1
        assert "Invalid status" in result.stdout

    def test_list_sort_by_created(self, tmp_path, monkeypatch):
        self._setup_apps(tmp_path, monkeypatch)
        result = runner.invoke(app, ["app", "list", "--sort-by", "created"])
        assert result.exit_code == 0

    def test_list_sort_by_status(self, tmp_path, monkeypatch):
        self._setup_apps(tmp_path, monkeypatch)
        result = runner.invoke(app, ["app", "list", "--sort-by", "status"])
        assert result.exit_code == 0


class TestAppStats:
    """Test app stats command with funnel and timeline."""

    def _setup_apps(self, tmp_path, monkeypatch):
        import nerajob.storage as s
        apps_dir = tmp_path / "applications"
        monkeypatch.setattr(s, "APPLICATIONS_DIR", apps_dir)
        save_application(ApplicationPackage(job_id="s1", status="draft"))
        save_application(ApplicationPackage(job_id="s2", status="applied"))
        save_application(ApplicationPackage(job_id="s3", status="applied"))
        save_application(ApplicationPackage(job_id="s4", status="interview"))
        save_application(ApplicationPackage(job_id="s5", status="offer"))
        save_application(ApplicationPackage(job_id="s6", status="rejected"))
        save_application(ApplicationPackage(job_id="s7", status="accepted"))

    def test_stats_shows_counts(self, tmp_path, monkeypatch):
        self._setup_apps(tmp_path, monkeypatch)
        result = runner.invoke(app, ["app", "stats"])
        assert result.exit_code == 0
        assert "7 total" in result.stdout
        assert "applied" in result.stdout
        assert "interview" in result.stdout

    def test_stats_shows_funnel(self, tmp_path, monkeypatch):
        self._setup_apps(tmp_path, monkeypatch)
        result = runner.invoke(app, ["app", "stats"])
        assert result.exit_code == 0
        assert "Conversion Funnel" in result.stdout or "Funnel" in result.stdout

    def test_stats_no_apps(self, tmp_path, monkeypatch):
        import nerajob.storage as s
        monkeypatch.setattr(s, "APPLICATIONS_DIR", tmp_path / "empty_apps")
        result = runner.invoke(app, ["app", "stats"])
        assert result.exit_code == 0
        assert "No applications" in result.stdout

    def test_stats_recent_activity(self, tmp_path, monkeypatch):
        self._setup_apps(tmp_path, monkeypatch)
        result = runner.invoke(app, ["app", "stats"])
        assert result.exit_code == 0
        assert "Activity" in result.stdout or "Recent" in result.stdout

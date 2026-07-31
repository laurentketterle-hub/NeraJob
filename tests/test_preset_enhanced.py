"""Tests for scan preset CLI commands — preset-show, preset-reset."""
import pytest
from typer.testing import CliRunner

from nerajob.cli import app
from nerajob.models import ScanPreset
from nerajob.storage import save_scan_preset, load_scan_preset

runner = CliRunner()


class TestPresetShow:
    """Test preset-show command."""

    def test_preset_show_defaults(self, tmp_path, monkeypatch):
        import nerajob.config as cfg
        preset_path = tmp_path / "scan-preset.json"
        monkeypatch.setattr(cfg, "SCAN_PRESET_PATH", preset_path)
        save_scan_preset(ScanPreset())
        result = runner.invoke(app, ["profile", "preset-show"])
        assert result.exit_code == 0
        assert "Remote Only" in result.stdout
        assert "False" in result.stdout  # default

    def test_preset_show_configured(self, tmp_path, monkeypatch):
        import nerajob.config as cfg
        preset_path = tmp_path / "scan-preset.json"
        monkeypatch.setattr(cfg, "SCAN_PRESET_PATH", preset_path)
        preset = ScanPreset(remote_only=True, skill_filters=["python", "api"], min_score=50.0)
        save_scan_preset(preset)
        result = runner.invoke(app, ["profile", "preset-show"])
        assert result.exit_code == 0
        assert "True" in result.stdout
        assert "python" in result.stdout
        assert "50.0" in result.stdout or "50" in result.stdout


class TestPresetReset:
    """Test preset-reset command."""

    def test_preset_reset(self, tmp_path, monkeypatch):
        import nerajob.config as cfg
        preset_path = tmp_path / "scan-preset.json"
        monkeypatch.setattr(cfg, "SCAN_PRESET_PATH", preset_path)
        preset = ScanPreset(remote_only=True, skill_filters=["rust"], min_score=80.0)
        save_scan_preset(preset)
        result = runner.invoke(app, ["profile", "preset-reset"])
        assert result.exit_code == 0
        loaded = load_scan_preset()
        assert loaded.remote_only is False
        assert loaded.skill_filters == []
        assert loaded.min_score == 0.0

    def test_preset_reset_idempotent(self, tmp_path, monkeypatch):
        import nerajob.config as cfg
        preset_path = tmp_path / "scan-preset.json"
        monkeypatch.setattr(cfg, "SCAN_PRESET_PATH", preset_path)
        save_scan_preset(ScanPreset())
        result = runner.invoke(app, ["profile", "preset-reset"])
        assert result.exit_code == 0
        loaded = load_scan_preset()
        assert loaded.remote_only is False


class TestPresetIntegration:
    """Test preset flows end-to-end."""

    def test_set_then_show(self, tmp_path, monkeypatch):
        import nerajob.config as cfg
        preset_path = tmp_path / "scan-preset.json"
        monkeypatch.setattr(cfg, "SCAN_PRESET_PATH", preset_path)
        # Set via preset command
        result = runner.invoke(app, [
            "profile", "preset",
            "--remote-only",
            "--skills", "python,java",
            "--min-score", "70",
        ])
        assert result.exit_code == 0
        # Verify via show
        result = runner.invoke(app, ["profile", "preset-show"])
        assert result.exit_code == 0
        assert "True" in result.stdout or "true" in result.stdout.lower()
        assert "python" in result.stdout

    def test_set_then_reset_then_show(self, tmp_path, monkeypatch):
        import nerajob.config as cfg
        preset_path = tmp_path / "scan-preset.json"
        monkeypatch.setattr(cfg, "SCAN_PRESET_PATH", preset_path)
        runner.invoke(app, ["profile", "preset", "--remote-only", "--min-salary", "50000"])
        runner.invoke(app, ["profile", "preset-reset"])
        result = runner.invoke(app, ["profile", "preset-show"])
        assert result.exit_code == 0
        assert "False" in result.stdout or "false" in result.stdout.lower()

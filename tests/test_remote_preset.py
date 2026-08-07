"""Tests for remote-only default profile preset."""
import json
from pathlib import Path


def test_remote_preset_exists():
    """Remote-only preset file should exist in data/."""
    preset_path = Path("data/scan-preset.json")
    assert preset_path.exists(), "scan-preset.json not found"


def test_remote_preset_is_valid_json():
    """Preset should be valid JSON with required fields (ScanPreset model)."""
    preset_path = Path("data/scan-preset.json")
    data = json.loads(preset_path.read_text())
    assert data["remote_only"] is True
    assert "skill_filters" in data
    assert "min_score" in data
    assert "min_salary" in data
    assert "max_results" in data


def test_remote_preset_skill_filters():
    """Preset should include relevant tech skills in skill_filters."""
    preset_path = Path("data/scan-preset.json")
    data = json.loads(preset_path.read_text())
    assert isinstance(data["skill_filters"], list)
    assert len(data["skill_filters"]) >= 1
    assert "python" in data["skill_filters"]


def test_remote_preset_values():
    """Preset should have sensible default values."""
    preset_path = Path("data/scan-preset.json")
    data = json.loads(preset_path.read_text())
    assert data["min_score"] >= 0
    assert data["min_salary"] >= 0
    assert data["max_results"] > 0


def test_load_scan_preset_import():
    """ScanPreset model should be importable."""
    from nerajob.models import ScanPreset
    assert ScanPreset is not None

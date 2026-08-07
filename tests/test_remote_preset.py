"""Tests for remote-only default profile preset."""
import json
from pathlib import Path


def test_remote_preset_exists():
    """Remote-only preset file should exist in data/."""
    preset_path = Path("data/scan-preset.json")
    assert preset_path.exists(), "scan-preset.json not found"


def test_remote_preset_is_valid_json():
    """Preset should be valid JSON with required fields."""
    preset_path = Path("data/scan-preset.json")
    data = json.loads(preset_path.read_text())
    assert data["name"] == "remote-only"
    assert data["filters"]["remote_only"] is True
    assert data["filters"]["exclude_onsite"] is True


def test_remote_preset_sources():
    """Preset should target remote-friendly sources."""
    preset_path = Path("data/scan-preset.json")
    data = json.loads(preset_path.read_text())
    remote_sources = {"remoteok", "weworkremotely", "remotive", "jobicy", "findwork"}
    assert set(data["sources"]).issubset(remote_sources) or len(data["sources"]) >= 3


def test_remote_preset_skills():
    """Preset should include relevant tech skills."""
    preset_path = Path("data/scan-preset.json")
    data = json.loads(preset_path.read_text())
    assert len(data["skills"]) >= 3
    assert "python" in data["skills"]


def test_load_scan_preset_import():
    """ScanPreset model should be importable."""
    from nerajob.models import ScanPreset
    assert ScanPreset is not None

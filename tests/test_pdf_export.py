"""Tests for PDF CV export."""
import os, json, pytest
from src.nerajob.pdf_export import export_cv_to_pdf

def test_export_creates_pdf(tmp_path):
    md = tmp_path / "profile.md"
    md.write_text("# Test CV\n## Skills\n- Python\n- Git\n## Experience\n5 years")
    result = export_cv_to_pdf(str(md))
    assert os.path.exists(result)
    assert result.endswith('.pdf')
    assert os.path.getsize(result) > 0

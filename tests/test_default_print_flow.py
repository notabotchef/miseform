"""Default print edition must preserve readable flow across natural page breaks."""
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from exporter import _find_chrome, export_pdf  # noqa: E402
from test_service_readability import synthetic_card  # noqa: E402


@pytest.mark.parametrize("theme", ["original", "paper", "atelier", "service", "ledger"])
def test_default_long_stage_keeps_heading_with_first_step(tmp_path, theme):
    pytest.importorskip("playwright.sync_api")
    if not _find_chrome() or not shutil.which("pdftotext"):
        pytest.skip("Rendered pagination test needs Chromium and pdftotext")
    output = tmp_path / "default-long.pdf"
    result = export_pdf(synthetic_card(32), output, theme=theme)
    assert result.ok, result.detail
    bbox = subprocess.run(["pdftotext", "-bbox", str(output), "-"], check=True,
                          text=True, capture_output=True)
    root = ET.fromstring(bbox.stdout)
    pages = list(root.iter("{http://www.w3.org/1999/xhtml}page"))
    assert len(pages) > 1
    all_words = []
    heading_count = 0
    for page in pages:
        words = list(page.iter("{http://www.w3.org/1999/xhtml}word"))
        all_words.extend(word.text or "" for word in words)
        headings = [word for word in words if word.text == "METHOD"]
        heading_count += len(headings)
        for heading in headings:
            assert any((word.text or "").startswith("Checkpoint001:")
                       and float(word.attrib["yMin"]) > float(heading.attrib["yMin"])
                       for word in words), "Method heading must share its page with first step"
    # The fixture stage is also named "Trial method"; both headings must stay
    # with its first instruction, and this assertion prevents vacuous checks.
    assert heading_count >= 1
    text = " ".join(all_words)
    for i in range(1, 33):
        assert f"Checkpoint{i:03d}:" in text
    assert "ObservationSentinel:" in text
    assert "ControlSentinel:" in text

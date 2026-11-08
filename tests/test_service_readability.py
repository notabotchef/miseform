"""Rendered service-theme regressions using fictional kitchen content only."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from card_model import Card  # noqa: E402
from exporter import _find_chrome, export_pdf  # noqa: E402


def synthetic_card(step_count: int = 6) -> Card:
    data = json.loads((ROOT / "examples/sesame-salt-garnish.card.json").read_text())
    rows = [{"row_id": f"R{i}", "name": f"Trial ingredient {i}", "weight_g": i * 10,
             "volume": None, "notes": "Weigh before mixing."} for i in range(1, 11)]
    return Card({**data, "recipe_id": "LAYOUT-TEST", "recipe_type": "component", "title": "Fictional station mix",
                 "intro": "A fictional layout fixture for checking kitchen reading order.",
                 "equipment": "Scale, bowl and spatula; one trial batch.",
                 "percentage_basis": {"basis_label": "Trial ingredient 1 = 100% = 10 g.",
                                      "reference_row_id": "R1", "reference_weight_g": 10},
                 "input_total_g": 550, "usable_yield_g": 540, "loss_g": 10,
                 "portion_g": 10, "portions": 54,
                 "facts": {**data["facts"], "yield_summary": "540 g usable",
                           "yield_portions": "54 portions at 10 g",
                           "difficulty_technique": "Fictional mixing trial"},
                 "components": [{"name": "Trial batch", "ingredients": rows,
                                 "reference_row_id": "R1", "reference_weight_g": 10}],
                 "stages": [{"name": "Trial method", "steps": [
                     {"number": i, "text": f"Checkpoint{i:03d}: combine the weighed trial ingredients in the bowl. Scrape the sides and stir until the mixture looks even. Record the observed texture before continuing.",
                      "ingredient_refs": ["R1"]} for i in range(1, step_count + 1)]}],
                 "notes": [{"heading": "Trial observations", "text": "ObservationSentinel: retain this note in every reading edition."}],
                 "process_controls": {**data["process_controls"], "emulsification": "ControlSentinel: fictional trial control awaiting chef review."}})


def pdf_pages(tmp_path: Path, steps: int = 6):
    pytest.importorskip("playwright.sync_api")
    if not _find_chrome() or not shutil.which("pdftotext"):
        pytest.skip("Rendered layout test needs Chromium and pdftotext")
    output = tmp_path / f"service-{steps}.pdf"
    result = export_pdf(synthetic_card(steps), output, theme="service")
    assert result.ok, result.detail
    parsed = subprocess.run(["pdftotext", "-bbox", str(output), "-"],
                            check=True, capture_output=True, text=True)
    root = ET.fromstring(parsed.stdout)
    return [list(page.iter("{http://www.w3.org/1999/xhtml}word"))
            for page in root.iter("{http://www.w3.org/1999/xhtml}page")]


def test_service_header_does_not_waste_station_reading_space(tmp_path):
    pages = pdf_pages(tmp_path)
    words = pages[0]
    brand = next(word for word in words if word.text == "Miseform")
    eyebrow = min((word for word in words if float(word.attrib["yMin"]) > float(brand.attrib["yMax"])),
                  key=lambda word: float(word.attrib["yMin"]))
    assert float(eyebrow.attrib["yMin"]) - float(brand.attrib["yMax"]) < 22
    assert len(pages) <= 2, "This bounded fixture should fit two readable A4 pages"


def test_service_long_method_flows_without_orphan_heading_or_lost_content(tmp_path):
    pages = pdf_pages(tmp_path, 32)
    assert len(pages) > 1, "Long methods must continue naturally, not shrink to fit"
    texts = [[word.text or "" for word in page] for page in pages]
    joined = " ".join(word for page in texts for word in page)
    for i in range(1, 33):
        assert f"Checkpoint{i:03d}:" in joined
    assert "ObservationSentinel:" in joined
    assert "ControlSentinel:" in joined
    for words in pages:
        headings = [word for word in words if word.text == "METHOD"]
        for heading in headings:
            following = [word for word in words if (word.text or "").startswith("Checkpoint")
                         and float(word.attrib["yMin"]) > float(heading.attrib["yMin"])]
            assert following, "Method heading must share its page with first instruction"
        for word in words:
            if (word.text or "").startswith("Checkpoint"):
                assert float(word.attrib["yMax"]) - float(word.attrib["yMin"]) >= 9

"""The four editions of one card must never drift apart.

One canonical JSON card record produces four editions: a Markdown master,
an HTML edition, a native PDF and a native XLSX workbook. The package
promises that the four files cannot disagree, because they are one record
rendered four ways.

These checks cover the defects in which they did disagree:

* an absent declared input total, a wrong declared input total and the
  workbook's own live sum each produced a different number;
* a weight below a tenth of a gram printed as zero, which tells a cook to
  add none of the leavener;
* the Markdown master doubled the colon of a source-record label.

Every card here is synthetic. Nothing in this file names a real recipe,
a real person or a private path.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from card_model import PROCESS_CONTROL_KEYS, Card, format_weight  # noqa: E402
from exporter import export_pdf, export_xlsx, extract_pdf_text  # noqa: E402
from render_html import render_html  # noqa: E402
from render_markdown import render_markdown  # noqa: E402

EXAMPLE = ROOT / "examples" / "sesame-salt-garnish.card.json"


def synthetic_card(**overrides) -> Card:
    """A synthetic card: 500 g flour, 10 g salt, 0.04 g instant yeast."""
    data = {
        "recipe_id": "DEMO-PARITY",
        "title": "PARITY PROOF CARD",
        "version": "v0.1",
        "revision_date": "2026-11-13",
        "status": "R&D",
        "recipe_type": "component",
        "intro": "Synthetic card used only by the edition parity regressions.",
        "facts": {
            "time_total": "10 minutes",
            "time_active": "10 minutes",
            "time_inactive": "0 minutes",
            "difficulty_level": "Basic",
            "difficulty_technique": "Weighing and mixing",
            "yield_summary": "500 g usable",
            "yield_portions": "10 portions at 50 g",
            "storage_summary": "Not established in this synthetic card.",
            "storage_reference": "Not established in this synthetic card.",
        },
        "equipment": "Scale readable to 0.01 g.",
        "allergens": "No allergen is declared in this synthetic card.",
        "release_blockers": [
            "This synthetic card is a parity fixture; it is never released."
        ],
        "percentage_basis": {
            "basis_label": "Flour = 100% = 500 g.",
            "reference_row_id": "i1",
            "reference_weight_g": 500,
        },
        "process_controls": {
            key: "N/A - no such step in this synthetic card."
            for key in PROCESS_CONTROL_KEYS
        },
        "components": [
            {
                "name": "Dough",
                "reference_row_id": "i1",
                "reference_weight_g": 500,
                "ingredients": [
                    {"row_id": "i1", "name": "Flour", "weight_g": 500},
                    {"row_id": "i2", "name": "Salt", "weight_g": 10},
                    {"row_id": "i3", "name": "Instant yeast", "weight_g": 0.04},
                ],
            }
        ],
        "input_total_g": 510.04,
        "usable_yield_g": 500,
        "loss_g": 10.04,
        "portion_g": 50,
        "portions": 10,
        "stages": [
            {
                "name": "MIX",
                "steps": [{"number": 1, "text": "Weigh every ingredient and mix."}],
            }
        ],
        "provenance": {
            "evidence": "Synthetic evidence recorded by the edition parity regressions.",
            "validation": "Synthetic validation recorded by the edition parity regressions.",
            "filing": "Synthetic filing recorded by the edition parity regressions.",
        },
    }
    data.update(overrides)
    return Card(data)


def displays_nonzero(value: object, number_format: str) -> bool:
    """True when ``number_format`` shows a nonzero number as a nonzero number.

    A fixed one-decimal format shows 0.04 g as 0.0 g: the cell holds the
    right number and the reader still sees a zero. Optional decimal places
    after the point are what keep a small weight visible.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value == 0:
        return False
    decimals = len(f"{float(value):.10f}".rstrip("0").split(".")[1])
    _, _, fraction = number_format.partition(".")
    return fraction.count("#") >= decimals


def printed_as_zero(text: str) -> bool:
    """True when the text shows a weight that is exactly zero grams."""
    return re.search(r"(?<![\d.])0\.0 g", text) is not None


def workbook_row(workbook, sheet_name: str, label: str):
    """Return the row whose label cell holds ``label``."""
    import openpyxl

    book = openpyxl.load_workbook(workbook, data_only=True)
    sheet = book[sheet_name]
    for row in sheet.iter_rows():
        if row[1].value == label:
            return row
    raise AssertionError(f"no row labelled {label!r} in {sheet_name}")


# ------------------------------------------------- a weight is never zero


def test_format_weight_keeps_a_sub_gram_weight_nonzero():
    """A real dose never prints as zero at display precision."""
    assert format_weight(0.04) == "0.04 g"
    assert format_weight(0.008) == "0.008 g"
    assert format_weight(0.00001) == "0.00001 g"
    assert format_weight(0) == "0 g"
    assert format_weight(0.5) == "0.5 g"
    assert format_weight(500) == "500 g"


@pytest.mark.parametrize("language", ["en", "es", "fr", "it", "pt"])
def test_format_weight_keeps_the_language_decimal_mark(language):
    """The comma languages still print a comma, and still print no zero."""
    shown = format_weight(0.04, language=language)
    assert shown == ("0.04 g" if language == "en" else "0,04 g")


def test_reading_editions_never_print_a_potent_ingredient_as_zero(tmp_path):
    """Markdown, HTML and PDF all show the leavener it actually weighs."""
    card = synthetic_card()
    assert card.schema_errors() == []

    pdf = tmp_path / "parity.pdf"
    result = export_pdf(card, pdf)
    assert result.ok, result.detail

    for text in (render_markdown(card), render_html(card), extract_pdf_text(pdf)):
        assert "0.04 g" in text
        assert not printed_as_zero(text), text[:600]
    # The scaling column reads 0.008% for the same row, so a zero in the
    # weight column would have contradicted the card on its face.
    assert "0.008%" in render_markdown(card)


def test_workbook_shows_a_potent_ingredient_as_a_nonzero_cell(tmp_path):
    """The stored value is not enough: the cell format must show it too."""
    import openpyxl

    workbook = tmp_path / "parity.xlsx"
    assert export_xlsx(synthetic_card(), workbook).ok

    book = openpyxl.load_workbook(workbook)
    sheet = book["Recipe Card"]
    yeast = next(row for row in sheet.iter_rows() if row[1].value == "i3 · Instant yeast")
    cell = yeast[2]
    assert cell.value == 0.04
    assert displays_nonzero(cell.value, cell.number_format), cell.number_format

"""Focused regression checks for the Miseform reading edition.

Two defects are covered here:

* the ingredient table header must keep a shared column layout, so
  ``SCALING %`` cannot wrap and displace the other labels;
* the reading editions show the process controls that apply, in readable
  prose, and hide the ones the card records as not applicable.

The source card record is never rewritten by the renderers: all eight keys,
their N/A reasons and the validator's verdict stay in the JSON.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from card_model import PROCESS_CONTROL_KEYS, Card, load_card  # noqa: E402
from exporter import export_xlsx  # noqa: E402
from render_html import card_css, render_html  # noqa: E402
from render_markdown import render_markdown  # noqa: E402

EXAMPLE = ROOT / "examples" / "sesame-salt-garnish.card.json"

ALL_NA = {
    key: "N/A - no such step in this card" for key in PROCESS_CONTROL_KEYS
}


@pytest.fixture()
def card() -> Card:
    return load_card(EXAMPLE)


def _card(controls: dict[str, str]) -> Card:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["process_controls"] = controls
    return Card(data)


def _mixed_card() -> Card:
    controls = dict(ALL_NA)
    controls["sous_vide"] = "65 C for 45 minutes, then sear 90 seconds"
    controls["combi"] = "170 C for 12 minutes, then rest 5 minutes"
    return _card(controls)


def _workbook_text(card: Card, tmp_path: Path) -> str:
    import openpyxl

    out = tmp_path / "card.xlsx"
    result = export_xlsx(card, out)
    if not result.ok:
        pytest.skip(f"XLSX export unavailable: {result.detail}")
    wb = openpyxl.load_workbook(out)
    return "\n".join(
        str(c.value)
        for row in wb["Recipe Card"].iter_rows()
        for c in row
        if c.value is not None
    )


# ------------------------------------------------------- ingredient header


def test_ingredient_table_declares_a_shared_colgroup(card: Card):
    """Every column width comes from one colgroup, so headers cannot drift."""
    markup = render_html(card)
    assert '<colgroup><col class="c-name"><col class="c-weight">' in markup
    assert '<col class="c-volume"><col class="c-scaling"></colgroup>' in markup


def test_ingredient_header_keeps_all_four_labels_and_numeric_columns(card: Card):
    markup = render_html(card)
    header = re.search(r"<thead>.*?</thead>", markup, re.S)
    assert header is not None
    head = header.group(0)
    assert head.count("<th scope") == 4
    for label in ("Ingredient", "Weight", "Volume", "Scaling %"):
        assert f">{label}</th>" in head
    # The three numeric columns carry the numeric class on the header cell
    # as well as on the body cells, so header and data share an edge.
    assert head.count('class="num"') == 3


def test_template_stylesheet_keeps_the_header_row_on_one_baseline():
    css = card_css()
    assert "table-layout:fixed" in css
    for selector in ("col.c-name", "col.c-weight", "col.c-volume", "col.c-scaling"):
        assert selector in css, f"missing column width for {selector}"
    assert "thead th{white-space:nowrap;vertical-align:bottom}" in css


def test_template_and_rendered_card_agree_on_the_colgroup():
    template = (ROOT / "templates" / "recipe-card.html").read_text(encoding="utf-8")
    assert '<colgroup><col class="c-name">' in template
    assert render_html(load_card(EXAMPLE)).count("<colgroup>") == 1


# ------------------------------------------------------- applicable controls


def test_mixed_card_shows_only_the_applicable_controls():
    card = _mixed_card()
    markup = render_html(card)
    assert "Sous vide" in markup
    assert "65 C for 45 minutes" in markup
    assert "no such step in this card" not in markup


def test_mixed_card_omits_the_not_applicable_controls_from_markdown():
    master = render_markdown(_mixed_card())
    assert "Sous vide" in master
    assert "65 C for 45 minutes" in master
    assert "no such step in this card" not in master


def test_mixed_card_omits_the_not_applicable_controls_from_the_workbook(tmp_path: Path):
    text = _workbook_text(_mixed_card(), tmp_path)
    assert "Sous vide" in text
    assert "65 C for 45 minutes" in text
    assert "no such step in this card" not in text


def test_all_not_applicable_card_hides_the_whole_section():
    card = _card(ALL_NA)
    markup = render_html(card)
    assert "Process controls" not in markup
    assert "PROCESS CONTROLS" not in render_markdown(card)
    # Unresolved operational content stays visible.
    assert "Labeling" in markup
    assert "Holding &amp; storage" in markup


def test_all_not_applicable_card_hides_the_workbook_section(tmp_path: Path):
    text = _workbook_text(_card(ALL_NA), tmp_path)
    assert "PROCESS CONTROLS" not in text
    assert "LABELING" in text


def test_unresolved_control_is_retained_in_every_edition(tmp_path: Path):
    controls = dict(ALL_NA)
    controls["chilling"] = "NEEDS CHEF CONFIRMATION - holding temperature is not established"
    card = _card(controls)
    for text in (render_html(card), render_markdown(card), _workbook_text(card, tmp_path)):
        assert "NEEDS CHEF CONFIRMATION - holding temperature" in text


def test_control_without_a_reason_is_retained_and_fails_validation():
    controls = dict(ALL_NA)
    controls["chilling"] = "N/A"
    card = _card(controls)
    assert any(f.code == "process-control-reason-missing" for f in card.findings())
    assert "Chilling" in render_html(card)


def test_the_record_keeps_every_key_and_its_reason():
    card = _card(ALL_NA)
    assert set(card.process_controls) == set(PROCESS_CONTROL_KEYS)
    for key in PROCESS_CONTROL_KEYS:
        assert card.process_controls[key].startswith("N/A - ")
    assert not [f for f in card.findings() if f.code.startswith("process-control")]


def test_the_example_card_keeps_its_own_controls_and_reasons():
    card = load_card(EXAMPLE)
    assert set(card.process_controls) == set(PROCESS_CONTROL_KEYS)
    for key in PROCESS_CONTROL_KEYS:
        assert card.process_controls[key].startswith("N/A - ")


# ------------------------------------------------- compact ingredient table


def test_example_row_notes_stay_short(card: Card):
    """A row carries preparation, step, proxy marker and the governing measure.

    The source title, URL, ratio, match and proxy status live in the
    supporting note block, so the ingredient table stays a table instead of
    three paragraphs of provenance.
    """
    for ing in card.ingredients:
        notes = str(ing.get("notes") or "")
        assert len(notes) <= 120, f"row {ing.get('row_id')} note is too long: {notes}"
        assert "http" not in notes
        assert "proxy" in notes
        assert "authoritative" in notes


def test_the_full_volume_source_record_still_travels(card: Card):
    """Shortening the rows must not lose the source record."""
    notes = " ".join(str(n.get("text", "")) for n in (card.data.get("notes") or []))
    for token in (
        "kingarthurbaking.com/learn/ingredient-weight-chart",
        "fdc.nal.usda.gov/food-details/173468/nutrients",
        "8.875 g",
        "6 g per US tsp",
        "Proxy status",
    ):
        assert token in notes, f"the source record must state {token!r}"

    for text in (render_markdown(card), render_html(card)):
        assert "Volume research and sources" in text
        assert "kingarthurbaking.com/learn/ingredient-weight-chart" in text

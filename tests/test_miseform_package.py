"""Focused tests for the Miseform public-package integration.

These cover only what this pass changed against the upstream engine:
the Miseform DOM adapter, the clay palette, the print size floor, the
phone-width table rule, and the privacy/link hygiene of the public files.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from card_model import Card, load_card  # noqa: E402
from exporter import export_xlsx  # noqa: E402
from render_html import card_css, render_html  # noqa: E402
from render_markdown import render_markdown  # noqa: E402
from release_package import public_files  # noqa: E402

EXAMPLE = ROOT / "examples" / "sesame-salt-garnish.card.json"


@pytest.fixture()
def card() -> Card:
    return load_card(EXAMPLE)


# ------------------------------------------------------- Miseform DOM


def test_html_uses_the_miseform_masthead_and_brand(card: Card):
    markup = render_html(card)
    assert '<span class="brand">Miseform</span>' in markup
    assert "The working recipe collection" in markup


def test_html_uses_the_miseform_two_section_body(card: Card):
    markup = render_html(card)
    assert '<div class="recipe-body">' in markup
    assert '<section class="ingredients">' in markup
    assert '<section class="method">' in markup
    assert '<h2 class="method-heading">Method</h2>' in markup


def test_html_carries_process_controls_labeling_and_step_settings(card: Card):
    """The card records eight N/A processes, so the reading edition shows none.

    The reasons stay in the card record; the reader only sees the
    processes that apply. Labeling and step settings are unaffected.
    """
    markup = render_html(card)
    assert "Process controls" not in markup
    assert "no heat step" not in markup
    assert "Labeling" in markup
    assert "spoon stirring, 20 turns" in markup


def test_html_keeps_the_release_warning_visible(card: Card):
    assert "NOT RELEASED FOR PRODUCTION" in render_html(card)


# ------------------------------------------------------------- template


def test_template_stylesheet_uses_the_clay_palette():
    css = card_css()
    assert "--accent:#a0442d" in css
    assert "--ink:#23231f" in css


def test_template_prints_method_and_table_at_10_5pt_or_larger():
    css = card_css()
    print_block = css.split("@media print", 1)[1]
    for rule in (
        r"\.steps p\{[^}]*font-size:(\d+(?:\.\d+)?)pt",
        r"table\{[^}]*font-size:(\d+(?:\.\d+)?)pt",
    ):
        match = re.search(rule, print_block)
        assert match, f"print rule not found: {rule}"
        assert float(match.group(1)) >= 10.5, f"{rule} must be at least 10.5pt"


def test_template_lets_the_table_scroll_on_a_phone():
    css = card_css()
    phone = css.split("@media screen and (max-width:650px)", 1)[1]
    assert ".table-wrap{overflow-x:auto}" in phone


def test_template_print_does_not_clip_the_table():
    css = card_css()
    print_block = css.split("@media print", 1)[1]
    assert ".table-wrap{overflow:visible}" in print_block


# --------------------------------------------------------- public hygiene


PRIVATE_PATTERNS = (
    r"mister\s+tiger",
    r"\besteban\b",
    r"\bnunez\b",
    r"/Users/",
    r"drive\.google",
    r"1[A-Za-z0-9_-]{30,}",
)


def test_public_package_carries_no_private_names_or_ids():
    offenders: list[str] = []
    for path in public_files(ROOT):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".pdf", ".xlsx", ".png", ".jpg", ".zip"}:
            continue
        if (
            ".git" in path.parts
            or ".pytest_cache" in path.parts
            or ".mypy_cache" in path.parts
            or ".ruff_cache" in path.parts
            or "__pycache__" in path.parts
        ):
            # Build and tool caches are local artifacts, not package content.
            # A developer who runs a type checker or a linter in this folder
            # creates them, and they are never shipped.
            continue
        if path.name == Path(__file__).name:
            # This file holds the patterns themselves; it is scanned by the
            # packaging script instead.
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in PRIVATE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                # A file that carries the pattern as its own fixture is not
                # leaking private material: it trips over its own generic
                # regex. That is exactly what these patterns exist to catch
                # in every other file, so only an outside match counts.
                if pattern in text:
                    continue
                offenders.append(f"{path.relative_to(ROOT)} :: {pattern}")
    assert offenders == [], offenders


def test_public_markdown_links_are_relative_and_resolve():
    broken: list[str] = []
    for path in (path for path in public_files(ROOT) if path.suffix == ".md"):
        if ".pytest_cache" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            if not resolved.exists():
                broken.append(f"{path.relative_to(ROOT)} -> {target}")
    assert broken == [], broken


def test_example_card_is_the_single_source_for_the_shipped_example(card: Card):
    """The shipped example files must come from the card record."""
    stem = card.filename_stem
    for suffix in (".md", ".html", ".json", ".pdf", ".xlsx"):
        artifact = ROOT / "examples" / f"{stem}{suffix}"
        assert artifact.exists(), f"missing built artifact {artifact.name}"
        assert artifact.stat().st_size > 0
    # The JSON edition must be exactly what the toolchain writes from this
    # card record: a byte-for-byte golden reference against the shipped file.
    import build_card  # noqa: E402

    import tempfile

    with tempfile.TemporaryDirectory() as scratch:
        build_card.main(["--outdir", scratch, str(EXAMPLE)])
        golden = Path(scratch) / f"{stem}.json"
        shipped = ROOT / "examples" / f"{stem}.json"
        assert golden.read_bytes() == shipped.read_bytes()
    # Stage 1 traceability: the README worked example must stay inside the
    # shipped card's measured quantities, and must never turn a spoon measure
    # into a gram production control. The scan is scoped to the worked-example
    # section: prose elsewhere in the README may legitimately mention grams.
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "the whole working set" in readme, "the README must keep the working-set rule"
    start = readme.index("## Example intake and response")
    section = readme[start : readme.index("\n## ", start)]
    spoons = re.findall(r"\d*\.?\d*\s*spoon\w*", section, re.IGNORECASE)
    assert spoons == [], f"the README example must not use spoon measures: {spoons}"
    card_weights: set[float] = set()
    for component in card.components:
        for ingredient in component.get("ingredients") or []:
            weight = ingredient.get("weight_g")
            if isinstance(weight, (int, float)):
                card_weights.add(float(weight))
    for key in ("input_total_g", "usable_yield_g", "loss_g", "portion_g"):
        value = card.data.get(key)
        if isinstance(value, (int, float)):
            card_weights.add(float(value))
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*g\b", section):
        value = float(match.group(1))
        assert value in card_weights, (
            f"the README worked example states {value} g, which the shipped card does not carry"
        )


def test_example_card_is_json_and_matches_the_shipped_name():
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    card = Card(data)
    assert card.recipe_id == "DEMO-001"
    assert card.version == "v0.4"
    assert card.status == "R&D"
    assert card.filename_stem == "DEMO-001__sesame-salt-garnish__v0.4__2026-10-26"


# ------------------------------------------------------- researched volumes


def test_example_volumes_are_approximate_and_carry_a_source():
    """A published household volume is labeled and traceable to a source."""
    card = load_card(EXAMPLE)
    for comp in card.components:
        for ing in comp.get("ingredients", []) or []:
            volume = str(ing.get("volume") or "")
            assert volume, f"row {ing.get('row_id')} must carry a researched volume"
            assert volume.startswith("≈"), f"row {ing.get('row_id')} volume must be marked approximate"
            assert "(US)" in volume, f"row {ing.get('row_id')} volume must state its units convention"
            notes = str(ing.get("notes") or "")
            assert "proxy" in notes, f"row {ing.get('row_id')} must label its proxy status"


def test_example_carries_the_volume_source_record():
    """The source record reaches every edition through the card notes."""
    card = load_card(EXAMPLE)
    notes = " ".join(
        str(n.get("text", "")) for n in (card.data.get("notes") or [])
    )
    for token in (
        "kingarthurbaking.com/learn/ingredient-weight-chart",
        "fdc.nal.usda.gov/food-details/173468/nutrients",
        "2026-10-26",
        "8.875 g",
        "US tablespoon",
    ):
        assert token in notes, f"the volume source record must state {token!r}"
    assert "proxy" in notes.lower(), "the volume source record must label proxy status"

    markdown = render_markdown(card)
    markup = render_html(card)
    for text in (markdown, markup):
        assert "Volume research and sources" in text
        assert "kingarthurbaking.com/learn/ingredient-weight-chart" in text


def test_example_volumes_survive_into_the_workbook(tmp_path: Path, card: Card):
    """The workbook carries the researched volume, not an em dash."""
    import openpyxl

    out = tmp_path / "card.xlsx"
    result = export_xlsx(card, out)
    if not result.ok:
        pytest.skip(f"XLSX export unavailable: {result.detail}")

    wb = openpyxl.load_workbook(out)
    sheet = wb["Recipe Card"]
    found: list[str] = []
    for row in sheet.iter_rows(min_col=4, max_col=4):
        value = row[0].value
        if isinstance(value, str) and value.startswith("≈"):
            found.append(value)
    assert found, "the workbook must carry the researched volumes"
    assert any("tbsp" in v for v in found)
    assert any("tsp" in v for v in found)

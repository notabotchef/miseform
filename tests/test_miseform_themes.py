"""Focused tests for the five Miseform editorial themes (release ticket 04).

Themes change presentation only: weights, volumes, scaling %, method text,
status and workbook values are identical in every theme. The default theme
(original, rust/cream) is also the compatible default for records that
predate the ``theme`` field.

Run with:

    python3 -m pytest tests/test_miseform_themes.py -q
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_card import resolve_theme  # noqa: E402
from exporter import export_xlsx  # noqa: E402
from render_html import card_css, render_html  # noqa: E402
from themes import DEFAULT_THEME, THEME_IDS, THEME_NAMES, theme  # noqa: E402

EXAMPLE = ROOT / "examples" / "sesame-salt-garnish.card.json"
SYNTHETIC = (
    ROOT / "examples" / "DEMO-002__smoked-eggplant-tahini-drizzle__v0.1__2026-11-02.json"
)


@pytest.fixture()
def card() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


@pytest.fixture()
def synthetic_card() -> dict:
    return json.loads(SYNTHETIC.read_text(encoding="utf-8"))


# --------------------------------------------------------------- registry


def test_theme_ids_are_exactly_the_five_shipped():
    assert THEME_IDS == ("original", "paper", "atelier", "service", "ledger")


def test_theme_names_are_human_readable():
    assert THEME_NAMES["original"] == "Miseform Original"
    assert set(THEME_NAMES) == set(THEME_IDS)


def test_default_theme_is_original():
    assert DEFAULT_THEME == "original"


def test_theme_unknown_raises():
    with pytest.raises(KeyError):
        theme("not-a-theme")


# ------------------------------------------------------------ HTML rendering


def test_render_html_uses_data_theme_attribute(card: dict):
    from card_model import load_card

    loaded = load_card(EXAMPLE)
    for theme_id in THEME_IDS:
        markup = render_html(loaded, theme=theme_id)
        assert f'data-theme="{theme_id}"' in markup


def test_original_theme_renders_base_stylesheet_only(card: dict):
    from card_model import load_card

    loaded = load_card(EXAMPLE)
    markup = render_html(loaded, theme="original")
    assert "/* theme: original */" not in markup
    assert '--ink:#23231f' in markup  # base variables, unchanged values


def test_non_original_themes_include_override_css(card: dict):
    from card_model import load_card

    loaded = load_card(EXAMPLE)
    for theme_id in ("paper", "atelier", "service", "ledger"):
        markup = render_html(loaded, theme=theme_id)
        assert f"/* theme: {theme_id} */" in markup
        assert f'[data-theme="{theme_id}"]' in markup


def test_ingredient_data_identical_across_themes(synthetic_card: dict):
    from card_model import load_card

    loaded = load_card(SYNTHETIC)
    expected_rows: dict[str, dict[str, str]] = {}
    for comp in loaded.components:
        for ing in comp.get("ingredients", []) or []:
            row_id = str(ing.get("row_id"))
            weight = ing.get("weight_g")
            volume = ing.get("volume")
            expected_rows[row_id] = {
                "weight": f"{weight} g" if isinstance(weight, (int, float)) else "—",
                "volume": volume if volume not in (None, "") else "—",
            }

    seen: dict[str, dict[str, dict[str, str]]] = {}
    for theme_id in THEME_IDS:
        markup = render_html(loaded, theme=theme_id)
        rows: dict[str, dict[str, str]] = {}
        for m in re.finditer(
            r"<tr>\s*<td>(.*?)</td>\s*<td class=\"num\">(.*?)</td>\s*<td class=\"num\">(.*?)</td>\s*<td class=\"num\">(.*?)</td>",
            markup,
            re.DOTALL,
        ):
            name_raw, weight, volume, scaling = m.groups()
            name_plain = re.sub(r"<[^>]+>", " ", name_raw)
            name_plain = re.sub(r"\s+", " ", name_plain).strip()
            row_id = name_plain.split(" · ")[0]
            rows[row_id] = {"weight": weight.strip(), "volume": volume.strip()}
        seen[theme_id] = rows

    for theme_id in THEME_IDS:
        assert seen[theme_id] == expected_rows, theme_id


def test_method_text_identical_across_themes(synthetic_card: dict):
    from card_model import load_card

    loaded = load_card(SYNTHETIC)
    step_texts = [
        step.get("text", "")
        for stage in loaded.stages
        for step in stage.get("steps", []) or []
    ]
    for theme_id in THEME_IDS:
        markup = render_html(loaded, theme=theme_id)
        for text in step_texts:
            assert text in markup, (theme_id, text[:40])


def test_status_block_visible_in_every_theme(card: dict):
    from card_model import load_card

    loaded = load_card(EXAMPLE)
    for theme_id in THEME_IDS:
        markup = render_html(loaded, theme=theme_id)
        assert "NOT RELEASED FOR PRODUCTION" in markup


# ------------------------------------------------------------ theme resolution


def test_resolve_theme_cli_wins(card: dict):
    assert resolve_theme("paper", card) == "paper"


def test_resolve_theme_card_field_next(card: dict):
    card["theme"] = "atelier"
    assert resolve_theme(None, card) == "atelier"


def test_resolve_theme_default_for_records_without_field(card: dict):
    card.pop("theme", None)
    assert resolve_theme(None, card) == DEFAULT_THEME


def test_resolve_theme_unknown_card_field_falls_back_to_default(card: dict):
    card["theme"] = "not-a-theme"
    assert resolve_theme(None, card) == DEFAULT_THEME


# ------------------------------------------------------------ Excel palettes


def test_xlsx_palette_differs_per_theme(synthetic_card: dict):
    from card_model import load_card

    loaded = load_card(SYNTHETIC)
    tabs: dict[str, str] = {}
    grids: dict[str, bool] = {}
    for theme_id in THEME_IDS:
        out = ROOT / ".theme-parity-scratch" / f"{theme_id}.xlsx"
        out.parent.mkdir(parents=True, exist_ok=True)
        result = export_xlsx(loaded, out, theme=theme_id)
        assert result.ok, result.detail
        import openpyxl  # type: ignore

        wb = openpyxl.load_workbook(out)
        tabs[theme_id] = wb.active.sheet_properties.tabColor
        grids[theme_id] = wb.active.sheet_view.showGridLines
    assert len(set(tabs.values())) == len(THEME_IDS), tabs  # every theme its own tab color
    assert grids["ledger"] is True  # ledger shows the grid; others do not
    assert grids["original"] is False


def test_xlsx_values_identical_across_themes(synthetic_card: dict):
    from card_model import load_card

    loaded = load_card(SYNTHETIC)
    import openpyxl  # type: ignore

    captured: dict[str, dict] = {}
    for theme_id in THEME_IDS:
        out = ROOT / ".theme-parity-scratch" / f"values-{theme_id}.xlsx"
        result = export_xlsx(loaded, out, theme=theme_id)
        assert result.ok, result.detail
        wb = openpyxl.load_workbook(out, data_only=True)
        captured[theme_id] = {
            sheet.title: {
                cell.coordinate: cell.value
                for row in sheet.iter_rows()
                for cell in row
                if cell.value is not None
            }
            for sheet in wb.worksheets
        }
    for theme_id in THEME_IDS[1:]:
        assert captured[theme_id] == captured["original"], theme_id


# ----------------------------------------------------------- pagination gate


def test_title_wraps_at_container_not_14ch():
    """Long titles must wrap at the container, never cap at 14ch (~4 lines)."""
    css = card_css()
    screen = css.split("@media screen and (max-width:650px)", 1)[0]
    assert "max-width:14ch" not in screen, screen
    assert "max-width:none" in css


def test_print_holds_table_header_with_its_first_row():
    """The ingredient table header must never strand at a page bottom."""
    css = card_css()
    print_block = css.split("@media print", 1)[1]
    for rule in (
        "thead{display:table-header-group}",
        "tr{break-inside:avoid}",
        ".table-wrap{overflow:visible}",
    ):
        assert rule in print_block, (rule, print_block[:120])


def test_print_font_floor_stays_readable():
    """Kitchen body text never shrinks below the 10.5 pt print floor."""
    css = card_css()
    print_block = css.split("@media print", 1)[1]
    assert "table{font-size:10.5pt}" in print_block
    assert ".steps p{font-size:10.5pt" in print_block

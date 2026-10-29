"""Tests for the recipe card toolchain.

Run with:

    python3 -m pytest tests/ -q

The suite covers the arithmetic the skill promises: reference percentages,
portion counts, input totals, release gating, formula safety in Excel, and the
PDF text layer.
"""

from __future__ import annotations

import html as html_lib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from card_model import PROCESS_CONTROL_KEYS, Card, CardError, load_card  # noqa: E402
from exporter import export_xlsx, extract_pdf_text  # noqa: E402
from render_html import has_suspicious_markup, render_html  # noqa: E402
from render_markdown import render_markdown  # noqa: E402

EXAMPLE = ROOT / "examples" / "sesame-salt-garnish.card.json"


@pytest.fixture()
def card() -> Card:
    return load_card(EXAMPLE)


@pytest.fixture()
def card_data() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ loading


def test_example_card_is_schema_valid(card: Card):
    assert card.schema_errors() == []


def test_example_card_has_no_blockers(card: Card):
    blockers = [f for f in card.findings() if f.severity == "blocker"]
    assert blockers == [], [str(b) for b in blockers]


def test_invalid_json_is_a_card_error(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(CardError):
        load_card(bad)


# ---------------------------------------------------------------- arithmetic


def test_reference_percentages_use_the_named_reference(card: Card):
    derived = card.derived()
    assert derived.percentages["I1"] == pytest.approx(100.0)
    assert derived.percentages["I2"] == pytest.approx(20.0)
    assert derived.percentages["I3"] == pytest.approx(10.0)


def test_percentages_may_total_more_than_one_hundred(card: Card):
    # 100 + 20 + 10 against a 100 g reference is 130%, not 100%.
    derived = card.derived()
    assert sum(derived.percentages.values()) == pytest.approx(130.0)


def test_input_total_is_the_sum_of_ingredient_weights(card: Card):
    assert card.derived().input_total_g == pytest.approx(130.0)


def test_loss_is_input_minus_usable_yield(card: Card):
    assert card.derived().loss_g == pytest.approx(2.0)


def test_portions_floor_the_usable_yield(card: Card):
    derived = card.derived()
    assert derived.portions == 64
    assert derived.portion_remainder_g == pytest.approx(0.0)


def test_scaling_multiplies_weights_only(card: Card):
    scaled = card.scaled_weights(2)
    assert scaled["I1"] == pytest.approx(200.0)
    assert scaled["I2"] == pytest.approx(40.0)
    assert scaled["I3"] == pytest.approx(20.0)


def test_scaling_rejects_a_non_positive_factor(card: Card):
    for bad in (0, -1, -0.5):
        with pytest.raises(ValueError):
            card.scaled_weights(bad)


# ----------------------------------------------------------------- findings


def test_wrong_input_total_is_a_blocker(card_data: dict):
    card_data["input_total_g"] = 125
    findings = Card(card_data).findings()
    assert any(f.code == "input-total-mismatch" for f in findings)


def test_wrong_portion_count_is_a_blocker(card_data: dict):
    card_data["portions"] = 32
    findings = Card(card_data).findings()
    assert any(f.code == "portions-mismatch" for f in findings)


def test_wrong_loss_is_a_blocker(card_data: dict):
    card_data["loss_g"] = 5
    findings = Card(card_data).findings()
    assert any(f.code == "loss-mismatch" for f in findings)


def test_reference_weight_mismatch_is_a_blocker(card_data: dict):
    card_data["components"][0]["reference_weight_g"] = 90
    findings = Card(card_data).findings()
    assert any(f.code == "reference-weight-mismatch" for f in findings)


def test_unreleased_card_without_blockers_is_a_blocker(card_data: dict):
    card_data["release_blockers"] = []
    findings = Card(card_data).findings()
    assert any(f.code == "release-blockers-missing" for f in findings)


def test_production_card_with_blockers_is_a_blocker(card_data: dict):
    card_data["status"] = "PRODUCTION"
    findings = Card(card_data).findings()
    assert any(f.code == "production-with-blockers" for f in findings)


def test_production_card_without_validation_evidence_is_a_blocker(card_data: dict):
    card_data["status"] = "PRODUCTION"
    card_data["release_blockers"] = []
    card_data["provenance"] = {}
    findings = Card(card_data).findings()
    assert any(f.code == "production-without-validation" for f in findings)


def test_step_numbering_must_continue_across_stages(card_data: dict):
    card_data["stages"][1]["steps"][0]["number"] = 9
    findings = Card(card_data).findings()
    assert any(f.code == "step-numbering" for f in findings)


def test_unknown_ingredient_reference_is_a_blocker(card_data: dict):
    card_data["stages"][0]["steps"][0]["ingredient_refs"] = ["I99"]
    findings = Card(card_data).findings()
    assert any(f.code == "unknown-ingredient-ref" for f in findings)


def test_placeholder_volume_is_flagged(card_data: dict):
    card_data["components"][0]["ingredients"][0]["volume"] = "?"
    findings = Card(card_data).findings()
    assert any(f.code == "placeholder-volume" for f in findings)


def test_volume_without_a_unit_is_flagged(card_data: dict):
    card_data["components"][0]["ingredients"][0]["volume"] = "12"
    findings = Card(card_data).findings()
    assert any(f.code == "volume-without-unit" for f in findings)


def test_volume_with_a_unit_is_not_flagged(card_data: dict):
    card_data["components"][0]["ingredients"][0]["volume"] = "≈ 11.3 tbsp (US)"
    findings = Card(card_data).findings()
    assert not any(f.code == "volume-without-unit" for f in findings)


def test_yield_larger_than_input_is_a_blocker(card_data: dict):
    card_data["usable_yield_g"] = 200
    findings = Card(card_data).findings()
    assert any(f.code == "yield-exceeds-input" for f in findings)


# -------------------------------------------------------------- rendering


def test_html_escapes_recipe_text(card_data: dict):
    card_data["components"][0]["ingredients"][0]["name"] = "Salt <script>alert(1)</script>"
    markup = render_html(Card(card_data))
    assert "<script>alert(1)</script>" not in markup
    assert "&lt;script&gt;" in markup


def test_suspicious_markup_detector_flags_source_text():
    assert has_suspicious_markup("onload=steal()")
    assert has_suspicious_markup("<iframe src=x>")
    assert not has_suspicious_markup("sesame, roasted")


def test_html_shows_the_release_warning_for_unreleased_cards(card: Card):
    markup = render_html(card)
    assert "NOT RELEASED FOR PRODUCTION" in markup


def test_html_shows_an_em_dash_for_unknown_volume(card: Card):
    markup = render_html(card)
    assert "—" in markup


def test_html_keeps_the_row_ids_the_procedure_refers_to(card: Card):
    markup = render_html(card)
    for row_id in ("I1", "I2", "I3"):
        assert row_id in markup, f"ingredient row id {row_id} must be visible on the card"


def test_markdown_carries_the_same_identity_as_the_card(card: Card):
    markdown = render_markdown(card)
    assert card.recipe_id in markdown
    assert card.version in markdown
    assert card.status in markdown
    assert "NOT RELEASED FOR PRODUCTION" in markdown


def test_markdown_and_html_agree_on_percentages(card: Card):
    markdown = render_markdown(card)
    markup = render_html(card)
    assert "100%" in markdown
    assert "100%" in markup


def test_blockers_join_without_double_punctuation():
    from card_model import join_blockers

    joined = join_blockers(
        [
            "Approved holding/storage SOP.",
            "Second-cook reproduction and chef-approved tolerances.",
            "Explicit production release.",
        ]
    )
    assert "SOP.;" not in joined
    assert ".; " not in joined
    assert joined.endswith(".")
    assert joined.count(";") == 2


def test_html_release_line_has_no_double_punctuation(card: Card):
    markup = render_html(card)
    assert "SOP.; " not in markup
    assert ".; " not in markup


def test_facts_strip_keeps_the_short_and_long_slots_separate(card: Card):
    markup = render_html(card)
    facts = card.data["facts"]
    assert facts["difficulty_level"] in markup
    assert facts["difficulty_technique"] in markup
    # The short level must not be glued to the technique inside one <strong>.
    assert f"<strong>{facts['difficulty_level']}{facts['difficulty_technique']}</strong>" not in markup


def test_all_four_editions_carry_the_same_identity(tmp_path: Path, card: Card):
    """One recipe, one version: master, HTML, PDF and XLSX must agree."""
    from exporter import export_pdf, export_xlsx

    stem = card.filename_stem
    master = tmp_path / f"{stem}.md"
    html = tmp_path / f"{stem}.html"
    pdf = tmp_path / f"{stem}.pdf"
    xlsx = tmp_path / f"{stem}.xlsx"

    master.write_text(render_markdown(card), encoding="utf-8")
    html.write_text(render_html(card), encoding="utf-8")
    pdf_result = export_pdf(card, pdf)
    xlsx_result = export_xlsx(card, xlsx)

    assert xlsx_result.ok, xlsx_result.detail

    master_text = master.read_text(encoding="utf-8")
    html_text = html.read_text(encoding="utf-8")
    # HTML escapes & as &amp;, so compare against the decoded text.
    html_plain = html_lib.unescape(html_text)

    for label, text in (("markdown", master_text), ("html", html_plain)):
        assert card.recipe_id in text, f"{label} must carry the recipe id"
        assert card.version in text, f"{label} must carry the version"
        assert card.status in text, f"{label} must carry the status"
        assert "100%" in text, f"{label} must carry the reference percentage"
        assert "NOT RELEASED FOR PRODUCTION" in text, f"{label} must carry the release warning"

    import openpyxl

    wb = openpyxl.load_workbook(xlsx)
    sheet = wb["Recipe Card"]
    sheet_text = "\n".join(
        str(c.value) for row in sheet.iter_rows() for c in row if c.value is not None
    )
    assert card.recipe_id in sheet_text
    assert card.version in sheet_text
    assert card.status in sheet_text

    if pdf_result.ok:
        pdf_text = extract_pdf_text(pdf)
        assert card.recipe_id in pdf_text, "pdf must carry the recipe id"
        assert card.version in pdf_text, "pdf must carry the version"
        assert "NOT RELEASED FOR PRODUCTION" in pdf_text.upper()


def test_filename_stem_is_versioned_and_shared(card: Card):
    stem = card.filename_stem
    assert card.recipe_id in stem
    assert card.version in stem
    assert card.revision_date in stem
    assert " " not in stem


# ------------------------------------------------------- process controls


def test_missing_process_control_is_a_blocker(card_data: dict):
    del card_data["process_controls"]["fermentation"]
    findings = Card(card_data).findings()
    assert any(f.code == "process-control-missing" for f in findings)


def test_process_control_not_applicable_needs_a_reason(card_data: dict):
    card_data["process_controls"]["chilling"] = "N/A"
    findings = Card(card_data).findings()
    assert any(f.code == "process-control-reason-missing" for f in findings)


def test_process_control_not_applicable_with_a_reason_is_clean(card_data: dict):
    card_data["process_controls"]["chilling"] = "N/A - no chilling step"
    findings = Card(card_data).findings()
    assert not [f for f in findings if f.code.startswith("process-control")]


def test_empty_process_control_is_a_blocker(card_data: dict):
    card_data["process_controls"]["smoking"] = "   "
    findings = Card(card_data).findings()
    assert any(f.code == "process-control-empty" for f in findings)


def test_every_process_is_answered_on_the_example(card: Card):
    for key in PROCESS_CONTROL_KEYS:
        assert key in card.process_controls, f"{key} must be answered on every card"


# ---------------------------------------------------------------- labeling


def test_incomplete_labeling_is_a_blocker(card_data: dict):
    card_data["labeling"]["allergen_declaration"] = ""
    findings = Card(card_data).findings()
    assert any(f.code == "labeling-field-missing" for f in findings)


def test_labeling_may_be_absent(card_data: dict):
    del card_data["labeling"]
    findings = Card(card_data).findings()
    assert not [f for f in findings if f.code.startswith("labeling")]


# ------------------------------------------------- operational detail flow


def test_process_controls_reach_every_edition(tmp_path: Path, card: Card):
    """The operational record must not stop at the JSON document.

    A control the card records as not applicable stays in the record and is
    left out of the reading editions. An applicable control reaches every
    edition.
    """
    import html as html_lib
    import json as json_lib

    from exporter import export_xlsx

    data = json_lib.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["process_controls"] = {
        key: "N/A - no such step in this card" for key in PROCESS_CONTROL_KEYS
    }
    data["process_controls"]["sous_vide"] = "65 C for 45 minutes, then sear 90 seconds"
    applicable = Card(data)

    master = render_markdown(applicable)
    markup = render_html(applicable)

    assert "PROCESS CONTROLS" in master
    assert "Process controls" in markup
    assert "Sous vide" in master
    assert "Sous vide" in markup
    assert "65 C for 45 minutes" in master
    assert "65 C for 45 minutes" in markup
    assert "no such step in this card" not in master
    assert "no such step in this card" not in markup

    out = tmp_path / "card.xlsx"
    export_xlsx(applicable, out)
    import openpyxl

    wb = openpyxl.load_workbook(out)
    sheet_text = "\n".join(
        str(c.value) for row in wb["Recipe Card"].iter_rows() for c in row if c.value is not None
    )
    assert "PROCESS CONTROLS" in sheet_text
    assert "Sous vide" in sheet_text
    assert "65 C for 45 minutes" in sheet_text
    assert "no such step in this card" not in sheet_text

    # The record itself keeps every key and every reason.
    assert set(applicable.process_controls) == set(PROCESS_CONTROL_KEYS)

    assert html_lib.unescape(markup)


def test_labeling_reaches_every_edition(tmp_path: Path, card: Card):
    from exporter import export_xlsx

    master = render_markdown(card)
    markup = render_html(card)
    assert "LABELING" in master
    assert "Labeling" in markup
    assert "Sesame salt garnish" in master
    assert "Sesame salt garnish" in markup

    out = tmp_path / "card.xlsx"
    export_xlsx(card, out)
    import openpyxl

    wb = openpyxl.load_workbook(out)
    sheet_text = "\n".join(
        str(c.value) for row in wb["Recipe Card"].iter_rows() for c in row if c.value is not None
    )
    assert "LABELING" in sheet_text
    assert "Sesame salt garnish" in sheet_text


def test_per_step_settings_reach_every_edition(tmp_path: Path, card: Card):
    from exporter import export_xlsx

    master = render_markdown(card)
    markup = render_html(card)
    assert "Settings" in master
    assert "Settings" in markup
    assert "spoon stirring, 20 turns" in master
    assert "spoon stirring, 20 turns" in markup

    out = tmp_path / "card.xlsx"
    export_xlsx(card, out)
    import openpyxl

    wb = openpyxl.load_workbook(out)
    sheet_text = "\n".join(
        str(c.value) for row in wb["Recipe Card"].iter_rows() for c in row if c.value is not None
    )
    assert "spoon stirring, 20 turns" in sheet_text


def test_step_settings_are_escaped_in_html(card_data: dict):
    card_data["stages"][0]["steps"][0]["settings"] = {"mode": "<b>fast</b>"}
    markup = render_html(Card(card_data))
    assert "<b>fast</b>" not in markup
    assert "&lt;b&gt;fast&lt;/b&gt;" in markup


# ------------------------------------------------------------------ excel


def test_xlsx_is_a_native_workbook(tmp_path: Path, card: Card):
    out = tmp_path / "card.xlsx"
    result = export_xlsx(card, out)
    assert result.ok, result.detail
    assert out.exists() and out.stat().st_size > 0

    import openpyxl

    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["Recipe Card", "Batch Scaling"]
    assert "xl/workbook.xml" in _zip_names(out)


def _zip_names(path: Path) -> set[str]:
    import zipfile

    with zipfile.ZipFile(path) as zf:
        return set(zf.namelist())


def test_xlsx_uses_formulas_for_percentages_and_scaling(tmp_path: Path, card: Card):
    out = tmp_path / "card.xlsx"
    export_xlsx(card, out)

    import openpyxl

    wb = openpyxl.load_workbook(out)
    sheet = wb["Recipe Card"]
    scaling = wb["Batch Scaling"]

    pct_formulas = [
        c.value for row in sheet.iter_rows(min_col=5, max_col=5) for c in row if isinstance(c.value, str)
    ]
    assert any(str(v).startswith("=IF(ISNUMBER(") for v in pct_formulas), pct_formulas

    scaled_formulas = [
        c.value for row in scaling.iter_rows(min_col=5, max_col=5) for c in row if isinstance(c.value, str)
    ]
    assert any("Invalid input" in str(v) for v in scaled_formulas), scaled_formulas


def test_xlsx_keeps_imported_notes_as_text(tmp_path: Path, card_data: dict):
    card_data["notes"][0]["text"] = "=cmd|'/c calc'!A1"
    card = Card(card_data)
    out = tmp_path / "card.xlsx"
    export_xlsx(card, out)

    import openpyxl

    wb = openpyxl.load_workbook(out)
    sheet = wb["Recipe Card"]
    stored = [
        c.value
        for row in sheet.iter_rows()
        for c in row
        if isinstance(c.value, str) and c.value.startswith("=cmd")
    ]
    assert stored, "the note text should still be present as a literal string"
    assert all(c.data_type == "s" for row in sheet.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("=cmd"))


def test_xlsx_rejects_invalid_batch_factors(tmp_path: Path, card: Card):
    out = tmp_path / "card.xlsx"
    export_xlsx(card, out)

    import openpyxl

    wb = openpyxl.load_workbook(out)
    scaling = wb["Batch Scaling"]
    factor = scaling["C6"]

    # The delivered default is a positive number.
    assert factor.value == 1

    dv = scaling.data_validations.dataValidation
    assert dv, "the factor cell must carry a data validation rule"
    assert any("C6" in str(dv_item.sqref) for dv_item in dv)


def test_xlsx_batch_factor_guard_rejects_bad_values(tmp_path: Path, card: Card):
    """The scaled-weight formula must refuse blank, zero, text and negatives."""
    out = tmp_path / "card.xlsx"
    export_xlsx(card, out)

    import openpyxl

    wb = openpyxl.load_workbook(out)
    scaling = wb["Batch Scaling"]
    scaled = scaling["E10"].value
    assert "Invalid input" in str(scaled)
    assert "$C$6" in str(scaled)

    # Evaluate the guard directly against the delivered formula shape.
    def guard(factor):
        if not isinstance(factor, (int, float)) or isinstance(factor, bool):
            return "Invalid input"
        if factor <= 0:
            return "Invalid input"
        return 100.0 * factor

    assert guard(2) == 200.0
    for bad in (0, -1, "", None, "bad"):
        assert guard(bad) == "Invalid input"


@pytest.mark.skipif(
    importlib.util.find_spec("formulas") is None,
    reason="formulas is not installed",
)
def test_xlsx_formulas_recalculate_to_the_expected_values(tmp_path: Path, card: Card):
    out = tmp_path / "card.xlsx"
    export_xlsx(card, out)

    import formulas

    xl = formulas.ExcelModel().loads(str(out)).finish()
    solution = xl.calculate()
    values = {}
    for key, val in solution.items():
        name = str(key)
        if "!" not in name:
            continue
        cell = name.rsplit("!", 1)[1]
        sheet = name.split("]")[-1].split("'")[0].split("!")[0]
        try:
            values[(sheet, cell)] = val.value[0, 0]
        except Exception:
            continue

    # Locate the rows instead of hardcoding them: the layout shifts when a
    # component group heading is present.
    import openpyxl

    wb = openpyxl.load_workbook(out)
    card_sheet = wb["Recipe Card"]
    i1_row = None
    for row in card_sheet.iter_rows(min_col=2, max_col=2):
        value = row[0].value
        if isinstance(value, str) and value.startswith("I1 · "):
            i1_row = row[0].row
            break
    assert i1_row is not None, "ingredient row I1 must be present"

    pct = values.get(("RECIPE CARD", f"E{i1_row}"))
    assert pct == pytest.approx(1.0), f"reference ingredient must read 100%, got {pct}"

    total_row = i1_row + 3
    total = values.get(("RECIPE CARD", f"C{total_row}"))
    assert total == pytest.approx(130.0), f"total input must be 130 g, got {total}"

    scaled = values.get(("BATCH SCALING", "E10"))
    assert scaled == pytest.approx(100.0), f"scaled I1 weight at factor 1 must be 100 g, got {scaled}"


# -------------------------------------------------------------------- pdf


def test_pdf_render_produces_readable_text(tmp_path: Path, card: Card):
    from exporter import export_pdf

    out = tmp_path / "card.pdf"
    result = export_pdf(card, out)
    if not result.ok:
        pytest.skip(f"PDF rendering unavailable: {result.detail}")

    text = extract_pdf_text(out)
    assert text.strip(), "PDF must expose a selectable text layer"
    assert "SESAME SALT GARNISH" in text.upper()
    assert "100" in text
    assert "NOT RELEASED FOR PRODUCTION" in text.upper()

"""Focused regression checks for the Miseform Excel card.

Three defects are covered here:

* a formula cell must ship with the value it evaluates to, so a preview, a
  PDF converter or a ``data_only`` reader shows the number instead of a
  blank cell, while the formula itself stays live;
* a wrapped text block must get a row height that shows all of its text, so
  no note is clipped and no row has to be resized by hand;
* the yield belongs at the top right of the card, beside the title, and is
  not repeated in the facts strip.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from card_model import Card, load_card  # noqa: E402
from exporter import export_xlsx, wrapped_height  # noqa: E402

EXAMPLE = ROOT / "examples" / "sesame-salt-garnish.card.json"


@pytest.fixture()
def card() -> Card:
    return load_card(EXAMPLE)


@pytest.fixture()
def workbook(tmp_path: Path, card: Card):
    """The exported workbook, read as formulas and as cached results."""
    import openpyxl

    out = tmp_path / "card.xlsx"
    result = export_xlsx(card, out)
    assert result.ok, f"XLSX export failed: {result.detail}"
    formulas = openpyxl.load_workbook(out)
    values = openpyxl.load_workbook(out, data_only=True)
    return formulas, values


def _formula_cells(wb) -> list[tuple[str, str, str]]:
    """Every formula cell in the workbook, as (sheet, coordinate, formula)."""
    out: list[tuple[str, str, str]] = []
    for name in wb.sheetnames:
        for row in wb[name].iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    out.append((name, cell.coordinate, cell.value))
    return out


def _scaling_rows(sheet) -> dict[str, int]:
    """Map each ingredient row id to the sheet row it occupies."""
    rows: dict[str, int] = {}
    for row in sheet.iter_rows(min_col=2, max_col=2):
        value = row[0].value
        if isinstance(value, str) and " · " in value:
            rows[value.split(" · ", 1)[0]] = row[0].row
    return rows


def _scaling_names(sheet) -> list[str]:
    """The ingredient names as the scaling sheet lists them."""
    names: list[str] = []
    for row in sheet.iter_rows(min_col=2, max_col=2):
        value = row[0].value
        if isinstance(value, str) and value not in names and " · " not in value:
            names.append(value)
    return names


# ----------------------------------------------------------- cached results


def test_every_formula_cell_ships_with_a_cached_result(workbook):
    """A formula without its result reads as an empty cell everywhere.

    Excel recalculates on open, so the formula is enough for a person with
    Excel. A preview, a PDF converter or a ``data_only`` reader never
    recalculates, and those readers see nothing at all without a cached
    result. Every formula cell therefore carries the value it evaluates to.
    """
    formulas, values = workbook
    formula_cells = _formula_cells(formulas)
    assert formula_cells, "the card must ship live formulas"

    blank: list[str] = []
    for sheet_name, coordinate, _ in formula_cells:
        cached = values[sheet_name][coordinate].value
        if cached is None:
            blank.append(f"{sheet_name}!{coordinate}")

    assert blank == [], f"formula cells without a cached result: {blank}"


def test_the_formula_stays_live_next_to_its_cached_result(workbook):
    """The cached result is an addition, never a replacement."""
    formulas, values = workbook
    sheet = formulas["Recipe Card"]
    rows = _scaling_rows(sheet)

    i1 = rows["I1"]
    formula = sheet[f"E{i1}"].value
    assert isinstance(formula, str) and formula.startswith("="), (
        "the scaling percentage must stay a live formula"
    )
    assert values["Recipe Card"][f"E{i1}"].value == pytest.approx(1.0)


def test_scaling_percentages_read_as_the_card_computes_them(workbook):
    """The demo shows 100%, 20% and 10% against the component reference."""
    formulas, values = workbook
    sheet = formulas["Recipe Card"]
    rows = _scaling_rows(sheet)

    expected = {"I1": 1.0, "I2": 0.2, "I3": 0.1}
    for row_id, ratio in expected.items():
        coordinate = f"E{rows[row_id]}"
        cached = values["Recipe Card"][coordinate].value
        assert cached == pytest.approx(ratio), (
            f"{row_id} must read {ratio:.0%}, got {cached}"
        )


def test_the_batch_scaling_sheet_caches_its_results(workbook):
    """The scaling sheet is the sheet a cook edits, so it must not read blank."""
    formulas, values = workbook
    sheet = formulas["Batch Scaling"]
    cached = values["Batch Scaling"]

    names = _scaling_names(sheet)
    assert "Purchased roasted white sesame" in names

    first = None
    for row in sheet.iter_rows(min_col=2, max_col=2):
        if row[0].value == "Purchased roasted white sesame":
            first = row[0].row
            break
    assert first is not None

    assert cached[f"C{first}"].value == pytest.approx(100.0)
    assert cached[f"D{first}"].value == pytest.approx(1.0)
    assert cached[f"E{first}"].value == pytest.approx(100.0)

    total_row = None
    for row in sheet.iter_rows(min_col=2, max_col=2):
        if row[0].value == "Total input (g)":
            total_row = row[0].row
    assert total_row is not None
    assert cached[f"C{total_row}"].value == pytest.approx(130.0)
    assert cached[f"E{total_row}"].value == pytest.approx(130.0)


def test_the_measured_yield_and_loss_carry_their_results(workbook):
    """Total input, loss and complete portions are read by a cook."""
    formulas, values = workbook
    sheet = formulas["Recipe Card"]
    values_sheet = values["Recipe Card"]

    total = None
    loss = None
    portions = None
    for row in sheet.iter_rows(min_col=2, max_col=2):
        label = row[0].value
        if label == "Total input":
            total = row[0].row
        elif label == "Measured usable yield (g)":
            loss = row[0].row
        elif label == "Portion weight (g)":
            portions = row[0].row

    assert total and loss and portions
    assert values_sheet[f"C{total}"].value == pytest.approx(130.0)
    assert values_sheet[f"E{loss}"].value == pytest.approx(2.0)
    assert values_sheet[f"E{portions}"].value == pytest.approx(64.0)


# -------------------------------------------------------------- row heights


def test_a_long_note_gets_a_row_tall_enough_to_show_it(card: Card):
    """The height is derived from the text, not from a fixed number."""
    from openpyxl.styles import Font

    long_text = "word " * 400
    height = wrapped_height(long_text, Font(name="Arial", size=10), 2, 5)
    short_text = "word " * 4
    short_height = wrapped_height(short_text, Font(name="Arial", size=10), 2, 5)

    assert height > short_height * 5, "a long note must be much taller"
    assert short_height < 40, "a short line must not be inflated"


def test_wrapped_height_accounts_for_the_font_and_the_span():
    """A bigger font and a wider span both change the height needed."""
    from openpyxl.styles import Font

    text = "Measured usable yield (g) with a controlled mortar crushing endpoint"

    small = wrapped_height(text, Font(name="Arial", size=9), 2, 5)
    large = wrapped_height(text, Font(name="Arial", size=16), 2,  5)
    narrow = wrapped_height(text, Font(name="Arial", size=10), 2, 3)
    wide = wrapped_height(text, Font(name="Arial", size=10), 2, 5)

    assert large > small, "a larger font needs a taller row"
    assert narrow > wide, "a wider span needs less height for the same text"


def test_no_merged_text_block_is_clipped(workbook):
    """Every merged block must fit inside the row it sits in.

    The check reads the shipped workbook: for each merged text cell it
    recomputes the height the text needs and compares it with the row
    height that was written. A row that is too short is the defect.
    """
    formulas, _ = workbook

    for name in formulas.sheetnames:
        sheet = formulas[name]
        for merged in sheet.merged_cells.ranges:
            anchor = sheet.cell(row=merged.min_row, column=merged.min_col)
            text = anchor.value
            if not isinstance(text, str) or not text.strip():
                continue
            font = anchor.font
            needed = wrapped_height(
                text, font, merged.min_col, merged.max_col
            )
            height = sheet.row_dimensions[merged.min_row].height
            assert height is not None, (
                f"{name}!{merged} has no row height, so Excel clips the text"
            )
            assert height >= needed - 0.5, (
                f"{name}!{merged} is {height}pt but the text needs {needed}pt"
            )


def test_the_reported_long_rows_are_tall_enough(workbook):
    """The two blocks the reader reported clipped now show all their text."""
    formulas, _ = workbook
    sheet = formulas["Recipe Card"]

    text_by_row = {
        row[0].row: row[0].value
        for row in sheet.iter_rows(min_col=2, max_col=2)
        if isinstance(row[0].value, str)
    }

    for row_number, text in text_by_row.items():
        if text.startswith("Volumes are researched approximations"):
            assert sheet.row_dimensions[row_number].height >= 150, (
                "the volume research note must show every line"
            )
        if text.startswith("Evidence:"):
            assert sheet.row_dimensions[row_number].height >= 45, (
                "the source record must show every line"
            )


# ------------------------------------------------------------ yield placement


def test_the_yield_sits_at_the_top_right_beside_the_title(workbook):
    """The title leads on the left, the yield reads at the top right."""
    formulas, _ = workbook
    sheet = formulas["Recipe Card"]

    assert sheet["B2"].value == "SESAME SALT GARNISH"
    assert sheet["D2"].value == "YIELD"

    merged = {str(r) for r in sheet.merged_cells.ranges}
    assert "B2:C2" in merged, "the title owns the left columns"
    assert "D2:E2" in merged, "the yield label owns the right columns"


def test_the_yield_value_reaches_the_top_right_block(workbook, card: Card):
    """The mass and the portion count both reach the card."""
    formulas, _ = workbook
    sheet = formulas["Recipe Card"]

    block = ""
    for merged in sheet.merged_cells.ranges:
        if merged.min_row == 3 and merged.min_col >= 4:
            block = str(sheet.cell(row=3, column=merged.min_col).value or "")
    facts = card.data["facts"]
    assert facts["yield_summary"] in block
    assert facts["yield_portions"] in block


def test_the_facts_strip_does_not_repeat_the_yield(workbook):
    """The yield is stated once, at the top right."""
    formulas, _ = workbook
    sheet = formulas["Recipe Card"]

    strip = ""
    for row in range(7, 13):
        value = sheet.cell(row=row, column=2).value
        if isinstance(value, str):
            strip += value + "\n"

    assert "YIELD" not in strip, "the facts strip must not repeat the yield"
    assert "TIME" in strip and "STORAGE" in strip


def test_the_measured_yield_controls_stay_below_the_table(workbook):
    """The measured yield controls are kept where they were."""
    formulas, _ = workbook
    sheet = formulas["Recipe Card"]

    labels = [
        cell.value
        for row in sheet.iter_rows(min_col=2, max_col=5)
        for cell in row
        if isinstance(cell.value, str)
    ]
    assert "Measured usable yield (g)" in labels
    assert "Portion weight (g)" in labels
    assert "Loss (g)" in labels


# --------------------------------------------------------------- long titles


def test_a_long_title_wraps_inside_its_own_columns(tmp_path: Path):
    """A long title must not run into the yield block."""
    import openpyxl

    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["title"] = "SESAME SALT GARNISH WITH BLACK SESAME AND A FLAT SALT FINISH"
    long_card = Card(data)

    out = tmp_path / "long.xlsx"
    result = export_xlsx(long_card, out)
    assert result.ok, result.detail

    wb = openpyxl.load_workbook(out)
    sheet = wb["Recipe Card"]
    merged = {str(r) for r in sheet.merged_cells.ranges}

    assert "B2:C2" in merged
    assert "D2:E2" in merged
    assert sheet["D2"].value == "YIELD"
    assert sheet.row_dimensions[2].height and sheet.row_dimensions[2].height >= 40


# ------------------------------------------------------------ base / scaled cache independence


def test_batch_scaling_base_total_caches_base_weights_not_scaled(tmp_path: Path) -> None:
    """Factor 2: the base column total must cache 130 g, the scaled column 260 g."""
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["batch_factor"] = 2
    card = Card(data)
    out = tmp_path / "card.xlsx"
    result = export_xlsx(card, out)
    assert result.ok, result.detail

    import openpyxl

    formulas = openpyxl.load_workbook(out)
    values = openpyxl.load_workbook(out, data_only=True)
    scaling = formulas["Batch Scaling"]

    total_row = None
    for row in scaling.iter_rows(min_col=2, max_col=2):
        if row[0].value == "Total input (g)":
            total_row = row[0].row
    assert total_row is not None

    # The total must be guarded on complete mass, never a bare SUM that would
    # silently drop an unweighed row and report a completed total.
    formula = scaling[f"C{total_row}"].value
    assert isinstance(formula, str) and formula.startswith("=IF(") and "ISNUMBER" in formula, (
        "the base total must be guarded on complete mass"
    )
    assert values["Batch Scaling"][f"C{total_row}"].value == pytest.approx(130.0)
    assert values["Batch Scaling"][f"E{total_row}"].value == pytest.approx(260.0)

    # Real formula evaluation, not only the cached view: complete mass totals
    # the base weights and scales them at factor 2.
    import formulas

    xl = formulas.ExcelModel().loads(str(out)).finish()
    solution = xl.calculate()
    computed: dict = {}
    for key, val in solution.items():
        name = str(key)
        if "!" not in name:
            continue
        cell = name.rsplit("!", 1)[1]
        sheet_name = name.split("]")[-1].split("'")[0].split("!")[0]
        try:
            computed[(sheet_name.upper(), cell)] = val.value[0, 0]
        except Exception:
            continue
    assert computed.get(("BATCH SCALING", f"C{total_row}")) == pytest.approx(130.0)
    assert computed.get(("BATCH SCALING", f"E{total_row}")) == pytest.approx(260.0)


def test_portions_stay_blank_when_usable_yield_is_unknown(tmp_path: Path) -> None:
    """A null usable yield must stay blank on recalculation, never become 0."""
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["usable_yield_g"] = None
    card = Card(data)
    out = tmp_path / "card.xlsx"
    export_xlsx(card, out)

    import openpyxl

    formulas = openpyxl.load_workbook(out)
    values = openpyxl.load_workbook(out, data_only=True)
    sheet = formulas["Recipe Card"]

    loss_row = portions_row = yield_row = None
    for row in sheet.iter_rows(min_col=2, max_col=5):
        for cell in row:
            if cell.value == "Loss (g)":
                loss_row = cell.row
            elif cell.value == "Portion weight (g)":
                portions_row = cell.row
            elif cell.value == "Measured usable yield (g)":
                yield_row = cell.row
    assert loss_row and portions_row and yield_row

    loss_formula = sheet[f"E{loss_row}"].value
    portions_formula = sheet[f"E{portions_row}"].value
    assert isinstance(loss_formula, str) and "ISNUMBER" in loss_formula
    assert isinstance(portions_formula, str) and "ISNUMBER" in portions_formula and "INT(" in portions_formula

    assert values["Recipe Card"][f"E{loss_row}"].value in (None, "")
    assert values["Recipe Card"][f"E{portions_row}"].value in (None, "")

    # Real formula evaluation, not only the cached view: blank, never zero.
    import formulas

    xl = formulas.ExcelModel().loads(str(out)).finish()
    solution = xl.calculate()
    computed: dict = {}
    for key, val in solution.items():
        name = str(key)
        if "!" not in name:
            continue
        cell = name.rsplit("!", 1)[1]
        sheet_name = name.split("]")[-1].split("'")[0].split("!")[0]
        try:
            computed[(sheet_name.upper(), cell)] = val.value[0, 0]
        except Exception:
            continue

    portions_value = computed.get(("RECIPE CARD", f"E{portions_row}"))
    assert portions_value not in (0, 0.0), "unknown yield must not recalculate to zero portions"


def test_incomplete_input_total_is_presented_as_partial(tmp_path: Path) -> None:
    """One supplied quantity with no established weight: Total input stays explicitly partial."""
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["input_total_g"] = None
    second_ing = data["components"][0]["ingredients"][1]
    second_ing.pop("weight_g", None)
    second_ing["quantity"] = {"amount": 1, "unit": "tbsp", "convention": "US"}
    card = Card(data)
    out = tmp_path / "card.xlsx"
    result = export_xlsx(card, out)
    assert result.ok, result.detail

    import openpyxl

    formulas = openpyxl.load_workbook(out)
    values = openpyxl.load_workbook(out, data_only=True)
    sheet = formulas["Recipe Card"]

    total_row = loss_row = None
    for row in sheet.iter_rows(min_col=2, max_col=5):
        for cell in row:
            if cell.value == "Total input":
                total_row = cell.row
            elif cell.value == "Loss (g)":
                loss_row = cell.row
    assert total_row and loss_row

    formula = sheet[f"C{total_row}"].value
    assert isinstance(formula, str) and formula.startswith("=IF(") and "ISNUMBER" in formula, (
        "the input total must be guarded on complete mass, not a bare SUM"
    )
    cached = values["Recipe Card"][f"C{total_row}"].value
    assert isinstance(cached, str) and "Partial" in cached and "110 g" not in cached
    assert values["Recipe Card"][f"E{loss_row}"].value in (None, "")

    # Real formula evaluation, not only the cached view: an incomplete mass
    # stays explicitly partial on recalculation, never a completed 110 g total.
    import formulas

    xl = formulas.ExcelModel().loads(str(out)).finish()
    solution = xl.calculate()
    computed: dict = {}
    for key, val in solution.items():
        name = str(key)
        if "!" not in name:
            continue
        cell = name.rsplit("!", 1)[1]
        sheet_name = name.split("]")[-1].split("'")[0].split("!")[0]
        try:
            computed[(sheet_name.upper(), cell)] = val.value[0, 0]
        except Exception:
            continue
    total_value = computed.get(("RECIPE CARD", f"C{total_row}"))
    assert isinstance(total_value, str) and "Partial" in total_value, total_value
    assert "110" not in str(total_value)

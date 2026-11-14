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
import shutil
import subprocess
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


def synthetic_card(yeast_g: float | None = 0.04, salt_g: float | None = 10,
                   **overrides) -> Card:
    """A synthetic card: 500 g flour, 10 g salt, 0.04 g instant yeast.

    ``yeast_g`` and ``salt_g`` set the two small weights; ``None`` leaves
    that mass unestablished, which is what an unknown mass looks like on a
    real card. Every other field is overridable.
    """
    ingredients = [{"row_id": "i1", "name": "Flour", "weight_g": 500}]
    if salt_g is None:
        ingredients.append(
            {
                "row_id": "i2",
                "name": "Salt",
                "weight_g": None,
                "quantity": {
                    "amount": 1,
                    "unit": "tsp",
                    "convention": "US",
                    "original": "1 tsp",
                },
            }
        )
    else:
        ingredients.append({"row_id": "i2", "name": "Salt", "weight_g": salt_g})
    if yeast_g is not None:
        ingredients.append(
            {"row_id": "i3", "name": "Instant yeast", "weight_g": yeast_g}
        )

    established = all(row.get("weight_g") is not None for row in ingredients)
    total = sum(
        float(row["weight_g"])
        for row in ingredients
        if row.get("weight_g") is not None
    )

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
                "ingredients": ingredients,
            }
        ],
        "input_total_g": total if established else None,
        "usable_yield_g": 500 if established else None,
        "loss_g": round(total - 500, 2) if established else None,
        "portion_g": 50 if established else None,
        "portions": 10 if established else None,
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
    section = painted_section(number_format, value)
    _, _, fraction = section.partition(".")
    return fraction.count("#") >= decimals


def printed_as_zero(text: str) -> bool:
    """True when the text shows a weight that is exactly zero grams."""
    return re.search(r"(?<![\d.])0\.0 g", text) is not None


def workbook_row(workbook, sheet_name: str, label: str):
    """Return the row that carries ``label`` in any of its label cells."""
    import openpyxl

    book = openpyxl.load_workbook(workbook, data_only=True)
    sheet = book[sheet_name]
    for row in sheet.iter_rows():
        if any(cell.value == label for cell in row[:5]):
            return row
    raise AssertionError(f"no row labelled {label!r} in {sheet_name}")


def shown_number(text: str, label: str) -> float:
    """Read the number a reader sees after ``label`` in an edition."""
    match = re.search(re.escape(label) + r"\s+([0-9]+(?:[.,][0-9]+)?)\s*g", text)
    assert match, f"{label!r} carries no number in:\n{text[:600]}"
    return float(match.group(1).replace(",", "."))


def _condition_holds(condition: str, value: object) -> bool:
    """True when ``value`` satisfies a number format condition."""
    match = re.match(r"^\s*(<=|>=|<|>)?\s*(-?[0-9.eE+-]+)\s*$", condition)
    if match is None:
        return False
    operator = match.group(1) or "="
    bound = float(match.group(2))
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    number = float(value)
    if operator == "<":
        return number < bound
    if operator == "<=":
        return number <= bound
    if operator == ">":
        return number > bound
    if operator == ">=":
        return number >= bound
    return number == bound


def painted_section(number_format: str, value: object) -> str:
    """The part of a number format that paints ``value``.

    A conditional number format carries one section per condition, and the
    sheet picks the section whose condition the cell's value satisfies. A
    formula cell's section is chosen from the value the formula computes,
    so the section that matters is the one the computed value selects.
    """
    sections = number_format.split(";")
    if not sections[0].startswith("["):
        return number_format
    for section in sections:
        condition, _, body = section.partition("]")
        if body and _condition_holds(condition[1:], value):
            return body
    return sections[-1]


def decimal_places(number_format: str, value: object = None) -> int:
    """The decimal places a number format paints for ``value``.

    A format's fraction can carry literal text after the digits - a
    percent sign, a unit - and that text is not a decimal place.
    """
    section = painted_section(number_format, value)
    _, _, fraction = section.partition(".")
    places = 0
    for character in fraction:
        if character in "0#":
            places += 1
        else:
            break
    return places


def displayed_numbers(text: str) -> set[str]:
    """The numbers a reader sees in a rendered edition."""
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def _find_soffice():
    """Where LibreOffice's soffice actually is, or None.

    The same lookup the native workbook checks use: the one on PATH
    first, then the usual install locations, because a headless runner
    often has LibreOffice installed without putting it on PATH.
    """
    found = shutil.which("soffice")
    if found:
        return Path(found)
    for candidate in (
        "/usr/bin/soffice",
        "/usr/local/bin/soffice",
        "/opt/libreoffice/program/soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ):
        path = Path(candidate)
        if path.is_file():
            return path
    return None


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


# --------------------------------- one mass, one number in every edition


def test_the_print_and_the_workbook_show_one_number_for_one_mass(tmp_path):
    """A mass reads as one number in the PDF and in the workbook.

    The card holds 33.333333 g of salt and 0.04 g of yeast. The print
    reads the salt at the one decimal a kitchen reads and keeps the
    yeast's own two digits. The workbook must paint those same two
    numbers, not the stored precision behind them: a cook who scales
    from the PDF and a cook who scales from the workbook have to weigh
    the same salt.

    The workbook is rendered through LibreOffice when the host has it,
    so the check reads what a reader actually sees. Without it the check
    reads the number format the cell carries and compares it with the
    decimals the print shows, so the check still runs on every host
    instead of skipping.
    """
    import openpyxl

    card = synthetic_card(salt_g=33.333333, yeast_g=0.04, loss_g=None)
    assert card.schema_errors() == []

    print_pdf = tmp_path / "print.pdf"
    assert export_pdf(card, print_pdf).ok
    print_text = extract_pdf_text(print_pdf)
    assert shown_number(print_text, "Salt") == 33.3
    assert shown_number(print_text, "Instant yeast") == 0.04
    assert shown_number(print_text, "Input") == 533.4
    assert "33.333333" not in print_text
    assert not printed_as_zero(print_text)

    print_pdf = tmp_path / "print.pdf"
    assert export_pdf(card, print_pdf).ok
    print_text = extract_pdf_text(print_pdf)

    workbook = tmp_path / "parity.xlsx"
    assert export_xlsx(card, workbook).ok
    book = openpyxl.load_workbook(workbook)
    sheet = book["Recipe Card"]
    salt = next(row for row in sheet.iter_rows() if row[1].value == "i2 · Salt")
    yeast = next(row for row in sheet.iter_rows() if row[1].value == "i3 · Instant yeast")
    total = next(row for row in sheet.iter_rows() if row[1].value == "Total input")
    total_value = 500.0 + 33.333333 + 0.04

    # The stored value keeps every digit the cook entered. Only what a
    # reader sees is rounded.
    assert salt[2].value == 33.333333
    assert yeast[2].value == 0.04

    # Each cell paints as many decimals as the print shows for the same
    # mass: one decimal for a mass of a tenth of a gram or more, the
    # stored precision for a smaller one. The total is a formula cell
    # and is held to the same rule.
    assert decimal_places(salt[2].number_format, salt[2].value) == 1
    assert decimal_places(yeast[2].number_format, yeast[2].value) == 19
    # A formula cell's section is chosen from the value the formula
    # computes, so the total is judged on that value, not on the formula
    # text it holds.
    assert decimal_places(total[2].number_format, total_value) == 1
    assert displays_nonzero(yeast[2].value, yeast[2].number_format)

    soffice = _find_soffice()
    if soffice is not None:
        run = subprocess.run(
            [
                str(soffice),
                "-env:UserInstallation=" + (tmp_path / "profile").as_uri(),
                "--headless",
                "--norestore",
                "--convert-to",
                "pdf:calc_pdf_Export",
                "--outdir",
                str(tmp_path),
                str(workbook),
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        assert run.returncode == 0, run.stderr
        numbers = displayed_numbers(extract_pdf_text(tmp_path / "parity.pdf"))
        assert "33.3" in numbers, sorted(numbers)
        assert "0.04" in numbers, sorted(numbers)
        assert "533.4" in numbers, sorted(numbers)
        assert "33.333333" not in numbers, sorted(numbers)


# --------------------------------------------------- source-record labels


def test_markdown_source_record_labels_carry_one_colon():
    """The locale table owns the label text, colon included."""
    markdown = render_markdown(synthetic_card())
    assert "**Evidence:**" in markdown
    assert "**Validation:**" in markdown
    assert "**Filing:**" in markdown
    for label in ("Evidence", "Validation", "Filing"):
        assert f"**{label}::**" not in markdown


@pytest.mark.parametrize("language", ["en", "es", "fr", "it", "pt"])
def test_every_source_record_label_is_written_once_in_every_edition(language, tmp_path):
    """No edition may double or drop the colon of a source-record label."""
    from locales import MESSAGES

    labels = {
        key: table[language]
        for key, table in MESSAGES.items()
        if key.startswith("trace.")
    }
    assert labels

    card = synthetic_card()
    markdown = render_markdown(card, language=language)
    html = render_html(card, language=language)
    workbook = tmp_path / "labels.xlsx"
    assert export_xlsx(card, workbook, language=language).ok

    import openpyxl

    book = openpyxl.load_workbook(workbook, data_only=True)
    sheet_text = "\n".join(
        str(cell.value)
        for row in book["Recipe Card"].iter_rows()
        for cell in row
        if cell.value is not None
    )
    for key, label in labels.items():
        assert label.endswith(":"), (key, label)
        assert f"**{label}**" in markdown, (key, label)
        assert f"{label}:" not in markdown, (key, label)
        assert f"<strong>{label}</strong>" in html, (key, label)
        assert label in sheet_text, (key, label)


# ------------------------------------------------------- the input total


def test_an_absent_declared_total_shows_one_total_in_every_edition(tmp_path):
    """Every mass is established, so the total is known in every edition.

    The card states no input total. The workbook computed one from the
    ingredient weights; the reading editions printed a dash. One record
    must produce one number in all four files.
    """
    card = synthetic_card(yeast_g=None, input_total_g=None, loss_g=None)
    assert card.schema_errors() == []
    assert card.derived().input_complete
    codes = {finding.code for finding in card.findings()}
    assert "input-total-mismatch" not in codes

    pdf = tmp_path / "parity.pdf"
    assert export_pdf(card, pdf).ok
    markdown = render_markdown(card)
    html = render_html(card)
    pdf_text = extract_pdf_text(pdf)

    workbook = tmp_path / "parity.xlsx"
    assert export_xlsx(card, workbook).ok
    total = workbook_row(workbook, "Recipe Card", "Total input")
    loss = workbook_row(workbook, "Recipe Card", "Loss (g)")

    assert total[2].value == 510
    assert loss[4].value == 10
    for text in (markdown, html, pdf_text):
        assert shown_number(text, "Input") == 510
        assert shown_number(text, "Transfer loss") == 10


def test_an_unknown_mass_keeps_every_edition_unknown(tmp_path):
    """No edition may show a total that the other editions cannot show."""
    card = synthetic_card(yeast_g=None, salt_g=None)
    assert card.schema_errors() == []
    assert not card.derived().input_complete

    pdf = tmp_path / "parity.pdf"
    assert export_pdf(card, pdf).ok
    markdown = render_markdown(card)
    html = render_html(card)
    pdf_text = extract_pdf_text(pdf)

    workbook = tmp_path / "parity.xlsx"
    assert export_xlsx(card, workbook).ok
    total = workbook_row(workbook, "Recipe Card", "Total input")

    for text in (markdown, html, pdf_text):
        assert "Input unknown" in text
        assert "Known mass subtotal (partial) 500 g" in text
    assert not isinstance(total[2].value, (int, float)), total[2].value


# --------------------------------------------- a disputed declared total


def test_a_wrong_declared_total_is_one_number_in_every_edition(tmp_path):
    """A declared total that is wrong is a blocked card, not a second truth.

    The card states the total and every edition shows it. The workbook
    must not publish a different number under the same filename stem.
    """
    card = synthetic_card(yeast_g=None, input_total_g=530, loss_g=None)
    codes = {finding.code for finding in card.findings()}
    assert "input-total-mismatch" in codes

    pdf = tmp_path / "parity.pdf"
    assert export_pdf(card, pdf).ok
    markdown = render_markdown(card)
    html = render_html(card)
    pdf_text = extract_pdf_text(pdf)

    workbook = tmp_path / "parity.xlsx"
    assert export_xlsx(card, workbook).ok
    total = workbook_row(workbook, "Recipe Card", "Total input")
    loss = workbook_row(workbook, "Recipe Card", "Loss (g)")

    assert total[2].value == 530
    assert loss[4].value == 30
    for text in (markdown, html, pdf_text):
        assert shown_number(text, "Input") == 530
        assert shown_number(text, "Transfer loss") == 30


def test_the_workbook_names_a_total_it_refuses_to_recalculate(tmp_path):
    """A disagreement the workbook knows about is never silent."""
    from locales import translate

    card = synthetic_card(yeast_g=None, input_total_g=530, loss_g=None)
    workbook = tmp_path / "parity.xlsx"
    assert export_xlsx(card, workbook).ok

    import openpyxl

    book = openpyxl.load_workbook(workbook, data_only=True)
    text = "\n".join(
        str(cell.value)
        for sheet in book
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )
    note = translate("xlsx.input_total_mismatch", "en").format(
        declared=format_weight(530), sum=format_weight(510)
    )
    assert note in text


def test_the_scaling_percentage_is_one_number_in_every_edition(tmp_path):
    """A percentage reads the same in the PDF and in the workbook.

    The workbook holds a ratio and its number format multiplies by a
    hundred at display time; the print holds percentage points. The two
    are the same percentage in different scales, and the editions must
    show the same number for the same ingredient.

    The percentage cell is a formula cell, so its number format has to be
    conditional: a spreadsheet chooses the section from the value the
    formula computes. A fixed format paints the raw ratio and the two
    editions drift apart by a factor of a hundred.
    """
    import openpyxl

    card = synthetic_card(
        salt_g=33.333333,
        yeast_g=0.04,
        loss_g=None,
        percentage_basis={
            "basis_label": "Synthetic basis = 100% = 500 g.",
            "reference_row_id": "i1",
            "reference_weight_g": 500,
        },
    )
    assert card.schema_errors() == []

    print_pdf = tmp_path / "print.pdf"
    assert export_pdf(card, print_pdf).ok
    print_text = extract_pdf_text(print_pdf)

    workbook = tmp_path / "parity.xlsx"
    assert export_xlsx(card, workbook).ok
    book = openpyxl.load_workbook(workbook)
    sheet = book["Recipe Card"]
    salt = next(row for row in sheet.iter_rows() if row[1].value == "i2 · Salt")

    # The percentage cell is the fifth column of the ingredient row.
    percent_cell = salt[4]
    number_format = percent_cell.number_format
    assert number_format.startswith("[<0.001]"), number_format
    assert "[>=0.001]" in number_format, number_format

    # The sheet's cell holds a ratio, so the section it paints is chosen
    # from that ratio: 33.333333 g against a 500 g basis is 0.0666666...,
    # which is at or above the threshold and so reads at one decimal.
    ratio = float(salt[2].value) / 500.0
    assert ratio >= 0.001
    assert painted_section(number_format, ratio).endswith("%")

    # A ratio at or above the threshold reads at one decimal, the way the
    # print reads a percentage at or above a tenth of a percentage point.
    # A ratio below it keeps its own digits, so a tiny percentage never
    # reads as zero.
    assert decimal_places(number_format, 0.5) == 1
    assert decimal_places(number_format, 0.0008) == 13

    soffice = _find_soffice()
    if soffice is not None:
        run = subprocess.run(
            [
                str(soffice),
                "-env:UserInstallation=" + (tmp_path / "profile").as_uri(),
                "--headless",
                "--norestore",
                "--convert-to",
                "pdf:calc_pdf_Export",
                "--outdir",
                str(tmp_path),
                str(workbook),
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        assert run.returncode == 0, run.stderr
        assert run.returncode == 0, run.stderr
        rendered = extract_pdf_text(tmp_path / "parity.pdf")
        # 33.333333 g of salt against a 500 g basis is 6.7%. The workbook
        # must not paint the raw ratio, and must not paint 6.6666666%.
        # The text layer is read here rather than through displayed_numbers,
        # because that helper strips the percent sign off a number.
        assert "6.7%" in rendered, rendered[:2000]
        assert "6.6666666%" not in rendered, rendered[:2000]
        # And the print edition says the same thing about the same mass.
        assert "6.7%" in print_text, print_text[:2000]
        assert "6.6666666%" not in print_text, print_text[:2000]


def test_a_nonzero_weight_never_reads_as_zero(tmp_path):
    """A mass below a nanogram is still a mass, and still reads as one.

    The integrality test that decides whether a mass is a whole number of
    grams must be exact. A tolerance swallows every small mass and prints
    it as zero, which is the one reading a potent ingredient must never
    get.
    """
    for value in (5e-10, 1e-11, 1e-13):
        printed = format_weight(value)
        assert printed != "0 g", (value, printed)
        assert float(printed.split(" ")[0]) != 0.0, (value, printed)

    card = synthetic_card(salt_g=10, yeast_g=5e-10, loss_g=None)
    assert card.schema_errors() == []
    print_pdf = tmp_path / "print.pdf"
    assert export_pdf(card, print_pdf).ok
    print_text = extract_pdf_text(print_pdf)
    assert not printed_as_zero(print_text)


def test_a_live_formula_cell_paints_the_mass_it_computes(tmp_path):
    """A formula cell's format follows the value the formula computes.

    The workbook is a working document: a cook edits an ingredient and the
    total recalculates. The number format cannot be frozen at write time,
    because a frozen format paints the new total with the old rule - and
    a mass of 0.04 g under a one-decimal format reads as 0.0 g.

    Every gram cell therefore carries the same conditional format, and a
    spreadsheet chooses its section from the value the cell computes.
    """
    import openpyxl

    card = synthetic_card(salt_g=33.333333, yeast_g=0.04, loss_g=None)
    assert card.schema_errors() == []

    workbook = tmp_path / "formula.xlsx"
    assert export_xlsx(card, workbook).ok
    book = openpyxl.load_workbook(workbook)
    sheet = book["Recipe Card"]

    total = next(row for row in sheet.iter_rows() if row[1].value == "Total input")
    # The total is a formula cell, so its format is the one conditional
    # format every gram cell carries.
    assert total[2].number_format.startswith("[<0.1]"), total[2].number_format
    assert "[>=0.1]" in total[2].number_format, total[2].number_format

    # The render is checked when the host has LibreOffice. The check above
    # stands on its own, so this test never skips: a skipped test would
    # leave the defect unguarded on the hosts that need it most.
    soffice = _find_soffice()
    if soffice is not None:

        run = subprocess.run(
            [
                str(soffice),
                "-env:UserInstallation=" + (tmp_path / "profile").as_uri(),
                "--headless",
                "--norestore",
                "--convert-to",
                "pdf:calc_pdf_Export",
                "--outdir",
                str(tmp_path),
                str(workbook),
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        assert run.returncode == 0, run.stderr
        numbers = displayed_numbers(extract_pdf_text(tmp_path / "formula.pdf"))
        assert "533.4" in numbers, sorted(numbers)

"""Export a recipe card to PDF and Excel.

PDF is rendered from the card's HTML edition with real selectable text.
Excel is a native ``.xlsx`` workbook whose reference percentages and scaled
weights are live formulas, so the numbers recalculate when a cook edits the
batch factor.

Design rules enforced here, from ``references/exports.md``:

* One recipe, one version, one filename stem across master, PDF and XLSX.
* Percentages are formulas against the named reference weight, never constants.
* An unverified volume is an em dash, never a fabricated conversion.
* The batch factor must be a positive number. Blank, zero, text and negative
  factors produce a visible error instead of plausible-looking weights.
* Imported notes stay text, including strings that begin with ``=``, ``+``,
  ``-`` or ``@``. Only trusted generated formulas become formula cells.
* A measured base yield stays measured at the base batch. Scaled output is
  labelled a projection and never overwrites the actual yield.
* Every formula cell ships with a cached result, so a preview, a PDF
  converter or a ``data_only`` reader shows the number instead of a blank
  cell. The formula stays live and Excel recalculates on open.
* A wrapped text block gets the row height its own text needs, so no note
  is clipped and no row has to be resized by hand.
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess
import textwrap
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from card_model import (
    LABELING_KEYS,
    RELEASE_WARNING,
    Card,
    applicable_process_controls,
    format_quantity,
    format_weight,
    join_blockers,
)
from render_html import render_html

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]

PDF_FORMAT_A4 = "A4"
PDF_FORMAT_LETTER = "Letter"


class ExportError(RuntimeError):
    """An export could not be produced."""


@dataclass
class ExportResult:
    """Outcome of one export."""

    kind: str
    path: Path | None
    ok: bool
    detail: str = ""
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- PDF export


def _find_playwright_chromium() -> str | None:
    """Return the Chromium build Playwright installed, if there is one.

    ``playwright install chromium`` puts the browser in Playwright's own
    cache — not on ``PATH`` and not in the macOS application folder — so the
    exporter asks Playwright where it put it. A browser found this way is
    driven exactly like a system Chrome.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:  # pragma: no cover - environment dependent
        return None
    try:
        with sync_playwright() as p:
            path = p.chromium.executable_path
    except Exception:  # pragma: no cover - environment dependent
        return None
    return path if path and Path(path).exists() else None


def _find_chrome() -> str | None:
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    found = (
        shutil.which("google-chrome")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    if found:
        return found
    return _find_playwright_chromium()


def export_pdf(
    card: Card,
    out_path: Path,
    *,
    paper: str = PDF_FORMAT_A4,
    html_path: Path | None = None,
) -> ExportResult:
    """Render ``card`` to a print-ready PDF with selectable text."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        return ExportResult(
            "pdf",
            None,
            False,
            f"Playwright is not installed, so PDF rendering is unavailable: {exc}",
        )

    chrome = _find_chrome()
    if chrome is None:
        return ExportResult(
            "pdf",
            None,
            False,
            "No Chrome/Chromium executable found, so PDF rendering is unavailable.",
        )

    markup = render_html(card)
    tmp_html = html_path or out_path.with_suffix(".html")
    tmp_html.parent.mkdir(parents=True, exist_ok=True)
    tmp_html.write_text(markup, encoding="utf-8")

    footer = (
        '<div style="font-size:8px;width:100%;text-align:center;color:#57645e">'
        f"{card.recipe_id} · {card.version} · {card.status}"
        ' — <span class="pageNumber"></span> / <span class="totalPages"></span></div>'
    )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=chrome, headless=True)
            try:
                page = browser.new_page()
                page.goto(tmp_html.resolve().as_uri())
                page.pdf(
                    path=str(out_path),
                    format=paper,
                    print_background=True,
                    display_header_footer=True,
                    header_template="<span></span>",
                    footer_template=footer,
                )
            finally:
                browser.close()
    except Exception as exc:
        return ExportResult("pdf", None, False, f"PDF rendering failed: {exc}")

    if not out_path.exists() or out_path.stat().st_size == 0:
        return ExportResult("pdf", None, False, "PDF renderer produced no output.")

    warnings: list[str] = []
    if not extract_pdf_text(out_path).strip():
        warnings.append(
            "PDF text layer could not be confirmed; the file may be rasterized."
        )

    return ExportResult(
        "pdf",
        out_path,
        True,
        f"{paper} PDF, {out_path.stat().st_size} bytes",
        warnings,
    )


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract PDF text. Uses pdftotext when present, else pypdf, else ''."""
    if shutil.which("pdftotext"):
        try:
            out = subprocess.run(
                ["pdftotext", "-layout", str(pdf_path), "-"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if out.returncode == 0:
                return out.stdout
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(pdf_path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""


# --------------------------------------------------------------- Excel export


# Worksheet column widths, in Excel width units (the width of one "0" in the
# default font). The same numbers set the sheet and size the text blocks, so
# a row height always matches the columns it has to fit into.
COLUMN_WIDTHS = {"A": 3, "B": 52, "C": 14, "D": 22, "E": 16, "F": 3}

# Average character width as a fraction of the font size. These are slightly
# pessimistic on purpose: a row that is a little too tall is harmless, a row
# that is too short clips the text.
CHAR_WIDTH_FACTOR = {"Arial": 0.56, "Georgia": 0.60}

# A line of text needs a little more than its point size in row height.
LINE_HEIGHT_FACTOR = 1.32

# Padding inside a merged cell, in points, and the pixels per Excel width
# unit used to convert a column width into printable width.
CELL_PADDING_PT = 8.0
PIXELS_PER_WIDTH_UNIT = 7


def merged_width_pt(start_col: int, end_col: int) -> float:
    """Printable width of a merged span, in points."""
    from openpyxl.utils import get_column_letter

    pixels = 0
    for col in range(start_col, end_col + 1):
        units = COLUMN_WIDTHS.get(get_column_letter(col), 8.43)
        pixels += int(round(units * PIXELS_PER_WIDTH_UNIT)) + 5
    return max(36.0, pixels * 0.75 - CELL_PADDING_PT)


def wrapped_height(text: Any, font: Any, start_col: int, end_col: int) -> float:
    """Row height needed to show ``text`` wrapped across a merged span.

    The estimate is deliberately generous. A note that needs four lines gets
    a row four lines tall, so nothing is clipped and the reader never has to
    drag a row border to read the card.
    """
    body = "" if text is None else str(text)
    if not body.strip():
        return 0.0

    size = float(getattr(font, "sz", None) or getattr(font, "size", None) or 10)
    family = str(getattr(font, "name", None) or "Arial")
    factor = CHAR_WIDTH_FACTOR.get(family, 0.56)
    chars_per_line = max(8, int(merged_width_pt(start_col, end_col) / (size * factor)))

    lines = 0
    for paragraph in body.split("\n"):
        wrapped = textwrap.wrap(
            paragraph, chars_per_line, break_long_words=True, break_on_hyphens=False
        )
        lines += max(1, len(wrapped))

    return round(lines * size * LINE_HEIGHT_FACTOR + 4.0, 1)


def _set_text(cell: Any, value: Any) -> None:
    """Write a value as literal text, never as a formula."""
    text = "" if value is None else str(value)
    cell.value = text
    if text.startswith(("=", "+", "-", "@")):
        cell.data_type = "s"


def _write_cached_results(path: Path, results: dict[str, dict[str, Any]]) -> int:
    """Store the evaluated value of every formula cell inside the workbook.

    openpyxl writes a formula without its result, so a spreadsheet preview,
    a PDF converter or a ``data_only`` reader sees an empty cell where the
    number belongs. The formula stays exactly as generated and the workbook
    still recalculates on open; this only adds the cached value a reader
    needs in order to see the number.
    """
    if not results:
        return 0

    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        entries = {info.filename: archive.read(info.filename) for info in infos}

    workbook_xml = entries.get("xl/workbook.xml", b"").decode("utf-8")
    rels_xml = entries.get("xl/_rels/workbook.xml.rels", b"").decode("utf-8")

    targets: dict[str, str] = {}
    for tag in re.findall(r"<Relationship\b[^>]*/?>", rels_xml):
        rel_id = re.search(r'Id="([^"]+)"', tag)
        target = re.search(r'Target="([^"]+)"', tag)
        if rel_id and target:
            targets[rel_id.group(1)] = target.group(1).lstrip("/")

    sheet_parts: dict[str, str] = {}
    for tag in re.findall(r"<sheet\b[^>]*/?>", workbook_xml):
        name = re.search(r'name="([^"]+)"', tag)
        rel_id = re.search(r'r:id="([^"]+)"', tag)
        if name and rel_id and rel_id.group(1) in targets:
            sheet_parts[name.group(1)] = targets[rel_id.group(1)]

    written = 0
    for sheet_name, cells in results.items():
        part = sheet_parts.get(sheet_name)
        if part is None or part not in entries:
            continue
        xml = entries[part].decode("utf-8")
        for ref, value in cells.items():
            patched = _patch_cell_result(xml, ref, value)
            if patched != xml:
                xml = patched
                written += 1
        entries[part] = xml.encode("utf-8")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for info in infos:
            archive.writestr(info.filename, entries[info.filename])

    return written


def _patch_cell_result(xml: str, ref: str, value: Any) -> str:
    """Return ``xml`` with the cached result of cell ``ref`` filled in."""
    pattern = re.compile(r'<c r="%s"([^>]*)>(.*?)</c>' % re.escape(ref), re.S)
    match = pattern.search(xml)
    if match is None:
        return xml

    attrs, body = match.group(1), match.group(2)
    formula = re.search(r"<f\b[^>]*(?:/>|>.*?</f>)", body, re.S)
    if formula is None:
        return xml

    attrs = re.sub(r'\s+t="[^"]*"', "", attrs)
    if isinstance(value, bool):
        attrs += ' t="b"'
        payload = "1" if value else "0"
    elif isinstance(value, (int, float)):
        payload = f"{value:.10g}"
    else:
        attrs += ' t="str"'
        payload = (
            str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )

    new_body = f"{formula.group(0)}<v>{payload}</v>"
    new_cell = f'<c r="{ref}"{attrs}>{new_body}</c>'
    return xml[: match.start()] + new_cell + xml[match.end() :]


def _yield_text(card: Card, key: str) -> str:
    """One line of the yield block shown at the top right of the card.

    The summary reads first and the portion count sits under it. When the
    card records neither, the line stays empty rather than inventing a
    number.
    """
    facts = card.data.get("facts", {}) or {}
    return str(facts.get(key, "") or "").strip()


def export_xlsx(card: Card, out_path: Path) -> ExportResult:
    """Build the native Excel card for ``card``."""
    try:
        import openpyxl  # type: ignore
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # type: ignore
        from openpyxl.worksheet.datavalidation import DataValidation  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        return ExportResult(
            "xlsx", None, False, f"openpyxl is not installed, so Excel export is unavailable: {exc}"
        )

    teal = "A0442D"
    ink = "23231F"
    pale = "F7F4EE"
    amber = "FBF1E6"
    amber_input = "FFF0B3"

    thin = Side(style="thin", color=teal)
    header_font = Font(name="Arial", size=10, bold=True, color=teal)
    body_font = Font(name="Arial", size=10, color=ink)
    label_font = Font(name="Arial", size=11, bold=True, color=teal)
    title_font = Font(name="Georgia", size=24, color=ink)
    meta_font = Font(name="Arial", size=10, color=ink)
    note_font = Font(name="Arial", size=10, color="68685F")

    wb = openpyxl.Workbook()
    sheet = wb.active
    if sheet is None:  # pragma: no cover - openpyxl always creates one
        return ExportResult("xlsx", None, False, "Excel writer produced no worksheet.")
    sheet.title = "Recipe Card"
    scaling = wb.create_sheet("Batch Scaling")

    for sh in (sheet, scaling):
        sh.sheet_view.showGridLines = False
        sh.sheet_properties.tabColor = teal
        sh.column_dimensions["A"].width = 3
        sh.column_dimensions["B"].width = 52
        sh.column_dimensions["C"].width = 14
        sh.column_dimensions["D"].width = 22
        sh.column_dimensions["E"].width = 16
        sh.column_dimensions["F"].width = 3

    def merged_text(
        sh: Any,
        row: int,
        text: str,
        height: float = 30,
        font: Any = None,
        fill: str | None = None,
        start_col: int = 2,
        end_col: int = 5,
        horizontal: str = "left",
        vertical: str = "center",
    ) -> None:
        """Write a merged text block and give the row the height it needs.

        The height is the greater of the requested minimum and the height the
        text actually needs when it wraps. Excel never auto-fits a merged
        cell, so a row that is too short clips the text and the reader has to
        drag the row border to read the card. Sizing every merged block from
        its own text fixes long notes, source sections and method steps at
        once, not only the rows that happened to be reported.
        """
        from openpyxl.utils import get_column_letter

        start = get_column_letter(start_col)
        end = get_column_letter(end_col)
        sh.merge_cells(f"{start}{row}:{end}{row}")
        cell = sh.cell(row=row, column=start_col)
        _set_text(cell, text)
        cell.alignment = Alignment(
            wrap_text=True, vertical=vertical, horizontal=horizontal
        )
        if font is not None:
            cell.font = font
        if fill:
            for col in range(start_col, end_col + 1):
                sh.cell(row=row, column=col).fill = PatternFill("solid", fgColor=fill)
        needed = wrapped_height(
            text, font if font is not None else body_font, start_col, end_col
        )
        current = sh.row_dimensions[row].height or 0
        sh.row_dimensions[row].height = max(float(height), needed, float(current))

    def heading(sh: Any, row: int, text: str) -> None:
        merged_text(sh, row, text, 28, label_font)
        for col in range(2, 6):
            sh.cell(row=row, column=col).border = Border(bottom=thin)

    facts = card.data.get("facts", {}) or {}
    basis = card.data.get("percentage_basis") or {}

    # The masthead: the title leads on the left, the yield sits top right,
    # where a cook reads it first. Title and yield own separate columns, so a
    # long title wraps inside B:C and never runs into the yield.
    merged_text(sheet, 2, card.title, 40, title_font, end_col=3, vertical="bottom")
    merged_text(
        sheet,
        2,
        "YIELD",
        16,
        Font(name="Arial", size=9, bold=True, color=teal),
        start_col=4,
        end_col=5,
        horizontal="right",
        vertical="bottom",
    )
    merged_text(
        sheet,
        3,
        f"{str(card.data.get('recipe_type', '')).upper()} · {str(card.data.get('library_name', '')).upper()}",
        22,
        Font(name="Arial", size=10, color=teal),
        end_col=3,
        vertical="top",
    )
    merged_text(
        sheet,
        3,
        "\n".join(
            part
            for part in (
                _yield_text(card, "yield_summary"),
                _yield_text(card, "yield_portions"),
            )
            if part
        ),
        22,
        Font(name="Georgia", size=14, color=ink),
        start_col=4,
        end_col=5,
        horizontal="right",
        vertical="top",
    )
    merged_text(sheet, 4, str(card.data.get("intro", "")), 52, meta_font)
    merged_text(sheet, 5, f"{card.recipe_id} · {card.version} · {card.revision_date}", 24, meta_font)

    status_text = card.status
    if not card.is_production:
        status_text = f"{card.status} — {RELEASE_WARNING}"
    if card.release_blockers:
        status_text = f"{status_text}. " + join_blockers(card.release_blockers)
    merged_text(
        sheet,
        6,
        status_text,
        44,
        Font(name="Arial", size=11, color="8A3A22"),
        fill=amber,
    )

    merged_text(
        sheet,
        8,
        f"TIME  {facts.get('time_total', '')} total ({facts.get('time_active', '')} active / "
        f"{facts.get('time_inactive', '')} inactive)"
        f"     DIFFICULTY  {facts.get('difficulty_level', '')} — {facts.get('difficulty_technique', '')}",
        26,
        meta_font,
    )
    # The yield leads the card at the top right. The facts strip keeps the
    # operational facts only, so the yield is never stated twice.
    merged_text(
        sheet,
        9,
        f"STORAGE  {facts.get('storage_summary', '')} — {facts.get('storage_reference', '')}",
        26,
        meta_font,
    )
    merged_text(sheet, 10, f"EQUIPMENT  {card.data.get('equipment', '')}", 44, meta_font)
    merged_text(sheet, 11, f"ALLERGENS  {card.data.get('allergens', '')}", 44, meta_font)

    # Every formula cell also records the value it evaluates to, so the
    # workbook can ship with a cached result a preview or a data_only reader
    # can show. The formula itself stays live and Excel recalculates on open.
    cell_values: dict[tuple[str, str], Any] = {}
    formula_results: dict[str, dict[str, Any]] = {}

    def put(cell: Any, value: Any) -> None:
        """Write a literal value and remember it for cross-sheet references."""
        cell.value = value
        cell_values[(cell.parent.title, cell.coordinate)] = value

    def put_formula(cell: Any, expression: str, value: Any) -> None:
        """Write a formula and remember the result it evaluates to."""
        cell.value = expression
        cell_values[(cell.parent.title, cell.coordinate)] = value
        formula_results.setdefault(cell.parent.title, {})[cell.coordinate] = value

    heading(sheet, 13, "INGREDIENTS")

    # Ingredient table. Reference percentages are formulas against the named
    # reference weight cell of the same component.
    row = 14
    sheet.cell(row=row, column=2, value="Ingredient")
    sheet.cell(row=row, column=3, value="Weight (g)")
    sheet.cell(row=row, column=4, value="Volume")
    sheet.cell(row=row, column=5, value="Scaling %")
    for col in range(2, 6):
        cell = sheet.cell(row=row, column=col)
        cell.font = header_font
        cell.border = Border(bottom=thin)
        cell.alignment = Alignment(horizontal="right" if col >= 3 else "left")
    row += 1

    first_data_row = row
    # Map each ingredient row to the sheet row it occupies, so the Batch
    # Scaling sheet links to the exact cell rather than assuming a layout.
    ingredient_rows: list[tuple[str, int]] = []
    row_weights: dict[int, float] = {}
    weight_sum = 0.0
    resolved = card.resolved_weights()
    for comp in card.components:
        comp_name = str(comp.get("name", ""))
        if isinstance(comp.get("linked"), dict):
            # A linked component is not restated here, so it contributes no
            # row and no mass to this card's totals.
            link = comp.get("linked") or {}
            group_cell = sheet.cell(row=row, column=2)
            _set_text(
                group_cell,
                f"{comp_name} — linked {link.get('component_id')} {link.get('version')}",
            )
            group_cell.font = Font(name="Georgia", size=12, italic=True, color=ink)
            for col in range(3, 6):
                sheet.cell(row=row, column=col).fill = PatternFill("solid", fgColor=pale)
            row += 1
            continue
        # The group heading stays unmerged so the numeric columns remain
        # writable and the SUM range below contains only real cells.
        group_cell = sheet.cell(row=row, column=2)
        _set_text(group_cell, comp_name)
        group_cell.font = Font(name="Georgia", size=12, italic=True, color=ink)
        for col in range(3, 6):
            sheet.cell(row=row, column=col).fill = PatternFill("solid", fgColor=pale)
        row += 1

        ref_row_id = str(comp.get("reference_row_id", ""))
        ingredients = comp.get("ingredients", []) or []
        comp_first_row = row
        ref_cell: str | None = None
        ref_weight: float | None = None
        for ing in ingredients:
            ing_row = row
            row_id = str(ing.get("row_id", ""))
            name_cell = sheet.cell(row=ing_row, column=2)
            _set_text(name_cell, f"{row_id} · {ing.get('name', '')}")
            name_cell.font = body_font
            name_cell.alignment = Alignment(wrap_text=True, vertical="center")

            weight_cell = sheet.cell(row=ing_row, column=3)
            weight = resolved.get(row_id)
            if isinstance(weight, (int, float)):
                put(weight_cell, float(weight))
                weight_cell.number_format = "0.0"
                row_weights[ing_row] = float(weight)
                weight_sum += float(weight)
            else:
                # The mass is not established. An empty cell keeps the SUM
                # honest; a zero would report a mass nobody weighed.
                _set_text(weight_cell, format_quantity(ing.get("quantity")))
                weight_cell.alignment = Alignment(horizontal="right", wrap_text=True)
            weight_cell.font = body_font
            weight_cell.alignment = Alignment(horizontal="right", wrap_text=True)

            volume_cell = sheet.cell(row=ing_row, column=4)
            volume = ing.get("volume")
            _set_text(volume_cell, volume if volume not in (None, "") else "—")
            volume_cell.font = body_font
            volume_cell.alignment = Alignment(horizontal="right", wrap_text=True, vertical="center")

            if row_id == ref_row_id and isinstance(weight, (int, float)):
                ref_cell = f"C{ing_row}"
                ref_weight = float(weight)
            ingredient_rows.append((row_id, ing_row))
            row += 1

        if ref_cell:
            for ing_row in range(comp_first_row, row):
                pct_cell = sheet.cell(row=ing_row, column=5)
                # The numerator is guarded too: a row whose mass was never
                # established holds text, and dividing text would leave a
                # visible error in the sheet instead of an empty cell.
                put_formula(
                    pct_cell,
                    f'=IF(AND(ISNUMBER({ref_cell}),ISNUMBER(C{ing_row})),'
                    f'C{ing_row}/{ref_cell},"")',
                    (row_weights[ing_row] / ref_weight)
                    if ref_weight and ing_row in row_weights
                    else "",
                )
                pct_cell.number_format = "0%"
                pct_cell.font = body_font
                pct_cell.alignment = Alignment(horizontal="right")

    total_row = row
    sheet.cell(row=total_row, column=2, value="Total input")
    put_formula(
        sheet.cell(row=total_row, column=3),
        f"=SUM(C{first_data_row}:C{total_row - 1})",
        weight_sum,
    )
    sheet.cell(row=total_row, column=3).number_format = "0.0"
    sheet.cell(row=total_row, column=4, value="—")
    for col in range(2, 6):
        cell = sheet.cell(row=total_row, column=col)
        cell.fill = PatternFill("solid", fgColor=pale)
        cell.border = Border(bottom=thin)
        if col > 2:
            cell.alignment = Alignment(horizontal="right")
    row = total_row + 2
    merged_text(
        sheet,
        row,
        f"Basis: {basis.get('basis_label', '')}"
        f" Input total {format_weight(card.data.get('input_total_g'))}."
        " Volume not measured is shown as —; weigh ingredients.",
        36,
        Font(name="Georgia", size=10, color="57645E"),
    )
    row += 2

    usable_yield = card.data.get("usable_yield_g")
    sheet.cell(row=row, column=2, value="Measured usable yield (g)")
    put(sheet.cell(row=row, column=3), usable_yield)
    sheet.cell(row=row, column=3).number_format = "0.0"
    sheet.cell(row=row, column=4, value="Loss (g)")
    # Guard the subtraction: with no measured yield the input cell is empty,
    # and an unguarded =C_total-C_yield recalculates in Excel to the full
    # input mass, which would report a fabricated total loss.
    put_formula(
        sheet.cell(row=row, column=5),
        f'=IF(ISNUMBER(C{row}),C{total_row}-C{row},"")',
        weight_sum - float(usable_yield) if usable_yield is not None else "",
    )
    sheet.cell(row=row, column=5).number_format = "0.0"
    yield_row = row
    for col in (2, 3, 4, 5):
        sheet.cell(row=row, column=col).font = body_font
    row += 1

    portion_g = card.data.get("portion_g")
    sheet.cell(row=row, column=2, value="Portion weight (g)")
    put(sheet.cell(row=row, column=3), portion_g)
    sheet.cell(row=row, column=3).number_format = "0.0"
    sheet.cell(row=row, column=4, value="Complete portions")
    complete_portions = (
        int(math.floor(float(usable_yield) / float(portion_g)))
        if usable_yield is not None and portion_g not in (None, 0)
        else ""
    )
    put_formula(
        sheet.cell(row=row, column=5),
        f'=IF(AND(ISNUMBER(C{row}),C{row}>0),INT(C{yield_row}/C{row}),"")',
        complete_portions,
    )
    for col in (2, 3, 4, 5):
        sheet.cell(row=row, column=col).font = body_font
    row += 2

    heading(sheet, row, "GENERAL DIRECTIONS")
    row += 1
    for stage in card.stages:
        merged_text(sheet, row, str(stage.get("name", "")), 25, label_font)
        row += 1
        for step in stage.get("steps", []) or []:
            merged_text(sheet, row, f"{step.get('number')}  {step.get('text', '')}", 44, body_font)
            row += 1
            settings = step.get("settings") or {}
            if isinstance(settings, dict) and settings:
                pairs = [
                    f"{key.replace('_', ' ')} {value}".strip()
                    for key, value in settings.items()
                    if str(value).strip()
                ]
                if pairs:
                    merged_text(
                        sheet,
                        row,
                        f"Settings — {'; '.join(pairs)}",
                        24,
                        note_font,
                    )
                    row += 1
        tip = stage.get("tip")
        if tip:
            merged_text(sheet, row, f"Tip — {tip}", 30, note_font)
            row += 1
        row += 1

    entries = applicable_process_controls(card.process_controls)
    if entries:
        heading(sheet, row, "PROCESS CONTROLS")
        row += 1
        for label, value in entries:
            merged_text(sheet, row, f"{label} — {value}", 30, body_font)
            row += 1
        row += 1

    labeling = card.labeling
    if labeling:
        heading(sheet, row, "LABELING")
        row += 1
        for key in LABELING_KEYS:
            value = str(labeling.get(key, "")).strip()
            if value:
                merged_text(sheet, row, f"{key.replace('_', ' ')} — {value}", 26, body_font)
                row += 1
        row += 1

    for note in card.data.get("notes") or []:
        heading(sheet, row, str(note.get("heading", "")))
        row += 1
        merged_text(sheet, row, str(note.get("text", "")), 44, body_font)
        row += 2

    checklist = list(card.data.get("release_checklist") or []) or list(card.release_blockers)
    if checklist:
        heading(
            sheet,
            row,
            "REQUIRED BEFORE PRODUCTION RELEASE" if not card.is_production else "RELEASE RECORD",
        )
        row += 1
        for item in checklist:
            merged_text(sheet, row, f"• {item}", 30, body_font)
            row += 1
        row += 1

    provenance = card.data.get("provenance") or {}
    if provenance:
        heading(sheet, row, "SOURCE & REVISION RECORD")
        row += 1
        for label, key in (("Evidence", "evidence"), ("Validation", "validation"), ("Filing", "filing")):
            value = provenance.get(key)
            if value:
                merged_text(sheet, row, f"{label}: {value}", 30, note_font)
                row += 1
        row += 1

    # The identity line is a print footer, not a trailing content row. A
    # trailing row lands alone on a page of its own; a footer repeats on every
    # printed page and keeps the card's identity visible without an orphan
    # page.
    sheet.oddFooter.center.text = (
        f"{card.data.get('library_name', '')} · {card.recipe_id} · {card.version} · "
        f"{card.status} · Page &P of &N"
    )
    sheet.oddFooter.center.size = 8
    sheet.oddFooter.center.color = "68685F"
    scaling.oddFooter.center.text = (
        f"{card.data.get('library_name', '')} · {card.recipe_id} · {card.version} · "
        "Batch scaling · Page &P of &N"
    )
    scaling.oddFooter.center.size = 8
    scaling.oddFooter.center.color = "68685F"

    # ------------------------------------------------------- Batch Scaling
    merged_text(scaling, 2, "Batch scaling", 40, title_font)
    merged_text(scaling, 3, f"{card.title} · {card.recipe_id} · {card.version}", 24, meta_font)
    merged_text(
        scaling,
        4,
        (
            "R&D — NOT RELEASED FOR PRODUCTION. Scaling never grants production approval."
            if not card.is_production
            else "Scaling never grants production approval."
        ),
        40,
        Font(name="Arial", size=11, color="8A3A22"),
        fill=amber,
    )

    scaling.cell(row=6, column=2, value="Batch multiplier · edit amber cell")
    scaling.cell(row=6, column=2).font = body_font
    factor_cell = scaling.cell(row=6, column=3)
    factor_cell.value = float(card.data.get("batch_factor", 1) or 1)
    factor_cell.number_format = '0.00"×"'
    factor_cell.font = Font(name="Arial", size=12, color=ink)
    factor_cell.fill = PatternFill("solid", fgColor=amber_input)

    validation = DataValidation(
        type="decimal", operator="greaterThan", formula1="0", allow_blank=False
    )
    validation.error = "Enter a positive number."
    validation.errorTitle = "Invalid input"
    validation.prompt = "Positive multiplier for ingredient weights only."
    validation.promptTitle = "Batch factor"
    scaling.add_data_validation(validation)
    validation.add(factor_cell)

    merged_text(
        scaling,
        7,
        "Enter a positive number. Ingredient weights are calculated; process, capacity and yield still require trial validation.",
        38,
        body_font,
    )

    scale_header_row = 9
    for col, text in enumerate(["Ingredient", "Base (g)", "Scaling %", "Scaled (g)"], start=2):
        cell = scaling.cell(row=scale_header_row, column=col, value=text)
        cell.font = header_font
        cell.border = Border(bottom=thin)
        cell.alignment = Alignment(horizontal="right" if col >= 3 else "left")

    scale_row = scale_header_row + 1
    scale_first = scale_row
    scale_sum = 0.0
    for row_id, card_row in ingredient_rows:
        ing = card.ingredient(row_id) or {}
        name_cell = scaling.cell(row=scale_row, column=2)
        _set_text(name_cell, str(ing.get("name", "")))
        name_cell.font = body_font
        name_cell.alignment = Alignment(wrap_text=True, vertical="center")

        base_weight = row_weights.get(card_row)
        base_cell = scaling.cell(row=scale_row, column=3)
        if base_weight is None:
            # The mass is not established, so there is nothing to scale. The
            # cell shows the quantity the cook gave and the scaled cell says
            # so; a zero would report a mass nobody weighed.
            put_formula(
                base_cell,
                f"='Recipe Card'!C{card_row}",
                format_quantity(ing.get("quantity")),
            )
            base_cell.number_format = "General"
            base_cell.font = body_font
            base_cell.alignment = Alignment(horizontal="right", wrap_text=True)

            pct_cell = scaling.cell(row=scale_row, column=4)
            _set_text(pct_cell, "—")
            pct_cell.font = body_font
            pct_cell.alignment = Alignment(horizontal="right")

            scaled_cell = scaling.cell(row=scale_row, column=5)
            _set_text(scaled_cell, "Pending")
            scaled_cell.font = body_font
            scaled_cell.alignment = Alignment(horizontal="right")
            scale_row += 1
            continue

        put_formula(
            base_cell,
            f"='Recipe Card'!C{card_row}",
            base_weight,
        )
        base_cell.number_format = "0.0"
        base_cell.font = body_font
        base_cell.alignment = Alignment(horizontal="right")

        pct_cell = scaling.cell(row=scale_row, column=4)
        put_formula(
            pct_cell,
            f"='Recipe Card'!E{card_row}",
            cell_values.get(("Recipe Card", f"E{card_row}"), ""),
        )
        pct_cell.number_format = "0%"
        pct_cell.font = body_font
        pct_cell.alignment = Alignment(horizontal="right")

        scaled_cell = scaling.cell(row=scale_row, column=5)
        put_formula(
            scaled_cell,
            f'=IF(ISNUMBER($C$6),IF($C$6>0,C{scale_row}*$C$6,"Invalid input"),"Invalid input")',
            base_weight * float(card.data.get("batch_factor", 1) or 1),
        )
        scaled_cell.number_format = "0.0"
        scaled_cell.font = body_font
        scaled_cell.alignment = Alignment(horizontal="right")
        scale_sum += base_weight * float(card.data.get("batch_factor", 1) or 1)

        scale_row += 1

    scale_total_row = scale_row
    scaling.cell(row=scale_total_row, column=2, value="Total input (g)")
    put_formula(
        scaling.cell(row=scale_total_row, column=3),
        f"=SUM(C{scale_first}:C{scale_total_row - 1})",
        scale_sum,
    )
    scaling.cell(row=scale_total_row, column=3).number_format = "0.0"
    put_formula(
        scaling.cell(row=scale_total_row, column=5),
        (
            f'=IF(ISNUMBER($C$6),IF($C$6>0,SUM(E{scale_first}:E{scale_total_row - 1}),"Invalid input"),'
            '"Invalid input")'
        ),
        scale_sum,
    )
    scaling.cell(row=scale_total_row, column=5).number_format = "0.0"
    for col in range(2, 6):
        cell = scaling.cell(row=scale_total_row, column=col)
        cell.fill = PatternFill("solid", fgColor=pale)
        cell.border = Border(bottom=thin)
        if col > 2:
            cell.alignment = Alignment(horizontal="right")
    scale_row += 2

    heading(scaling, scale_row, "PROCESS LIMITS")
    scale_row += 1
    tested_range = card.data.get("tested_batch_range")
    limits = (f"Tested batch range: {tested_range}. " if tested_range else "") + (
        "Scale ingredient amounts only. Do not scale time, temperature, vessel loading, "
        "mixing, cooling or fermentation automatically. Repeating a tested batch is "
        "different from increasing its load."
    )
    merged_text(scaling, scale_row, limits, 58, body_font)
    scale_row += 1
    merged_text(
        scaling,
        scale_row,
        "Finished yield must be weighed for every batch. Reference yield and portions below remain "
        "fixed to the original trial; scaled output is a projection, not a measured yield.",
        38,
        body_font,
    )
    scale_row += 2

    scaling.cell(row=scale_row, column=2, value="Reference usable yield (g)")
    put_formula(
        scaling.cell(row=scale_row, column=3),
        f"='Recipe Card'!C{yield_row}",
        cell_values.get(("Recipe Card", f"C{yield_row}"), ""),
    )
    scaling.cell(row=scale_row, column=3).number_format = "0.0"
    scale_row += 1
    scaling.cell(row=scale_row, column=2, value="Reference portion weight (g)")
    put(scaling.cell(row=scale_row, column=3), card.data.get("portion_g"))
    scaling.cell(row=scale_row, column=3).number_format = "0.0"
    scale_row += 1
    scaling.cell(row=scale_row, column=2, value="Reference complete portions")
    put_formula(
        scaling.cell(row=scale_row, column=3),
        f"='Recipe Card'!E{yield_row + 1}",
        cell_values.get(("Recipe Card", f"E{yield_row + 1}"), ""),
    )
    scale_row += 2

    merged_text(
        scaling,
        scale_row,
        "Source quantities: Recipe Card. Amber cell is editable. Blank, zero, negative and text "
        "multipliers produce “Invalid input”.",
        44,
        note_font,
    )

    # Print setup: fit one page wide, unlimited height.
    for sh in (sheet, scaling):
        sh.page_setup.orientation = "portrait"
        sh.page_setup.fitToWidth = 1
        sh.page_setup.fitToHeight = 0
        setup_props = sh.sheet_properties.pageSetUpPr
        if setup_props is not None:
            setup_props.fitToPage = True
        sh.page_margins.left = 0.4
        sh.page_margins.right = 0.4
        sh.page_margins.top = 0.5
        sh.page_margins.bottom = 0.5

    # The card sheet is one continuous document, not a repeating table, so no
    # title row is repeated across pages: a repeated ingredient header would
    # sit above the method and labeling sections and mislabel them. The print
    # area covers the written content only, so no empty tail page prints.
    sheet.print_area = f"B2:E{sheet.max_row}"
    scaling.print_area = f"B2:E{scaling.max_row}"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        wb.save(out_path)
    except Exception as exc:
        return ExportResult("xlsx", None, False, f"Excel export failed: {exc}")

    if not out_path.exists() or out_path.stat().st_size == 0:
        return ExportResult("xlsx", None, False, "Excel writer produced no output.")

    # Store the value every formula evaluates to beside the formula, so a
    # preview, a PDF converter or a data_only reader shows the number. The
    # formulas stay live and the workbook still recalculates on open.
    try:
        cached = _write_cached_results(out_path, formula_results)
    except Exception as exc:
        return ExportResult(
            "xlsx",
            None,
            False,
            f"Excel export failed while caching formula results: {exc}",
        )

    detail = f"native xlsx, {out_path.stat().st_size} bytes"
    if cached != sum(len(cells) for cells in formula_results.values()):
        detail += f" ({cached} formula results cached)"

    return ExportResult("xlsx", out_path, True, detail)


__all__ = [
    "ExportError",
    "ExportResult",
    "export_pdf",
    "export_xlsx",
    "extract_pdf_text",
    "PDF_FORMAT_A4",
    "PDF_FORMAT_LETTER",
]

'''Export a recipe card to PDF and Excel.

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
* Workbook labels are localized per the cook's language; formulas, cell
  references and cached numbers are never translated, so a localized label
  never breaks a formula or a reference.
'''

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
    GRAM_EPSILON,
    LABELING_KEYS,
    RELEASE_WARNING,
    Card,
    applicable_process_controls,
    format_quantity,
    format_weight,
    input_mass_label,
    join_blockers,
    row_weight_label,
    weight_display,
)
from translation import display_controls, display_release, display_settings, display_translation, recipe_field
from locales import (  # noqa: E402
    DEFAULT_LANGUAGE as _LOCALE_DEFAULT,
    note_text,
    recipe_text,
    step_text,
    translate,
)
from render_html import render_html
from themes import DEFAULT_THEME as _DEFAULT_THEME, theme as _resolve_theme

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


# Every gram cell in the workbook carries ONE number format, and every
# percentage cell carries its own. Both are conditional, so the branch is
# chosen from the cell's computed value at recalculation time.
#
# A mass of a tenth of a gram or more reads at one decimal, which is the
# scale a kitchen reads. A smaller mass keeps its stored precision, so a
# potent ingredient never reads as zero.
#
# The reading editions are bounded by the same depths, so the PDF and the
# workbook show the same digits for the same mass. The format strings stay
# short on purpose: a very long one makes Calc drop the percent sign and
# paint the bare ratio instead of the percentage.
MASS_FORMAT = "[<0.1]" + "0.0" + "#" * 18 + ";[>=0.1]0.0"
PERCENT_FORMAT = "[<0.001]" + "0.0" + "#" * 12 + "%;[>=0.001]0.0%"


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
    cache -- not on ``PATH`` and not in the macOS application folder -- so the
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
    theme: str | None = None,
    language: str = _LOCALE_DEFAULT,
    texts: dict[str, Any] | None = None,
) -> ExportResult:
    """Render ``card`` to a print-ready PDF with selectable text.

    ``language`` and ``texts`` flow into the HTML edition, so the PDF carries
    the cook's language: translated labels, localized decimal marks and the
    translated recipe text when a bundle covers it.
    """
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

    markup = render_html(card, theme=theme, language=language, texts=texts)
    tmp_html = html_path or out_path.with_suffix(".html")
    tmp_html.parent.mkdir(parents=True, exist_ok=True)
    tmp_html.write_text(markup, encoding="utf-8")

    footer = (
        '<div style="font-size:8px;width:100%;text-align:center;color:#57645e">'
        f"{card.recipe_id} · {card.version} · {card.status}"
        ' — <span class="pageNumber"></span> / <span class="totalPages\"></span></div>'
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
    """Extract PDF text. Uses pdftotext when present, else pypdf, else ''. """
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
    if value is None:
        attrs += ' t="str"'
        payload = ""
    elif isinstance(value, bool):
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


def export_xlsx(
    card: Card,
    out_path: Path,
    *,
    theme: str | None = None,
    language: str = _LOCALE_DEFAULT,
    texts: dict[str, Any] | None = None,
) -> ExportResult:
    """Build the native Excel card for ``card``.

    ``language`` selects the cook language for rendered labels; numbers,
    formulas and cached results stay locale-neutral, so a localized label
    never breaks a formula or a reference. ``texts`` optionally carries
    translated recipe text for the language.
    """
    try:
        import openpyxl  # type: ignore
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # type: ignore
        from openpyxl.worksheet.datavalidation import DataValidation  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        return ExportResult(
            "xlsx", None, False, f"Excel export is unavailable: {exc}"
        )

    palette = _resolve_theme(theme or _DEFAULT_THEME).xlsx
    teal = palette.accent
    ink = palette.ink
    pale = palette.pale
    amber = palette.status_fill
    amber_input = palette.input_fill
    muted = palette.muted
    status_text_c = palette.status_text
    caption_c = palette.caption
    tab_color = palette.tab
    title_font_name = palette.title_font

    thin = Side(style="thin", color=teal)
    header_font = Font(name="Arial", size=10, bold=True, color=teal)
    body_font = Font(name="Arial", size=10, color=ink)
    label_font = Font(name="Arial", size=11, bold=True, color=teal)
    title_font = Font(name=title_font_name, size=24, color=ink)
    meta_font = Font(name="Arial", size=10, color=ink)
    note_font = Font(name="Arial", size=10, color=muted)

    wb = openpyxl.Workbook()
    sheet = wb.active
    if sheet is None:  # pragma: no cover - openpyxl always creates one
        return ExportResult("xlsx", None, False, "Excel writer produced no worksheet.")
    sheet.title = "Recipe Card"
    scaling = wb.create_sheet("Batch Scaling")

    for sh in (sheet, scaling):
        sh.sheet_view.showGridLines = palette.gridlines
        sh.sheet_properties.tabColor = tab_color
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

    texts = display_translation(card, texts)
    facts = card.data.get("facts", {}) or {}
    facts = {key: recipe_text(texts, key, value) for key, value in facts.items()}
    basis = card.data.get("percentage_basis") or {}

    title = recipe_text(texts, "title", card.title)
    intro = recipe_text(texts, "intro", card.data.get("intro", ""))
    allergens = recipe_text(texts, "allergens", card.data.get("allergens", ""))
    basis_label = str(basis.get("basis_label", ""))
    basis_label = recipe_text(texts, "percentage_basis", basis_label)

    # The masthead: the title leads on the left, the yield sits top right,
    # where a cook reads it first. Title and yield own separate columns, so a
    # long title wraps inside B:C and never runs into the yield.
    merged_text(sheet, 2, title, 40, title_font, end_col=3, vertical="bottom")
    merged_text(
        sheet,
        2,
        translate("xlsx.yield", language),
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
        f"{str(card.data.get('recipe_type', '')).upper()} · {str(recipe_text(texts, 'library_name', card.data.get('library_name', ''))).upper()}",
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
                facts.get("yield_summary", ""),
                facts.get("yield_portions", ""),
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
    merged_text(sheet, 4, intro, 52, meta_font)
    merged_text(sheet, 5, f"{card.recipe_id} · {card.version} · {card.revision_date}", 24, meta_font)

    status_text = card.status
    if not card.is_production:
        status_text = f"{card.status} — {translate('status.release_warning', language)}"
    if card.release_blockers:
        status_text = f"{status_text}. " + join_blockers(display_release(card, texts))
    merged_text(
        sheet,
        6,
        status_text,
        44,
        Font(name="Arial", size=11, color=status_text_c),
        fill=amber,
    )

    merged_text(
        sheet,
        8,
        translate("xlsx.time", language).format(
            total=facts.get("time_total", ""),
            active=facts.get("time_active", ""),
            inactive=facts.get("time_inactive", ""),
        )
        + "     "
        + translate("xlsx.difficulty", language)
        + "  "
        + f"{facts.get('difficulty_level', '')} — {facts.get('difficulty_technique', '')}",
        26,
        meta_font,
    )
    merged_text(
        sheet,
        9,
        translate("xlsx.storage", language)
        + "  "
        + f"{facts.get('storage_summary', '')} — {facts.get('storage_reference', '')}",
        26,
        meta_font,
    )
    merged_text(
        sheet, 10, translate("xlsx.equipment", language) + "  " + recipe_text(texts, "equipment", card.data.get("equipment", "")), 44, meta_font
    )
    merged_text(
        sheet, 11, translate("xlsx.allergens", language) + "  " + allergens, 44, meta_font
    )

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

    heading(sheet, 13, translate("xlsx.ingredients", language))

    # Ingredient table. Reference percentages are formulas against the named
    # reference weight cell of the same component.
    row = 14
    sheet.cell(row=row, column=2, value=translate("xlsx.table.ingredient", language))
    sheet.cell(row=row, column=3, value=translate("xlsx.table.weight", language))
    sheet.cell(row=row, column=4, value=translate("xlsx.table.volume", language))
    sheet.cell(row=row, column=5, value=translate("xlsx.table.scaling", language))
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
    ingredient_count = 0
    established_count = 0
    resolved = card.resolved_weights()
    ing_names: dict[str, str] = {}
    ingredient_records = {}
    ingredient_notes = []
    seen_links: set[tuple[str, str]] = set()
    for comp_index, comp in enumerate(card.components):
        comp_name = recipe_field(texts, f"components.{comp_index}.name", str(comp.get("name", "")))
        if isinstance(comp.get("linked"), dict):
            # An allocation is editable mass; the shared formula stays external.
            link = comp.get("linked") or {}
            key = (str(link.get("component_id", "")), str(link.get("version", "")))
            if key in seen_links:
                continue
            seen_links.add(key)
            group_cell = sheet.cell(row=row, column=2)
            _set_text(
                group_cell,
                f"{comp_name} — linked {link.get('component_id')} {link.get('version')}",
            )
            group_cell.font = Font(name="Georgia", size=12, italic=True, color=ink)
            group_cell.alignment = Alignment(wrap_text=True, vertical="top")
            sheet.row_dimensions[row].height = wrapped_height(
                group_cell.value, group_cell.font, 2, 2
            )
            allocation_id = f"__linked_{row}"
            ingredient_rows.append((allocation_id, row))
            ing_names[allocation_id] = str(group_cell.value)
            ingredient_count += 1
            quantity = link.get("quantity_g")
            if isinstance(quantity, (int, float)) and not isinstance(quantity, bool) and math.isfinite(quantity) and quantity > 0:
                put(sheet.cell(row=row, column=3), float(quantity))
                row_weights[row] = float(quantity)
                weight_sum += float(quantity)
                established_count += 1
            else:
                _set_text(sheet.cell(row=row, column=3), "Pending")
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
            allocation_key = f"{comp_index}:{row_id}"
            ingredient_records[allocation_key] = ing
            name = recipe_field(texts, f"components.{comp_index}.ingredients.{row_id}.name", ing.get("name", ""))
            notes = recipe_field(texts, f"components.{comp_index}.ingredients.{row_id}.notes", ing.get("notes", ""))
            ing_names[allocation_key] = name
            if notes:
                ingredient_notes.append(f"{translate('heading.notes', language)} ({row_id}) — {notes}")
            name_cell = sheet.cell(row=ing_row, column=2)
            _set_text(
                name_cell,
                f"{row_id} · {ing_names[allocation_key]}",
            )
            name_cell.font = body_font
            name_cell.alignment = Alignment(wrap_text=True, vertical="center")

            weight_cell = sheet.cell(row=ing_row, column=3)
            weight = resolved.get(row_id)
            if isinstance(weight, (int, float)):
                put(weight_cell, float(weight))
                weight_cell.number_format = MASS_FORMAT
                row_weights[ing_row] = float(weight)
                weight_sum += float(weight)
            else:
                # The mass is not established. An empty cell keeps the SUM
                # honest; a zero would report a mass nobody weighed.
                _set_text(
                    weight_cell, format_quantity(ing.get("quantity"), language)
                )
                weight_cell.alignment = Alignment(horizontal="right", wrap_text=True)
            weight_cell.font = body_font
            weight_cell.alignment = Alignment(horizontal="right", wrap_text=True)

            volume_cell = sheet.cell(row=ing_row, column=4)
            volume = ing.get("volume")
            _set_text(
                volume_cell,
                volume if volume not in (None, "") else "—",
            )
            volume_cell.font = body_font
            volume_cell.alignment = Alignment(horizontal="right", wrap_text=True, vertical="center")

            if row_id == ref_row_id and isinstance(weight, (int, float)):
                ref_cell = f"C{ing_row}"
                ref_weight = float(weight)
            ingredient_rows.append((allocation_key, ing_row))
            ingredient_count += 1
            if isinstance(weight, (int, float)):
                established_count += 1
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
                pct_cell.number_format = PERCENT_FORMAT
                pct_cell.font = body_font
                pct_cell.alignment = Alignment(horizontal="right")

    # Numeric cells may resolve missing masses live, but cannot repair a
    # duplicate allocation or a restated linked formula. Preserve that static
    # model-level ambiguity in formulas and cached values alike.
    input_structure_complete = card.derived().input_structure_complete
    structure_guard = "TRUE" if input_structure_complete else "FALSE"
    partial_input = (translate("xlsx.partial_input", language).format(
        n=established_count, m=ingredient_count) if input_structure_complete
        else translate("xlsx.ambiguous_input", language))
    total_row = row
    sheet.cell(row=total_row, column=2, value=translate("xlsx.total_input", language))
    # The card states the input total; the workbook can also compute one
    # from the weight cells. When the two disagree the card is blocked, and
    # the workbook refuses to publish a second, different total in silence.
    # It shows the total the card states and names the disagreement.
    declared_total = card.derived().declared_input_total_g
    effective_total = card.derived().input_total_known_g
    total_is_complete = (
        input_structure_complete and ingredient_count > 0
        and established_count == ingredient_count
    )
    mismatch_note = ""
    disputed_total: float | None = None
    if (
        declared_total is not None
        and total_is_complete
        and not math.isclose(float(declared_total), weight_sum, abs_tol=GRAM_EPSILON)
    ):
        disputed_total = float(declared_total)
        mismatch_note = translate("xlsx.input_total_mismatch", language).format(
            declared=format_weight(declared_total, language=language),
            sum=format_weight(weight_sum, language=language),
        )
    # A total is honest only when every ingredient mass is established. A row
    # the cook supplied as a quantity in their own unit contributes no weighed
    # mass, so the SUM would silently undercount. Guard the formula and cache
    # an explicit partial subtotal instead of a completed total.
    if disputed_total is not None:
        # The card states a total and the weight cells add up to another one.
        # The stated total is what the reading editions show, so the workbook
        # shows it too instead of a recomputed number under the same filename
        # stem. The disagreement is named in the caption below.
        total_cached: Any = disputed_total
        put(sheet.cell(row=total_row, column=3), total_cached)
    else:
        if ingredient_count > 0:
            guard = "AND(" + structure_guard + "," + ",".join(f"ISNUMBER(C{sheet_row})" for _, sheet_row in ingredient_rows) + ")"
            total_formula = (
                f'=IF({guard},SUM(C{first_data_row}:C{total_row - 1}),'
                f'"{partial_input}")'
            )
            total_cached: Any = (
                weight_sum
                if input_structure_complete and established_count == ingredient_count
                else partial_input
            )
        else:
            total_formula = f'"{translate("xlsx.no_input", language)}"'
            total_cached = translate("xlsx.no_input", language)
        put_formula(
            sheet.cell(row=total_row, column=3),
            total_formula,
            total_cached,
        )
    # The total cell holds a mass when the input is complete and a status
    # when it is not. The format comes from the number the cell holds, so
    # the sheet paints the total the way the print shows it.
    sheet.cell(row=total_row, column=3).number_format = MASS_FORMAT
    sheet.cell(row=total_row, column=4, value="—")
    for col in range(2, 6):
        cell = sheet.cell(row=total_row, column=col)
        cell.fill = PatternFill("solid", fgColor=pale)
        cell.border = Border(bottom=thin)
        if col > 2:
            cell.alignment = Alignment(horizontal="right")
    # Formula results can be long localized partial-status prose. Reserve
    # enough height even for an initially complete total: clearing an input
    # later must not hide the warning behind a numeric-column boundary.
    total_cell = sheet.cell(row=total_row, column=3)
    total_cell.alignment = Alignment(horizontal="right", vertical="top", wrap_text=True)
    partial_text = translate("xlsx.partial_input", language).format(n=established_count, m=ingredient_count)
    sheet.row_dimensions[total_row].height = max(
        wrapped_height(partial_text, total_cell.font, 3, 3),
        wrapped_height(total_cached, total_cell.font, 3, 3),
    )
    row = total_row + 2
    if not card.derived().input_complete:
        sheet.cell(row=row, column=2, value=translate("caption.known_input_subtotal", language))
        put_formula(sheet.cell(row=row, column=3),
                    f'=SUM(C{first_data_row}:C{total_row - 1})', weight_sum)
        sheet.cell(row=row, column=3).number_format = MASS_FORMAT
        row += 2
    caption_note = translate("xlsx.caption_note", language).format(
        basis=basis_label,
        input=input_mass_label(card, language),
    )
    if mismatch_note:
        # A total the card states and the ingredient weights disagree on is
        # never left for the reader to work out: the workbook names both
        # numbers and says which is which.
        caption_note = f"{caption_note} {mismatch_note}"
    merged_text(
        sheet,
        row,
        caption_note,
        36,
        Font(name=palette.body_font, size=10, color=caption_c),
    )
    row += 2

    usable_yield = card.data.get("usable_yield_g")
    sheet.cell(row=row, column=2, value=translate("xlsx.yield_g", language))
    put(sheet.cell(row=row, column=3), usable_yield)
    sheet.cell(row=row, column=3).number_format = MASS_FORMAT
    sheet.cell(row=row, column=4, value=translate("xlsx.loss_g", language))
    # The loss is honest only when the input total itself is complete: with
    # an incomplete total, subtracting the yield would report a fabricated
    # number. The formula guards on ISNUMBER(C_total), so the cached value
    # must guard the same way and stay empty when the total is partial. The
    # loss follows the total the workbook shows, which is the total every
    # other edition shows too.
    total_complete = input_structure_complete and ingredient_count > 0 and established_count == ingredient_count
    loss_cached: Any = (
        effective_total - float(usable_yield)
        if usable_yield is not None and total_complete and effective_total is not None
        else ""
    )
    put_formula(
        sheet.cell(row=row, column=5),
        f'=IF(AND(ISNUMBER(C{total_row}),ISNUMBER(C{row})),C{total_row}-C{row},"")',
        loss_cached,
    )
    # The loss cell paints a mass when the total is complete and nothing
    # when it is not. Its format comes from the number it holds; with an
    # incomplete total the established subtotal minus the yield is the best
    # estimate of the mass the cell will show once the input is complete.
    sheet.cell(row=row, column=5).number_format = MASS_FORMAT
    yield_row = row
    for col in (2, 3, 4, 5):
        sheet.cell(row=row, column=col).font = body_font
    row += 1

    portion_g = card.data.get("portion_g")
    sheet.cell(row=row, column=2, value=translate("xlsx.portion_g", language))
    put(sheet.cell(row=row, column=3), portion_g)
    sheet.cell(row=row, column=3).number_format = MASS_FORMAT
    sheet.cell(row=row, column=4, value=translate("xlsx.complete_portions", language))
    complete_portions = (
        int(math.floor(float(usable_yield) / float(portion_g)))
        if usable_yield is not None and portion_g not in (None, 0)
        else ""
    )
    put_formula(
        sheet.cell(row=row, column=5),
        f'=IF(AND(ISNUMBER(C{yield_row}),ISNUMBER(C{row}),C{row}>0),INT(C{yield_row}/C{row}),"")',
        complete_portions,
    )
    for col in (2, 3, 4, 5):
        sheet.cell(row=row, column=col).font = body_font
    row += 2

    # Operational notes remain visible outside numeric/formula row ranges.
    for note in ingredient_notes:
        merged_text(sheet, row, note, 30, note_font)
        row += 1
    if ingredient_notes:
        row += 1
    heading(sheet, row, translate("heading.directions", language))
    row += 1
    for stage_index, stage in enumerate(card.stages):
        stage_name = recipe_text(texts, f"stage.{stage_index}.name", stage.get("name", ""))
        merged_text(sheet, row, stage_name, 25, label_font)
        row += 1
        for step in stage.get("steps", []) or []:
            merged_text(
                sheet,
                row,
                f"{step.get('number')}  {step_text(texts, stage_index, step.get('number'), step.get('text', ''))}",
                44,
                body_font,
            )
            row += 1
            settings = step.get("settings") or {}
            if isinstance(settings, dict) and settings:
                pairs = [
                    f"{key} {value}".strip()
                    for key, value in display_settings(texts, stage_index, step)
                    if str(value).strip()
                ]
                if pairs:
                    merged_text(
                        sheet,
                        row,
                        f"{translate('settings.label', language)}{'; '.join(pairs)}",
                        24,
                        note_font,
                    )
                    row += 1
        tip = recipe_field(texts, f"stages.{stage_index}.tip", stage.get("tip"))
        if tip:
            merged_text(sheet, row, f"{translate('tip.label', language)}{tip}", 30, note_font)
            row += 1
        row += 1

    entries = display_controls(card, texts, language)
    if entries:
        heading(sheet, row, translate("xlsx.process_controls", language))
        row += 1
        for label, value in entries:
            merged_text(sheet, row, f"{label} — {value}", 30, body_font)
            row += 1
        row += 1

    labeling = card.labeling
    if labeling:
        heading(sheet, row, translate("xlsx.labeling", language))
        row += 1
        for key in LABELING_KEYS:
            value = recipe_field(texts, f"labeling.{key}", str(labeling.get(key, "")).strip())
            if value:
                merged_text(
                    sheet,
                    row,
                    f"{translate(f'labeling.{key}', language)} — {value}",
                    26,
                    body_font,
                )
                row += 1
        row += 1

    for index, note in enumerate(card.data.get("notes") or []):
        heading_text, note_text_value = note_text(texts, index, note.get("heading", ""), str(note.get("text", "")))
        heading(sheet, row, heading_text)
        row += 1
        merged_text(sheet, row, note_text_value, 44, body_font)
        row += 2

    checklist = display_release(card, texts, checklist=True)
    if checklist:
        heading(
            sheet,
            row,
            translate("heading.release_before", language)
            if not card.is_production
            else translate("heading.release_record", language),
        )
        row += 1
        for item in checklist:
            merged_text(sheet, row, f"• {item}", 30, body_font)
            row += 1
        row += 1

    provenance = card.data.get("provenance") or {}
    if provenance:
        heading(sheet, row, translate("xlsx.source_record", language))
        row += 1
        for label, key in (("Evidence", "evidence"), ("Validation", "validation"), ("Filing", "filing")):
            value = recipe_field(texts, f"provenance.{key}", provenance.get(key))
            if value:
                merged_text(sheet, row, f"{translate(f'trace.{key}', language)} {value}", 30, note_font)
                row += 1
        row += 1

    # The identity line is a print footer, not a trailing content row. A
    # trailing row lands alone on a page of its own; a footer repeats on every
    # printed page and keeps the card's identity visible without an orphan
    # page.
    sheet.oddFooter.center.text = (
        f"{recipe_text(texts, 'library_name', card.data.get('library_name', ''))} · {card.recipe_id} · {card.version} · "
        f"{card.status} · Page &P of &N"
    )
    sheet.oddFooter.center.size = 8
    sheet.oddFooter.center.color = "68685F"
    scaling.oddFooter.center.text = (
        f"{recipe_text(texts, 'library_name', card.data.get('library_name', ''))} · {card.recipe_id} · {card.version} · "
        "Batch scaling · Page &P of &N"
    )
    scaling.oddFooter.center.size = 8
    scaling.oddFooter.center.color = "68685F"

    # ------------------------------------------------------- Batch Scaling
    merged_text(scaling, 2, translate("xlsx.batch_scaling", language), 40, title_font)
    merged_text(scaling, 3, f"{title} · {card.recipe_id} · {card.version}", 24, meta_font)
    merged_text(
        scaling,
        4,
        (
            "R&D — NOT RELEASED FOR PRODUCTION. Scaling never grants production approval."
            if not card.is_production
            else "Scaling never grants production approval."
        ),
        40,
        Font(name="Arial", size=11, color=status_text_c),
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
    validation.error = translate("xlsx.validation.error", language)
    validation.errorTitle = translate("xlsx.validation.title", language)
    validation.prompt = translate("xlsx.validation.prompt", language)
    validation.promptTitle = translate("xlsx.batch_factor", language)
    scaling.add_data_validation(validation)
    validation.add(factor_cell)

    merged_text(
        scaling,
        7,
        translate("xlsx.batch_note", language),
        38,
        body_font,
    )

    scale_header_row = 9
    for col, text in enumerate(
        [
            translate("xlsx.table.ingredient", language),
            translate("xlsx.table.base", language),
            translate("xlsx.table.scaling", language),
            translate("xlsx.table.scaled", language),
        ],
        start=2,
    ):
        cell = scaling.cell(row=scale_header_row, column=col, value=text)
        cell.font = header_font
        cell.border = Border(bottom=thin)
        cell.alignment = Alignment(horizontal="right" if col >= 3 else "left")

    scale_row = scale_header_row + 1
    scale_first = scale_row
    scale_sum = 0.0
    base_sum = 0.0
    scale_ingredient_count = 0
    scale_established_count = 0
    scale_base_rows: list[int] = []
    for row_id, card_row in ingredient_rows:
        ing = ingredient_records.get(row_id, {})
        name_cell = scaling.cell(row=scale_row, column=2)
        _set_text(name_cell, ing_names.get(row_id, str(ing.get("name", ""))))
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
                format_quantity(ing.get("quantity"), language),
            )
            base_cell.number_format = "General"
            base_cell.font = body_font
            base_cell.alignment = Alignment(horizontal="right", wrap_text=True)

            pct_cell = scaling.cell(row=scale_row, column=4)
            _set_text(pct_cell, "—")
            pct_cell.font = body_font
            pct_cell.alignment = Alignment(horizontal="right")

            scaled_cell = scaling.cell(row=scale_row, column=5)
            put_formula(
                scaled_cell,
                f'=IF(ISNUMBER(C{scale_row}),IF(ISNUMBER($C$6),IF($C$6>0,C{scale_row}*$C$6,"{translate("xlsx.validation.title", language)}"),"{translate("xlsx.validation.title", language)}"),"Pending")',
                "Pending",
            )
            scaled_cell.font = body_font
            scaled_cell.alignment = Alignment(horizontal="right")
            scale_ingredient_count += 1
            scale_base_rows.append(scale_row)
            scale_row += 1
            continue

        put_formula(
            base_cell,
            f"='Recipe Card'!C{card_row}",
            base_weight,
        )
        base_cell.number_format = MASS_FORMAT
        base_cell.font = body_font
        base_cell.alignment = Alignment(horizontal="right")

        pct_cell = scaling.cell(row=scale_row, column=4)
        put_formula(
            pct_cell,
            f"='Recipe Card'!E{card_row}",
            cell_values.get(("Recipe Card", f"E{card_row}"), ""),
        )
        pct_cell.number_format = PERCENT_FORMAT
        pct_cell.font = body_font
        pct_cell.alignment = Alignment(horizontal="right")

        scaled_cell = scaling.cell(row=scale_row, column=5)
        scaled_mass = base_weight * float(card.data.get("batch_factor", 1) or 1)
        put_formula(
            scaled_cell,
            f'=IF(ISNUMBER($C$6),IF($C$6>0,C{scale_row}*$C$6,"{translate("xlsx.validation.title", language)}"),"{translate("xlsx.validation.title", language)}")',
            scaled_mass,
        )
        scaled_cell.number_format = MASS_FORMAT
        scaled_cell.font = body_font
        scaled_cell.alignment = Alignment(horizontal="right")
        scale_sum += scaled_mass
        base_sum += base_weight
        scale_ingredient_count += 1
        scale_established_count += 1
        scale_base_rows.append(scale_row)

        scale_row += 1

    scale_ingredient_end = scale_row - 1
    if not card.derived().input_complete:
        scaling.cell(row=scale_row, column=2,
                     value=translate("caption.known_input_subtotal", language))
        put_formula(scaling.cell(row=scale_row, column=3),
                    f'=SUM(C{scale_first}:C{scale_ingredient_end})', base_sum)
        put_formula(scaling.cell(row=scale_row, column=5),
                    f'=IF(AND(ISNUMBER($C$6),$C$6>0),SUM(E{scale_first}:E{scale_ingredient_end}),'
                    f'"{translate("xlsx.validation.title", language)}")', scale_sum)
        for column in (3, 5):
            scaling.cell(row=scale_row, column=column).number_format = MASS_FORMAT
        scale_row += 2

    partial_scaling = (translate("xlsx.partial_scaling", language).format(
        n=scale_established_count, m=scale_ingredient_count) if input_structure_complete
        else translate("xlsx.ambiguous_input", language))
    scale_total_row = scale_row
    scaling.cell(row=scale_total_row, column=2, value=translate("xlsx.total_input_g", language))
    guard = ""
    if scale_ingredient_count > 0:
        guard = "AND(" + structure_guard + "," + ",".join(f"ISNUMBER(C{r})" for r in scale_base_rows) + ")"
        base_formula = (
            f'=IF({guard},SUM(C{scale_first}:C{scale_ingredient_end}),'
            f'"{partial_scaling}")'
        )
        base_cached: Any = (
            base_sum
            if input_structure_complete and scale_established_count == scale_ingredient_count
            else partial_scaling
        )
    else:
        base_formula = f'"{translate("xlsx.no_scaling", language)}"'
        base_cached = translate("xlsx.no_scaling", language)
    put_formula(
        scaling.cell(row=scale_total_row, column=3),
        base_formula,
        base_cached,
    )
    scaling.cell(row=scale_total_row, column=3).number_format = MASS_FORMAT
    if scale_ingredient_count > 0:
        guard = "AND(" + structure_guard + "," + ",".join(f"ISNUMBER(E{r})" for r in scale_base_rows) + ")"
        e_formula = (
            f'=IF(AND(ISNUMBER($C$6),{guard}),'
            f'IF($C$6>0,SUM(E{scale_first}:E{scale_ingredient_end}),"{translate("xlsx.validation.title", language)}"),'
            f'"{partial_scaling}")'
        )
        e_cached: Any = (
            scale_sum
            if input_structure_complete and scale_established_count == scale_ingredient_count
            else partial_scaling
        )
    else:
        e_formula = (
            '=IF(ISNUMBER($C$6),IF($C$6>0,"No ingredient masses established; '
            'scaling total incomplete","Invalid input"),"Invalid input")'
        )
        e_cached = translate("xlsx.no_scaling", language)
    put_formula(
        scaling.cell(row=scale_total_row, column=5),
        e_formula,
        e_cached,
    )
    scaling.cell(row=scale_total_row, column=5).number_format = MASS_FORMAT
    if disputed_total is not None:
        # The card states a total and the ingredient weights add up to another
        # one. The Recipe Card sheet shows the stated total, so this sheet
        # does not publish a second total under the same name: it names the
        # disagreement instead, the way it names an ambiguous input. The
        # formula keeps the cell a formula cell, so the workbook ships the
        # note as a cached result a reader can see.
        base_formula = f'="{mismatch_note}"'
        base_cached = mismatch_note
        e_formula = f'="{mismatch_note}"'
        e_cached = mismatch_note
        put_formula(
            scaling.cell(row=scale_total_row, column=3),
            base_formula,
            base_cached,
        )
        put_formula(
            scaling.cell(row=scale_total_row, column=5),
            e_formula,
            e_cached,
        )
    for col in range(2, 6):
        cell = scaling.cell(row=scale_total_row, column=col)
        cell.fill = PatternFill("solid", fgColor=pale)
        cell.border = Border(bottom=thin)
        if col > 2:
            cell.alignment = Alignment(horizontal="right", vertical="center", wrap_text=True)
    partial_warning = translate("xlsx.partial_scaling", language).format(
        n=scale_established_count, m=scale_ingredient_count)
    scaling.row_dimensions[scale_total_row].height = max(
        wrapped_height(partial_warning, scaling.cell(scale_total_row, 3).font, 3, 3),
        wrapped_height(partial_warning, scaling.cell(scale_total_row, 5).font, 5, 5),
        wrapped_height(base_cached, scaling.cell(scale_total_row, 3).font, 3, 3),
        wrapped_height(e_cached, scaling.cell(scale_total_row, 5).font, 5, 5),
    )
    scale_row += 2

    heading(scaling, scale_row, translate("xlsx.process_limits", language))
    scale_row += 1
    tested_range = recipe_field(texts, "tested_batch_range", card.data.get("tested_batch_range"))
    limits = (f"{translate('xlsx.tested_batch_range', language)} {tested_range}. " if tested_range else "") + (
        "Scale ingredient amounts only. Do not scale time, temperature, vessel loading, "
        "mixing, cooling or fermentation automatically. Repeating a tested batch is "
        "different from increasing its load."
    )
    merged_text(scaling, scale_row, (f"{tested_range}. " if tested_range else "") + translate("xlsx.limits_body", language), 58, body_font)
    scale_row += 1
    merged_text(
        scaling,
        scale_row,
        translate("xlsx.yield_note", language),
        38,
        body_font,
    )
    scale_row += 2

    scaling.cell(row=scale_row, column=2, value=translate("xlsx.ref_yield", language))
    ref_yield_cached = cell_values.get(("Recipe Card", f"C{yield_row}"), "")
    put_formula(
        scaling.cell(row=scale_row, column=3),
        f"=IF(ISNUMBER('Recipe Card'!C{yield_row}),'Recipe Card'!C{yield_row},\"\")",
        ref_yield_cached,
    )
    scaling.cell(row=scale_row, column=3).number_format = MASS_FORMAT
    scale_row += 1
    scaling.cell(row=scale_row, column=2, value=translate("xlsx.ref_portion", language))
    put(scaling.cell(row=scale_row, column=3), card.data.get("portion_g"))
    scaling.cell(row=scale_row, column=3).number_format = MASS_FORMAT
    scale_row += 1
    scaling.cell(row=scale_row, column=2, value=translate("xlsx.ref_portions", language))
    put_formula(
        scaling.cell(row=scale_row, column=3),
        f"='Recipe Card'!E{yield_row + 1}",
        cell_values.get(("Recipe Card", f"E{yield_row + 1}"), ""),
    )
    scale_row += 2

    merged_text(
        scaling,
        scale_row,
        translate("xlsx.source_quantities", language),
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

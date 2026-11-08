#!/usr/bin/env python3
"""Locale x theme parity proof for release ticket 05 (five-language output).

One synthetic fixture is rendered across all 25 theme-language combinations
(5 themes x 5 languages: en, es, fr, it, pt). Every combination produces the
four editions: Markdown master, HTML, PDF (selectable text layer) and XLSX.

The proof checks:

* canonical numbers stay locale-neutral in JSON and identical in every
  rendered edition -- only the decimal mark switches (comma for es/fr/it/pt)
* ingredient names, weights and volumes are identical in every combination
  (proper product names are never translated)
* allergen intent is identical in every combination
* live XLSX formula structure is identical across combinations; the only
  language variance is the user-facing message branch of the partial-total
  guard formula, which is intentional
* the PDF text layer carries localized labels, accents and the same numbers
* XLSX cells carry localized labels and accents; long labels are written in
  full (no truncation)

Usage:

    python3 scripts/locale_parity_proof.py [--out DIR]

Previews are written to DIR (default:
work/miseform-release-20261101/evidence/05/previews) as
{stem}.theme-{theme}.lang-{lang}.{md,html,pdf,xlsx}, plus a
locale-parity-report.txt summarizing every check.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from card_model import load_card  # noqa: E402
from exporter import export_pdf, export_xlsx, extract_pdf_text  # noqa: E402
from locales import LANGUAGE_CODES, format_number, translate  # noqa: E402
from render_html import render_html  # noqa: E402
from render_markdown import render_markdown  # noqa: E402
from themes import THEME_IDS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = (
    ROOT
    / "examples"
    / "DEMO-002__smoked-eggplant-tahini-drizzle__v0.1__2026-11-02.json"
)

EXPECTED_LABELS = {
    language: (
        translate("heading.ingredients", language),
        translate("facts.total_time", language),
        translate("status.release_warning", language),
    )
    for language in LANGUAGE_CODES
}

ACCENT_LANGUAGES = ("es", "fr", "it", "pt")

ACCENTS = ("á", "é", "í", "ó", "ú", "à", "è", "ù", "â", "ê", "î", "ô", "û",
           "ã", "õ", "ç", "ñ", "ü", "Á", "É", "Í", "Ó", "Ú")


def stem_for(card: Path) -> str:
    data = json.loads(card.read_text(encoding="utf-8"))
    return data["filename_stem"] if "filename_stem" in data else card.stem


def normalize_formula(formula: str) -> str:
    """Compare formula structure: erase user-facing message string branches.

    The guard, references and arithmetic are identical in every language;
    only the quoted message the formula returns on invalid input is
    localized. Stripping those literals lets us prove the formula
    structure itself never changes with language.
    """
    return re.sub(r'"[^"]*"', '"TEXT"', formula)


def html_rows(markup: str) -> dict[str, dict[str, str]]:
    """Extract ingredient-table cells per row id from one HTML edition."""
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
        rows[row_id] = {
            "weight": weight.strip(),
            "volume": volume.strip(),
            "scaling": scaling.strip(),
            "name": name_plain,
        }
    return rows


def normalize_number(text: str) -> float | None:
    """Read a rendered number back as a float, locale mark agnostic."""
    text = text.strip().replace(" ", "").replace("g", "").replace("%", "")
    if text in ("—", "", "-"):
        return None
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def pdf_row_weights(text: str) -> dict[str, float]:
    """Read ingredient masses from the PDF's layout-preserving text layer.

    Row identifiers anchor the ingredient table; multiple spaces separate
    its columns. Ingredient names and the weight column may wrap, while a
    gram amount mentioned in a method or note must never satisfy a row.
    """
    rows = list(re.finditer(r"^[ \t]*(\S+)[ \t]*·[ \t]*", text, re.MULTILINE))
    weights: dict[str, float] = {}
    for index, row in enumerate(rows):
        end = rows[index + 1].start() if index + 1 < len(rows) else len(text)
        block = text[row.end():end]
        # Only the row's first physical line (or its wrapped weight cell)
        # supplies a weight. Stop before notes or another table section.
        match = re.match(
            r"[^\n]*?(?:[ \t]{2,}|\n[ \t]+)"
            r"([0-9]+(?:[.,][0-9]+)?)[ \t]*g(?=\s|$)",
            block,
        )
        if match:
            weights[row.group(1)] = float(match.group(1).replace(",", "."))
    return weights


def norm_text(text: str) -> str:
    """Normalize PDF-extracted text for comparison.

    PDF extraction can wrap (and hyphen-split) a paragraph across lines, so a
    raw substring check can miss text that is present. Join hyphen-split
    line breaks, collapse whitespace, and uppercase before comparing a full
    declaration such as the allergen statement.
    """
    text = re.sub(r"-\s+", "-", text)
    return re.sub(r"\s+", " ", text).strip().upper()


def xlsx_cells(path: Path) -> dict[str, object]:
    import openpyxl  # type: ignore

    wb = openpyxl.load_workbook(path, data_only=False)
    out: dict[str, object] = {}
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is not None:
                    out[f"{ws.title}!{cell.coordinate}"] = cell.value
    return out


def formula_cells(cells: dict[str, object]) -> dict[str, str]:
    return {coord: str(v) for coord, v in cells.items() if isinstance(v, str) and v.startswith("=")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prove locale x theme parity across all 25 combinations.",
    )
    parser.add_argument(
        "--card",
        default=str(FIXTURE),
        help="Path to the synthetic card JSON (default: the shipped DEMO-002 fixture)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Preview directory (default: work/.../evidence/05/previews)",
    )
    args = parser.parse_args(argv)

    card_path = Path(args.card)
    if not card_path.exists():
        print(f"MISSING fixture: {card_path}")
        return 1

    stem = stem_for(card_path)
    out = Path(args.out) if args.out else (
        ROOT / "work" / "miseform-release-20261101" / "evidence" / "05" / "previews"
    )
    out.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    checks: list[str] = []

    rendered: dict[tuple[str, str], dict[str, str | Path]] = {}
    row_data: dict[tuple[str, str], dict[str, dict[str, str]]] = {}
    xlsx_data: dict[tuple[str, str], dict[str, object]] = {}
    pdf_text: dict[tuple[str, str], str] = {}

    for theme_id in THEME_IDS:
        for language in LANGUAGE_CODES:
            # A fresh card per combination: build_card.main persists the
            # resolved language/theme on the canonical record, so never reuse
            # one loaded object across combinations.
            card = load_card(card_path)
            # Snapshot the canonical record before any renderer touches it:
            # renderers/exporters must not mutate ANY canonical field.
            canonical_snapshot = copy.deepcopy(card.data)
            key = (theme_id, language)
            base = out / f"{stem}.theme-{theme_id}.lang-{language}"
            md_path = Path(f"{base}.md")
            html_path = Path(f"{base}.html")
            pdf_path = Path(f"{base}.pdf")
            xlsx_path = Path(f"{base}.xlsx")

            md_path.write_text(render_markdown(card, language=language), encoding="utf-8")
            html_path.write_text(
                render_html(card, theme=theme_id, language=language), encoding="utf-8"
            )
            pdf_result = export_pdf(card, pdf_path, theme=theme_id, language=language)
            xlsx_result = export_xlsx(card, xlsx_path, theme=theme_id, language=language)
            if not pdf_result.ok:
                failures.append(f"{key}: PDF export failed: {pdf_result.detail}")
            if not xlsx_result.ok:
                failures.append(f"{key}: XLSX export failed: {xlsx_result.detail}")

            # Renderers must not mutate any canonical field. Compare the full
            # record after all four editions were produced.
            if card.data != canonical_snapshot:
                failures.append(
                    f"{key}: renderer mutated canonical card data "
                    f"(must not change any field)"
                )

            rendered[key] = {"md": md_path, "html": html_path, "pdf": pdf_path, "xlsx": xlsx_path}
            row_data[key] = html_rows(html_path.read_text(encoding="utf-8"))
            if xlsx_result.ok:
                xlsx_data[key] = xlsx_cells(xlsx_path)
            if pdf_result.ok:
                pdf_text[key] = extract_pdf_text(pdf_path)

    # --- 1. canonical JSON stays locale-neutral: reload per combination and
    #    the ingredient masses, volumes and allergen text must not change
    reference_card = json.loads(card_path.read_text(encoding="utf-8"))
    for theme_id in THEME_IDS:
        for language in LANGUAGE_CODES:
            card = load_card(card_path)
            for comp in card.components:
                for ing in comp.get("ingredients", []) or []:
                    ref = next(
                        (r for c in reference_card["components"]
                         for r in c.get("ingredients", []) or []
                         if r.get("row_id") == ing.get("row_id")),
                        None,
                    )
                    if ref is None:
                        continue
                    if ing.get("weight_g") != ref.get("weight_g"):
                        failures.append(
                            f"({theme_id},{language}) ingredient {ing.get('row_id')} "
                            f"mass changed: {ing.get('weight_g')} vs {ref.get('weight_g')}"
                        )
                    if ing.get("volume") != ref.get("volume"):
                        failures.append(
                            f"({theme_id},{language}) ingredient {ing.get('row_id')} "
                            f"volume changed"
                        )
            if card.data.get("allergens") != reference_card.get("allergens"):
                failures.append(
                    f"({theme_id},{language}) allergen text changed on the canonical record"
                )

    # --- 1b. emitted build JSON binds canonical numbers/source facts and the
    #    resolved language/theme, and carries translated text into every edition
    import tempfile
    import build_card  # noqa: E402
    from card_model import load_card as _load_card

    card_stem = _load_card(card_path).filename_stem
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        code = build_card.main(
            ["--outdir", str(tmp_path), "--lang", "fr", "--theme", "atelier", str(card_path)]
        )
        if code != 0:
            failures.append("CLI build (fr/atelier) exited non-zero")
        else:
            emitted = json.loads(
                (tmp_path / f"{card_stem}.json").read_text(encoding="utf-8")
            )
            if emitted.get("language") != "fr":
                failures.append(
                    "emitted JSON language not persisted: "
                    f"{emitted.get('language')!r}"
                )
            if emitted.get("theme") != "atelier":
                failures.append(
                    "emitted JSON theme not persisted: "
                    f"{emitted.get('theme')!r}"
                )
            # Canonical numbers unchanged by translation.
            for ref_ing, got_ing in zip(
                reference_card["components"][0]["ingredients"],
                emitted["components"][0]["ingredients"],
            ):
                if ref_ing.get("weight_g") != got_ing.get("weight_g"):
                    failures.append(
                        "emitted JSON ingredient mass changed: "
                        f"{ref_ing.get('row_id')} {ref_ing.get('weight_g')} "
                        f"vs {got_ing.get('weight_g')}"
                    )
            if emitted.get("input_total_g") != reference_card.get("input_total_g"):
                failures.append("emitted JSON input_total_g changed")
            if emitted.get("usable_yield_g") != reference_card.get("usable_yield_g"):
                failures.append("emitted JSON usable_yield_g changed")
            if emitted.get("allergens") != reference_card.get("allergens"):
                failures.append("emitted JSON allergens changed")
            # Canonical title stays the source (proper names verbatim).
            if emitted.get("title") != reference_card.get("title"):
                failures.append("emitted JSON canonical title changed")
            # Translated title reached all four editions.
            md_txt = (tmp_path / f"{card_stem}.md").read_text(encoding="utf-8")
            html_txt = (tmp_path / f"{card_stem}.html").read_text(encoding="utf-8")
            pdf_txt = extract_pdf_text(tmp_path / f"{card_stem}.pdf")
            import openpyxl  # type: ignore
            wb = openpyxl.load_workbook(tmp_path / f"{card_stem}.xlsx")
            xlsx_txt = "\n".join(
                str(c.value) for row in wb[wb.sheetnames[0]].iter_rows()
                for c in row if c.value is not None
            )
            for label, text in (
                ("markdown", md_txt), ("html", html_txt),
                ("pdf", pdf_txt), ("xlsx", xlsx_txt),
            ):
                if "AUBERGINE FUMÉE" not in text:
                    failures.append(f"translated title missing from {label}")
                if "FUMAGE" not in text:
                    failures.append(f"translated stage missing from {label}")
            checks.append(
                "CLI build emits canonical numbers unchanged, persists language/theme, "
                "and carries translated title/stage into MD/HTML/PDF/XLSX"
            )
    checks.append(
        "emitted build JSON binds canonical numbers/source facts + resolved language/theme"
    )

    # --- 2. rendered ingredient numbers identical modulo decimal mark
    reference_rows = row_data[("original", "en")]
    for theme_id in THEME_IDS:
        for language in LANGUAGE_CODES:
            rows = row_data[(theme_id, language)]
            if rows != reference_rows:
                # names match exactly; only decimal marks may differ inside
                # weights, volumes and scaling % (the amounts never change).
                for row_id in reference_rows:
                    ref = reference_rows[row_id]
                    got = rows.get(row_id, {})
                    if got.get("name") != ref["name"]:
                        failures.append(
                            f"({theme_id},{language}) row {row_id} name changed: "
                            f"{got.get('name')} vs {ref['name']}"
                        )
                    if got.get("volume", "").replace(",", ".") != ref["volume"]:
                        failures.append(
                            f"({theme_id},{language}) row {row_id} volume changed: "
                            f"{got.get('volume')} vs {ref['volume']}"
                        )
                    w_ref, w_got = normalize_number(ref["weight"]), normalize_number(got.get("weight", ""))
                    if w_ref is not None and w_got is None:
                        failures.append(
                            f"({theme_id},{language}) row {row_id} weight missing/unparseable "
                            f"while reference is numeric: {ref['weight']} vs {got.get('weight')}"
                        )
                    elif w_ref is not None and w_got is not None and w_ref != w_got:
                        failures.append(
                            f"({theme_id},{language}) row {row_id} weight differs: "
                            f"{ref['weight']} vs {got.get('weight')}"
                        )
                    s_ref, s_got = normalize_number(ref["scaling"]), normalize_number(got.get("scaling", ""))
                    if s_ref is not None and s_got is None:
                        failures.append(
                            f"({theme_id},{language}) row {row_id} scaling missing/unparseable "
                            f"while reference is numeric: {ref['scaling']} vs {got.get('scaling')}"
                        )
                    elif s_ref is not None and s_got is not None and abs(s_ref - s_got) > 1e-9:
                        failures.append(
                            f"({theme_id},{language}) row {row_id} scaling differs: "
                            f"{ref['scaling']} vs {got.get('scaling')}"
                        )
            checks.append(
                f"({theme_id},{language}) ingredient table: {len(rows)} rows "
                f"names/volumes exact, weights and scaling % locale-neutral"
            )

    # --- 2b. real XLSX numeric weight cells equal canonical weights, matched
    #    by row_id (column B holds "row_id · name", column C holds weight).
    #    Membership on a shared weight value would permit swapped equal-set
    #    weights, so each row_id is compared against its own row C cell.
    reference_weights = {}
    for comp in reference_card["components"]:
        for ing in comp.get("ingredients", []) or []:
            w = ing.get("weight_g")
            if isinstance(w, (int, float)):
                reference_weights[str(ing.get("row_id"))] = float(w)
    for theme_id in THEME_IDS:
        for language in LANGUAGE_CODES:
            cells = xlsx_data.get((theme_id, language), {})
            # Map row_id -> numeric weight from column C of the Recipe Card
            # sheet, keyed by the row_id printed in column B ("row_id · name")
            # of the same row. Column B holds strings; column C holds the
            # numeric weight. Inspect B strings first, then validate paired C.
            row_weight: dict[str, float] = {}
            for coord, value in cells.items():
                if coord.split("!")[0] != "Recipe Card":
                    continue
                cell_ref = coord.split("!")[1]
                col = "".join(ch for ch in cell_ref if ch.isalpha())
                row_num = "".join(ch for ch in cell_ref if ch.isdigit())
                if col != "B":
                    continue
                b_cell = str(value)
                if " · " not in b_cell:
                    continue
                row_id = b_cell.split(" · ", 1)[0].strip()
                c_coord = f"Recipe Card!C{row_num}"
                c_value = cells.get(c_coord)
                if isinstance(c_value, (int, float)):
                    row_weight[row_id] = float(c_value)
            for row_id, ref_w in reference_weights.items():
                if row_id not in row_weight:
                    failures.append(
                        f"({theme_id},{language}) XLSX has no weight row for "
                        f"canonical row {row_id}"
                    )
                elif abs(row_weight[row_id] - ref_w) > 1e-9:
                    failures.append(
                        f"({theme_id},{language}) XLSX weight for row {row_id} "
                        f"is {row_weight[row_id]} g, canonical is {ref_w} g"
                    )
    checks.append(
        "real XLSX numeric weight cells equal canonical ingredient masses "
        "in every combination"
    )

    # --- 2c. PDF ingredient masses must agree by row identity, not merely
    #    appear somewhere in a caption or method elsewhere in the document.
    for theme_id in THEME_IDS:
        for language in LANGUAGE_CODES:
            weights = pdf_row_weights(pdf_text.get((theme_id, language), ""))
            for row_id, expected in reference_weights.items():
                actual = weights.get(row_id)
                if actual != float(format_number(expected, "en")):
                    failures.append(
                        f"({theme_id},{language}) PDF weight for row {row_id} "
                        f"is {actual!r} g, canonical is {expected} g"
                    )
    checks.append("PDF ingredient masses match canonical rows in every combination")

    # --- 3. allergen intent reaches every edition, identical text
    allergens = reference_card.get("allergens", "")
    for theme_id in THEME_IDS:
        for language in LANGUAGE_CODES:
            markup = rendered[(theme_id, language)]["html"].read_text(encoding="utf-8")
            text = pdf_text.get((theme_id, language), "")
            cells = xlsx_data.get((theme_id, language), {})
            sheet_text = "\n".join(str(v) for v in cells.values() if isinstance(v, str))
            if allergens and allergens not in markup:
                failures.append(f"({theme_id},{language}) allergens missing from HTML")
            if allergens:
                target = " ".join(str(allergens).split()).upper()
                if target not in norm_text(text):
                    failures.append(f"({theme_id},{language}) allergens missing from PDF text layer")
            if allergens and allergens not in sheet_text:
                failures.append(f"({theme_id},{language}) allergens missing from XLSX")

    # --- 4. localized labels and accents land in the PDF text layer and XLSX
    for theme_id in THEME_IDS:
        for language in LANGUAGE_CODES:
            heading, total_time, release = EXPECTED_LABELS[language]
            markup = rendered[(theme_id, language)]["html"].read_text(encoding="utf-8")
            text = pdf_text.get((theme_id, language), "").upper()
            flat = re.sub(r"\s+", "", text)
            cells = xlsx_data.get((theme_id, language), {})
            sheet_text = "\n".join(str(v) for v in cells.values() if isinstance(v, str))
            xlsx_heading = translate("xlsx.ingredients", language)
            xlsx_release = translate("status.release_warning", language)
            for label in (heading, total_time, release):
                if label not in markup:
                    failures.append(f"({theme_id},{language}) label missing from HTML: {label}")
                if label.replace(" ", "").upper() not in flat:
                    failures.append(f"({theme_id},{language}) label missing from PDF: {label}")
            if xlsx_heading not in sheet_text:
                failures.append(f"({theme_id},{language}) label missing from XLSX: {xlsx_heading}")
            if xlsx_release not in sheet_text:
                failures.append(f"({theme_id},{language}) release warning missing from XLSX")
            if language in ACCENT_LANGUAGES:
                label_accents = [
                    ch for label in (heading, total_time, release) for ch in label if ch in ACCENTS
                ]
                if label_accents and not any(ch in text for ch in label_accents):
                    failures.append(f"({theme_id},{language}) accents did not survive in PDF text layer")
            # long labels written in full in the workbook
            long_label = translate("xlsx.yield_g", language)
            if long_label not in sheet_text:
                failures.append(f"({theme_id},{language}) long label truncated in XLSX: {long_label}")
            checks.append(
                f"({theme_id},{language}) localized labels + accents verified "
                f"(HTML, PDF text layer, XLSX)"
            )

    # --- 4b. multi-allergen fixture: every declared allergen reaches each
    #    edition in every language (full declaration, not a reduced sentence)
    multi_path = ROOT / "examples" / "DEMO-003__multi-allergen-demonstration-dish__v0.1__2026-11-02.json"
    if multi_path.exists():
        for language in LANGUAGE_CODES:
            mc = load_card(multi_path)
            mhtml = render_html(mc, theme="original", language=language)
            mmd = render_markdown(mc, language=language)
            mpdf = out / f"DEMO-003__multi-allergen-demonstration-dish__v0.1__2026-11-02.lang-{language}.pdf"
            mxlsx = out / f"DEMO-003__multi-allergen-demonstration-dish__v0.1__2026-11-02.lang-{language}.xlsx"
            mpr = export_pdf(mc, mpdf, theme="original", language=language)
            mxr = export_xlsx(mc, mxlsx, theme="original", language=language)
            mtext = extract_pdf_text(mpdf).upper() if mpr.ok else ""
            mxtext = ""
            if mxr.ok:
                import openpyxl  # type: ignore
                mw = openpyxl.load_workbook(mxlsx)
                mxtext = "\n".join(
                    str(c.value) for row in mw.worksheets[0].iter_rows()
                    for c in row if c.value is not None
                ).upper()
            for token in ("SESAME (TAHINI)", "MILK (BUTTER)"):
                if token not in mhtml.upper():
                    failures.append(f"(multi,{language}) allergen missing from HTML: {token}")
                if token not in mmd.upper():
                    failures.append(f"(multi,{language}) allergen missing from Markdown: {token}")
                if mpr.ok and token not in mtext:
                    failures.append(f"(multi,{language}) allergen missing from PDF: {token}")
                if mxr.ok and token not in mxtext:
                    failures.append(f"(multi,{language}) allergen missing from XLSX: {token}")
            checks.append(
                f"(multi,{language}) both declared allergens reach HTML, Markdown, PDF and XLSX"
            )

    # --- 5. live formula structure identical across combinations
    reference_formulas = {
        coord: normalize_formula(v)
        for coord, v in formula_cells(xlsx_data[("original", "en")]).items()
    }
    for theme_id in THEME_IDS:
        for language in LANGUAGE_CODES:
            formulas = {
                coord: normalize_formula(v)
                for coord, v in formula_cells(xlsx_data[(theme_id, language)]).items()
            }
            same = [
                coord for coord in reference_formulas
                if coord in formulas and formulas[coord] == reference_formulas[coord]
            ]
            if len(same) != len(reference_formulas):
                diff = [
                    coord for coord in reference_formulas
                    if coord not in formulas or formulas[coord] != reference_formulas[coord]
                ]
                failures.append(
                    f"({theme_id},{language}) live formula structure differs: {diff}"
                )
            # percentage formulas must be live everywhere (message branches aside)
            pct = [
                v for v in formulas.values()
                if v.startswith("=IF(AND(ISNUMBER(") and "TEXT" in v
            ]
            if not pct:
                failures.append(f"({theme_id},{language}) no live percentage formulas")
    checks.append(
        "live XLSX formula structure identical across all 25 combinations "
        f"({len(reference_formulas)} formula cells compared; localized "
        f"message branches normalized out)"
    )

    # --- 6. CLI spot check: language and theme persist on the canonical JSON
    import tempfile
    import build_card  # noqa: E402

    with tempfile.TemporaryDirectory() as tmp:
        code = build_card.main(
            ["--outdir", tmp, "--lang", "fr", "--theme", "atelier", str(card_path)]
        )
        if code != 0:
            failures.append("CLI spot check: build_card exited non-zero")
        else:
            written_paths = list(Path(tmp).glob("*.json"))
            if not written_paths:
                failures.append("CLI spot check: no JSON edition was written")
            else:
                written = json.loads(written_paths[0].read_text(encoding="utf-8"))
                if written.get("language") != "fr" or written.get("theme") != "atelier":
                    failures.append(
                        f"CLI spot check: language/theme not persisted: "
                        f"language={written.get('language')!r} theme={written.get('theme')!r}"
                    )
                else:
                    checks.append("CLI persists resolved language and theme on the canonical JSON record")

    print(f"combinations checked: {len(THEME_IDS)} themes x {len(LANGUAGE_CODES)} languages = {len(THEME_IDS) * len(LANGUAGE_CODES)}")
    print(f"previews written to: {out}")
    print("checks passed:")
    for line in checks:
        print(f"  + {line}")
    if failures:
        print("PARITY FAILURES:")
        for line in failures:
            print(f"  - {line}")
        return 1
    print("PARITY OK: canonical numbers, ingredients, allergen intent and formulas are identical across all 25 combinations; localized labels and accents render in HTML, PDF text layer and XLSX.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

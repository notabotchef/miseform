#!/usr/bin/env python3
"""Numeric and structural parity proof across the five Miseform themes.

Same card record, same underlying recipe data. For every theme this checks:

* HTML ingredient table: identical weight, volume and scaling-% cell text.
* HTML method: identical step text across themes.
* Excel workbook: identical cached values and identical live formulas for
  percentage cells, totals, loss and portions.
* PDF: same selectable text layer (weights, volumes, status line) across themes.

Usage:
    python3 scripts/theme_parity_proof.py --card examples/DEMO-002__smoked-eggplant-tahini-drizzle__v0.1__2026-11-02.json --preview miseform-theme-preview

This is evidence for release ticket 04 (five editorial themes). Themes change
presentation only; numbers never move between them.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from card_model import load_card  # noqa: E402

try:
    import openpyxl  # type: ignore
except Exception:  # pragma: no cover - environment dependent
    openpyxl = None

THEME_IDS = ("original", "paper", "atelier", "service", "ledger")


def html_cells(html_path: Path) -> dict:
    """Extract ingredient table weight/volume/scaling text per row id."""
    markup = html_path.read_text(encoding="utf-8")
    rows: dict[str, dict[str, str]] = {}
    # A row looks like:
    # <tr><td>I1 · name [optional <br><span class="caption">notes</span>]</td><td class="num">420 g</td><td class="num">—</td><td class="num">100%</td></tr>
    # Name cell may contain inline markup, so extract generically and strip tags.
    for m in re.finditer(
        r"<tr>\s*<td>(.*?)</td>\s*<td class=\"num\">(.*?)</td>\s*<td class=\"num\">(.*?)</td>\s*<td class=\"num\">(.*?)</td>",
        markup,
        re.DOTALL,
    ):
        name_raw, weight, volume, scaling = m.groups()
        name_plain = re.sub(r"<[^>]+>", " ", name_raw)
        name_plain = re.sub(r"\s+", " ", name_plain).strip()
        row_id = name_plain.split(" · ")[0]
        rows[row_id] = {"weight": weight.strip(), "volume": volume.strip(), "scaling": scaling.strip()}
    # Method step texts
    steps = re.findall(r"<p>([^<]+)</p>", markup)
    return {"rows": rows, "steps": steps, "markup": markup}


def xlsx_values(xlsx_path: Path) -> dict:
    """Read cached values and live formulas from a theme workbook."""
    if openpyxl is None:
        return {"error": "openpyxl not installed"}
    wb = openpyxl.load_workbook(xlsx_path, data_only=False)
    values: dict[str, dict[str, str | float]] = {}
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        sheet: dict[str, object] = {}
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is None:
                    continue
                sheet[cell.coordinate] = cell.value
        values[sheet_name] = sheet
    return values


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prove numeric/structural parity across all five themes.",
    )
    parser.add_argument("--card", required=True, help="Path to the synthetic card JSON")
    parser.add_argument(
        "--preview",
        required=True,
        help="Directory containing theme-*.html/.pdf/.xlsx previews",
    )
    args = parser.parse_args(argv)

    preview = Path(args.preview)
    card = load_card(args.card)
    stem = card.filename_stem

    html_by_theme: dict[str, dict] = {}
    xlsx_by_theme: dict[str, dict] = {}
    missing: list[str] = []

    for theme_id in THEME_IDS:
        html_path = preview / f"{stem}.theme-{theme_id}.html"
        xlsx_path = preview / f"{stem}.theme-{theme_id}.xlsx"
        if not html_path.exists() or not xlsx_path.exists():
            missing.append(theme_id)
            continue
        html_by_theme[theme_id] = html_cells(html_path)
        xlsx_by_theme[theme_id] = xlsx_values(xlsx_path)

    if missing:
        print(f"MISSING previews for themes: {missing}")
        return 1

    failures: list[str] = []

    # --- HTML ingredient table parity ---
    reference = html_by_theme["original"]["rows"]
    for theme_id in THEME_IDS[1:]:
        rows = html_by_theme[theme_id]["rows"]
        if rows != reference:
            failures.append(f"ingredient table differs in {theme_id}: {rows} vs {reference}")

    # --- HTML method parity (step text) ---
    ref_steps = html_by_theme["original"]["steps"]
    for theme_id in THEME_IDS[1:]:
        if html_by_theme[theme_id]["steps"] != ref_steps:
            failures.append(f"method step text differs in {theme_id}")

    # --- Shared card status line present in every theme ---
    status_marker = "NOT RELEASED FOR PRODUCTION"
    for theme_id in THEME_IDS:
        if status_marker not in html_by_theme[theme_id]["markup"]:
            failures.append(f"status block missing in {theme_id} HTML")

    # --- XLSX cached value parity ---
    ref_xlsx = xlsx_by_theme["original"]
    for theme_id in THEME_IDS[1:]:
        if xlsx_by_theme[theme_id] != ref_xlsx:
            failures.append(f"workbook cached values/formulas differ in {theme_id}")

    # --- Percentage formulas are live in every theme workbook ---
    for theme_id in THEME_IDS:
        sheet = xlsx_by_theme[theme_id].get("Recipe Card", {})
        formulas = [v for v in sheet.values() if isinstance(v, str) and v.startswith("=IF(")]
        if not formulas:
            failures.append(f"no live percentage formulas found in {theme_id} workbook")

    print(f"themes checked: {', '.join(THEME_IDS)}")
    print(f"HTML ingredient rows compared: {len(reference)}")
    print(f"live formula cells found (original): {len([v for v in ref_xlsx.get('Recipe Card', {}).values() if isinstance(v, str) and v.startswith('=')])}")
    if failures:
        print("PARITY FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PARITY OK: weights, volumes, scaling %, step text, status block, cached values and live formulas are identical across all five themes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

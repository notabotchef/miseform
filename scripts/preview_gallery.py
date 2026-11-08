#!/usr/bin/env python3
"""Preview gallery: render one synthetic card in all five Miseform themes.

Same card record, same underlying recipe data, five real visual systems:
Miseform Original (rust/cream default), Paper (minimal black/white),
Atelier (restrained teal editorial), Service (high-contrast compact kitchen),
Ledger (precise tabular prep).

For every theme the script writes a genuine HTML edition, a genuine PDF
(rendered from that HTML through Chromium, selectable text) and a native
Excel workbook (live percentage formulas, cached results). It also writes
gallery.html, a single page that previews all five themes side by side.

This is the evidence bundle for release ticket 04 (five editorial themes).
The card record is the public synthetic fixture
examples/DEMO-002__smoked-eggplant-tahini-drizzle__v0.1__2026-11-02.json.
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from card_model import load_card  # noqa: E402
from exporter import export_pdf, export_xlsx  # noqa: E402
from render_html import render_html  # noqa: E402
from themes import DEFAULT_THEME, THEME_IDS, THEME_DESCRIPTIONS, THEME_NAMES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CARD = ROOT / "examples" / "DEMO-002__smoked-eggplant-tahini-drizzle__v0.1__2026-11-02.json"

GALLERY_CSS = """
:root{--ink:#1a1a1a;--muted:#555555;--rule:#c9c9c9;--paper:#ffffff;--body-bg:#fafafa}
* { box-sizing: border-box }
body { margin: 0; background: var(--body-bg); color: var(--ink); font: 15px/1.6 var(--font-sans); }
.page { max-width: 1200px; margin: 30px auto; padding: 0 24px; }
.header { border-bottom: 2px solid var(--ink); padding: 0 0 20px; margin-bottom: 26px; }
.header h1 { font: 26px var(--font-serif); margin: 0 0 4px; letter-spacing: -0.03em; }
.header p { margin: 0; color: var(--muted); font-size: 13px; }
.grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 26px; }
@media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
.card { background: var(--paper); border: 1px solid var(--rule); padding: 18px 20px 16px; break-inside: avoid; }
.card h2 { font: 16px var(--font-serif); margin: 0 0 6px; letter-spacing: -0.02em; }
.card p { font-size: 12.5px; margin: 0 0 12px; color: var(--muted); }
.card .meta { font-size: 11px; color: var(--muted); margin-bottom: 14px; }
.card iframe { width: 100%; height: 640px; border: 1px solid var(--rule); background: white; margin-bottom: 10px; }
.card .links a { font-size: 12px; color: var(--ink); text-decoration: underline; margin-right: 14px; }
.card .links span.note { color: var(--muted); font-size: 11px; }
.footer { margin-top: 34px; padding-top: 16px; border-top: 1px solid var(--rule); font-size: 11px; color: var(--muted); }
"""

def escape(value: str) -> str:
    return html.escape(value, quote=True)

def build_gallery(card, results: list[dict]) -> str:
    title = escape(card.title)
    items = []
    for result in results:
        items.append(f"""
        <div class="card">
          <h2>{escape(result['name'])} — {escape(result['theme_id'])}</h2>
          <p class="meta">Theme: {escape(result['theme_id'])} · Output: {escape(result['html_path'].name)}, {escape(result['pdf_path'].name)}, {escape(result['xlsx_path'].name)}</p>
          <p>{escape(THEME_DESCRIPTIONS[result['theme_id']])}</p>
          <iframe src="{escape(result['html_path'].name)}" title="Preview of {escape(result['name'])} in the {escape(result['theme_id'])} theme"></iframe>
          <div class="links">
            <a href="{escape(result['html_path'].name)}">Open HTML edition</a>
            <a href="{escape(result['pdf_path'].name)}">Download PDF</a>
            <a href="{escape(result['xlsx_path'].name)}">Download Excel workbook</a>
            <span class="note">Same card ID {escape(card.recipe_id)} · {escape(card.version)} · {escape(card.status)} · identical recipe data in every theme</span>
          </div>
        </div>
        """)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Miseform theme preview gallery · {title}</title>
<style>{GALLERY_CSS}</style></head><body><div class="page">
<div class="header">
<h1>Miseform theme preview gallery</h1>
<p>{title} · {card.recipe_id} · {card.version} · {card.status} — one card record, five editorial themes, identical recipe data</p>
</div>
<div class="grid">{"".join(items)}</div>
<div class="footer">
<p>Miseform — the working recipe collection. Themes change presentation only: weights, volumes, percentages, method steps, blockers and status are byte-identical across themes. PDFs are rendered from the theme HTML editions; workbooks carry live percentage formulas with cached results.</p>
</div>
</div></body></html>"""

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="preview_gallery.py",
        description="Render one synthetic card in all five Miseform themes (HTML, PDF, XLSX + gallery page).",
    )
    parser.add_argument("--card", default=str(DEFAULT_CARD), help="Path to the synthetic card JSON (default: the DEMO-002 fixture)")
    parser.add_argument(
        "--outdir",
        default=str(ROOT / "miseform-theme-preview"),
        help="Directory that receives the previews and gallery.html",
    )
    args = parser.parse_args(argv)

    card = load_card(args.card)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for theme_id in THEME_IDS:
        stem = f"{card.filename_stem}.theme-{theme_id}"
        html_path = outdir / f"{stem}.html"
        pdf_path = outdir / f"{stem}.pdf"
        xlsx_path = outdir / f"{stem}.xlsx"

        html_path.write_text(render_html(card, theme=theme_id), encoding="utf-8")
        print(f"html [{theme_id}]: {html_path}")

        pdf_result = export_pdf(card, pdf_path, theme=theme_id)
        if not pdf_result.ok:
            print(f"  pdf [{theme_id}]: PENDING — {pdf_result.detail}", file=sys.stderr)
        else:
            print(f"  pdf [{theme_id}]: {pdf_result.path} ({pdf_result.detail})")

        xlsx_result = export_xlsx(card, xlsx_path, theme=theme_id)
        if not xlsx_result.ok:
            print(f"  xlsx [{theme_id}]: PENDING — {xlsx_result.detail}", file=sys.stderr)
        else:
            print(f"  xlsx [{theme_id}]: {xlsx_result.path} ({xlsx_result.detail})")

        results.append(
            {
                "theme_id": theme_id,
                "name": THEME_NAMES[theme_id],
                "html_path": html_path,
                "pdf_path": pdf_path,
                "xlsx_path": xlsx_path,
            }
        )

    gallery_path = outdir / "gallery.html"
    gallery_path.write_text(build_gallery(card, results), encoding="utf-8")
    print(f"gallery: {gallery_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
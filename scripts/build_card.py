#!/usr/bin/env python3
"""Validate a recipe card and export it to Markdown, HTML, PDF and XLSX.

Usage:

    python3 scripts/build_card.py CARD.json --outdir DIR [--paper A4|Letter]

The card document is validated first. Findings are printed. A card with
blockers still exports, because an unreleased draft is a valid deliverable,
but the exit code reports whether the card is clean.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from card_model import CardError, load_card  # noqa: E402
from exporter import (  # noqa: E402
    PDF_FORMAT_A4,
    PDF_FORMAT_LETTER,
    export_pdf,
    export_xlsx,
)
from render_html import render_html  # noqa: E402
from render_markdown import render_markdown  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_card.py",
        description="Validate a recipe card and export it to Markdown, HTML, PDF and XLSX.",
    )
    parser.add_argument("card", help="Path to the card JSON document")
    parser.add_argument(
        "--outdir",
        default=".",
        help="Directory that receives the exported files (default: current directory)",
    )
    parser.add_argument(
        "--paper",
        default=PDF_FORMAT_A4,
        choices=[PDF_FORMAT_A4, PDF_FORMAT_LETTER],
        help="PDF paper size (default: A4)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the findings as JSON instead of human-readable lines",
    )
    parser.add_argument("--skip-pdf", action="store_true", help="Do not attempt the PDF export")
    parser.add_argument("--skip-xlsx", action="store_true", help="Do not attempt the Excel export")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        card = load_card(args.card)
    except CardError as exc:
        print(f"CARD ERROR: {exc}", file=sys.stderr)
        return 2

    findings = card.findings()
    blockers = [f for f in findings if f.severity == "blocker"]
    warnings = [f for f in findings if f.severity == "warning"]

    if args.json:
        print(
            json.dumps(
                {
                    "recipe_id": card.recipe_id,
                    "version": card.version,
                    "status": card.status,
                    "findings": [
                        {
                            "code": f.code,
                            "severity": f.severity,
                            "path": f.path,
                            "message": f.message,
                        }
                        for f in findings
                    ],
                },
                indent=2,
            )
        )
    else:
        print(f"Card: {card.title} ({card.recipe_id} {card.version}) — status {card.status}")
        if not findings:
            print("Findings: none")
        else:
            print(f"Findings: {len(findings)} ({len(blockers)} blocker, {len(warnings)} warning)")
            for finding in findings:
                print(f"  {finding}")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = card.filename_stem

    master_path = outdir / f"{stem}.md"
    master_path.write_text(render_markdown(card), encoding="utf-8")
    print(f"master: {master_path}")

    html_path = outdir / f"{stem}.html"
    html_path.write_text(render_html(card), encoding="utf-8")
    print(f"html:   {html_path}")

    pending: list[str] = []

    if not args.skip_pdf:
        result = export_pdf(card, outdir / f"{stem}.pdf", paper=args.paper)
        if result.ok:
            print(f"pdf:    {result.path} ({result.detail})")
            for warning in result.warnings:
                print(f"  warning: {warning}")
        else:
            pending.append(f"pdf ({result.detail})")
            print(f"pdf:    PENDING — {result.detail}", file=sys.stderr)

    if not args.skip_xlsx:
        result = export_xlsx(card, outdir / f"{stem}.xlsx")
        if result.ok:
            print(f"xlsx:   {result.path} ({result.detail})")
        else:
            pending.append(f"xlsx ({result.detail})")
            print(f"xlsx:   PENDING — {result.detail}", file=sys.stderr)

    if pending:
        print(f"Required exports pending: {len(pending)}", file=sys.stderr)
        for item in pending:
            print(f"  - {item}", file=sys.stderr)

    if blockers:
        print(f"Card has {len(blockers)} blocking finding(s); it is not deliverable as a clean card.")
        return 1
    if pending:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from translation import normalize_translation, translation_coverage
from workflow_completeness import validate_ledger
from build_manifest import write_manifest
from card_model import Card, CardError, load_card  # noqa: E402
from exporter import (  # noqa: E402
    PDF_FORMAT_A4,
    PDF_FORMAT_LETTER,
    export_pdf,
    export_xlsx,
)
from render_html import render_html  # noqa: E402
from render_markdown import render_markdown  # noqa: E402
from themes import DEFAULT_THEME, THEME_IDS  # noqa: E402
from locales import (  # noqa: E402
    DEFAULT_LANGUAGE,
    LANGUAGE_CODES,
    resolve_language,
    load_translation_bundle,
)


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
    parser.add_argument(
        "--theme",
        default=None,
        type=_theme_value,
        help=f"Editorial theme: {', '.join(THEME_IDS)}. Defaults to the card record's theme field, then '{DEFAULT_THEME}'.",
    )
    parser.add_argument(
        "--lang",
        default=None,
        type=_language_value,
        help=f"Cook language: {', '.join(LANGUAGE_CODES)}. Defaults to the card record's language field, then the host environment, then '{DEFAULT_LANGUAGE}'.",
    )
    parser.add_argument("--workflow-ledger", help="Optional bound workflow completeness sidecar; incomplete R&D still exports with nonzero status")
    return parser


def _theme_value(value: str) -> str:
    """Validate a --theme argument against the registered themes."""
    if value not in THEME_IDS:
        raise argparse.ArgumentTypeError(
            f"unknown theme {value!r}; expected one of {THEME_IDS}"
        )
    return value


def _language_value(value: str) -> str:
    """Validate a --lang argument against the registered languages."""
    if value not in LANGUAGE_CODES:
        raise argparse.ArgumentTypeError(
            f"unknown language {value!r}; expected one of {LANGUAGE_CODES}"
        )
    return value


def resolve_theme(cli_theme: str | None, card_data: dict) -> str:
    """Resolve the theme for one build run.

    CLI flag wins, then the card record's ``theme`` field, then the
    compatible default for records that predate the field.
    """
    if cli_theme is not None:
        return cli_theme
    card_theme = card_data.get("theme")
    if card_theme in THEME_IDS:
        return str(card_theme)
    return DEFAULT_THEME


def _source_hash(path: str | Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        card = load_card(args.card)
    except CardError as exc:
        print(f"CARD ERROR: {exc}", file=sys.stderr)
        return 2

    workflow_hashes = {"ledger_sha256": _source_hash(args.workflow_ledger),
                       "card_sha256": _source_hash(args.card)} if args.workflow_ledger else {}
    workflow_findings = validate_ledger(args.workflow_ledger, args.card) if args.workflow_ledger else []
    if args.workflow_ledger:
        print("WORKFLOW: declared coverage only; source truth and release approval require independent review")
        for finding in workflow_findings:
            print(f"WORKFLOW: {finding}")

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

    theme = resolve_theme(args.theme, card.data)
    print(f"theme:   {theme}")

    language = resolve_language(args.lang, card.data)
    # Load the persisted per-language recipe translation bundle for this
    # card. Fields the bundle cover override the card record; everything
    # else falls back to the card, so a partial or absent bundle is safe.
    # A sidecar that exists but is invalid is a validation error: the build
    # fails loudly instead of silently falling back to the card record.
    try:
        texts = load_translation_bundle(language, args.card)
        if texts is None and card.data.get("render_translation_language") == language:
            texts = card.data.get("render_translation")
        texts = normalize_translation(card, texts, language)
    except ValueError as exc:
        print(f"CARD ERROR: {exc}", file=sys.stderr)
        return 2
    # Persist the cook's effective choice on the canonical record so the next
    # build (and the manifest the next worker binds) carries the same
    # language/theme. Defaults are implied: only store a non-default language
    # or an explicitly recorded theme, so a default build adds no new keys and
    # the JSON edition still equals the source record it was built from.
    effective = {key: value for key, value in card.data.items()
                 if key not in {"render_translation", "render_translation_language"}}
    if language != DEFAULT_LANGUAGE or "language" in effective:
        effective["language"] = language
    if theme != DEFAULT_THEME or "theme" in effective:
        effective["theme"] = theme
    if texts is not None:
        effective["render_translation"] = texts
        effective["render_translation_language"] = language
    card = Card(effective, source=card.source)
    print(f"language: {language}")
    coverage = translation_coverage(card, texts)
    print(f"translation: {len(coverage['covered_paths'])}/{len(coverage['required_paths'])} supplied; "
          f"{len(coverage['missing_paths'])} missing; complete={coverage['complete']}; semantic review not certified")

    master_path = outdir / f"{stem}.md"
    master_path.write_text(
        render_markdown(card, language=language, texts=texts), encoding="utf-8"
    )
    print(f"master: {master_path}")

    html_path = outdir / f"{stem}.html"
    html_path.write_text(
        render_html(card, theme=theme, language=language, texts=texts),
        encoding="utf-8",
    )
    print(f"html:   {html_path}")

    json_path = outdir / f"{stem}.json"
    json_path.write_text(
        json.dumps(card.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"json:   {json_path}")

    pending: list[str] = []

    if not args.skip_pdf:
        result = export_pdf(
            card,
            outdir / f"{stem}.pdf",
            paper=args.paper,
            theme=theme,
            language=language,
            texts=texts,
        )
        if result.ok:
            print(f"pdf:    {result.path} ({result.detail})")
            for warning in result.warnings:
                print(f"  warning: {warning}")
        else:
            pending.append(f"pdf ({result.detail})")
            print(f"pdf:    PENDING — {result.detail}", file=sys.stderr)

    if not args.skip_xlsx:
        result = export_xlsx(
            card,
            outdir / f"{stem}.xlsx",
            theme=theme,
            language=language,
            texts=texts,
        )
        if result.ok:
            print(f"xlsx:   {result.path} ({result.detail})")
        else:
            pending.append(f"xlsx ({result.detail})")
            print(f"xlsx:   PENDING — {result.detail}", file=sys.stderr)

    paths = {"markdown": master_path, "html": html_path, "json": json_path,
             "pdf": outdir / f"{stem}.pdf", "xlsx": outdir / f"{stem}.xlsx"}
    requested = ["markdown", "html", "json"]
    if not args.skip_pdf:
        requested.append("pdf")
    if not args.skip_xlsx:
        requested.append("xlsx")
    # Failed exporters must never bind an old file left by a previous build.
    for kind in ("pdf", "xlsx"):
        if any(item.startswith(kind + " (") for item in pending):
            paths = {key: path for key, path in paths.items() if key != kind}
    write_manifest(card, outdir, paths, requested, language=language,
                   theme=theme, paper=args.paper, texts=texts)

    if args.workflow_ledger:
        changed = [f"{key}: source changed during build; recheck and rebuild"
                   for key, path in (("ledger_sha256", args.workflow_ledger), ("card_sha256", args.card))
                   if _source_hash(path) != workflow_hashes[key]]
        final_findings = validate_ledger(args.workflow_ledger, args.card)
        workflow_findings = [*workflow_findings, *changed,
                             *(item for item in final_findings if item not in workflow_findings)]
        # The receipt binds this declared-coverage check to the built artifact
        # manifest, without adding private intake or sidecar paths to exports.
        receipt = {
            "schema_version": 1,
            **workflow_hashes,
            "manifest_sha256": hashlib.sha256((outdir / f"{stem}.manifest.json").read_bytes()).hexdigest(),
            "workflow_findings": workflow_findings,
            "release_approval": False,
            "scope": "Declared coverage and byte binding only; independent semantic review required",
        }
        (outdir / f"{stem}.workflow-receipt.json").write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if pending:
        print(f"Required exports pending: {len(pending)}", file=sys.stderr)
        for item in pending:
            print(f"  - {item}", file=sys.stderr)

    if workflow_findings:
        print("WORKFLOW: incomplete; exports remain R&D, no useful-completion or release promotion")
        return 1
    if blockers:
        print(f"Card has {len(blockers)} blocking finding(s); it is not deliverable as a clean card.")
        return 1
    if pending:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

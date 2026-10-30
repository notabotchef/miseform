#!/usr/bin/env python3
"""Report what the Miseform toolchain can and cannot do on this machine.

The diagnostic is read-only. It installs nothing, changes no host setting,
starts no browser, and writes no file inside the package — not even a
byte-code cache. Run it as often as you like; the package is byte-identical
before and after.

It reports three separate outcomes, because they fail for three different
reasons and a cook needs to know which one is missing:

    schema validation   needs the ``jsonschema`` dependency
    PDF export          needs the ``playwright`` dependency AND a
                        Chrome/Chromium/Edge executable to drive
    XLSX export         needs the ``openpyxl`` spreadsheet writer

A missing dependency, a missing browser binary and a missing spreadsheet
writer are three distinct problems with three distinct remedies, and the
reason line names which one you have.

Usage:

    python3 scripts/capability_check.py            # human-readable report
    python3 scripts/capability_check.py --json     # machine-readable report

Exit status is 0 when all three outcomes are available and 1 when at least
one is pending.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# Keep the package byte-identical: importing the packaged modules must not
# leave a __pycache__ directory behind.
sys.dont_write_bytecode = True

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# Sibling modules of this package. They are not third-party dependencies.
LOCAL_MODULES = {
    "build_card",
    "capability_check",
    "card_model",
    "exporter",
    "install",
    "render_html",
    "render_markdown",
}


def _module_present(name: str) -> bool:
    """Return True when a module can be imported in this environment.

    Kept as its own function so the three outcomes can be exercised for a
    missing dependency without uninstalling anything.
    """
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _module_version(name: str) -> str:
    """Return the installed version of a module, or an empty string."""
    if not _module_present(name):
        return ""
    try:
        from importlib import metadata

        return metadata.version(name)
    except Exception:
        pass
    try:
        module = __import__(name)
    except Exception:  # pragma: no cover - a broken install is still "present"
        return "(version unreadable)"
    version = getattr(module, "__version__", "")
    return str(version) if version else ""


def _find_browser() -> str:
    """Locate a browser the exporter can drive, exactly as the exporter does."""
    try:
        from exporter import _find_chrome  # type: ignore

        return _find_chrome() or ""
    except Exception:
        # Fall back to the same lookups the exporter makes, in case the
        # packaged module cannot be imported for any reason.
        for candidate in (
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ):
            if Path(candidate).exists():
                return candidate
        return (
            shutil.which("google-chrome")
            or shutil.which("chromium")
            or shutil.which("chromium-browser")
            or ""
        )


def _schema_outcome() -> dict:
    """Can a card be validated against the packaged schema?"""
    schema_path = ROOT / "references" / "card.schema.json"
    if not schema_path.exists():
        return {
            "outcome": "pending",
            "reason": (
                "the packaged schema references/card.schema.json is missing, "
                "so no card can be validated"
            ),
            "remedy": (
                "reinstall the package so references/card.schema.json is present "
                "beside SKILL.md"
            ),
        }

    if not _module_present("jsonschema"):
        return {
            "outcome": "pending",
            "reason": (
                "the jsonschema dependency is not installed, so card validation "
                "cannot run"
            ),
            "remedy": (
                "install the dependency into the environment that runs the "
                "toolchain: python3 -m pip install -r requirements.txt"
            ),
        }

    version = _module_version("jsonschema")
    try:
        import jsonschema  # type: ignore

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
    except Exception as exc:
        return {
            "outcome": "pending",
            "reason": f"the packaged schema did not validate: {exc}",
            "remedy": (
                "reinstall the package; the schema file is the one the card "
                "model enforces"
            ),
        }

    return {
        "outcome": "available",
        "reason": (
            f"jsonschema {version} is installed and the packaged schema is a "
            "valid Draft 2020-12 schema"
        ),
        "remedy": "",
    }


def _pdf_outcome() -> dict:
    """Can a card be rendered to a PDF?"""
    if not _module_present("playwright"):
        return {
            "outcome": "pending",
            "reason": (
                "the playwright dependency is not installed, so no PDF can be "
                "rendered"
            ),
            "remedy": (
                "install the dependency and its browser: python3 -m pip install "
                "-r requirements.txt && python3 -m playwright install chromium"
            ),
        }

    version = _module_version("playwright")
    browser = _find_browser()
    if not browser:
        return {
            "outcome": "pending",
            "reason": (
                "playwright is installed but no Chrome, Chromium or Edge "
                "executable was found to drive"
            ),
            "remedy": (
                "install a browser the toolchain can launch (macOS: "
                "'brew install --cask google-chrome'; Debian/Ubuntu: 'sudo apt "
                "install chromium'; or run 'python3 -m playwright install "
                "chromium' and put the resulting binary on PATH)"
            ),
        }

    # PDF text-layer verification uses pdftotext when the host has it and
    # falls back to pypdf. It only downgrades a warning, never the export.
    if shutil.which("pdftotext"):
        text_tool = "pdftotext is on PATH"
    elif importlib.util.find_spec("pypdf") is not None:
        text_tool = "pypdf is installed"
    else:
        text_tool = (
            "neither pdftotext nor pypdf is present, so the PDF text layer "
            "cannot be confirmed (the export still works)"
        )

    return {
        "outcome": "available",
        "reason": f"playwright {version} is installed and {browser} is available",
        "remedy": "",
        "text_layer": text_tool,
    }


def _xlsx_outcome() -> dict:
    """Can a card be written as a native workbook?"""
    if not _module_present("openpyxl"):
        return {
            "outcome": "pending",
            "reason": (
                "the openpyxl spreadsheet writer is not installed, so no "
                "workbook can be written"
            ),
            "remedy": (
                "install the dependency into the environment that runs the "
                "toolchain: python3 -m pip install -r requirements.txt"
            ),
        }

    version = _module_version("openpyxl")
    return {
        "outcome": "available",
        "reason": f"openpyxl {version} is installed",
        "remedy": "",
    }


def collect() -> dict:
    """Report every outcome. Reads only; writes nothing."""
    schema = _schema_outcome()
    pdf = _pdf_outcome()
    xlsx = _xlsx_outcome()
    return {
        "python": {
            "version": ".".join(str(part) for part in sys.version_info[:3]),
            "executable": sys.executable,
        },
        "package": str(ROOT),
        "capabilities": {
            "schema_validation": schema,
            "pdf_export": pdf,
            "xlsx_export": xlsx,
        },
    }


def render(report: dict) -> str:
    """Render the report as plain text."""
    lines = [
        "Miseform capability check",
        f"  python  : {report['python']['version']} ({report['python']['executable']})",
        f"  package : {report['package']}",
        "",
    ]
    labels = {
        "schema_validation": "schema validation",
        "pdf_export": "PDF export",
        "xlsx_export": "XLSX export",
    }
    for key, label in labels.items():
        entry = report["capabilities"][key]
        lines.append(f"  {label:<18}: {entry['outcome'].upper()}")
        lines.append(f"  {'':<18}  {entry['reason']}")
        if entry.get("remedy"):
            lines.append(f"  {'':<18}  remedy: {entry['remedy']}")
        if entry.get("text_layer"):
            lines.append(f"  {'':<18}  text layer: {entry['text_layer']}")
    pending = [
        key
        for key, entry in report["capabilities"].items()
        if entry["outcome"] != "available"
    ]
    lines.append("")
    if pending:
        names = ", ".join(labels[key] for key in pending)
        lines.append(f"  {len(pending)} of 3 capabilities pending: {names}")
        lines.append(
            "  A pending capability is a missing tool, not a broken skill: the "
            "affected export stays pending and no file is fabricated."
        )
    else:
        lines.append("  all 3 capabilities available")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="capability_check.py",
        description=(
            "Report whether schema validation, PDF export and XLSX export are "
            "available. Installs nothing and changes nothing."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as JSON instead of plain text",
    )
    args = parser.parse_args(argv)

    report = collect()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render(report))

    pending = [
        entry
        for entry in report["capabilities"].values()
        if entry["outcome"] != "available"
    ]
    return 1 if pending else 0


if __name__ == "__main__":
    raise SystemExit(main())

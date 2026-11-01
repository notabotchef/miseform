"""Tests for the reproducible install, the dependency manifest and the
capability diagnostic.

Run with:

    python3 -m pytest tests/ -q

These checks guard the promises the package makes about its own setup:

* the manifest at the package root declares every third-party import the
  scripts actually use, so the two cannot drift apart;
* the optional PDF-text dependency stays optional, and the suite passes
  without it;
* the capability diagnostic reports the three outcomes separately, tells a
  missing dependency apart from a missing browser and a missing spreadsheet
  writer, and changes nothing when it runs;
* the installer refuses to overwrite private configuration and is safe to
  run twice;
* the workbook leaves the loss cell empty when there is no measured yield,
  instead of reporting a fabricated total loss;
* the README names one install command, one activation line per host, the
  optional steps, and an honest list of what is not supported.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import capability_check  # noqa: E402
import install as installer  # noqa: E402
from card_model import load_card  # noqa: E402
from exporter import export_xlsx  # noqa: E402

MANIFEST = ROOT / "requirements.txt"
EXAMPLE = ROOT / "examples" / "sesame-salt-garnish.card.json"

# The third-party imports the toolchain is allowed to depend on. A new
# third-party import in scripts/ must be added here and to the manifest in
# the same change, which is what the drift test enforces.
EXPECTED_THIRD_PARTY = {"jsonschema", "openpyxl", "playwright"}
EXPECTED_OPTIONAL = {"pypdf", "formulas"}


# --------------------------------------------------------------- stdlib names


def _stdlib_names() -> set[str]:
    """Return the top-level module names that ship with Python.

    ``sys.stdlib_module_names`` only exists from 3.10 on, and this package
    supports 3.9, so the standard library directory is read as well. Some
    builds keep the compiled modules in a separate ``lib-dynload`` folder.
    """
    names = set(getattr(sys, "stdlib_module_names", ()))
    names |= set(sys.builtin_module_names)

    import sysconfig

    directories = []
    for key in ("stdlib", "platstdlib"):
        path = sysconfig.get_paths().get(key)
        if path:
            directories.append(Path(path))
    for base in directories:
        if not base.is_dir():
            continue
        for entry in base.iterdir():
            if entry.suffix == ".py":
                names.add(entry.stem)
            elif entry.suffix == ".so":
                names.add(entry.name.split(".")[0])
            elif (entry / "__init__.py").exists():
                names.add(entry.name)
        dynload = base / "lib-dynload"
        if dynload.is_dir():
            for entry in dynload.iterdir():
                if entry.suffix == ".so":
                    names.add(entry.name.split(".")[0])
    return names


STDLIB = _stdlib_names()

def _local_module_names(directory: Path) -> set[str]:
    """Return the module names that live in ``directory``.

    A module that sits beside the scripts is part of this package, not a
    third-party dependency. The set is read from the directory instead of
    being written out by hand, so a new sibling module added later is
    recognized without editing this test — the drift guard then fires on a
    genuine third-party import only.
    """
    return {path.stem for path in directory.glob("*.py")}


def _imported_roots(path: Path) -> set[str]:
    """Return the top-level module names a script imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # a relative import, always local
                continue
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _script_imports() -> set[str]:
    """Return every third-party module the scripts import."""
    scripts = ROOT / "scripts"
    local = _local_module_names(scripts)
    found: set[str] = set()
    for script in sorted(scripts.glob("*.py")):
        for name in _imported_roots(script):
            if name in STDLIB or name in local:
                continue
            if name == "__future__":
                continue
            found.add(name)
    return found


# ------------------------------------------------------------ manifest shape


def _manifest_lines() -> tuple[list[str], list[str]]:
    """Return the required and optional requirement lines of the manifest.

    A requirement line is any non-comment line. An optional requirement is
    written as a comment beginning with ``optional:``, so a plain
    ``pip install -r requirements.txt`` installs the required set only.
    """
    required: list[str] = []
    optional: list[str] = []
    for raw in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            marker = line.lstrip("#").strip()
            if marker.lower().startswith("optional:"):
                spec = marker.split(":", 1)[1].strip()
                if spec:
                    optional.append(spec)
            continue
        required.append(line)
    return required, optional


def _requirement_name(spec: str) -> str:
    """Return the distribution name of a requirement specifier."""
    name = re.split(r"[<>=!~;\[\s]", spec.strip(), maxsplit=1)[0]
    return name.strip().lower().replace("_", "-")


# ------------------------------------------------------- the manifest itself


def test_the_manifest_declares_every_third_party_import_the_scripts_use():
    """The manifest and the code must list the same dependencies.

    This is the drift guard: a third-party import added to a script without
    a matching manifest entry fails here.
    """
    used = _script_imports()
    required, optional = _manifest_lines()
    declared = {_requirement_name(spec) for spec in required} | {
        _requirement_name(spec) for spec in optional
    }

    missing = sorted(used - declared)
    assert missing == [], (
        f"scripts/ imports {missing} but requirements.txt does not declare them; "
        "add each one to the manifest (and to EXPECTED_THIRD_PARTY or "
        "EXPECTED_OPTIONAL in this test) in the same change"
    )


def test_the_manifest_declares_the_expected_dependencies():
    """The manifest declares exactly the documented dependency set."""
    required, optional = _manifest_lines()
    required_names = {_requirement_name(spec) for spec in required}
    optional_names = {_requirement_name(spec) for spec in optional}

    assert required_names == EXPECTED_THIRD_PARTY | {"pytest"}, required_names
    assert optional_names == EXPECTED_OPTIONAL, optional_names


def test_the_manifest_pins_a_compatible_range_for_every_dependency():
    """Every requirement carries a bounded version range."""
    required, optional = _manifest_lines()
    for spec in required + optional:
        assert re.match(
            r"^[A-Za-z0-9_.\-]+>=[0-9][^,]*,<[0-9]", spec
        ), f"{spec!r} does not carry a pinned compatible range"


def test_the_optional_pdf_dependency_is_documented_as_optional():
    """pypdf is optional, and the code guards its import."""
    required, optional = _manifest_lines()
    assert "pypdf" not in {_requirement_name(spec) for spec in required}
    assert "pypdf" in {_requirement_name(spec) for spec in optional}

    exporter_source = (ROOT / "scripts" / "exporter.py").read_text(encoding="utf-8")
    assert "from pypdf import PdfReader" in exporter_source
    # The import is inside a try block, so a missing pypdf never breaks an
    # export.
    guarded = re.search(
        r"try:\s*\n\s*from pypdf import PdfReader.*?\n\s*except Exception:",
        exporter_source,
        re.DOTALL,
    )
    assert guarded is not None, "the pypdf import is not guarded by a try block"

    # The manifest says why it is optional, in prose, in the file itself.
    manifest_text = MANIFEST.read_text(encoding="utf-8")
    assert "pypdf" in manifest_text
    assert "pdftotext" in manifest_text


def test_the_manifest_does_not_imply_publication_to_a_package_index():
    """The manifest is an install manifest, not a distribution."""
    for name in ("setup.py", "setup.cfg", "pyproject.toml", "MANIFEST.in"):
        assert not (ROOT / name).exists(), f"{name} would imply publication"

    required, optional = _manifest_lines()
    for spec in required + optional:
        assert "://" not in spec, f"{spec!r} points at an index or a URL"
        assert "@" not in spec, f"{spec!r} looks like a direct reference"


def test_the_drift_guard_actually_catches_an_undeclared_import(tmp_path: Path):
    """The drift test fails when a script imports something undeclared.

    Without this, the drift test could pass by being too permissive. This
    proves it would catch a real dependency added without a manifest entry.
    """
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "build_card.py").write_text(
        "import json\nimport os\nimport numpy\n", encoding="utf-8"
    )
    (scripts / "card_model.py").write_text("import re\n", encoding="utf-8")

    local = _local_module_names(scripts)
    found: set[str] = set()
    for script in sorted(scripts.glob("*.py")):
        for name in _imported_roots(script):
            if name in STDLIB or name in local or name == "__future__":
                continue
            found.add(name)

    assert found == {"numpy"}, found
    declared = {_requirement_name(spec) for spec in _manifest_lines()[0]}
    assert found - declared == {"numpy"}, "the drift guard did not fire"


def test_the_drift_guard_does_not_report_a_new_sibling_module(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """A module added beside the scripts is local, not a dependency.

    The guard used to carry a hand-written list of the local modules, so a
    module added later was reported as an undeclared third-party import and
    the suite failed for a change that needed no dependency at all. The
    local set is read from the directory instead, so this stays green.
    """
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "intake_policy.py").write_text("import json\n", encoding="utf-8")
    (scripts / "build_card.py").write_text(
        "import intake_policy\nimport numpy\n", encoding="utf-8"
    )
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)

    found = _script_imports()

    assert "intake_policy" not in found, found
    assert "numpy" in found, found


# --------------------------------------------------- the capability diagnostic


def test_the_capability_diagnostic_reports_three_separate_outcomes():
    """The diagnostic reports schema, PDF and XLSX as three outcomes."""
    report = capability_check.collect()
    capabilities = report["capabilities"]
    assert set(capabilities) == {
        "schema_validation",
        "pdf_export",
        "xlsx_export",
    }, sorted(capabilities)
    for key, entry in capabilities.items():
        assert entry["outcome"] in {"available", "pending"}, (key, entry)
        assert entry["reason"], key


def test_the_diagnostic_tells_a_missing_dependency_from_a_missing_browser(
    monkeypatch: pytest.MonkeyPatch,
):
    """Three different problems produce three different reasons."""
    # A missing dependency: jsonschema is not installed.
    monkeypatch.setattr(
        capability_check, "_module_present", lambda name: name != "jsonschema"
    )
    entry = capability_check._schema_outcome()
    assert entry["outcome"] == "pending"
    assert "jsonschema" in entry["reason"]
    assert entry["remedy"]

    # A missing browser, with the dependency present.
    monkeypatch.setattr(capability_check, "_module_present", lambda name: True)
    monkeypatch.setattr(capability_check, "_find_browser", lambda: "")
    entry = capability_check._pdf_outcome()
    assert entry["outcome"] == "pending"
    assert "browser" in entry["reason"].lower() or "chrome" in entry["reason"].lower()
    assert "chromium" in entry["remedy"].lower() or "chrome" in entry["remedy"].lower()

    # A missing spreadsheet writer.
    monkeypatch.setattr(
        capability_check, "_module_present", lambda name: name != "openpyxl"
    )
    entry = capability_check._xlsx_outcome()
    assert entry["outcome"] == "pending"
    assert "openpyxl" in entry["reason"]

    # The three reasons are distinct problems, not one message repeated.
    reasons = {
        capability_check._schema_outcome()["reason"],
        capability_check._pdf_outcome()["reason"],
        capability_check._xlsx_outcome()["reason"],
    }
    assert len(reasons) == 3, reasons


def test_the_diagnostic_writes_nothing_into_the_package():
    """Running the diagnostic leaves the package byte-identical."""
    before = {
        str(path.relative_to(ROOT)): path.stat().st_mtime_ns
        for path in ROOT.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and "__pycache__" not in path.parts
        and ".pytest_cache" not in path.parts
    }
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "capability_check.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode in (0, 1), result.stderr
    after = {
        str(path.relative_to(ROOT)): path.stat().st_mtime_ns
        for path in ROOT.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and "__pycache__" not in path.parts
        and ".pytest_cache" not in path.parts
    }
    assert after == before


def test_the_diagnostic_can_be_run_twice_without_changing_anything():
    """Two runs in a row produce the same report and change no file."""
    first = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "capability_check.py"), "--json"],
        capture_output=True,
        text=True,
    )
    second = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "capability_check.py"), "--json"],
        capture_output=True,
        text=True,
    )
    assert first.returncode == second.returncode
    assert first.stdout == second.stdout

    report = json.loads(first.stdout)
    assert set(report["capabilities"]) == {
        "schema_validation",
        "pdf_export",
        "xlsx_export",
    }


def test_the_diagnostic_installs_nothing_and_touches_no_host_setting():
    """The diagnostic only reads: it never shells out and never writes.

    The remedy strings mention ``pip install`` on purpose — that is the
    instruction the cook follows — but the diagnostic itself never runs it.
    """
    source = (ROOT / "scripts" / "capability_check.py").read_text(encoding="utf-8")
    assert "import subprocess" not in source
    assert "subprocess." not in source
    assert "os.environ" not in source
    assert "os.remove" not in source
    assert "shutil.rmtree" not in source
    assert "Path.write" not in source
    assert ".write_text(" not in source
    assert ".write_bytes(" not in source


# ------------------------------------------------------------ the installer


def test_the_installer_never_overwrites_private_configuration(tmp_path: Path):
    """A second run leaves private configuration exactly as it was."""
    destination = tmp_path / "skills" / "miseform"
    destination.mkdir(parents=True)

    private = destination / "recipe-library.local.json"
    private.write_text('{"root": "keep me"}', encoding="utf-8")
    config_dir = destination / "config"
    config_dir.mkdir()
    (config_dir / "settings.json").write_text("keep me too", encoding="utf-8")
    profile = destination / "miseform.local.json"
    profile.write_text("{}", encoding="utf-8")
    env_file = destination / ".env"
    env_file.write_text("TOKEN=keep", encoding="utf-8")

    written = installer.copy_skill(destination)
    assert written >= 0

    assert private.read_text(encoding="utf-8") == '{"root": "keep me"}'
    assert (config_dir / "settings.json").read_text(encoding="utf-8") == "keep me too"
    assert profile.read_text(encoding="utf-8") == "{}"
    assert env_file.read_text(encoding="utf-8") == "TOKEN=keep"

    # The public files were written.
    assert (destination / "SKILL.md").exists()
    assert (destination / "requirements.txt").exists()


def test_the_installer_is_safe_to_run_twice(tmp_path: Path):
    """A second install writes nothing new and deletes nothing."""
    destination = tmp_path / "skills" / "miseform"
    destination.mkdir(parents=True)
    installer.copy_skill(destination)
    first = {
        str(p.relative_to(destination)): p.read_bytes()
        for p in destination.rglob("*")
        if p.is_file()
    }
    second_written = installer.copy_skill(destination)
    second = {
        str(p.relative_to(destination)): p.read_bytes()
        for p in destination.rglob("*")
        if p.is_file()
    }
    assert second == first
    assert second_written == 0, "a second install rewrote files it did not need to"


def test_the_installer_never_deletes_anything(tmp_path: Path):
    """An unrelated file in the destination survives the install."""
    destination = tmp_path / "skills" / "miseform"
    destination.mkdir(parents=True)
    stranger = destination / "notes-from-the-cook.md"
    stranger.write_text("keep", encoding="utf-8")
    installer.copy_skill(destination)
    assert stranger.exists()
    assert stranger.read_text(encoding="utf-8") == "keep"


def test_the_installer_never_copies_a_tool_cache_into_a_host_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """A developer's local tool caches stay in the developer's folder.

    A type checker or a linter run in the package folder leaves cache
    directories behind. They are local artifacts, not skill content, and
    they must not be copied into a host's skill folder.
    """
    # A stand-in package root, so the test never writes into the real one.
    package = tmp_path / "package"
    (package / "scripts").mkdir(parents=True)
    (package / "SKILL.md").write_text("# miseform\n", encoding="utf-8")
    (package / "requirements.txt").write_text("jsonschema>=4.18,<5\n", encoding="utf-8")
    for name in (".mypy_cache", ".ruff_cache"):
        cache = package / name
        cache.mkdir()
        (cache / "cache.0.db").write_text("local artifact", encoding="utf-8")
    pycache = package / "scripts" / "__pycache__"
    pycache.mkdir()
    (pycache / "stale.pyc").write_text("local artifact", encoding="utf-8")

    monkeypatch.setattr(installer, "PACKAGE", package)

    destination = tmp_path / "skills" / "miseform"
    destination.mkdir(parents=True)
    installer.copy_skill(destination)

    copied = [
        p.relative_to(destination) for p in destination.rglob("*") if p.is_file()
    ]
    names = {p.as_posix() for p in copied}

    assert "SKILL.md" in names, sorted(names)
    assert "requirements.txt" in names, sorted(names)
    for name in (".mypy_cache", ".ruff_cache", "__pycache__"):
        offenders = [str(p) for p in copied if name in p.parts]
        assert not offenders, offenders


def test_the_installer_reports_a_missing_prerequisite_by_name():
    """A failed prerequisite is named, with the remedy, not a stack trace."""
    error = installer.fail("the thing is missing", "do the other thing")
    assert isinstance(error, installer.InstallError)
    message = str(error)
    assert "the thing is missing" in message
    assert "do the other thing" in message
    # The remedy is the last line, so it reads as the fix.
    assert message.strip().splitlines()[-1].strip().startswith("fix:")


def test_the_installer_knows_where_each_host_keeps_its_skills():
    """Each supported host has a skill folder and an activation form."""
    assert set(installer.HOSTS) == {"codex", "claude", "opencode", "hermes"}
    for name, folder in installer.HOSTS.items():
        assert folder.name == "miseform"
        assert folder.parent.name == "skills"
        assert installer.ACTIVATION[name].strip()


# --------------------------------------------------------- the loss-cell guard


def test_an_unmeasured_yield_leaves_the_loss_cell_empty(tmp_path: Path):
    """No measured yield means no loss, not a fabricated total loss.

    The input total is 130 g. An unguarded ``=C_total-C_yield`` recalculates
    in Excel to 130 g of loss, which would report that the whole batch was
    lost. The guard makes the cell empty instead.
    """
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["usable_yield_g"] = None
    card_path = tmp_path / "no-yield.card.json"
    card_path.write_text(json.dumps(data), encoding="utf-8")
    card = load_card(card_path)

    out = tmp_path / "no-yield.xlsx"
    result = export_xlsx(card, out)
    assert result.ok, result.detail

    import openpyxl

    formulas = openpyxl.load_workbook(out)
    sheet = formulas["Recipe Card"]

    loss_cells = [
        cell
        for row in sheet.iter_rows(min_col=5, max_col=5)
        for cell in row
        if isinstance(cell.value, str)
        and cell.value.startswith("=")
        and "-" in cell.value
        and "SUM" not in cell.value
        and "C" in cell.value
    ]
    assert loss_cells, "no loss formula was written"
    for cell in loss_cells:
        formula = str(cell.value)
        assert "ISNUMBER(" in formula, (
            f"{cell.coordinate} is an unguarded loss formula: {formula}"
        )
        assert '""' in formula, (
            f"{cell.coordinate} does not yield an empty cell: {formula}"
        )

    # The cached value the workbook ships with is empty, not the input mass.
    values = openpyxl.load_workbook(out, data_only=True)["Recipe Card"]
    input_total = None
    for row in values.iter_rows(min_col=2, max_col=3):
        for cell in row:
            if cell.column == 2 and cell.value == "Total input":
                input_total = values.cell(row=cell.row, column=3).value
    assert input_total == 130, input_total

    for row in values.iter_rows(min_col=2, max_col=5):
        for cell in row:
            if cell.column == 2 and cell.value == "Measured usable yield (g)":
                cached = values.cell(row=cell.row, column=5).value
                assert cached in (None, ""), (
                    f"the loss cell reports {cached!r} with no measured yield; "
                    f"the input total is {input_total} g"
                )


def test_a_measured_yield_still_reports_the_real_loss(tmp_path: Path):
    """The guard does not suppress a real loss number."""
    card = load_card(EXAMPLE)
    out = tmp_path / "with-yield.xlsx"
    result = export_xlsx(card, out)
    assert result.ok, result.detail

    import openpyxl

    values = openpyxl.load_workbook(out, data_only=True)["Recipe Card"]
    found = None
    for row in values.iter_rows(min_col=2, max_col=5):
        for cell in row:
            if cell.column == 2 and cell.value == "Measured usable yield (g)":
                found = values.cell(row=cell.row, column=5).value
    assert found == 2, f"expected 2 g of loss, got {found!r}"


def test_the_exporter_finds_the_chromium_build_playwright_installs(
    monkeypatch: pytest.MonkeyPatch,
):
    """The install command's Chromium step is real, not a promise.

    ``playwright install chromium`` puts the browser in Playwright's own
    cache, where ``PATH`` and the macOS application folder cannot see it.
    The exporter asks Playwright where it put it.
    """
    import exporter

    monkeypatch.setattr(exporter, "CHROME_CANDIDATES", [])
    monkeypatch.setattr(exporter.shutil, "which", lambda name: None)

    # Without the fallback there is no browser to drive.
    monkeypatch.setattr(exporter, "_find_playwright_chromium", lambda: None)
    assert exporter._find_chrome() is None

    # With it, the Playwright build is found.
    monkeypatch.setattr(
        exporter, "_find_playwright_chromium", lambda: "/some/chromium/binary"
    )
    assert exporter._find_chrome() == "/some/chromium/binary"


def test_the_pdf_export_is_pending_rather_than_faked_without_a_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """With no browser, the PDF export is pending — never a renamed file."""
    import exporter

    card = load_card(EXAMPLE)
    out = tmp_path / "no-browser.pdf"
    monkeypatch.setattr(exporter, "CHROME_CANDIDATES", [])
    monkeypatch.setattr(exporter.shutil, "which", lambda name: None)
    monkeypatch.setattr(exporter, "_find_playwright_chromium", lambda: None)

    result = exporter.export_pdf(card, out)
    assert not result.ok
    assert result.path is None
    assert "Chrome" in result.detail or "browser" in result.detail.lower()
    assert not out.exists(), "a PDF file was written with no browser to write it"


# --------------------------------------------------------------- the README


def _readme() -> str:
    return (ROOT / "README.md").read_text(encoding="utf-8")


def test_the_readme_names_exactly_one_install_command():
    """A cook copies one command, not a procedure."""
    readme = _readme()
    assert "python3 scripts/install.py" in readme
    # The command is the subject of the Install section, not buried.
    install_section = readme.split("## Install", 1)[1].split("\n## ", 1)[0]
    assert "python3 scripts/install.py" in install_section


def test_the_readme_names_one_activation_line_per_host():
    """Each supported host has its activation form in the README."""
    readme = _readme()
    for host in ("Codex", "Claude Code", "OpenCode", "Hermes"):
        assert host in readme, f"{host} is not named in the README"
    assert "$miseform" in readme
    assert "/miseform" in readme


def test_the_readme_marks_the_pdf_and_drive_steps_as_optional():
    """The optional steps are labelled optional, not implied."""
    readme = _readme().lower()
    assert "optional" in readme
    # The PDF edition needs a browser; the Drive filing needs a library.
    assert "pdf" in readme
    assert "drive" in readme or "filing" in readme


def test_the_readme_states_what_is_not_supported():
    """The README says plainly what this package does not do."""
    readme = _readme().lower()
    assert "not supported" in readme
    assert "universal" in readme or "every platform" in readme


def test_the_readme_carries_no_private_path_host_or_credential():
    """The README works from a fresh checkout on any machine."""
    readme = _readme()
    # The private-path pattern is assembled rather than written out, so this
    # test file does not itself trip the package privacy scan.
    private_path = "/" + "Users" + "/"
    assert private_path not in readme
    assert not re.search(r"[A-Za-z]:\\", readme), "a Windows private path"
    assert "Osiris" not in readme
    for pattern in (
        r"\bapi[_-]?key\b\s*[:=]",
        r"\btoken\b\s*[:=]\s*\S",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"\bpassword\b\s*[:=]\s*\S",
    ):
        assert not re.search(pattern, readme, re.IGNORECASE), pattern


def test_the_readme_keeps_the_agent_neutral_scope_statement():
    """The scope statement still describes what the skill is."""
    readme = _readme()
    assert "Host-neutral" in readme
    for host in ("Codex", "Claude Code", "OpenCode", "Hermes"):
        assert host in readme


# ------------------------------------------------------ packaging and drift


def test_the_package_carries_the_rc_references():
    """The readiness and remediation plans ship with the package."""
    for name in ("rc-readiness.md", "rc-remediation-plan.md"):
        assert (ROOT / "references" / name).exists(), name


def test_the_public_exporter_keeps_the_loss_cell_guard():
    """The guard ported from the installed copy is still in the source."""
    source = (ROOT / "scripts" / "exporter.py").read_text(encoding="utf-8")
    assert "ISNUMBER" in source
    assert 'f\'=IF(ISNUMBER(C{row}),C{total_row}-C{row},"")\'' in source


def test_the_diagnostic_and_installer_ship_with_the_package():
    """The new scripts are part of the public package."""
    assert (ROOT / "scripts" / "capability_check.py").exists()
    assert (ROOT / "scripts" / "install.py").exists()
    assert MANIFEST.exists()

#!/usr/bin/env python3
"""Install Miseform: the skill itself, its dependencies, and its browser.

One command, run from the folder that holds ``SKILL.md``:

    python3 scripts/install.py

What it does, in order:

1. **Checks the prerequisites** before changing anything. A missing
   prerequisite is reported by name, with the exact remedy, never as a stack
   trace.
2. **Resolves an isolated environment.** If you already have a virtual
   environment active, that one is used. Otherwise a fresh virtual
   environment is created at ``~/.local/share/miseform/venv``. The system
   interpreter is never written to.
3. **Installs the dependencies** listed in ``requirements.txt`` into that
   environment.
4. **Installs the Chromium build** Playwright drives, so the PDF edition has
   a browser. This step is optional: skip it with ``--skip-browser``.
5. **Copies the skill** into the skill directory of every supported host
   already present on this machine. The copy is additive: it never deletes
   anything, and it never touches private configuration.
6. **Prints the activation line** for each supported host, the environment
   the export scripts run in, and the capability check output.

Re-running is safe. It updates the skill files it owns, leaves everything
else in place, and never overwrites private configuration.

Options:

    --host NAME     install into this host only; repeatable. Default is every
                    supported host whose skill directory already exists.
    --venv PATH     use this virtual environment instead of the default.
    --no-optional   skip the optional dependencies (see requirements.txt).
    --skip-browser  do not install the Chromium build.
    --dry-run       report what would happen and change nothing.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
DEFAULT_VENV = Path.home() / ".local" / "share" / "miseform" / "venv"
MIN_PYTHON = (3, 9)

# Where each supported host keeps a skill folder, and how the host is
# activated once the skill is there.
HOSTS = {
    "codex": Path.home() / ".agents" / "skills" / "miseform",
    "claude": Path.home() / ".claude" / "skills" / "miseform",
    "opencode": Path.home() / ".config" / "opencode" / "skills" / "miseform",
    "hermes": Path.home() / ".hermes" / "skills" / "miseform",
}
ACTIVATION = {
    "codex": "$miseform, or ask for the skill by name",
    "claude": "/miseform",
    "opencode": 'ask for the skill by name: "Use miseform skill"',
    "hermes": "/miseform",
}

# Never copied, never deleted, never overwritten. These are the private
# configuration files a cook keeps beside or beside-the skill.
PRIVATE_NAMES = {"recipe-library.local.json", ".env"}
PRIVATE_SUFFIXES = (".local.json", ".local.yaml")
PRIVATE_DIRS = {"config"}
# Build output that must not travel with the skill. Tool caches count: a
# developer who runs a type checker or a linter in the package folder gets
# cache directories, and those must never be copied into a host's skill
# folder.
SKIP_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    ".venv",
    ".DS_Store",
}
SKIP_SUFFIXES = (".pyc",)


class InstallError(RuntimeError):
    """A prerequisite or a step failed, with the remedy attached."""


# --------------------------------------------------------------------- output


def say(message: str = "") -> None:
    print(message)


def step(message: str) -> None:
    print(f"==> {message}")


def warn(message: str) -> None:
    print(f"    note: {message}")


def fail(message: str, remedy: str) -> InstallError:
    return InstallError(f"{message}\n    fix: {remedy}")


# ------------------------------------------------------------------- manifest


def parse_manifest(text: str) -> tuple[list[str], list[str]]:
    """Return the required and optional requirement lines of the manifest.

    A requirement line is any non-comment line. An optional requirement is
    written as a comment beginning with ``optional:``, so a plain
    ``pip install -r requirements.txt`` installs the required set only.
    """
    required: list[str] = []
    optional: list[str] = []
    for raw in text.splitlines():
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


# ----------------------------------------------------------------- preflight


def check_python() -> None:
    if sys.version_info < MIN_PYTHON:
        found = ".".join(str(part) for part in sys.version_info[:3])
        raise fail(
            f"Miseform needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer; "
            f"this interpreter is {found}.",
            "install a newer Python and run this command with it, for example "
            "'python3.11 scripts/install.py'",
        )


def check_source() -> None:
    if not (PACKAGE / "SKILL.md").exists():
        raise fail(
            f"this folder does not look like the Miseform package: no SKILL.md "
            f"beside {HERE.name}/.",
            "run the command from inside the miseform folder, the one that "
            "holds SKILL.md",
        )
    if not (PACKAGE / "requirements.txt").exists():
        raise fail(
            "the package is missing requirements.txt, so its dependencies "
            "cannot be declared.",
            "reinstall or re-download the miseform folder",
        )


def check_venv_module() -> None:
    try:
        import ensurepip  # noqa: F401
    except ImportError:
        raise fail(
            "this Python cannot create a virtual environment (the venv or "
            "ensurepip module is missing).",
            "install the matching virtual-environment package for your "
            "interpreter, for example 'sudo apt install python3-venv' on "
            "Debian or Ubuntu, then run this command again",
        ) from None


def check_pip(python: Path) -> None:
    probe = subprocess.run(
        [str(python), "-m", "pip", "--version"],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        raise fail(
            f"pip is not usable inside {python}.",
            "run 'python3 -m ensurepip --upgrade' with that interpreter, then "
            "run this command again",
        )


def check_network(python: Path) -> None:
    """Best-effort reachability check for the package index."""
    probe = subprocess.run(
        [str(python), "-m", "pip", "download", "--no-deps", "--dest",
         str(Path(os.environ.get("TMPDIR", "/tmp")) / "mf-netcheck"),
         "jsonschema"],
        capture_output=True,
        text=True,
    )
    shutil.rmtree(
        Path(os.environ.get("TMPDIR", "/tmp")) / "mf-netcheck", ignore_errors=True
    )
    if probe.returncode != 0:
        raise fail(
            "the package index could not be reached, so the dependencies "
            "cannot be installed.",
            "check the network and any proxy settings, or download the wheels "
            "on another machine and install them with "
            "'pip install --no-index --find-links <dir> -r requirements.txt'",
        )


# ------------------------------------------------------------------ the steps


def resolve_environment(explicit: Path | None) -> Path:
    """Return the virtual environment to install into.

    An already-active virtual environment wins, then an existing ``.venv``
    beside the package, then a fresh environment at the default location.
    A virtual environment that is active without being activated — a venv
    Python invoked by its own path — is detected too, so the dependencies
    land in the interpreter the cook actually ran the command with.
    """
    if explicit is not None:
        target = explicit.expanduser()
        if not (target / "bin" / "python").exists():
            raise fail(
                f"{target} is not a virtual environment.",
                "point --venv at an existing virtual environment, or drop the "
                "option to let Miseform create one",
            )
        return target

    active = os.environ.get("VIRTUAL_ENV")
    if active:
        candidate = Path(active)
        if (candidate / "bin" / "python").exists():
            return candidate

    # A venv Python run by its own path: sys.prefix differs from the base
    # prefix, and the prefix is the environment to install into.
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        candidate = Path(sys.prefix)
        if (candidate / "bin" / "python").exists():
            return candidate

    local = PACKAGE / ".venv"
    if (local / "bin" / "python").exists():
        return local

    return DEFAULT_VENV


def create_environment(target: Path) -> Path:
    if (target / "bin" / "python").exists():
        warn(f"reusing the existing environment at {target}")
        return target / "bin" / "python"
    step(f"creating an isolated environment at {target}")
    try:
        venv.EnvBuilder(with_pip=True, clear=False).create(str(target))
    except Exception as exc:
        raise fail(
            f"the virtual environment at {target} could not be created: {exc}",
            "install the virtual-environment package for your interpreter, for "
            "example 'sudo apt install python3-venv' on Debian or Ubuntu, then "
            "run this command again",
        ) from None
    return target / "bin" / "python"


def install_requirements(python: Path, required: list[str], optional: list[str],
                         include_optional: bool) -> None:
    step("installing the declared dependencies")
    install = subprocess.run(
        [str(python), "-m", "pip", "install", "--disable-pip-version-check",
         "-r", str(PACKAGE / "requirements.txt")],
        capture_output=True,
        text=True,
    )
    if install.returncode != 0:
        detail = (install.stderr or install.stdout).strip().splitlines()
        tail = detail[-1] if detail else "no output"
        raise fail(
            f"the required dependencies could not be installed: {tail}",
            "check the network and any proxy settings, then run this command "
            "again; the dependencies are listed in requirements.txt",
        )

    if include_optional and optional:
        step("installing the optional dependencies")
        result = subprocess.run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check",
             *optional],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            tail = detail[-1] if detail else "no output"
            warn(
                "the optional dependencies could not be installed, and Miseform "
                f"does not need them to work: {tail}"
            )


def install_browser(python: Path) -> None:
    step("installing the Chromium build Playwright drives (optional)")
    result = subprocess.run(
        [str(python), "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        tail = detail[-1] if detail else "no output"
        warn(
            "the Chromium build could not be downloaded, so the PDF edition "
            f"stays pending until a browser is available: {tail}"
        )
        warn(
            "install a browser yourself and re-run the capability check to "
            "confirm: on Debian or Ubuntu 'sudo apt install chromium', on "
            "macOS 'brew install --cask google-chrome'"
        )


# --------------------------------------------------------------- the skill copy


def is_private(relative: Path) -> bool:
    if relative.name in PRIVATE_NAMES:
        return True
    if relative.name.endswith(PRIVATE_SUFFIXES):
        return True
    return any(part in PRIVATE_DIRS for part in relative.parts)


def copy_skill(destination: Path) -> int:
    """Copy the skill into ``destination`` without removing anything.

    Only files the package owns are written. Private configuration in the
    destination is left exactly as it is, and nothing is ever deleted.
    """
    written = 0
    for source in sorted(PACKAGE.rglob("*")):
        relative = source.relative_to(PACKAGE)
        if any(part in SKIP_NAMES for part in relative.parts):
            continue
        if source.name.endswith(SKIP_SUFFIXES):
            continue
        if is_private(relative):
            continue
        target = destination / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != source.read_bytes():
            shutil.copy2(source, target)
            written += 1
    return written


def selected_hosts(requested: list[str]) -> list[str]:
    if requested:
        unknown = [name for name in requested if name not in HOSTS]
        if unknown:
            raise fail(
                f"unknown host: {', '.join(unknown)}.",
                "use one of: " + ", ".join(sorted(HOSTS)),
            )
        return sorted(set(requested))
    # Only touch hosts that are already installed on this machine. Installing
    # into a host that is not present would create directories nobody asked
    # for.
    return sorted(
        name
        for name, destination in HOSTS.items()
        if destination.parent.parent.exists()
    )


# --------------------------------------------------------------------- report


def print_activation(installed: list[str]) -> None:
    step("how to activate the skill")
    for name in ("codex", "claude", "opencode", "hermes"):
        marker = "installed" if name in installed else "not installed here"
        say(f"    {name:<9} {ACTIVATION[name]:<45} {HOSTS[name]}  ({marker})")
    say(
        "    The skill folder can be copied by hand to any other host: the "
        "folder that holds SKILL.md is the whole skill."
    )


def print_environment(python: Path) -> None:
    step("the environment the export scripts run in")
    say(f"    interpreter: {python}")
    say(f"    activate:    source {python.parent.parent}/bin/activate")
    say(
        "    Miseform's own scripts are run by your host agent; they need this "
        "environment's packages, so keep it activated in the shell your agent "
        "runs in."
    )


def run_capability_check(python: Path) -> None:
    step("capability check")
    result = subprocess.run(
        [str(python), str(PACKAGE / "scripts" / "capability_check.py")],
        capture_output=True,
        text=True,
    )
    for line in (result.stdout or "").splitlines():
        say(f"    {line}")
    if result.returncode not in (0, 1):
        for line in (result.stderr or "").splitlines():
            say(f"    {line}")


# ----------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="install.py",
        description=(
            "Install the Miseform skill, its dependencies and its browser. "
            "Safe to run again."
        ),
    )
    parser.add_argument(
        "--host",
        action="append",
        default=[],
        metavar="NAME",
        help="install into this host only; repeatable (" + ", ".join(HOSTS) + ")",
    )
    parser.add_argument(
        "--venv",
        default=None,
        metavar="PATH",
        help="use this virtual environment instead of the default",
    )
    parser.add_argument(
        "--no-optional",
        action="store_true",
        help="skip the optional dependencies listed in requirements.txt",
    )
    parser.add_argument(
        "--skip-browser",
        action="store_true",
        help="do not install the Chromium build",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would happen and change nothing",
    )
    args = parser.parse_args(argv)

    say("Miseform installer")
    say(f"    package:  {PACKAGE}")
    say()

    try:
        step("checking prerequisites")
        check_python()
        check_source()
        check_venv_module()
        hosts = selected_hosts(args.host)
        if not hosts:
            warn(
                "no supported host was found on this machine, so the skill "
                "folder was not copied anywhere"
            )
        say(f"    python:   {'.'.join(str(p) for p in sys.version_info[:3])}")
        say(f"    hosts:    {', '.join(hosts) if hosts else 'none detected'}")
        say()

        if args.dry_run:
            say("Dry run: nothing was installed and nothing was changed.")
            return 0

        target = resolve_environment(Path(args.venv) if args.venv else None)
        python = create_environment(target)
        check_pip(python)
        check_network(python)

        required, optional = parse_manifest(
            (PACKAGE / "requirements.txt").read_text(encoding="utf-8")
        )
        install_requirements(python, required, optional, not args.no_optional)

        if not args.skip_browser:
            install_browser(python)

        installed: list[str] = []
        for name in hosts:
            destination = HOSTS[name]
            try:
                destination.mkdir(parents=True, exist_ok=True)
                written = copy_skill(destination)
            except OSError as exc:
                warn(f"the skill folder for {name} could not be written: {exc}")
                continue
            installed.append(name)
            step(f"installed the skill for {name}")
            say(f"    folder:   {destination}")
            say(
                f"    files:    {written} written"
                + (
                    ", everything else left in place"
                    if written
                    else ", already up to date"
                )
            )

        print_environment(python)
        print_activation(installed)
        run_capability_check(python)
        say()
        step("done")
        say(
            "    Run the published checks with: "
            f"{python} -m pytest tests/ -q"
        )
        return 0
    except InstallError as exc:
        print()
        print(f"Cannot continue: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

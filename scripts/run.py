#!/usr/bin/env python3
"""Run a bundled tool with the isolated interpreter recorded by installation."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    scripts = Path(__file__).resolve().parent
    if not args or Path(args[0]).name != args[0] or not args[0].endswith('.py'):
        print('Usage: python3 scripts/run.py TOOL.py [arguments]', file=sys.stderr)
        return 2
    tool = scripts / args[0]
    if not tool.is_file() or tool.name in {'run.py', 'install.py'}:
        print('Unknown bundled tool; use a script from scripts/.', file=sys.stderr)
        return 2
    runtime = scripts.parent / '.miseform-runtime.json'
    python = Path(sys.executable)
    if runtime.exists():
        try:
            python = Path(json.loads(runtime.read_text())['python'])
            if not python.is_file():
                raise ValueError('installed interpreter is missing')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f'Runtime pending: {exc}. Re-run python3 scripts/install.py.', file=sys.stderr)
            return 1
    try:
        return subprocess.run([str(python), str(tool), *args[1:]], check=False).returncode
    except OSError as exc:
        print(f'Runtime pending: {exc}. Re-run python3 scripts/install.py.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

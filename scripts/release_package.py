#!/usr/bin/env python3
"""Select public source, bind its hashes, and build a deterministic ZIP."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT_FILES = {'SKILL.md', 'README.md', 'TESTING.md', 'LICENSE', 'CONTRIBUTING.md',
              'CHANGELOG.md', 'CONTENT_POLICY.md', 'VERSION', 'requirements.txt',
              '.gitignore', 'recipe-library.example.json', 'kitchen-defaults.example.json'}
ROOT_DIRS = {'scripts', 'references', 'templates', 'tests', 'examples', '.github',
             'miseform-theme-preview'}
EXCLUDED = {'__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.git',
            '.venv', 'work', 'private', 'profiles', 'uploads', 'recipes', 'exports',
            'receipts', 'staging', 'output', 'outputs', 'config', '.miseform-backups',
            'logs', 'log', 'evidence', 'scratch', 'tmp', 'temp', 'backups', 'secrets'}
SUFFIXES = {'scripts': {'.py'}, 'tests': {'.py', '.json', '.md'},
            'references': {'.md', '.json'}, 'templates': {'.md', '.html', '.css'},
            'examples': {'.json', '.md', '.html', '.pdf', '.xlsx', '.png', '.jpg', '.jpeg'},
            'miseform-theme-preview': {'.html', '.pdf', '.xlsx', '.png'},
            '.github': {'.md', '.yml', '.yaml'}}


def public_files(root: Path) -> list[Path]:
    """Allow public roots only; never follow symlinks or include local state."""
    selected = []
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if relative.parts[0] not in ROOT_DIRS and str(relative) not in ROOT_FILES:
            continue
        if any(part in EXCLUDED or part.startswith('.env')
               or 'scratch' in part.lower() for part in relative.parts):
            continue
        if any(parent.is_symlink() for parent in [path, *path.parents] if parent != root.parent):
            continue
        if relative.parts[0] in SUFFIXES and path.suffix.lower() not in SUFFIXES[relative.parts[0]]:
            continue
        if (not path.is_file() or path.name == '.DS_Store'
                or re.search(r'(?:^|[-_.])(?:credentials?|secrets?|private[-_]?key)(?:[-_.]|$)', path.name, re.IGNORECASE)
                or path.name.endswith(('.local.json', '.local.yaml', '.pyc'))
                or re.search(r' \d+\.[^.]+$', path.name)):
            continue
        selected.append(path)
    return selected


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_version(root: Path) -> str:
    version = (root / 'VERSION').read_text().strip()
    skill = (root / 'SKILL.md').read_text()
    match = re.search(r'^\s+version:\s*["\']?([\w.+-]+)', skill, re.MULTILINE)
    if not match or match.group(1) != version:
        raise ValueError('VERSION and SKILL.md metadata version differ')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][\w.-]+)?', version):
        raise ValueError('invalid package version')
    return version


def source_manifest(root: Path) -> dict:
    return {'schema': 1, 'package': 'miseform', 'version': package_version(root),
            'files': {path.relative_to(root).as_posix(): sha256(path)
                      for path in public_files(root)}}


def verify_source(root: Path) -> None:
    """Check extracted release bytes and version; local checkouts may lack metadata."""
    path = root / 'SOURCE_MANIFEST.json'
    if not path.exists():
        raise ValueError('SOURCE_MANIFEST.json is missing')
    expected = json.loads(path.read_text())
    actual = source_manifest(root)
    if expected != actual:
        raise ValueError('source integrity mismatch; use an unchanged release archive or a reviewed checkout')


def build_release(root: Path, outdir: Path) -> Path:
    manifest = source_manifest(root)
    outdir.mkdir(parents=True, exist_ok=True)
    target = outdir / f'miseform-{manifest["version"]}-source.zip'
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in [*manifest['files'], 'SOURCE_MANIFEST.json']:
            payload = ((json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
                       if name == 'SOURCE_MANIFEST.json' else (root / name).read_bytes())
            entry = zipfile.ZipInfo(f'miseform/{name}', date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, payload)
    (outdir / 'SOURCE_MANIFEST.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    (outdir / 'SHA256SUMS').write_text(f'{sha256(target)}  {target.name}\n')
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--outdir', type=Path)
    group.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    if args.verify:
        verify_source(root)
        print('Source manifest: all selected file hashes and version verified')
    else:
        print(build_release(root, args.outdir))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

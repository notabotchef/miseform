"""Build-time integrity binding for local, accidental artifact staleness.

Not an attestation: anyone able to replace artifacts and manifest can forge a
new binding. Only build_card writes this metadata during normal workflow.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from locales import DEFAULT_LANGUAGE, load_translation_bundle, resolve_language
from themes import DEFAULT_THEME
from translation import normalize_translation, translation_coverage

KINDS = ('markdown', 'html', 'json', 'pdf', 'xlsx')


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_path(card, directory: Path) -> Path:
    return directory / f'{card.filename_stem}.manifest.json'


def write_manifest(card, directory: Path, paths: dict, requested: list[str], *,
                   language: str, theme: str, paper: str, texts) -> None:
    manifest = {
        'schema': 2,
        'translation_coverage': translation_coverage(card, texts),
        'record_digest': digest(card.data),
        'settings': {'language': language, 'theme': theme, 'paper': paper},
        'translation': texts,
        'translation_digest': digest(texts),
        'requested_editions': requested,
        'artifacts': {kind: {'name': paths[kind].name,
                             'sha256': file_hash(paths[kind])}
                      for kind in requested if kind in paths and paths[kind].is_file()},
    }
    target = manifest_path(card, directory)
    temporary = target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(target)


def verify_manifest(card, directory: Path, paths: dict) -> tuple[dict | None, dict[str, str]]:
    """Recheck source record, effective translations and all requested bytes."""
    try:
        manifest = json.loads(manifest_path(card, directory).read_text())
        requested = manifest['requested_editions']
        if (manifest['schema'] != 2 or not isinstance(requested, list)
                or not requested or len(set(requested)) != len(requested)
                or any(kind not in KINDS for kind in requested)
                or 'json' not in requested):
            raise ValueError('invalid requested editions or manifest schema')
        if manifest['record_digest'] != digest(card.data):
            raise ValueError('manifest canonical record digest differs from current card')
        settings = manifest['settings']
        if (settings['language'] != resolve_language(None, card.data)
                or settings['theme'] != card.data.get('theme', DEFAULT_THEME)):
            raise ValueError('manifest rendering settings differ from current card')
        texts = manifest['translation']
        normalize_translation(card, texts, settings['language'])
        if manifest['translation_coverage'] != translation_coverage(card, texts):
            raise ValueError('translation coverage differs; rebuild required')
        if manifest['translation_digest'] != digest(texts):
            raise ValueError('manifest translation digest differs')
        # Built JSON embeds the effective overlay, allowing portable rebuilds.
        embedded = card.data.get('render_translation')
        if embedded is not None and (embedded != texts or
                card.data.get("render_translation_language") != settings["language"]):
            raise ValueError('manifest translation differs from embedded translation')
        if card.source:
            current = load_translation_bundle(settings['language'], card.source)
            if current is not None and current != texts:
                raise ValueError('translation sidecar changed since build')
        canonical = json.loads(paths['json'].read_text())
        if canonical != card.data:
            raise ValueError('build canonical JSON differs from current card')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, {kind: f'build manifest missing or invalid: {exc}; export not built with verified binding'
                      for kind in KINDS}
    errors = {}
    for kind in requested:
        try:
            artifact = manifest['artifacts'][kind]
            if artifact['name'] != paths[kind].name or artifact['sha256'] != file_hash(paths[kind]):
                raise ValueError('artifact bytes differ from build manifest')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors[kind] = f'{kind} build integrity failed: {exc}'
    return manifest, errors

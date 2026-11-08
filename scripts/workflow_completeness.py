"""Check declared workflow coverage, never source truth or production approval.

This optional sidecar is separate from the canonical recipe and arithmetic.
An accepted ledger is evidence of declared coverage only: independent review
still judges extraction completeness, source quality and ingredient identity.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _pointer(document, pointer):
    """Resolve a strict JSON pointer; do not accept Python negative indexes."""
    if not isinstance(pointer, str) or not pointer.startswith('/'):
        raise ValueError('Expected an absolute JSON pointer')
    value = document
    for raw in pointer[1:].split('/'):
        if '~' in raw.replace('~0', '').replace('~1', ''):
            raise ValueError('Invalid pointer escape')
        key = raw.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not key.isdecimal() or str(int(key)) != key:
                raise ValueError('Invalid array index')
            value = value[int(key)]
        elif isinstance(value, dict):
            value = value[key]
        else:
            raise TypeError('Pointer traverses a scalar')
    return value


def _disposition(value, kind):
    if not isinstance(value, dict):
        return False
    status = value.get('status')
    if status == 'not_applicable':
        return _text(value.get('reason'))
    if status == 'research_unresolved' and kind != 'allergens':
        attempts = value.get('attempts')
        return (_text(value.get('reason')) and isinstance(attempts, list) and bool(attempts)
                and all(isinstance(a, dict) and all(_text(a.get(k)) for k in
                        ('query', 'source', 'result')) for a in attempts))
    if kind == 'allergens':
        if status == 'unknown_external':
            return _text(value.get('reason'))
        if status == 'known':
            labels = value.get('intentional')
            return (isinstance(labels, list) and all(_text(label) for label in labels)
                    and _text(value.get('basis')))
        return False
    if status != 'sourced_proposal' or not all(_text(value.get(k)) for k in ('unit', 'basis', 'source')):
        return False
    if kind == 'research':
        return _number(value.get('amount'))
    low, high = value.get('minimum'), value.get('maximum')
    return (_number(low) and _number(high) and low <= high
            and value.get('unit') in {'seconds', 'minutes', 'hours'} and _text(value.get('endpoint')))


def _coverage(entries, expected, card, intake, kind):
    findings, seen = [], set()
    if not isinstance(entries, list):
        return [f'{kind}: expected an array of dispositions']
    for index, entry in enumerate(entries):
        label = f'{kind}/{index}'
        if not isinstance(entry, dict):
            findings.append(f'{label}: expected an object')
            continue
        pointer = entry.get('pointer')
        if not isinstance(pointer, str) or pointer not in expected:
            findings.append(f'{label}: dangling or wrong-kind pointer')
            continue
        if pointer in seen:
            findings.append(f'{label}: duplicate pointer {pointer}')
        seen.add(pointer)
        if kind == 'ingredients':
            excerpt = entry.get('input_excerpt')
            if not _text(excerpt) or excerpt not in intake or not _text(entry.get('input_locator')):
                findings.append(f'{pointer}: intake excerpt/locator missing or not present in input')
            try:
                retained = _pointer(card, entry.get('retained_pointer'))
                prefix = pointer + '/'
                if (not entry.get('retained_pointer', '').startswith(prefix)
                        or not isinstance(retained, str) or not _text(excerpt) or excerpt not in retained):
                    raise ValueError('Original excerpt not retained in this ingredient')
            except (ValueError, KeyError, IndexError, TypeError):
                findings.append(f'{pointer}: original intake excerpt not retained at ingredient pointer')
            for field in ('research', 'allergens'):
                if not _disposition(entry.get(field), field):
                    findings.append(f'{pointer}: incomplete {field} disposition')
        elif not _disposition(entry.get('timing'), 'timing'):
            findings.append(f'{pointer}: incomplete routine timing disposition')
    findings.extend(f'{pointer}: missing {kind} disposition' for pointer in sorted(expected - seen))
    return findings


def validate_ledger(ledger_path: str | Path, card_path: str | Path) -> list[str]:
    """Return findings for a version-1 sidecar; do not mutate any inputs.

    Input paths resolve relative to the sidecar. Hashes bind exact bytes, so
    any correction or reserialization requires a freshly reviewed ledger.
    """
    ledger_path, card_path = Path(ledger_path), Path(card_path)
    try:
        ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
        card_bytes = card_path.read_bytes()
        card = json.loads(card_bytes)
        if not isinstance(ledger, dict) or type(ledger.get('schema_version')) is not int or ledger.get('schema_version') != 1:
            return ['ledger: expected schema_version 1 object']
        if not _text(ledger.get('input_file')):
            return ['ledger: input_file missing']
        input_name = Path(ledger['input_file'])
        input_path = (ledger_path.parent / input_name).resolve()
        if input_name.is_absolute() or not input_path.is_relative_to(ledger_path.parent.resolve()):
            return ['ledger: input_file must remain inside the ledger directory']
        input_bytes = input_path.read_bytes()
        intake = input_bytes.decode('utf-8')
        components = card['components']
        if not isinstance(components, list):
            return ['card: components must be an array']
        if any(not isinstance(component, dict) for component in components):
            return ['card: every component must be an object']
        for component in components:
            ingredients = component.get('ingredients', [])
            if not isinstance(ingredients, list) or any(not isinstance(row, dict) for row in ingredients):
                return ['card: ingredients must be an array of objects']
        expected_components = {f'/components/{i}' for i in range(len(components))}
        expected_ingredients = {f'/components/{i}/ingredients/{j}'
                                for i, c in enumerate(components)
                                for j in range(len(c.get('ingredients', [])))}
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return [f'ledger: cannot read bound workflow inputs ({type(exc).__name__})']
    findings = []
    for key, content in (('card_sha256', card_bytes), ('input_sha256', input_bytes)):
        if ledger.get(key) != hashlib.sha256(content).hexdigest():
            findings.append(f'ledger: stale or missing {key}')
    findings.extend(_coverage(ledger.get('ingredients'), expected_ingredients, card, intake, 'ingredients'))
    findings.extend(_coverage(ledger.get('components'), expected_components, card, intake, 'components'))
    return findings

#!/usr/bin/env python3
"""Fill unknown boilerplate around agent-authored canonical culinary fields.

This tool does not extract recipes, research techniques, establish applicability,
select scaling references, or approve cards. Output is an unreleased draft.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

from card_model import Card, CardError, PROCESS_CONTROL_KEYS

UNKNOWN = 'NEEDS CHEF CONFIRMATION'
FACT_FIELDS = (
    'time_total', 'time_active', 'time_inactive', 'difficulty_level',
    'difficulty_technique', 'yield_summary', 'yield_portions',
    'storage_summary', 'storage_reference',
)
CORE_FIELDS = ('recipe_id', 'title', 'revision_date', 'recipe_type',
               'components', 'stages', 'provenance')


def _fill_missing(defaults: dict, supplied: dict) -> dict:
    """Return independent data, preserving explicit values including nulls."""
    result = copy.deepcopy(defaults)
    for key, value in supplied.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _fill_missing(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def scaffold(seed: dict) -> dict:
    """Complete structural unknowns only; preserve every supplied field value."""
    if not isinstance(seed, dict):
        raise CardError('seed must be a canonical card JSON object')
    missing = [key for key in CORE_FIELDS if key not in seed]
    if missing:
        raise CardError('supply culinary core fields: ' + ', '.join(missing))
    status = seed.get('status', 'R&D')
    if not isinstance(status, str) or status not in {'R&D', 'NEEDS CHEF CONFIRMATION'}:
        raise CardError('scaffold accepts unreleased draft seeds only')
    evidence = seed.get('provenance')
    if not isinstance(evidence, dict) or not isinstance(evidence.get('evidence'), str) or not evidence['evidence'].strip():
        raise CardError('supply provenance.evidence identifying culinary source support')
    defaults = {
        'version': 'v0.1-draft.1', 'status': 'R&D',
        'intro': UNKNOWN + ': description not supplied.',
        'equipment': UNKNOWN + ': equipment and capacity not established.',
        'allergens': UNKNOWN + ': ingredient labels and cross-contact controls not verified.',
        'facts': {field: UNKNOWN + ': not established.' for field in FACT_FIELDS},
        'percentage_basis': {'basis_label': UNKNOWN + ': scaling basis not established.'},
        'process_controls': {key: UNKNOWN + ': applicability and parameters not established.'
                             for key in PROCESS_CONTROL_KEYS},
        'input_total_g': None, 'usable_yield_g': None,
        'release_blockers': [UNKNOWN + ': unresolved scaffold fields require review; draft is unreleased.'],
    }
    result = _fill_missing(defaults, seed)
    errors = Card(result).schema_errors()
    if errors:
        raise CardError('invalid canonical card: ' + '; '.join(errors))
    if 'input_total_g' not in seed:
        derived = Card(result).derived()
        if derived.input_complete and derived.input_structure_complete:
            result = {**result, 'input_total_g': derived.input_total_g}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            'Required canonical seed fields: recipe_id, title, revision_date '
            '(YYYY-MM-DD), recipe_type (master recipe/component/assembly), '
            'components, stages, provenance.evidence. '
            'components: [{"name": "...", "ingredients": '
            '[{"row_id": "...", "name": "...", "weight_g": null, '
            '"notes": "source evidence"}]}]. '
            'stages: [{"name": "...", "steps": '
            '[{"number": 1, "text": "chef method or labeled sourced proposal"}]}]. '
            'provenance: {"evidence": "source support"}. '
            'Keep supplied quantity/original units, formula, source_excerpt and '
            'research evidence in their canonical fields; do not invent missing '
            'ingredients or methods. Other supplied canonical fields are preserved.'
        ),
    )
    parser.add_argument('seed', help='Agent-authored subset of canonical card JSON')
    parser.add_argument('--out', required=True, help='Unreleased canonical card JSON destination')
    args = parser.parse_args(argv)
    try:
        seed = json.loads(Path(args.seed).read_text(encoding='utf-8'))
        result = scaffold(seed)
        findings = Card(result).findings()
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    except (OSError, UnicodeError, ValueError, CardError) as exc:
        print(f'CARD ERROR: {exc}', file=sys.stderr)
        return 2
    print(f'Unreleased card: {destination}')
    for finding in findings:
        print(f'  {finding}')
    print('Scaffolding supplies no research, source verification, workflow coverage or approval.')
    return 1 if any(finding.severity == 'blocker' for finding in findings) else 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Scaffolding removes boilerplate without inventing culinary facts."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from card_model import Card, CardError, PROCESS_CONTROL_KEYS
from scaffold_card import scaffold


def seed():
    return {
        'recipe_id': 'TEMP-SCAFFOLD', 'title': 'TEST DRESSING',
        'revision_date': '2026-11-05', 'recipe_type': 'component',
        'components': [{'name': 'Dressing', 'ingredients': [
            {'row_id': 'oil', 'name': 'Sesame oil', 'weight_g': 100,
             'notes': 'chef-stated: 100 g sesame oil'},
            {'row_id': 'vinegar', 'name': 'Vinegar', 'weight_g': None,
             'quantity': {'amount': 1, 'unit': 'tbsp', 'kind': 'volume',
                          'original': '1 tbsp vinegar'},
             'notes': 'chef-stated: 1 tbsp vinegar'},
        ]}],
        'stages': [{'name': 'Mix', 'steps': [{'number': 1,
            'text': 'Chef-stated: mix oil and vinegar.',
            'ingredient_refs': ['oil', 'vinegar']}]}],
        'provenance': {'evidence': 'Chef supplied ingredient list and mixing method.'},
    }


def test_source_and_input_are_preserved_without_aliasing():
    source = seed()
    original = copy.deepcopy(source)
    output = scaffold(source)
    assert source == original
    for key, value in original.items():
        assert output[key] == value
    output['components'][0]['ingredients'][0]['name'] = 'Changed'
    assert source == original
    assert Card(scaffold(source)).schema_errors() == []


def test_unknown_mass_and_measured_yield_remain_null():
    output = scaffold(seed())
    assert output['input_total_g'] is None
    assert output['usable_yield_g'] is None
    assert output['components'][0]['ingredients'][1]['quantity']['original'] == '1 tbsp vinegar'


def test_defaults_are_explicit_unknowns_not_unsupported_na():
    output = scaffold(seed())
    assert output['status'] == 'R&D'
    assert set(output['process_controls']) == set(PROCESS_CONTROL_KEYS)
    assert all('NEEDS CHEF CONFIRMATION' in text for text in output['process_controls'].values())
    assert all('NEEDS CHEF CONFIRMATION' in text for text in output['facts'].values())
    assert output['release_blockers']
    assert 'NEEDS CHEF CONFIRMATION' in output['percentage_basis']['basis_label']
    assert 'reference_row_id' not in output['components'][0]


def test_explicit_values_and_nulls_are_not_replaced():
    source = {**seed(), 'input_total_g': None, 'usable_yield_g': 42,
              'facts': {'time_active': 'Chef-stated: 2 minutes'},
              'process_controls': {'fermentation': 'Chef-stated: 2 days; temperature unresolved'}}
    output = scaffold(source)
    assert output['input_total_g'] is None
    assert output['usable_yield_g'] == 42
    assert output['facts']['time_active'] == source['facts']['time_active']
    assert output['process_controls']['fermentation'] == source['process_controls']['fermentation']
    source['input_total_g'] = 99
    assert scaffold(source)['input_total_g'] == 99


def test_complete_mass_uses_native_formula_resolution():
    source = seed()
    source['components'][0]['ingredients'][1] = {
        'row_id': 'salt', 'name': 'Salt',
        'formula': {'kind': 'percent', 'basis_row_id': 'oil', 'value': 2},
        'notes': 'chef-stated: 2% of oil mass',
    }
    assert scaffold(source)['input_total_g'] == 102
    assert scaffold(source)['usable_yield_g'] is None


@pytest.mark.parametrize('status', ['PRODUCTION', 'SUPERSEDED', [], {}, None])
def test_release_states_refused(status):
    with pytest.raises(CardError):
        scaffold({**seed(), 'status': status})


@pytest.mark.parametrize('field', ['title', 'components', 'stages', 'provenance'])
def test_missing_culinary_core_is_not_fabricated(field):
    source = seed()
    del source[field]
    with pytest.raises(CardError):
        scaffold(source)


def test_invalid_canonical_field_refused():
    with pytest.raises(CardError):
        scaffold({**seed(), 'invented_recipe_field': 'no alternate schema'})


def test_cli_saves_unreleased_record_reports_findings_and_native_build(tmp_path):
    source = tmp_path / 'seed.json'
    output = tmp_path / 'card.json'
    source.write_text(json.dumps(seed()))
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/run.py'),
        'scaffold_card.py', str(source), '--out', str(output)], text=True, capture_output=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert output.exists()
    assert 'reference-row-missing' in result.stdout
    built = subprocess.run([sys.executable, str(ROOT / 'scripts/run.py'),
        'build_card.py', str(output), '--outdir', str(tmp_path / 'built'),
        '--skip-pdf', '--skip-xlsx'], text=True, capture_output=True)
    assert built.returncode == 1, built.stdout + built.stderr
    assert list((tmp_path / 'built').glob('*.html'))
    assert list((tmp_path / 'built').glob('*.md'))
    assert list((tmp_path / 'built').glob('*.manifest.json'))


def test_repeated_link_keeps_full_total_unknown():
    source = seed()
    linked = {'name': 'Linked sauce', 'linked': {
        'component_id': 'SAUCE-1', 'version': 'v1.0', 'quantity_g': 20}}
    source['components'] = [linked, copy.deepcopy(linked)]
    assert scaffold(source)['input_total_g'] is None


@pytest.mark.parametrize('source', [[], {**seed(), 'provenance': {'evidence': ' '}}])
def test_invalid_seed_and_missing_evidence_refused(source):
    with pytest.raises(CardError):
        scaffold(source)


def test_invalid_cli_does_not_write_card(tmp_path):
    source = tmp_path / 'seed.json'
    output = tmp_path / 'card.json'
    source.write_text(json.dumps({**seed(), 'status': 'PRODUCTION'}))
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/scaffold_card.py'),
        str(source), '--out', str(output)], text=True, capture_output=True)
    assert result.returncode == 2
    assert 'CARD ERROR:' in result.stderr
    assert not output.exists()


def test_help_exposes_canonical_core_without_reading_source():
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/run.py'),
        'scaffold_card.py', '--help'], text=True, capture_output=True)
    assert result.returncode == 0
    for field in (*('recipe_id', 'title', 'revision_date', 'recipe_type',
                    'components', 'stages', 'provenance.evidence'),
                  'row_id', 'steps', 'number', 'source_excerpt'):
        assert field in result.stdout


def test_original_source_excerpt_preserved():
    source = seed()
    source['components'][0]['ingredients'][0]['source_excerpt'] = '100 g sesame oil'
    assert scaffold(source)['components'] == source['components']

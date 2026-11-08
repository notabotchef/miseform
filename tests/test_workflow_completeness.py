"""Completeness is an auditable sidecar; it never manufactures recipe mass."""
import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


def fixture(tmp_path):
    card = json.loads((ROOT / 'examples/sesame-salt-garnish.card.json').read_text())
    card['components'][0]['ingredients'][0]['weight_g'] = None
    card['components'][0]['ingredients'][0]['quantity'] = {'amount': 2, 'unit': 'cloves'}
    source = tmp_path / 'input.txt'
    source.write_text('Garlic 2 cloves; sesame 20 g; salt 10 g. Mix.\n')
    for i, excerpt in enumerate(['Garlic 2 cloves', 'sesame 20 g', 'salt 10 g']):
        card['components'][0]['ingredients'][i]['notes'] = excerpt
    path = tmp_path / 'card.json'
    path.write_text(json.dumps(card))
    proposal = {'status': 'sourced_proposal', 'amount': 6, 'unit': 'g',
                'basis': 'Comparable ingredient estimate, not measured',
                'source': 'https://example.org/ingredient-table'}
    ingredients = []
    for i in range(3):
        ingredients.append({'pointer': f'/components/0/ingredients/{i}',
                            'input_excerpt': ['Garlic 2 cloves', 'sesame 20 g', 'salt 10 g'][i],
                            'input_locator': 'line 1',
                            'retained_pointer': f'/components/0/ingredients/{i}/notes',
                            'research': deepcopy(proposal),
                            'allergens': {'status': 'unknown_external', 'reason': 'Supplier label unavailable for this ingredient'}})
    ledger = {'schema_version': 1, 'input_file': 'input.txt',
              'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'card_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'ingredients': ingredients,
              'components': [{'pointer': '/components/0', 'timing': {
                  'status': 'sourced_proposal', 'minimum': 1, 'maximum': 2, 'unit': 'minutes',
                  'endpoint': 'Evenly combined', 'basis': 'Routine mixing proposal',
                  'source': 'https://example.org/method'}}]}
    ledger_path = tmp_path / 'workflow.json'
    ledger_path.write_text(json.dumps(ledger))
    return path, ledger_path, ledger


def check(paths):
    from workflow_completeness import validate_ledger
    return validate_ledger(paths[1], paths[0])


def save(paths):
    paths[1].write_text(json.dumps(paths[2]))
    return check(paths)


def test_proposal_covers_counted_ingredient_without_inventing_mass(tmp_path):
    paths = fixture(tmp_path)
    before = paths[0].read_bytes()
    assert check(paths) == []
    assert paths[0].read_bytes() == before
    assert json.loads(before)['components'][0]['ingredients'][0]['weight_g'] is None


@pytest.mark.parametrize('case', ['missing_research', 'missing_allergen', 'missing_timing',
    'invalid_duration', 'dangling_pointer', 'duplicate', 'measured_proposal',
    'missing_excerpt', 'empty_attempts', 'stale_card', 'stale_input'])
def test_incomplete_or_stale_ledgers_fail(tmp_path, case):
    paths = fixture(tmp_path)
    ledger = paths[2]
    first = ledger['ingredients'][0]
    if case == 'missing_research':
        first.pop('research')
    elif case == 'missing_allergen':
        first.pop('allergens')
        ledger['batch_allergens'] = 'Unknown supplier'
    elif case == 'missing_timing':
        ledger['components'] = []
    elif case == 'invalid_duration':
        ledger['components'][0]['timing']['maximum'] = -1
    elif case == 'dangling_pointer':
        first['pointer'] = '/components/0/ingredients/99'
    elif case == 'duplicate':
        ledger['ingredients'].append(deepcopy(first))
    elif case == 'measured_proposal':
        first['research']['status'] = 'measured_proposal'
    elif case == 'missing_excerpt':
        first['input_excerpt'] = 'Not actually in the intake'
    elif case == 'empty_attempts':
        first['research'] = {'status': 'research_unresolved', 'attempts': [], 'reason': 'No useful result'}
    elif case == 'stale_card':
        paths[0].write_text(paths[0].read_text() + ' ')
    elif case == 'stale_input':
        (tmp_path / 'input.txt').write_text('Correction: 3 cloves')
    assert save(paths), case


def test_actual_unsuccessful_research_and_external_compound_unknown_allowed(tmp_path):
    paths = fixture(tmp_path)
    paths[2]['ingredients'][0]['research'] = {
        'status': 'research_unresolved', 'attempts': [
            {'query': 'garlic clove mass chart', 'source': 'https://example.org/chart', 'result': '404'}],
        'reason': 'No usable source returned; retain own unit and null mass'}
    paths[2]['ingredients'][0]['allergens'] = {
        'status': 'unknown_external', 'reason': 'Compound stock supplier label unavailable'}
    assert save(paths) == []


@pytest.mark.parametrize('value', [None, [], '', 3, {'schema_version': 1}])
def test_invalid_ledger_shapes_are_findings(tmp_path, value):
    paths = fixture(tmp_path)
    paths[1].write_text(json.dumps(value))
    assert check(paths)


def test_cli_exports_rd_and_returns_nonzero_for_missing_coverage(tmp_path):
    paths = fixture(tmp_path)
    paths[2]['ingredients'][0].pop('research')
    paths[1].write_text(json.dumps(paths[2]))
    outdir = tmp_path / 'exports'
    run = subprocess.run([sys.executable, str(ROOT / 'scripts/build_card.py'), str(paths[0]),
        '--workflow-ledger', str(paths[1]), '--outdir', str(outdir), '--skip-pdf', '--skip-xlsx'],
        text=True, capture_output=True, check=False)
    assert run.returncode == 1, run.stderr
    assert 'WORKFLOW' in run.stdout
    assert list(outdir.glob('*.md')) and list(outdir.glob('*.html'))
    exported = next(p for p in outdir.glob('*.json') if not p.name.endswith('.manifest.json'))
    assert json.loads(exported.read_text())['components'][0]['ingredients'][0]['weight_g'] is None


@pytest.mark.parametrize('amount', [None, False, 0, -1, float('nan'), float('inf'), 10 ** 400, '6'])
def test_invalid_proposal_amounts_are_findings(tmp_path, amount):
    paths = fixture(tmp_path)
    paths[2]['ingredients'][0]['research']['amount'] = amount
    assert save(paths)


@pytest.mark.parametrize('field,value', [('ingredients', None), ('ingredients', [None]),
    ('components', [None]), ('components', None)])
def test_invalid_coverage_collections(tmp_path, field, value):
    paths = fixture(tmp_path)
    paths[2][field] = value
    assert save(paths)


@pytest.mark.parametrize('pointer', ['/components/0/ingredients/-1/notes',
    '/components/0/ingredients/01/notes', '/components/0/ingredients/99/notes',
    '/components/0/ingredients/1/notes', '/components/0/ingredients/0/~2notes', None])
def test_invalid_or_cross_ingredient_retention_pointer(tmp_path, pointer):
    paths = fixture(tmp_path)
    paths[2]['ingredients'][0]['retained_pointer'] = pointer
    assert save(paths)


def test_reasoned_na_and_known_allergen_dispositions(tmp_path):
    paths = fixture(tmp_path)
    paths[2]['ingredients'][1]['research'] = {
        'status': 'not_applicable', 'reason': 'Chef supplied weighed quantity; no conversion required'}
    paths[2]['ingredients'][1]['allergens'] = {
        'status': 'known', 'intentional': ['sesame'], 'basis': 'Ingredient identity explicitly supplied'}
    paths[2]['components'][0]['timing'] = {
        'status': 'not_applicable', 'reason': 'Purchased ready-to-use component, no preparation step'}
    assert save(paths) == []
    paths[2]['ingredients'][1]['research']['reason'] = ''
    assert save(paths)


def test_malformed_or_missing_file_becomes_finding(tmp_path):
    paths = fixture(tmp_path)
    paths[1].write_text('{')
    assert check(paths)
    paths[1].unlink()
    assert check(paths)


def test_cli_records_bound_ledger_and_build_receipt(tmp_path):
    paths = fixture(tmp_path)
    outdir = tmp_path / 'exports'
    run = subprocess.run([sys.executable, str(ROOT / 'scripts/build_card.py'), str(paths[0]),
        '--workflow-ledger', str(paths[1]), '--outdir', str(outdir), '--skip-pdf', '--skip-xlsx'],
        text=True, capture_output=True, check=False)
    assert 'WORKFLOW' in run.stdout
    receipt_path = next(outdir.glob('*.workflow-receipt.json'))
    receipt = json.loads(receipt_path.read_text())
    assert receipt['ledger_sha256'] == hashlib.sha256(paths[1].read_bytes()).hexdigest()
    assert receipt['card_sha256'] == hashlib.sha256(paths[0].read_bytes()).hexdigest()
    manifest = next(outdir.glob('*.manifest.json'))
    assert receipt['manifest_sha256'] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert receipt['workflow_findings'] == []
    assert receipt['release_approval'] is False


@pytest.mark.parametrize('name', ['../outside.txt', 'absolute'])
def test_input_path_must_stay_within_ledger_directory(tmp_path, name):
    paths = fixture(tmp_path)
    outside = tmp_path.parent / 'outside.txt'
    outside.write_bytes((tmp_path / 'input.txt').read_bytes())
    paths[2]['input_file'] = str(tmp_path / 'input.txt') if name == 'absolute' else name
    assert save(paths)


def test_symlink_escape_and_boolean_schema_rejected(tmp_path):
    paths = fixture(tmp_path)
    (tmp_path.parent / 'outside.txt').write_bytes((tmp_path / 'input.txt').read_bytes())
    (tmp_path / 'escape.txt').symlink_to(tmp_path.parent / 'outside.txt')
    paths[2]['input_file'] = 'escape.txt'
    assert save(paths)
    paths[2]['input_file'] = 'input.txt'
    paths[2]['schema_version'] = True
    assert save(paths)


def test_ledger_changed_during_build_cannot_receive_clean_receipt(tmp_path, monkeypatch):
    import build_card
    paths = fixture(tmp_path)
    render = build_card.render_markdown

    def mutate_after_validation(*args, **kwargs):
        paths[1].write_text('{}')
        return render(*args, **kwargs)

    monkeypatch.setattr(build_card, 'render_markdown', mutate_after_validation)
    outdir = tmp_path / 'exports'
    assert build_card.main([str(paths[0]), '--workflow-ledger', str(paths[1]),
        '--outdir', str(outdir), '--skip-pdf', '--skip-xlsx']) == 1
    receipt = json.loads(next(outdir.glob('*.workflow-receipt.json')).read_text())
    assert any('changed during build' in item for item in receipt['workflow_findings'])


def test_intake_correction_during_build_rejects_clean_coverage(tmp_path, monkeypatch):
    import build_card
    paths = fixture(tmp_path)
    render = build_card.render_markdown

    def correct_intake(*args, **kwargs):
        (tmp_path / 'input.txt').write_text('Correction: garlic 3 cloves')
        return render(*args, **kwargs)

    monkeypatch.setattr(build_card, 'render_markdown', correct_intake)
    outdir = tmp_path / 'exports'
    build_card.main([str(paths[0]), '--workflow-ledger', str(paths[1]),
        '--outdir', str(outdir), '--skip-pdf', '--skip-xlsx'])
    receipt = json.loads(next(outdir.glob('*.workflow-receipt.json')).read_text())
    assert any('input_sha256' in item for item in receipt['workflow_findings'])


@pytest.mark.parametrize('rows', [{}, '', [None], ['garlic'], None])
def test_standalone_checker_rejects_malformed_ingredient_collection(tmp_path, rows):
    paths = fixture(tmp_path)
    card = json.loads(paths[0].read_text())
    card['components'][0]['ingredients'] = rows
    paths[0].write_text(json.dumps(card))
    paths[2]['card_sha256'] = hashlib.sha256(paths[0].read_bytes()).hexdigest()
    paths[2]['ingredients'] = []
    assert save(paths)


@pytest.mark.parametrize('component', [None, 'sauce', []])
def test_standalone_checker_rejects_malformed_component_objects(tmp_path, component):
    paths = fixture(tmp_path)
    card = json.loads(paths[0].read_text())
    card['components'] = [component]
    paths[0].write_text(json.dumps(card))
    paths[2]['card_sha256'] = hashlib.sha256(paths[0].read_bytes()).hexdigest()
    paths[2]['ingredients'] = []
    assert save(paths)


def test_cli_workflow_failure_is_independent_of_card_blockers(tmp_path):
    import build_card
    paths = fixture(tmp_path)
    card = json.loads(paths[0].read_text())
    card['components'][0]['ingredients'][0]['weight_g'] = 100
    card['components'][0]['ingredients'][0].pop('quantity')
    original = json.loads((ROOT / 'examples/sesame-salt-garnish.card.json').read_text())
    for row, source in zip(card['components'][0]['ingredients'], original['components'][0]['ingredients']):
        row['notes'] += '; ' + source['notes']
    paths[0].write_text(json.dumps(card))
    paths[2]['card_sha256'] = hashlib.sha256(paths[0].read_bytes()).hexdigest()
    paths[2]['ingredients'][0].pop('research')
    paths[1].write_text(json.dumps(paths[2]))
    base = [str(paths[0]), '--skip-pdf', '--skip-xlsx']
    assert build_card.main([*base, '--outdir', str(tmp_path / 'legacy')]) == 0
    outdir = tmp_path / 'checked'
    assert build_card.main([*base, '--outdir', str(outdir), '--workflow-ledger', str(paths[1])]) == 1
    assert list(outdir.glob('*.md')) and list(outdir.glob('*.html'))

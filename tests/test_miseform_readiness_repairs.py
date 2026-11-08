"""Recipe translation parity and unknown measured yield regressions."""
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from card_model import Card
from exporter import export_pdf, export_xlsx, extract_pdf_text
from render_html import render_html
from render_markdown import render_markdown
from test_miseform_linked_mass import _calculated, _row


def card():
    data = json.loads((ROOT / 'examples/sesame-salt-garnish.card.json').read_text())
    return Card({**data, 'usable_yield_g': None, 'loss_g': None, 'portions': None})


@pytest.mark.parametrize('nested', [False, True])
def test_recipe_facts_and_equipment_override_all_editions(tmp_path, nested):
    record = card()
    facts = {'yield_summary': 'RENDEMENTFR'}
    texts = {'equipment': 'MATERIELFR', **({'facts': facts} if nested else facts)}
    md = render_markdown(record, language='fr', texts=texts)
    html = render_html(record, language='fr', texts=texts)
    pdf = tmp_path / 'translated.pdf'; xlsx = tmp_path / 'translated.xlsx'
    assert export_pdf(record, pdf, language='fr', texts=texts).ok
    assert export_xlsx(record, xlsx, language='fr', texts=texts).ok
    import openpyxl
    wb = openpyxl.load_workbook(xlsx)
    workbook = '\n'.join(str(c.value) for sheet in wb for row in sheet for c in row)
    for edition in [md, html, extract_pdf_text(pdf), workbook]:
        normalized = ' '.join(edition.split())
        assert facts['yield_summary'] in normalized
        assert texts['equipment'] in normalized


def test_unknown_measured_yield_stays_unknown_after_recalculation(tmp_path):
    import openpyxl
    path = tmp_path / 'unknown-yield.xlsx'
    assert export_xlsx(card(), path).ok
    wb = openpyxl.load_workbook(path)
    recipe = wb['Recipe Card']; scaling = wb['Batch Scaling']
    reference = _row(scaling, 'Reference usable yield')
    yield_row = _row(recipe, 'Measured usable yield')
    computed = _calculated(path)
    assert not isinstance(computed[('BATCH SCALING', f'C{reference}')], (int, float))
    recipe.cell(yield_row, 3).value = 50
    wb.save(path)
    assert _calculated(path)[('BATCH SCALING', f'C{reference}')] == 50


def test_rejected_volume_source_with_reason_does_not_publish_conversion():
    data = deepcopy(card().data)
    ingredient = data['components'][0]['ingredients'][0]
    ingredient['volume'] = None
    ingredient['notes'] = 'USDA chopped 89 g/US cup or shredded 70 g/US cup; state unspecified. https://example.invalid/source accessed 2026-11-02.'
    ingredient['volume_source'] = {'status': 'unresolved', 'source_url': 'https://example.invalid/source',
        'unresolved_reason': 'Cut unspecified; neither chopped nor shredded conversion is established.'}
    record = Card(data)
    assert 'volume-source-record-without-volume' not in {f.code for f in record.findings()}
    assert record.ingredients[0]['volume'] is None
    assert record.scaled_volumes(2).get(ingredient['row_id']) is None
    ingredient['volume_source']['status'] = 'derived'
    assert 'volume-source-record-without-volume' in {f.code for f in Card(data).findings()}

"""Unknown ingredient mass must never become a complete input total."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from card_model import Card
from exporter import export_xlsx
from render_html import render_html
from render_markdown import render_markdown


def partial_card():
    data = json.loads((ROOT / 'examples/sesame-salt-garnish.card.json').read_text())
    ingredients = data['components'][0]['ingredients']
    ingredients[1]['weight_g'] = None
    ingredients[1]['quantity'] = {'amount': 1, 'unit': 'tbsp', 'convention': 'US'}
    ingredients[1]['quantity']['original'] = '1 tbsp'
    ingredients[1]['volume'] = None
    data['input_total_g'] = None
    data['usable_yield_g'] = None
    data['loss_g'] = None
    data['portion_g'] = None
    data['portions'] = None
    return Card(data)


def test_unknown_full_total_is_schema_valid_and_known_subtotal_explicit():
    card = partial_card()
    assert card.schema_errors() == []
    assert card.derived().known_input_subtotal_g == 110
    assert not card.derived().input_complete


@pytest.mark.parametrize('claimed_total', [110, 130, 999])
def test_numeric_total_with_unresolved_mass_is_blocked(claimed_total):
    data = deepcopy(partial_card().data)
    data['input_total_g'] = claimed_total
    assert 'input-total-incomplete' in {f.code for f in Card(data).findings()}


@pytest.mark.parametrize('renderer', [render_html, render_markdown])
def test_captions_distinguish_unknown_full_total_from_known_subtotal(renderer):
    text = renderer(partial_card())
    assert 'Input unknown' in text
    assert 'Known mass subtotal (partial) 110 g' in text
    assert 'Input 100 g' not in text
    assert '1 tbsp' in text


def test_unresolved_mass_remains_unknown_when_scaling():
    card = partial_card()
    unknown = card.components[0]['ingredients'][1]['row_id']
    assert unknown not in card.scaled_weights(2)
    assert card.components[0]['ingredients'][1]['quantity']['amount'] == 1
    assert card.components[0]['ingredients'][1]['weight_g'] is None


def test_native_xlsx_has_unknown_total_and_separate_live_subtotals(tmp_path):
    import openpyxl
    target = tmp_path / 'partial.xlsx'
    result = export_xlsx(partial_card(), target)
    assert result.ok, result.detail
    values = openpyxl.load_workbook(target, data_only=True)
    formulas = openpyxl.load_workbook(target)
    text = ' '.join(str(c.value) for ws in values for row in ws for c in row if c.value is not None)
    assert 'Input total unknown' in text
    assert 'Known mass subtotal (partial) 110 g' in text
    for sheet_name in ('Recipe Card', 'Batch Scaling'):
        sheet = values[sheet_name]
        rows = [row for row in sheet if row[1].value == 'Known mass subtotal (partial)']
        assert len(rows) == 1
        assert rows[0][2].value == 110
        assert formulas[sheet_name].cell(rows[0][2].row, 3).value.startswith('=SUM(')
    assert '1 tbsp' in text


def test_complete_card_numbers_unchanged():
    data = json.loads((ROOT / 'examples/sesame-salt-garnish.card.json').read_text())
    card = Card(data)
    assert card.schema_errors() == []
    assert card.derived().known_input_subtotal_g == 130
    assert card.derived().input_complete
    assert 'Input 130 g' in render_markdown(card)
    assert not any(f.code.startswith('input-total') for f in card.findings())


@pytest.mark.parametrize('ambiguity', ['duplicate', 'restated'])
def test_structurally_ambiguous_linked_input_never_caches_or_calculates_full_total(tmp_path, ambiguity):
    import openpyxl
    data = json.loads((ROOT / 'examples/sesame-salt-garnish.card.json').read_text())
    linked = {'name': 'Linked sauce', 'linked': {'component_id': 'SAUCE', 'version': 'v1', 'quantity_g': 250}}
    data['components'].append(linked)
    if ambiguity == 'duplicate':
        data['components'].append(deepcopy(linked))
    else:
        linked['ingredients'] = [{'row_id': 'restated', 'name': 'Invalid restatement', 'weight_g': 250}]
    data['input_total_g'] = None
    card = Card(data)
    assert not card.derived().input_complete
    assert card.derived().loss_g is None
    target = tmp_path / f'{ambiguity}.xlsx'
    assert export_xlsx(card, target).ok
    values = openpyxl.load_workbook(target, data_only=True)
    formulas = openpyxl.load_workbook(target)
    import formulas as formula_engine
    solution = formula_engine.ExcelModel().loads(str(target)).finish().calculate()
    calculated = {str(key): value.value[0, 0] for key, value in solution.items()}
    for sheet_name, label in [('Recipe Card', 'Total input'), ('Batch Scaling', 'Total input (g)')]:
        total = next(row for row in values[sheet_name] if row[1].value == label)
        assert not isinstance(total[2].value, (int, float))
        assert 'ambiguous' in total[2].value.lower()
        assert 'FALSE' in formulas[sheet_name].cell(total[2].row, 3).value
        recomputed = [value for key, value in calculated.items()
                      if sheet_name.upper() in key and key.endswith('!' + total[2].coordinate)]
        assert len(recomputed) == 1 and 'ambiguous' in str(recomputed[0]).lower()
        if sheet_name == 'Batch Scaling':
            assert not isinstance(total[4].value, (int, float))
            assert 'FALSE' in formulas[sheet_name].cell(total[4].row, 5).value
            scaled_total = [value for key, value in calculated.items()
                            if sheet_name.upper() in key and key.endswith('!' + total[4].coordinate)]
            assert len(scaled_total) == 1 and 'ambiguous' in str(scaled_total[0]).lower()
    loss_row = next(row for row in values['Recipe Card'] if row[3].value == 'Loss (g)')
    assert loss_row[4].value is None
    recomputed_loss = [value for key, value in calculated.items()
                       if 'RECIPE CARD' in key and key.endswith('!' + loss_row[4].coordinate)]
    assert recomputed_loss == ['']

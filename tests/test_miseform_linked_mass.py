"""Linked allocations enter input mass once without restating their formula."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from card_model import Card
from exporter import export_pdf, export_xlsx
from render_html import render_html
from render_markdown import render_markdown


def linked_card():
    data = json.loads((ROOT / 'examples/sesame-salt-garnish.card.json').read_text())
    return Card({**data, 'recipe_id': 'LINKED-TEST', 'title': 'Synthetic linked allocation',
        'components': [
            {'name': 'Direct', 'reference_row_id': 'base', 'reference_weight_g': 1,
             'ingredients': [{'row_id': 'base', 'name': 'Synthetic base', 'weight_g': 1}]},
            {'name': 'Linked garnish', 'linked': {'component_id': 'SHARED-TEST',
                'version': 'v1', 'quantity_g': 2}}],
        'percentage_basis': {'basis_label': 'Base 1 g = 100%', 'reference_row_id': 'base', 'reference_weight_g': 1},
        'input_total_g': 3, 'usable_yield_g': None, 'loss_g': None, 'portion_g': None, 'portions': None,
        'stages': [{'name': 'Synthetic', 'steps': [{'number': 1, 'text': 'Synthetic test only.', 'ingredient_refs': ['base']}]}]})


def test_direct_plus_linked_mass_enters_total_once():
    card = linked_card()
    assert not any(f.code == 'input-total-mismatch' for f in card.findings())
    assert card.derived().input_total_g == 3
    assert card.derived().input_complete


def test_all_linked_mass_needs_no_percentage_reference():
    data = linked_card().data
    card = Card({**data, 'components': data['components'][1:], 'input_total_g': 2,
                 'percentage_basis': {'basis_label': 'Unknown', 'reference_row_id': None, 'reference_weight_g': None}})
    assert card.derived().input_total_g == 2
    assert card.derived().input_complete
    assert not any(f.code == 'input-total-mismatch' for f in card.findings())


def test_ordinary_mass_without_reference_still_enters_total():
    data = linked_card().data
    component = {**data['components'][0], 'reference_row_id': None, 'reference_weight_g': None}
    card = Card({**data, 'components': [component, data['components'][1]]})
    assert card.derived().input_total_g == 3
    assert not card.derived().percentages


def test_unknown_linked_mass_is_partial_and_never_zero():
    data = deepcopy(linked_card().data)
    data['components'][1]['linked']['quantity_g'] = None
    data['input_total_g'] = None
    card = Card(data)
    assert card.derived().input_total_g == 1
    assert not card.derived().input_complete
    assert 'Partial' in render_markdown(card)
    assert 'Partial' in render_html(card)


def test_duplicate_and_restated_link_cannot_double_mass():
    data = deepcopy(linked_card().data)
    linked = data['components'][1]
    linked['ingredients'] = [{'row_id': 'restated', 'name': 'Bad restatement', 'weight_g': 40}]
    data['components'].append(deepcopy(linked))
    card = Card(data)
    assert {'linked-component-duplicated', 'linked-component-restated'} <= {f.code for f in card.findings()}
    assert card.derived().input_total_g == 3
    assert not card.derived().input_complete


def test_link_quantity_visible_in_reading_editions():
    card = linked_card()
    for text in [render_markdown(card), render_html(card)]:
        assert 'SHARED-TEST' in text and 'v1' in text and '2 g' in text


def _row(sheet, label):
    return next(cell.row for row in sheet for cell in row if isinstance(cell.value, str) and label in cell.value)


def _calculated(path):
    import formulas
    solution = formulas.ExcelModel().loads(str(path)).finish().calculate()
    out = {}
    for key, value in solution.items():
        name = str(key)
        if '!' not in name:
            continue
        sheet = name.split(']')[-1].split("'")[0].split('!')[0].upper()
        out[(sheet, name.rsplit('!', 1)[1])] = value.value[0, 0]
    return out


def test_native_link_mass_edit_scale_and_recalculate(tmp_path):
    import openpyxl
    path = tmp_path / 'linked.xlsx'
    assert export_xlsx(linked_card(), path).ok
    wb = openpyxl.load_workbook(path)
    values = openpyxl.load_workbook(path, data_only=True)
    sheet = wb['Recipe Card']; scaling = wb['Batch Scaling']
    link_row = _row(sheet, 'SHARED-TEST')
    total = _row(sheet, 'Total input')
    scale_link = _row(scaling, 'SHARED-TEST')
    scale_total = _row(scaling, 'Total input')
    assert sheet.cell(link_row, 3).value == 2
    assert values['Recipe Card'].cell(total, 3).value == 3
    sheet.cell(link_row, 3).value = 5
    scaling['C6'] = 3
    wb.save(path)
    calculated = _calculated(path)
    assert calculated[('RECIPE CARD', f'C{total}')] == 6
    assert calculated[('BATCH SCALING', f'C{scale_link}')] == 5
    assert calculated[('BATCH SCALING', f'E{scale_link}')] == 15
    assert calculated[('BATCH SCALING', f'E{scale_total}')] == 18


def test_unknown_link_remains_partial_in_native_workbook(tmp_path):
    import openpyxl
    data = deepcopy(linked_card().data)
    data['components'][1]['linked']['quantity_g'] = None
    data['input_total_g'] = None
    path = tmp_path / 'unknown.xlsx'
    assert export_xlsx(Card(data), path).ok
    values = openpyxl.load_workbook(path, data_only=True)
    sheet = values['Recipe Card']
    assert not isinstance(sheet.cell(_row(sheet, 'SHARED-TEST'), 3).value, (int, float))
    assert 'Partial' in str(sheet.cell(_row(sheet, 'Total input'), 3).value)


def test_pdf_carries_linked_quantity(tmp_path):
    import exporter
    from filing import _pdf_text
    path = tmp_path / 'linked.pdf'
    result = export_pdf(linked_card(), path)
    assert result.ok, result.detail
    text = _pdf_text(path)
    assert 'SHARED-TEST' in text and '2 g' in text


def test_unknown_link_can_be_weighed_then_scaled_in_workbook(tmp_path):
    import openpyxl
    data = deepcopy(linked_card().data)
    data['components'][1]['linked']['quantity_g'] = None
    data['input_total_g'] = None
    path = tmp_path / 'resolved.xlsx'
    assert export_xlsx(Card(data), path).ok
    wb = openpyxl.load_workbook(path)
    recipe = wb['Recipe Card']; scaling = wb['Batch Scaling']
    link = _row(recipe, 'SHARED-TEST')
    scale_link = _row(scaling, 'SHARED-TEST')
    total = _row(scaling, 'Total input')
    recipe.cell(link, 3).value = 5
    scaling['C6'] = 3
    wb.save(path)
    calculated = _calculated(path)
    assert calculated[('BATCH SCALING', f'E{scale_link}')] == 15
    assert calculated[('BATCH SCALING', f'E{total}')] == 18

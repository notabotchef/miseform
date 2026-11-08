"""Own-unit quantities and percentages must survive display formatting."""
import json
import sys
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from card_model import Card, format_quantity
from exporter import export_xlsx


def test_third_cup_does_not_become_three_tenths():
    displayed = format_quantity({'amount': 1 / 3, 'unit': 'cup'})
    assert displayed in {'1/3 cup', '0.3333333333333333 cup'}, displayed


def test_xlsx_sub_one_percent_format_retains_decimal(tmp_path):
    data = json.loads((ROOT / 'examples/sesame-salt-garnish.card.json').read_text())
    data['components'][0]['ingredients'][0]['weight_g'] = 100
    data['components'][0]['ingredients'][1]['weight_g'] = 0.8
    card = Card(data)
    path = tmp_path / 'precision.xlsx'
    assert export_xlsx(card, path).ok
    book = load_workbook(path, data_only=False)
    percentages = [cell for sheet in book for row in sheet for cell in row
                   if cell.data_type == 'f' and cell.number_format.endswith('%')]
    assert percentages
    assert all('.' in cell.number_format for cell in percentages), [cell.number_format for cell in percentages]


def precision_card():
    data = json.loads((ROOT / 'examples/sesame-salt-garnish.card.json').read_text())
    ingredients = [
        {'row_id': 'base', 'name': 'Synthetic base', 'weight_g': 100},
        {'row_id': 'salt', 'name': 'Synthetic salt', 'weight_g': 0.8},
        {'row_id': 'third', 'name': 'Synthetic third', 'weight_g': None,
         'quantity': {'amount': 1 / 3, 'unit': 'cup', 'convention': 'US', 'original': '1/3 cup'}},
        {'row_id': 'quarter', 'name': 'Synthetic quarter', 'weight_g': None,
         'quantity': {'amount': 1 / 4, 'unit': 'cup', 'convention': 'US', 'original': '1/4 cup'}}]
    return Card({**data, 'components': [{'name': 'Synthetic precision', 'reference_row_id': 'base',
        'reference_weight_g': 100, 'ingredients': ingredients}],
        'percentage_basis': {'basis_label': 'Base100g', 'reference_row_id': 'base', 'reference_weight_g': 100},
        'input_total_g': None, 'usable_yield_g': None, 'portion_g': None, 'portions': None, 'loss_g': None})


def test_all_reading_formats_and_xlsx_preserve_fractions_and_nulls(tmp_path):
    from copy import deepcopy

    from exporter import export_pdf, extract_pdf_text
    from render_html import render_html
    from render_markdown import render_markdown
    card = precision_card()
    before = deepcopy(card.data)
    pdf = tmp_path / 'precision.pdf'
    result = export_pdf(card, pdf)
    assert result.ok, result.detail
    for text in [render_markdown(card), render_html(card), extract_pdf_text(pdf)]:
        assert '1/3 cup' in text and '1/4 cup' in text
    path = tmp_path / 'precision.xlsx'
    assert export_xlsx(card, path).ok
    book = load_workbook(path, data_only=True)
    for sheet in book:
        values = [cell.value for row in sheet for cell in row]
        assert '1/3 cup (US)' in values and '1/4 cup (US)' in values
        assert 'None' not in values
    assert card.data == before


def test_own_decimal_precision_and_language_are_retained():
    from card_model import row_weight_label
    assert format_quantity({'amount': 0.123456789, 'unit': 'cup'}, 'fr') == '0,123456789 cup'
    assert row_weight_label({'weight_g': None, 'quantity': {'amount': 0.123456789, 'unit': 'cup'}}, language='fr') == '0,123456789 cup'
    assert format_quantity({'amount': 1 / 4, 'unit': 'cup'}) == '1/4 cup'


def test_native_calc_print_and_factor_two_recalculation(tmp_path):
    import shutil
    import subprocess

    from exporter import extract_pdf_text
    soffice = Path(shutil.which('soffice') or (Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice'))
    assert soffice.is_file(), 'Native Calc required for this release-critical regression'
    source = tmp_path / 'precision.xlsx'
    assert export_xlsx(precision_card(), source).ok
    run = subprocess.run([str(soffice), '-env:UserInstallation=' + (tmp_path / 'print-profile').as_uri(),
        '--headless', '--norestore', '--convert-to', 'pdf:calc_pdf_Export', '--outdir', str(tmp_path), str(source)],
        capture_output=True, text=True, timeout=90, check=False)
    assert run.returncode == 0, run.stderr
    text = extract_pdf_text(tmp_path / 'precision.pdf')
    assert text.count('1/3 cup') >= 2 and text.count('1/4 cup') >= 2, text
    assert text.count('0.8%') >= 2, text
    book = load_workbook(source)
    book['Batch Scaling']['C6'] = 2
    edit = tmp_path / 'edit'
    edit.mkdir()
    book.save(edit / source.name)
    recalc = tmp_path / 'recalc'
    recalc.mkdir()
    run = subprocess.run([str(soffice), '-env:UserInstallation=' + (tmp_path / 'recalc-profile').as_uri(),
        '--headless', '--norestore', '--convert-to', 'xlsx', '--outdir', str(recalc), str(edit / source.name)],
        capture_output=True, text=True, timeout=90, check=False)
    assert run.returncode == 0, run.stderr
    actual = load_workbook(recalc / source.name, data_only=True)
    sheet = actual['Batch Scaling']
    salt_row = next(c.row for row in sheet for c in row if c.value == 'Synthetic salt')
    assert sheet.cell(salt_row, 3).value == 0.8
    assert sheet.cell(salt_row, 4).value == 0.008
    assert sheet.cell(salt_row, 5).value == 1.6
    for name in ['Synthetic third', 'Synthetic quarter']:
        row = next(c.row for cells in sheet for c in cells if c.value == name)
        assert sheet.cell(row, 5).value == 'Pending'
    assert not any(c.value == 'None' for sh in actual for row in sh for c in row)


import pytest


@pytest.mark.parametrize('language', ['en', 'es', 'fr', 'it', 'pt'])
def test_tiny_percent_keeps_its_positive_value(language):
    from card_model import format_percent
    expected = '0.00001%' if language == 'en' else '0,00001%'
    assert format_percent(0.00001, language) == expected


def test_scaling_partial_total_reserves_wrapped_warning_height(tmp_path):
    path = tmp_path / 'partial.xlsx'
    assert export_xlsx(precision_card(), path).ok
    book = load_workbook(path)
    sheet = book['Batch Scaling']
    total_row = next(cell.row for row in sheet for cell in row
                     if cell.column == 2 and cell.value == 'Total input (g)')
    assert sheet.cell(total_row, 3).alignment.wrap_text
    assert sheet.cell(total_row, 5).alignment.wrap_text
    assert sheet.row_dimensions[total_row].height > 30


def test_native_scaling_print_keeps_both_complete_partial_warnings(tmp_path):
    import shutil
    import subprocess

    from locales import translate
    source = tmp_path / 'partial.xlsx'
    assert export_xlsx(precision_card(), source).ok
    soffice = Path(shutil.which('soffice') or (Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice'))
    run = subprocess.run([str(soffice), '-env:UserInstallation=' + (tmp_path / 'profile').as_uri(),
        '--headless', '--norestore', '--convert-to', 'pdf:calc_pdf_Export', '--outdir', str(tmp_path), str(source)],
        capture_output=True, text=True, timeout=90, check=False)
    assert run.returncode == 0, run.stderr
    # Reconstruct each printed column separately: line-oriented extraction
    # legitimately interleaves adjacent wrapped cells at the same baseline.
    from xml.etree import ElementTree as ET
    bbox = tmp_path / 'bbox.html'
    subprocess.run(['pdftotext', '-bbox-layout', str(tmp_path / 'partial.pdf'), str(bbox)], check=True)
    ns = {'p': 'http://www.w3.org/1999/xhtml'}
    pages = ET.parse(bbox).getroot().findall('.//p:page', ns)
    warning = translate('xlsx.partial_scaling').format(n=2, m=4)
    found = []
    for page in pages:
        words = page.findall('.//p:word', ns)
        starts = [word for word in words if word.text == 'Partial']
        if len(starts) != 2:
            continue
        bottom = min(float(w.attrib['yMin']) for w in words
                     if w.text == 'PROCESS' and float(w.attrib['yMin']) > float(starts[0].attrib['yMin']))
        for start in starts:
            x, y = float(start.attrib['xMin']), float(start.attrib['yMin'])
            selected = [w for w in words if x - 75 <= float(w.attrib['xMin'])
                        and float(w.attrib['xMax']) <= x + 70
                        and y <= float(w.attrib['yMin']) < bottom]
            selected.sort(key=lambda w: (float(w.attrib['yMin']), float(w.attrib['xMin'])))
            found.append(' '.join(w.text for w in selected))
    assert found == [warning, warning], found


@pytest.mark.parametrize('language', ['en', 'es', 'fr', 'it', 'pt'])
def test_tiny_percent_preserved_in_reading_editions(tmp_path, language):
    from copy import deepcopy

    from exporter import export_pdf, extract_pdf_text
    from render_html import render_html
    from render_markdown import render_markdown
    data = deepcopy(precision_card().data)
    data['components'][0]['ingredients'][1]['weight_g'] = 0.00001
    card = Card(data)
    expected = '0.00001%' if language == 'en' else '0,00001%'
    pdf = tmp_path / 'tiny.pdf'
    result = export_pdf(card, pdf, language=language)
    assert result.ok, result.detail
    for text in [render_markdown(card, language=language), render_html(card, language=language), extract_pdf_text(pdf)]:
        assert expected in text

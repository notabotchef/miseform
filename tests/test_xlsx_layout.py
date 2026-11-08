"""Native Calc catches clipping that workbook cell-value checks cannot see."""
import re
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from card_model import Card
from exporter import export_xlsx
from locales import translate
from test_miseform_linked_mass import linked_card

SOFFICE = Path(shutil.which('soffice') or (Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice'))


def partial_card():
    data = deepcopy(linked_card().data)
    data['components'][0]['ingredients'][0]['weight_g'] = None
    data['components'][1]['name'] = 'Sauce au yaourt et au citron'
    data['components'][1]['linked'] = {'component_id': 'TEMP-20261101-SAUCE', 'version': 'v0.1-draft.2', 'quantity_g': 18}
    data['components'].append({'name': 'Garniture sèche de graines commune', 'linked': {
        'component_id': 'TEMP-20261101-SEED', 'version': 'v0.1-draft.2', 'quantity_g': 2}})
    data['input_total_g'] = None
    return Card(data)


def compact(text):
    return re.sub(r'\s+', '', text)


@pytest.mark.skipif(not SOFFICE.is_file() or not shutil.which('pdftotext'), reason='native Calc/pdftotext unavailable')
@pytest.mark.parametrize('language', ['en', 'es', 'fr', 'it', 'pt'])
def test_native_recipe_page_preserves_partial_status_and_link_identity(tmp_path, language):
    source = tmp_path / 'layout.xlsx'
    assert export_xlsx(partial_card(), source, language=language, theme='atelier').ok
    command = [str(SOFFICE), '-env:UserInstallation=' + (tmp_path/'profile').as_uri(),
        '--headless', '--norestore', '--convert-to', 'pdf:calc_pdf_Export', '--outdir', str(tmp_path), str(source)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    assert result.returncode == 0, result.stderr
    pdf = tmp_path / 'layout.pdf'
    assert pdf.is_file(), result.stdout
    # Page one is Recipe Card. Never satisfy this check with the repeated
    # Batch Scaling text from later pages.
    page = subprocess.run(['pdftotext', '-raw', '-f', '1', '-l', '1', str(pdf), '-'],
        capture_output=True, text=True, check=True).stdout
    text = compact(page)
    expected = translate('xlsx.partial_input', language).format(n=2, m=3)
    assert compact(expected) in text
    assert 'TEMP-20261101-SAUCEv0.1-draft.2' in text
    assert 'TEMP-20261101-SEEDv0.1-draft.2' in text


def test_known_complete_total_keeps_numeric_formula_and_cache(tmp_path):
    import openpyxl
    source = tmp_path/'complete.xlsx'
    assert export_xlsx(linked_card(), source).ok
    formula = openpyxl.load_workbook(source)
    cached = openpyxl.load_workbook(source, data_only=True)
    total = next(c for row in formula['Recipe Card'] for c in row if c.value == 'Total input')
    assert formula['Recipe Card'].cell(total.row, 3).value.startswith('=IF(')
    assert cached['Recipe Card'].cell(total.row, 3).value == 3

"""Process-control N/A reasons accept ordinary editorial dash variants."""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from card_model import Card, applicable_process_controls, na_reason


@pytest.mark.parametrize('dash', ['-', '–', '—'])
def test_na_reason_accepts_dash_variants_and_card_does_not_false_block(dash):
    text = f'N/A {dash} no heat step'
    assert na_reason(text) == 'no heat step'
    data = json.loads((ROOT / 'examples/sesame-salt-garnish.card.json').read_text())
    data['process_controls']['sous_vide'] = text
    assert 'process-control-reason-missing' not in {f.code for f in Card(data).findings()}
    assert not any(label == 'Sous vide' for label, _ in applicable_process_controls(data['process_controls']))


@pytest.mark.parametrize('text', [None, '', 'N/A', 'N/A -', 'N/A —  ',
                                   'N/A – ---', 'N/A nonsense - no heat',
                                   'N/Aside - no heat', 'not an N/A - no heat'])
def test_na_reason_rejects_missing_or_malformed_reason(text):
    assert na_reason(text) == ''


@pytest.mark.parametrize('prefix', ['N/A', 'n/a', 'Not applicable'])
def test_reason_keeps_hyphens_inside_text(prefix):
    assert na_reason(f'{prefix} — ready-to-use product') == 'ready-to-use product'

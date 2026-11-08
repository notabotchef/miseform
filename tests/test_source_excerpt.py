"""Source excerpts retain intake evidence without entering kitchen row notes."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from card_model import Card
from render_html import render_html
from render_markdown import render_markdown
from test_workflow_completeness import fixture
from workflow_completeness import validate_ledger


@pytest.mark.parametrize('excerpt', [None, 'Original supplied text: CABBAGE 2 heads; preserve exact source spelling.'])
def test_optional_source_excerpt_schema_accepts_and_preserves_original(excerpt):
    data = json.loads((ROOT / 'examples/sesame-salt-garnish.card.json').read_text())
    data['components'][0]['ingredients'][0]['source_excerpt'] = excerpt
    card = Card(data)
    assert card.schema_errors() == []
    assert card.components[0]['ingredients'][0]['source_excerpt'] == excerpt
    assert json.loads(json.dumps(card.data))['components'][0]['ingredients'][0]['source_excerpt'] == excerpt


def test_ledger_binds_original_excerpt_without_printing_it_as_kitchen_note(tmp_path):
    path, ledger_path, ledger = fixture(tmp_path)
    data = json.loads(path.read_text())
    for row, entry in zip(data['components'][0]['ingredients'], ledger['ingredients']):
        row['source_excerpt'] = entry['input_excerpt']
        row['notes'] = 'Kitchen note: weigh before mixing.'
        entry['retained_pointer'] = entry['pointer'] + '/source_excerpt'
    path.write_text(json.dumps(data))
    ledger['card_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    ledger_path.write_text(json.dumps(ledger))
    before = path.read_bytes()
    assert Card(data).schema_errors() == []
    assert validate_ledger(ledger_path, path) == []
    assert path.read_bytes() == before
    for renderer in (render_html, render_markdown):
        text = renderer(Card(data))
        assert 'Kitchen note: weigh before mixing.' in text
        assert 'Garlic 2 cloves' not in text
        assert 'sesame 20 g' not in text
        assert 'salt 10 g' not in text

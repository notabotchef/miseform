"""Bound semantic rendering overlays never replace canonical culinary facts."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from card_model import Card
from translation import (
    normalize_translation,
    recipe_field,
    source_digest,
    translation_coverage,
    translation_inventory,
)


def rich_card():
    data = json.loads((ROOT / 'examples/sesame-salt-garnish.card.json').read_text())
    data['components'].append({'name': 'Other component', 'ingredients': [{'row_id': 'RICH', 'name': 'Other ingredient', 'weight_g': 1, 'notes': 'Ingredient note'}]})
    data['process_controls']['chilling'] = 'Keep below 4 °C; unresolved approval.'
    data['stages'][0]['tip'] = 'A useful tip'
    data['stages'][0]['steps'][0]['settings'] = {'heat_level': 'Gentle heat'}
    data['labeling']['storage_instruction'] = 'Keep below 4 °C.'
    data['provenance']['evidence'] = 'Synthetic evidence https://example.invalid/source'
    return Card(data)


def strict(card, fields=None):
    return {'schema_version': 1, 'language': 'fr', 'source_record_digest': source_digest(card),
        'fields': fields or {p: value for p, value in translation_inventory(card).items()}}


def test_strict_inventory_complete_and_canonical_unchanged():
    card = rich_card(); before = copy.deepcopy(card.data)
    overlay = normalize_translation(card, strict(card), 'fr')
    assert translation_coverage(card, overlay)['complete']
    assert recipe_field(overlay, 'stages.0.tip', '') == 'A useful tip'
    assert card.data == before


@pytest.mark.parametrize('change', ['stale', 'language', 'numeric', 'unknown', 'url'])
def test_bad_strict_overlay_rejected(change):
    card = rich_card(); bundle = strict(card)
    if change == 'stale': bundle['source_record_digest'] = 'bad'
    if change == 'language': bundle['language'] = 'es'
    if change == 'numeric': bundle['fields']['process_controls.chilling'] = 'Keep below 40 °C; unresolved approval.'
    if change == 'unknown': bundle['fields']['usable_yield_g'] = '100'
    if change == 'url': bundle['fields']['provenance.evidence'] = 'Synthetic evidence'
    with pytest.raises(ValueError): normalize_translation(card, bundle, 'fr')


def test_partial_legacy_is_honest_and_scope_is_unambiguous():
    card = rich_card()
    overlay = normalize_translation(card, {'title': 'Titre traduit'}, 'fr')
    coverage = translation_coverage(card, overlay)
    assert not coverage['complete']
    assert 'process_controls.chilling' in coverage['missing_paths']
    assert coverage['covered_paths'] == ['title']


def test_ancillary_prose_all_reading_editions(tmp_path):
    import openpyxl
    from exporter import export_pdf, export_xlsx, extract_pdf_text
    from render_html import render_html
    from render_markdown import render_markdown
    card = rich_card(); before = copy.deepcopy(card.data)
    bundle = strict(card)
    paths = ['components.0.name', 'components.1.name', 'components.1.ingredients.RICH.notes',
        'stages.0.tip', 'stages.0.steps.1.settings.heat_level', 'notes.0.heading', 'notes.0.text',
        'release_blockers.0', 'release_checklist.0']
    sentinels = []
    for n, path in enumerate(paths):
        if path not in bundle['fields']: continue
        source = bundle['fields'][path]
        sentinel = f'FRSENTINEL{chr(65+n)}'
        bundle['fields'][path] = sentinel + ' ' + source
        sentinels.append(sentinel)
    for path in ['process_controls.chilling', 'labeling.storage_instruction', 'provenance.evidence']:
        sentinel = 'FRCONTROL' if path.startswith('process') else 'FRLABEL' if path.startswith('labeling') else 'FREVIDENCE'
        bundle['fields'][path] = sentinel + ' ' + bundle['fields'][path]
        sentinels.append(sentinel)
    overlay = normalize_translation(card, bundle, 'fr')
    md = render_markdown(card, language='fr', texts=overlay)
    html = render_html(card, language='fr', texts=overlay)
    pdf = tmp_path/'rich.pdf'; xlsx = tmp_path/'rich.xlsx'
    assert export_pdf(card, pdf, language='fr', texts=overlay).ok
    assert export_xlsx(card, xlsx, language='fr', texts=overlay).ok
    wb = openpyxl.load_workbook(xlsx)
    xtext = '\n'.join(str(c.value) for sheet in wb for row in sheet for c in row)
    for edition in [md, html, extract_pdf_text(pdf), xtext]:
        for sentinel in sentinels: assert sentinel in ''.join(edition.split())
    assert card.data == before
    bundle['fields']['process_controls.chilling'] = 'N/A 4 °C'
    assert 'N/A 4 °C' in render_html(card, language='fr', texts=normalize_translation(card, bundle, 'fr'))


def test_canonical_english_complete_and_bad_legacy_shape_rejected():
    card = rich_card()
    assert translation_coverage(card, None)['complete']
    with pytest.raises(ValueError): normalize_translation(card, {'facts': []}, 'fr')


def test_strict_build_embeds_and_binds_coverage(tmp_path):
    from build_card import main
    from build_manifest import verify_manifest
    from card_model import load_card
    card = rich_card()
    source = tmp_path / 'rich.json'
    source.write_text(json.dumps(card.data))
    sidecar = tmp_path / 'rich.lang-fr.json'
    sidecar.write_text(json.dumps(strict(card)))
    out = tmp_path / 'out'
    main([str(source), '--lang', 'fr', '--outdir', str(out), '--skip-pdf', '--skip-xlsx'])
    built = load_card(out / (card.filename_stem + '.json'))
    assert built.data['components'] == card.data['components']
    assert built.data['render_translation'] == strict(card)
    paths = {kind: out / (card.filename_stem + ext) for kind, ext in [('json','.json'),('markdown','.md'),('html','.html')]}
    manifest, errors = verify_manifest(built, out, paths)
    assert not errors
    assert manifest['translation_coverage']['complete']
    mp = out / (card.filename_stem + '.manifest.json')
    value = json.loads(mp.read_text()); value['translation_coverage']['missing_paths'] = ['title']
    mp.write_text(json.dumps(value))
    assert verify_manifest(built, out, paths)[1]
    # A stale strict bundle fails before any edition is written.
    bad = strict(card); bad['source_record_digest'] = 'stale'; sidecar.write_text(json.dumps(bad))
    rejected = tmp_path / 'rejected'
    assert main([str(source), '--lang', 'fr', '--outdir', str(rejected), '--skip-pdf', '--skip-xlsx']) == 2
    assert not list(rejected.glob('*.md'))


def test_alias_conflict_and_duplicate_scoped_row_rejected():
    card = rich_card()
    with pytest.raises(ValueError, match='conflicting'):
        normalize_translation(card, {'yield_summary': 'one', 'facts': {'yield_summary': 'two'}}, 'fr')
    card.data['components'][0]['ingredients'].append(copy.deepcopy(card.data['components'][0]['ingredients'][0]))
    with pytest.raises(ValueError, match='unique row'):
        translation_inventory(card)


def test_verbatim_and_missing_paths_are_explicit():
    card = rich_card(); overlay = strict(card)
    source = overlay['fields'].pop('title')
    overlay['verbatim'] = {'title': 'Reviewed proper name retained verbatim.'}
    checked = normalize_translation(card, overlay, 'fr')
    assert translation_coverage(card, checked)['complete']
    assert recipe_field(checked, 'title', source) == source
    del overlay['fields']['process_controls.chilling']
    assert 'process_controls.chilling' in translation_coverage(card, normalize_translation(card, overlay, 'fr'))['missing_paths']


def test_strict_decimal_localization_and_unicode_words_are_not_unit_edits():
    card = rich_card()
    card.data['title'] = 'Vegetables 2.5 kg'
    bundle = strict(card)
    bundle['fields']['title'] = 'LÉGUMES 2,5 kg'
    assert normalize_translation(card, bundle, 'fr')


@pytest.mark.parametrize('source,target', [('Chill for 4 hours.', 'Chill for 4 minutes.'), ('Add 2 tbsp oil.', 'Add 2 cups oil.')])
def test_changed_quantity_units_rejected(source, target):
    card = rich_card(); card.data['process_controls']['chilling'] = source
    overlay = strict(card); overlay['fields']['process_controls.chilling'] = target
    with pytest.raises(ValueError, match='protected tokens'):
        normalize_translation(card, overlay, 'fr')


@pytest.mark.parametrize('source,target', [('Chill for 4 hours.', 'Refroidir pendant 4 heures.'), ('Add 2 tbsp oil.', 'Ajouter 2 c. à soupe huile.'), ('Add 2 g salt.', 'Ajouter 2 grammes de sel.')])
def test_translated_equivalent_quantity_units_accepted(source, target):
    card = rich_card(); card.data['process_controls']['chilling'] = source
    overlay = strict(card); overlay['fields']['process_controls.chilling'] = target
    assert normalize_translation(card, overlay, 'fr')


def test_quantity_unit_association_cannot_be_swapped():
    card = rich_card(); card.data['process_controls']['chilling'] = 'Keep at 4 °C for 60 minutes.'
    bundle = strict(card)
    bundle['fields']['process_controls.chilling'] = 'Garder à 60 °C pendant 4 minutes.'
    with pytest.raises(ValueError, match='protected tokens'):
        normalize_translation(card, bundle, 'fr')
    bundle['fields']['process_controls.chilling'] = 'Garder à 4 °C pendant 60 minutes.'
    assert normalize_translation(card, bundle, 'fr')

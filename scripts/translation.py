"""Source-bound prose overlays; canonical validation always uses the original Card.

Token preservation catches obvious corruption, not mistranslation or approval.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from typing import Any

RENDER_FIELDS = {'language', 'theme', 'render_translation', 'render_translation_language'}
SCALARS = ('title', 'intro', 'library_name', 'equipment', 'allergens', 'tested_batch_range')
LABEL_PROSE = ('product_name', 'use_by_basis', 'storage_instruction', 'allergen_declaration')
FACTS = ('time_total', 'time_active', 'time_inactive', 'difficulty_level', 'difficulty_technique',
         'yield_summary', 'yield_portions', 'storage_summary', 'storage_reference')


def source_digest(card) -> str:
    data = card.data if hasattr(card, 'data') else card
    source = {k: v for k, v in data.items() if k not in RENDER_FIELDS}
    return hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def translation_inventory(card) -> dict[str, str]:
    """Enumerate only display prose; identity/status/approvers/source objects excluded."""
    data = card.data if hasattr(card, 'data') else card
    out = {}
    def add(path, value):
        if isinstance(value, str) and value.strip(): out[path] = value
    for key in SCALARS: add(key, data.get(key))
    add('percentage_basis.basis_label', (data.get('percentage_basis') or {}).get('basis_label'))
    for key in FACTS: add(f'facts.{key}', (data.get('facts') or {}).get(key))
    for family, keys in [('process_controls', None), ('labeling', LABEL_PROSE),
                         ('provenance', ('evidence', 'validation', 'filing'))]:
        values = data.get(family) or {}
        for key in keys or values: add(f'{family}.{key}', values.get(key))
    for family in ('release_blockers', 'release_checklist'):
        for index, value in enumerate(data.get(family) or []): add(f'{family}.{index}', value)
    for index, note in enumerate(data.get('notes') or []):
        for key in ('heading', 'text'): add(f'notes.{index}.{key}', note.get(key))
    for index, component in enumerate(data.get('components') or []):
        add(f'components.{index}.name', component.get('name'))
        seen = set()
        for ingredient in component.get('ingredients') or []:
            rid = str(ingredient.get('row_id', ''))
            if not rid or rid in seen: raise ValueError('translation requires unique row IDs within each component')
            seen.add(rid)
            for key in ('name', 'notes'): add(f'components.{index}.ingredients.{rid}.{key}', ingredient.get(key))
    for index, stage in enumerate(data.get('stages') or []):
        for key in ('name', 'tip'): add(f'stages.{index}.{key}', stage.get(key))
        seen = set()
        for step in stage.get('steps') or []:
            number = str(step.get('number', ''))
            if not number or number in seen: raise ValueError('translation requires unique step numbers within each stage')
            seen.add(number)
            root = f'stages.{index}.steps.{number}'
            add(root + '.text', step.get('text'))
            for key, value in (step.get('settings') or {}).items(): add(root + '.settings.' + key, value)
    return dict(sorted(out.items()))


# Exact unit equivalence only; changing hours to minutes changes the control.
# Long aliases precede short abbreviations; Unicode boundaries avoid matching
# the L in LÉGUMES or the s in ordinary words.
_UNIT_GROUPS = {
    'celsius': ('°C',), 'fahrenheit': ('°F',), 'percent': ('%',),
    'hour': ('hours', 'hour', 'heures', 'heure', 'horas', 'hora', 'ore', 'ora', 'hrs', 'hr', 'h'),
    'minute': ('minutes', 'minute', 'minutos', 'minuto', 'minuti', 'mins', 'min'),
    'second': ('seconds', 'second', 'secondes', 'seconde', 'segundos', 'segundo', 'secondi', 'secondo', 'secs', 'sec', 's'),
    'day': ('days', 'day', 'jours', 'jour', 'días', 'día', 'dias', 'dia', 'giorni', 'giorno'),
    'week': ('weeks', 'week', 'semaines', 'semaine', 'semanas', 'semana', 'settimane', 'settimana'),
    'tsp': ('teaspoons', 'teaspoon', 'tsp', 'c. à café', 'cuillères à café', 'cucharaditas', 'cucharadita', 'cucchiaini', 'cucchiaino', 'colheres de chá', 'colher de chá'),
    'tbsp': ('tablespoons', 'tablespoon', 'tbsp', 'c. à soupe', 'cuillères à soupe', 'cucharadas', 'cucharada', 'cucchiai', 'cucchiaio', 'colheres de sopa', 'colher de sopa'),
    'cup': ('US cups', 'US cup', 'cups', 'cup', 'tasses', 'tasse', 'tazas', 'taza', 'tazze', 'tazza', 'xícaras', 'xícara'),
    'kg': ('kilograms', 'kilogram', 'kilogrammes', 'kilogramme', 'kilogramos', 'kilogramo', 'chilogrammi', 'chilogrammo', 'quilogramas', 'quilograma', 'kg'),
    'g': ('grams', 'gram', 'grammes', 'gramme', 'gramos', 'gramo', 'grammi', 'grammo', 'gramas', 'grama', 'g'),
    'mg': ('milligrams', 'milligram', 'milligrammes', 'milligramme', 'miligramos', 'miligrama', 'mg'),
    'ml': ('millilitres', 'millilitre', 'milliliters', 'milliliter', 'mililitros', 'millilitri', 'ml'),
    'l': ('litres', 'litre', 'liters', 'liter', 'litros', 'litro', 'litri', 'l'),
}
_UNIT_ALIASES = {alias.casefold(): unit for unit, aliases in _UNIT_GROUPS.items() for alias in aliases}
_UNIT_PATTERN = re.compile(r'(?<![\w])([-+]?\d+(?:[.,]\d+)?)\s*(' +
    '|'.join(re.escape(alias) for alias in sorted(_UNIT_ALIASES, key=len, reverse=True)) + r')(?![\w])', re.IGNORECASE)


def _protected(text: str) -> Counter:
    urls = re.findall(r'https?://[^\s<>]+', text)
    cleaned = text
    tokens = []
    for url in urls:
        url = url.rstrip('.,;)')
        tokens.append('url:' + url)
        cleaned = cleaned.replace(url, '')
    tokens += ['quote:' + quote for quote in re.findall(r'"([^"\n]+)"', cleaned)]
    # Decimal punctuation may localize; amounts, IDs and physical units may not.
    tokens += ['number:' + token.replace(',', '.') for token in re.findall(r'(?<![\w])[-+]?\d+(?:[.,]\d+)?', cleaned)]
    tokens += ['id:' + token for token in re.findall(r'\b[A-Z]+[-_]?[0-9]+\b', cleaned)]
    tokens += ['unit:' + token for token in re.findall(r'(?<![\w])(?:°[CF]|%)(?![\w])', cleaned)]
    tokens += ['measure:' + number.replace(',', '.') + ':' + _UNIT_ALIASES[unit.casefold()]
               for number, unit in _UNIT_PATTERN.findall(cleaned)]
    return Counter(tokens)


def _legacy_fields(card, texts, inventory):
    """Normalize existing aliases; reject conflicting or ambiguous scope."""
    data = card.data if hasattr(card, 'data') else card
    for family in ('facts', 'process_controls', 'labeling', 'provenance'):
        if family in texts and not isinstance(texts[family], dict):
            raise ValueError(f'legacy translation {family} must be an object')
    for family in ('notes', 'components', 'stages', 'release_blockers', 'release_checklist'):
        if family in texts and not isinstance(texts[family], list):
            raise ValueError(f'legacy translation {family} must be an array')
    out = {}
    def add(path, value):
        if not isinstance(value, str) or not value.strip(): return
        if path in out and out[path] != value: raise ValueError(f'conflicting translation aliases: {path}')
        if path in inventory: out[path] = value
    for key, value in texts.items():
        if key in inventory: add(key, value)
        elif key in FACTS: add('facts.' + key, value)
        elif key == 'percentage_basis': add('percentage_basis.basis_label', value)
        elif key.startswith('stage.'): add('stages.' + key[6:], value)
        elif key.startswith('component.') or key == 'component':
            name = key[len('component.'):] if key != 'component' else None
            matches = [i for i, comp in enumerate(data.get('components') or []) if name is None or comp.get('name') == name]
            if len(matches) != 1: raise ValueError(f'ambiguous component translation: {key}')
            add(f'components.{matches[0]}.name', value)
    for key, value in (texts.get('facts') or {}).items(): add('facts.' + key, value)
    for family in ('process_controls', 'labeling', 'provenance'):
        for key, value in (texts.get(family) or {}).items(): add(f'{family}.{key}', value)
    for family in ('release_blockers', 'release_checklist'):
        for i, value in enumerate(texts.get(family) or []): add(f'{family}.{i}', value)
    for i, note in enumerate(texts.get('notes') or []):
        for key in ('heading', 'text'): add(f'notes.{i}.{key}', note.get(key))
    for i, comp in enumerate(texts.get('components') or []):
        add(f'components.{i}.name', comp.get('name'))
        for ing in comp.get('ingredients') or []:
            for key in ('name', 'notes'): add(f'components.{i}.ingredients.{ing.get("row_id")}.{key}', ing.get(key))
    for i, stage in enumerate(texts.get('stages') or []):
        for key in ('name', 'tip'): add(f'stages.{i}.{key}', stage.get(key))
        for step in stage.get('steps') or []:
            root = f'stages.{i}.steps.{step.get("number")}'
            add(root + '.text', step.get('text'))
            for key, value in (step.get('settings') or {}).items(): add(root + '.settings.' + key, value)
    return out


def normalize_translation(card, texts, language: str):
    if texts is None: return None
    # Invalid translation types use ValueError consumed at the build boundary.
    if not isinstance(texts, dict): raise ValueError('translation must be an object')  # noqa: TRY004
    inventory = translation_inventory(card)
    if 'schema_version' not in texts:
        # Preserve legacy shape for portable rebuilds and old binding tests.
        try:
            _legacy_fields(card, texts, inventory)
        except (AttributeError, TypeError) as exc:
            raise ValueError('malformed legacy translation structure') from exc
        return copy.deepcopy(texts)
    if set(texts) - {'schema_version', 'language', 'source_record_digest', 'fields', 'verbatim'}:
        raise ValueError('unknown translation contract metadata')
    if type(texts.get('schema_version')) is not int or texts.get('schema_version') != 1 or texts.get('language') != language:
        raise ValueError('translation schema or language mismatch')
    if texts.get('source_record_digest') != source_digest(card): raise ValueError('stale translation source digest')
    fields = texts.get('fields'); verbatim = texts.get('verbatim', {})
    # Keep invalid translation types inside the same build-boundary contract.
    if not isinstance(fields, dict) or not isinstance(verbatim, dict): raise ValueError('translation fields/verbatim must be objects')  # noqa: TRY004
    for path, value in fields.items():
        if path not in inventory: raise ValueError(f'unknown or protected translation path: {path}')
        if not isinstance(value, str) or not value.strip(): raise ValueError(f'blank/non-string translation: {path}')
        if _protected(inventory[path]) != _protected(value): raise ValueError(f'protected tokens changed: {path}')
    for path, reason in verbatim.items():
        if path not in inventory or path in fields or not isinstance(reason, str) or not reason.strip():
            raise ValueError(f'invalid verbatim declaration: {path}')
    return copy.deepcopy(texts)


def translation_coverage(card, texts) -> dict[str, Any]:
    inventory = translation_inventory(card)
    strict = isinstance(texts, dict) and 'schema_version' in texts
    fields = texts.get('fields', {}) if strict else _legacy_fields(card, texts or {}, inventory)
    verbatim = texts.get('verbatim', {}) if strict else {}
    canonical_english = texts is None and (card.data if hasattr(card, 'data') else card).get('language', 'en') == 'en'
    missing = [] if canonical_english else sorted(set(inventory) - set(fields) - set(verbatim))
    return {'source_record_digest': source_digest(card), 'required_paths': sorted(inventory),
        'covered_paths': sorted(fields), 'verbatim_paths': sorted(verbatim), 'missing_paths': missing,
        'complete': canonical_english or (strict and not missing), 'canonical_english': canonical_english, 'semantic_review': 'not-certified'}


def recipe_field(texts, path: str, default):
    if not texts: return default
    if 'schema_version' in texts:
        value = texts.get('fields', {}).get(path)
    else:
        value = texts.get(path)
        if value is None:
            current = texts
            for part in path.split('.'):
                if isinstance(current, dict): current = current.get(part)
                elif isinstance(current, list) and part.isdigit() and int(part) < len(current): current = current[int(part)]
                else: current = None; break
            value = current
    return value if isinstance(value, str) and value.strip() else default


def display_translation(card, texts):
    """Normalize legacy aliases once for readers without altering canonical Card."""
    if texts is None or 'schema_version' in texts: return texts
    return {'fields': _legacy_fields(card, texts, translation_inventory(card)), 'schema_version': 1}


def display_controls(card, texts, language):
    from card_model import PROCESS_CONTROL_LABELS, applicable_process_controls
    from locales import translate
    reverse = {label: key for key, label in PROCESS_CONTROL_LABELS.items()}
    return [(translate('control.' + reverse[label], language),
             recipe_field(texts, 'process_controls.' + reverse[label], value))
            for label, value in applicable_process_controls(card.process_controls)]


def display_release(card, texts, checklist=False):
    family = 'release_checklist' if checklist and card.data.get('release_checklist') else 'release_blockers'
    values = card.data.get(family) or []
    return [recipe_field(texts, f'{family}.{i}', value) for i, value in enumerate(values)]


def display_settings(texts, stage_index, step):
    root = f'stages.{stage_index}.steps.{step.get("number")}.settings'
    return [(key.replace('_', ' '), recipe_field(texts, root + '.' + key, value))
            for key, value in (step.get('settings') or {}).items() if str(value).strip()]

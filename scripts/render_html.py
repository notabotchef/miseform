'''Render a recipe card to the Miseform editorial HTML edition.

The stylesheet is not duplicated here. It is extracted from the skill's own
``templates/recipe-card.html`` so the rendered card and the hand-editable
template can never drift apart.

All card text is HTML-escaped. A recipe note is data, never markup.

Rendered text is localized per the resolved language (``locales``): UI
labels, headings, status lines and the decimal mark of rendered numbers.
The canonical card record stays locale-neutral: numbers keep the dot decimal
in JSON, and only the rendering switches to the language's convention
(comma for es/fr/it/pt). Proper product names and source text are never
translated.
'''

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from card_model import (
    LABELING_KEYS,
    PROCESS_CONTROL_KEYS,
    RELEASE_WARNING,
    Card,
    applicable_process_controls,
    format_percent,
    format_weight,
    input_mass_label,
    join_blockers,
    row_weight_label,
)
from translation import display_controls, display_release, display_settings, display_translation, recipe_field
from locales import (  # noqa: E402
    DEFAULT_LANGUAGE,
    component_name,
    ingredient_name,
    localize_decimals,
    note_text,
    recipe_text,
    step_text,
    translate,
)
from themes import DEFAULT_THEME as _DEFAULT_THEME, THEMES as _THEMES

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "recipe-card.html"
THEMES_PATH = TEMPLATE_PATH.parent / "themes"

_STYLE_RE = re.compile(r"<style>(.*?)</style>", re.DOTALL)

# Markup that must never appear as executable content in source material.
_SUSPICIOUS_RE = re.compile(
    r"<\s*(script|iframe|object|embed|style|link|meta)\b|javascript:|on[a-z]+\s*=",
    re.IGNORECASE,
)

# Recipe-text fields a translation bundle may override. Keys are stable
# identifiers; values are the translated strings for one language.
_RECIPE_TEXT_KEYS = (
    "title",
    "intro",
    "allergens",
)


def card_css(template_path: Path | None = None) -> str:
    """Return the stylesheet used by the skill's HTML template."""
    path = template_path or TEMPLATE_PATH
    try:
        markup = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cannot read HTML template at {path}: {exc}") from exc
    match = _STYLE_RE.search(markup)
    if not match:
        raise RuntimeError(f"no <style> block found in {path}")
    return match.group(1).strip()


def theme_css(theme_id: str) -> str:
    """Return the override stylesheet for one theme.

    ``original`` ships with the base stylesheet only, so its override is
    empty. Every other theme lives in ``templates/themes/<id>.css`` and is
    scoped under ``[data-theme="<id>"]`` so it can never leak into another
    theme's rendering.
    """
    if theme_id == _DEFAULT_THEME:
        return ""
    if theme_id not in _THEMES:
        raise KeyError(f"unknown theme {theme_id!r}; expected one of {sorted(_THEMES)}")
    path = THEMES_PATH / f"{theme_id}.css"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"no theme stylesheet for {theme_id!r} at {path}: {exc}") from exc


def esc(value: Any) -> str:
    """Escape a value for HTML text or attribute context."""
    return html.escape("" if value is None else str(value), quote=True)


def has_suspicious_markup(value: Any) -> bool:
    """True when source text contains markup that must never be rendered."""
    return bool(_SUSPICIOUS_RE.search("" if value is None else str(value)))


def _facts_value(texts: dict[str, Any] | None, slot: str, default: str) -> str:
    """Return the translated facts-strip value for one slot."""
    if not texts:
        return default
    value = (texts.get("facts") or {}).get(slot)
    if isinstance(value, str) and value.strip():
        return value
    return default


def _step_text(texts: dict[str, Any] | None, stage_index: int, step_number: int,
               default: str) -> str:
    """Return the translated text for one step, or the card default."""
    return step_text(texts, stage_index, step_number, default)


def _facts_block(card: Card, language: str, texts: dict[str, Any] | None) -> str:
    facts = card.data.get("facts", {}) or {}
    return (
        '<div class="fact"><dt>{total_time}</dt><dd><strong>{total}</strong>Active {active}<br>Inactive {inactive}</dd></div>'
        '<div class="fact"><dt>{difficulty}</dt><dd><strong>{difficulty_level}</strong>{difficulty_technique}</dd></div>'
        '<div class="fact"><dt>{yield_portion}</dt><dd><strong>{yield_summary}</strong>{yield_portions}</dd></div>'
        '<div class="fact"><dt>{storage}</dt><dd><strong>{storage_summary}</strong>{storage_reference}</dd></div>'
    ).format(
        total_time=esc(translate("facts.total_time", language)),
        total=esc(recipe_text(texts, "time_total", facts.get("time_total"))),
        active=esc(recipe_text(texts, "time_active", facts.get("time_active"))),
        inactive=esc(recipe_text(texts, "time_inactive", facts.get("time_inactive"))),
        difficulty=esc(translate("facts.difficulty", language)),
        difficulty_level=esc(recipe_text(texts, "difficulty_level", facts.get("difficulty_level"))),
        difficulty_technique=esc(recipe_text(texts, "difficulty_technique", facts.get("difficulty_technique"))),
        yield_portion=esc(translate("facts.yield_portion", language)),
        yield_summary=esc(recipe_text(texts, "yield_summary", facts.get("yield_summary"))),
        yield_portions=esc(recipe_text(texts, "yield_portions", facts.get("yield_portions"))),
        storage=esc(translate("facts.storage", language)),
        storage_summary=esc(recipe_text(texts, "storage_summary", facts.get("storage_summary"))),
        storage_reference=esc(recipe_text(texts, "storage_reference", facts.get("storage_reference"))),
    )


def _ingredients_table(card: Card, language: str,
                       texts: dict[str, Any] | None) -> str:
    derived = card.derived()
    resolved = card.resolved_weights()
    rows: list[str] = []
    if not derived.input_complete:
        rows.append('<tr><td colspan="4">' + esc(translate("status.partial_input", language)) + "</td></tr>")
    for comp_index, comp in enumerate(card.components):
        comp_name = str(comp.get("name", ""))
        comp_name = recipe_field(texts, f"components.{comp_index}.name", comp_name)
        if isinstance(comp.get("linked"), dict):
            link = comp.get("linked") or {}
            rows.append(
                '<tr class="group"><th colspan="4" scope="colgroup">'
                f'{esc(comp_name)} — linked {esc(link.get("component_id"))} '
                f'{esc(link.get("version"))} · {esc(format_weight(link.get("quantity_g"), language=language))}</th></tr>'
            )
            continue
        rows.append(
            f'<tr class="group"><th colspan="4" scope="colgroup">{esc(comp_name)}</th></tr>'
        )
        for ing in comp.get("ingredients", []) or []:
            row_id = str(ing.get("row_id", ""))
            volume = ing.get("volume")
            volume_text = esc(localize_decimals(volume, language)) if volume not in (None, "") else "—"
            name = f"{esc(row_id)} · {esc(recipe_field(texts, f'components.{comp_index}.ingredients.{row_id}.name', ing.get('name')))}"
            notes = recipe_field(texts, f"components.{comp_index}.ingredients.{row_id}.notes", ing.get("notes"))
            if notes:
                name = f"{name}<br><span class=\"caption\">{esc(notes)}</span>"
            weight_text = row_weight_label(ing, resolved.get(row_id), language)
            rows.append(
                "<tr>"
                f"<td>{name}</td>"
                f'<td class="num">{esc(weight_text)}</td>'
                f'<td class="num">{volume_text}</td>'
                f'<td class="num">{esc(format_percent(derived.percentages.get(row_id), language))}</td>'
                "</tr>"
            )

    usable = card.data.get("usable_yield_g")
    rows.append(
        (
            '<tr class="yield"><td>{yield_measured}</td>'
            f'<td class="num">{esc(format_weight(usable, language=language))}</td>'
            '<td class="num">—</td><td class="num">—</td></tr>'
        ).format(yield_measured=esc(translate("table.yield_measured", language)))
    )

    return (
        '<h2>{heading}</h2><div class="table-wrap"><table>'
        '<colgroup><col class="c-name"><col class="c-weight">'
        '<col class="c-volume"><col class="c-scaling"></colgroup>'
        '<thead><tr><th scope="col">{ingredient}</th><th scope="col" class="num">{weight}</th>'
        f'<th scope="col" class="num">{esc(translate("table.volume", language))}</th>'
        f'<th scope="col" class="num">{esc(translate("table.scaling", language))}</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    ).format(
        heading=esc(translate("heading.ingredients", language)),
        ingredient=esc(translate("table.ingredient", language)),
        weight=esc(translate("table.weight", language)),
    )


def _caption(card: Card, language: str, texts: dict[str, Any] | None) -> str:
    derived = card.derived()
    basis = str((card.data.get("percentage_basis") or {}).get("basis_label", ""))
    basis = recipe_text(texts, "percentage_basis", basis)
    input_total = input_mass_label(card, language)
    usable = format_weight(card.data.get("usable_yield_g"), language=language)
    loss = derived.loss_g

    parts = [f"{translate('caption.basis', language)} {basis}" if basis else "",
             f"{translate('caption.input', language)} {input_total}."]
    if usable != "—":
        parts.append(f"{translate('caption.measured_output', language)} {usable}.")
    if loss is not None:
        parts.append(f"{translate('caption.loss', language)} {format_weight(loss, language=language)}.")
    if derived.portions is not None:
        remainder = derived.portion_remainder_g or 0.0
        parts.append(f"{translate('caption.portions', language)} {derived.portions}.")
        if remainder > 0.01:
            parts.append(f"{translate('caption.remainder', language)} {format_weight(remainder, language=language)} {translate('caption.not_portioned', language)}")
    volumes = [
        ing
        for comp in card.components
        for ing in (comp.get("ingredients") or [])
    ]
    sourced = [ing for ing in volumes if ing.get("volume") not in (None, "")]
    if not volumes:
        parts.append(translate("caption.no_volumes", language))
    elif len(sourced) == len(volumes):
        parts.append(translate("caption.volumes_researched", language))
    else:
        parts.append(
            translate("caption.volume_recorded", language).format(
                n=len(sourced), m=len(volumes)
            )
        )
    return '<p class="caption">' + esc(" ".join(p for p in parts if p)) + "</p>"


def _directions(card: Card, language: str, texts: dict[str, Any] | None) -> str:
    stages: list[str] = []
    for stage_index, stage in enumerate(card.stages):
        steps: list[str] = []
        for step_index, step in enumerate(stage.get("steps", []) or []):
            settings = step.get("settings") or {}
            setting_text = ""
            if isinstance(settings, dict) and settings:
                pairs = [
                    f"{key} {value}".strip()
                    for key, value in display_settings(texts, stage_index, step)
                    if str(value).strip()
                ]
                if pairs:
                    setting_text = f'<span class="step-settings">{translate("settings.label", language)}{esc("; ".join(pairs))}</span>'
            text = _step_text(texts, stage_index, step.get("number"), step.get("text"))
            steps.append(
                '<li><span class="step-no">{num}</span><p>{text}{settings}</p></li>'.format(
                    num=esc(step.get("number")),
                    text=esc(text),
                    settings=setting_text,
                )
            )
        tip = recipe_field(texts, f"stages.{stage_index}.tip", stage.get("tip"))
        tip_html = f'<p class="tip">{esc(tip)}</p>' if tip else ""
        stage_name = str(stage.get("name"))
        stage_name = recipe_text(texts, f"stage.{stage_index}.name", stage_name)
        stages.append(
            f'<section class="stage"><h3>{esc(stage_name)}</h3>'
            f'<ol class="steps">{"".join(steps)}</ol>{tip_html}</section>'
        )
    return (
        '<h2 class="method-heading">{heading}</h2>'
        '<div class="directions">' + "".join(stages) + '</div>'
    ).format(heading=esc(translate("heading.method", language)))


def _process_controls(card: Card, language: str, texts=None) -> str:
    """Render the process controls that apply to this card.

    A control the card records as not applicable is left out of the reading
    edition: the reason stays in the card record, and the reader sees only
    the processes the cook actually performs. An unresolved control stays
    visible, because the reader must see what is still open.

    Canonical applicability is resolved first; only display prose is translated.
    Translation cannot change approval, applicability or blocker membership.
    """
    entries = display_controls(card, texts, language)
    if not entries:
        return ""
    rows = []
    for label, value in entries:
        rows.append(
            '<p class="control"><span class="control-label">{label}</span>'
            '<span class="control-value">— {value}</span></p>'.format(
                label=esc(label),
                value=esc(value),
            )
        )
    return (
        '<section class="process"><h3>{heading}</h3>' + "".join(rows) + "</section>"
    ).format(heading=esc(translate("heading.process_controls", language)))


def _labeling(card: Card, language: str, texts=None) -> str:
    """Render the label content block.

    Display prose may be translated; canonical label records and approvals stay intact.
    """
    labeling = card.labeling
    if not labeling:
        return ""
    rows = []
    for key in LABELING_KEYS:
        value = recipe_field(texts, f"labeling.{key}", str(labeling.get(key, "")).strip())
        if not value:
            continue
        label = translate(f"labeling.{key}", language)
        rows.append(f"<p><strong>{esc(label)}:</strong> {esc(value)}</p>")
    if not rows:
        return ""
    return (
        '<section class="process"><h3>{heading}</h3>' + "".join(rows) + "</section>"
    ).format(heading=esc(translate("heading.labeling", language)))


def _notes(card: Card, language: str, texts: dict[str, Any] | None) -> str:
    notes = card.data.get("notes") or []
    if not notes:
        return ""
    blocks = []
    for index, n in enumerate(notes):
        heading, text = note_text(texts, index, n.get("heading"), n.get("text"))
        blocks.append(
            f'<section class="note"><h3>{esc(heading)}</h3><p>{esc(text)}</p></section>'
        )
    return '<div class="notes">' + "".join(blocks) + '</div>'


def _release(card: Card, language: str, texts=None) -> str:
    items = display_release(card, texts, checklist=True)
    if not items:
        return ""
    lis = "".join(f"<li>{esc(i)}</li>" for i in items)
    heading = "Required before production release" if not card.is_production else "Release record"
    heading = translate("heading.release_before", language) if not card.is_production else translate("heading.release_record", language)
    return f'<section class="release"><h2>{esc(heading)}</h2><ul>{lis}</ul></section>'


def _trace(card: Card, language: str, texts=None) -> str:
    provenance = card.data.get("provenance") or {}
    parts = []
    for label, key in (("Evidence", "evidence"), ("Validation", "validation"), ("Filing", "filing")):
        value = recipe_field(texts, f"provenance.{key}", provenance.get(key))
        if value:
            parts.append(f"<p><strong>{esc(translate(f'trace.{key}', language))}</strong> {esc(value)}</p>")
    if not parts:
        return ""
    return '<aside class="trace" aria-label="Source and revision record">' + "".join(parts) + '</aside>'


def render_html(card: Card, template_path: Path | None = None, theme: str | None = None,
                language: str = DEFAULT_LANGUAGE,
                texts: dict[str, Any] | None = None) -> str:
    """Return the complete HTML edition of ``card``.

    ``theme`` selects the editorial theme: the CLI flag, the card record's
    ``theme`` field, or the compatible default ``original`` for records
    that predate the field. The theme changes presentation only -- the
    recipe data is identical in every theme.

    ``language`` selects the cook language for rendered labels and numbers:
    the CLI flag, the card record's ``language`` field, the host
    environment, or English. The language changes presentation only -- the
    canonical numbers and the recipe identity are identical in every
    language. ``texts`` optionally carries translated recipe text
    (title, intro, ingredients, steps, notes) for the language; fields the
    bundle does not cover fall back to the card record.
    """
    texts = display_translation(card, texts)
    theme_id = theme or _DEFAULT_THEME
    if theme_id not in _THEMES:
        raise KeyError(f"unknown theme {theme_id!r}; expected one of {sorted(_THEMES)}")
    css = card_css(template_path)
    overrides = theme_css(theme_id)
    full_css = css + ("\n/* theme: " + theme_id + " */\n" + overrides if overrides else "")

    derived = card.derived()

    status_line = card.status
    if not card.is_production:
        status_line = f"{card.status} — {translate('status.release_warning', language)}"
    blockers = join_blockers(display_release(card, texts))
    if blockers:
        status_line = f"{status_line}. {blockers}"

    library_name = card.data.get("library_name") or "Working Recipe Collection"
    library_name = recipe_text(texts, "library_name", library_name)
    basis_label = (card.data.get("percentage_basis") or {}).get("basis_label", "")

    title = recipe_text(texts, "title", card.title)
    intro = recipe_text(texts, "intro", card.data.get("intro", ""))
    allergens = recipe_text(texts, "allergens", card.data.get("allergens", ""))

    return f'''<!doctype html>
<html lang="{language}" data-theme="{theme_id}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · {esc(card.version)}</title><style>
{full_css}
</style></head><body><main class="page">
<header class="masthead"><span class="brand">Miseform</span><span>{esc(translate("brand.line", language))}</span></header>
<p class="eyebrow">{esc(card.data.get("recipe_type", ""))} · {esc(library_name)}</p><h1>{esc(title)}</h1>
<div class="hero"><p class="intro">{esc(intro)}</p><dl class="facts">
{_facts_block(card, language, texts)}
</dl></div>
<div class="status"><strong>{esc(status_line)}</strong></div>
<p class="meta"><strong>{esc(card.recipe_id)} · {esc(card.version)} · {esc(card.revision_date)}</strong><br><strong>{translate("meta.equipment", language)}</strong> {esc(recipe_text(texts, "equipment", card.data.get("equipment", "")))}<br><strong>{translate("meta.allergens", language)}</strong> {esc(allergens)}<br><strong>{translate("meta.percentage_basis", language)}</strong> {esc(recipe_text(texts, "percentage_basis", basis_label))}</p>
<div class="recipe-body"><section class="ingredients">
{_ingredients_table(card, language, texts)}
{_caption(card, language, texts)}
</section><section class="method">
{_directions(card, language, texts)}
</section></div>
{_process_controls(card, language, texts)}
{_labeling(card, language, texts)}
{_notes(card, language, texts)}
{_release(card, language, texts)}
{_trace(card, language, texts)}
<footer class="footer"><span>{esc(library_name)} · {esc(card.recipe_id)} · {esc(card.version)}</span><span>{esc(card.status)}</span></footer>
</main></body></html>
'''


__all__ = ["card_css", "theme_css", "esc", "has_suspicious_markup", "render_html"]

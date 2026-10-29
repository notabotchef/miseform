"""Render a recipe card to the Miseform editorial HTML edition.

The stylesheet is not duplicated here. It is extracted from the skill's own
``templates/recipe-card.html`` so the rendered card and the hand-editable
template can never drift apart.

All card text is HTML-escaped. A recipe note is data, never markup.
"""

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
    join_blockers,
)

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "recipe-card.html"

_STYLE_RE = re.compile(r"<style>(.*?)</style>", re.DOTALL)

# Markup that must never appear as executable content in source material.
_SUSPICIOUS_RE = re.compile(
    r"<\s*(script|iframe|object|embed|style|link|meta)\b|javascript:|on[a-z]+\s*=",
    re.IGNORECASE,
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


def esc(value: Any) -> str:
    """Escape a value for HTML text or attribute context."""
    return html.escape("" if value is None else str(value), quote=True)


def has_suspicious_markup(value: Any) -> bool:
    """True when source text contains markup that must never be rendered."""
    return bool(_SUSPICIOUS_RE.search("" if value is None else str(value)))


def _facts_block(card: Card) -> str:
    facts = card.data.get("facts", {}) or {}
    return (
        '<div class="fact"><dt>Total time</dt><dd><strong>{total}</strong>Active {active}<br>Inactive {inactive}</dd></div>'
        '<div class="fact"><dt>Difficulty</dt><dd><strong>{difficulty_level}</strong>{difficulty_technique}</dd></div>'
        '<div class="fact"><dt>Yield / portion</dt><dd><strong>{yield_summary}</strong>{yield_portions}</dd></div>'
        '<div class="fact"><dt>Storage</dt><dd><strong>{storage_summary}</strong>{storage_reference}</dd></div>'
    ).format(
        total=esc(facts.get("time_total")),
        active=esc(facts.get("time_active")),
        inactive=esc(facts.get("time_inactive")),
        difficulty_level=esc(facts.get("difficulty_level")),
        difficulty_technique=esc(facts.get("difficulty_technique")),
        yield_summary=esc(facts.get("yield_summary")),
        yield_portions=esc(facts.get("yield_portions")),
        storage_summary=esc(facts.get("storage_summary")),
        storage_reference=esc(facts.get("storage_reference")),
    )


def _ingredients_table(card: Card) -> str:
    derived = card.derived()
    rows: list[str] = []
    for comp in card.components:
        comp_name = str(comp.get("name", ""))
        rows.append(
            f'<tr class="group"><th colspan="4" scope="colgroup">{esc(comp_name)}</th></tr>'
        )
        for ing in comp.get("ingredients", []) or []:
            row_id = str(ing.get("row_id", ""))
            volume = ing.get("volume")
            volume_text = esc(volume) if volume not in (None, "") else "—"
            notes = ing.get("notes")
            # The row ID stays visible: the procedure refers to rows by ID.
            name = f"{esc(row_id)} · {esc(ing.get('name'))}"
            if notes:
                name = f"{name}<br><span class=\"caption\">{esc(notes)}</span>"
            rows.append(
                "<tr>"
                f"<td>{name}</td>"
                f'<td class="num">{esc(format_weight(ing.get("weight_g")))}</td>'
                f'<td class="num">{volume_text}</td>'
                f'<td class="num">{esc(format_percent(derived.percentages.get(row_id)))}</td>'
                "</tr>"
            )

    usable = card.data.get("usable_yield_g")
    rows.append(
        '<tr class="yield"><td>Measured usable yield</td>'
        f'<td class="num">{esc(format_weight(usable))}</td>'
        '<td class="num">—</td><td class="num">—</td></tr>'
    )

    return (
        '<h2>Ingredients</h2><div class="table-wrap"><table>'
        '<colgroup><col class="c-name"><col class="c-weight">'
        '<col class="c-volume"><col class="c-scaling"></colgroup>'
        '<thead><tr><th scope="col">Ingredient</th><th scope="col" class="num">Weight</th>'
        '<th scope="col" class="num">Volume</th><th scope="col" class="num">Scaling %</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def _caption(card: Card) -> str:
    derived = card.derived()
    basis = str((card.data.get("percentage_basis") or {}).get("basis_label", ""))
    input_total = format_weight(card.data.get("input_total_g"))
    usable = format_weight(card.data.get("usable_yield_g"))
    loss = derived.loss_g

    parts = [f"Basis: {basis}" if basis else "", f"Input {input_total}."]
    if usable != "—":
        parts.append(f"Measured usable output {usable}.")
    if loss is not None:
        parts.append(f"Transfer loss {format_weight(loss)}.")
    if derived.portions is not None:
        remainder = derived.portion_remainder_g or 0.0
        parts.append(f"Complete portions {derived.portions}.")
        if remainder > 0.01:
            parts.append(f"Remainder {format_weight(remainder)} not portioned.")
    volumes = [
        ing
        for comp in card.components
        for ing in (comp.get("ingredients") or [])
    ]
    sourced = [ing for ing in volumes if ing.get("volume") not in (None, "")]
    if not volumes:
        parts.append("No ingredient volumes recorded; weigh ingredients.")
    elif len(sourced) == len(volumes):
        parts.append(
            "Volumes are researched approximations from cited sources, not measured spoonfuls; weigh ingredients."
        )
    else:
        parts.append(
            f"Volume recorded for {len(sourced)} of {len(volumes)} ingredients; "
            "a researched volume is an approximation, not a measured spoonful. Weigh ingredients."
        )
    return '<p class="caption">' + esc(" ".join(p for p in parts if p)) + "</p>"


def _directions(card: Card) -> str:
    stages: list[str] = []
    for stage in card.stages:
        steps: list[str] = []
        for step in stage.get("steps", []) or []:
            settings = step.get("settings") or {}
            setting_text = ""
            if isinstance(settings, dict) and settings:
                pairs = [
                    f"{key.replace('_', ' ')} {value}".strip()
                    for key, value in settings.items()
                    if str(value).strip()
                ]
                if pairs:
                    setting_text = f'<span class="step-settings">Settings — {esc("; ".join(pairs))}</span>'
            steps.append(
                '<li><span class="step-no">{num}</span><p>{text}{settings}</p></li>'.format(
                    num=esc(step.get("number")),
                    text=esc(step.get("text")),
                    settings=setting_text,
                )
            )
        tip = stage.get("tip")
        tip_html = f'<p class="tip">{esc(tip)}</p>' if tip else ""
        stages.append(
            f'<section class="stage"><h3>{esc(stage.get("name"))}</h3>'
            f'<ol class="steps">{"".join(steps)}</ol>{tip_html}</section>'
        )
    return (
        '<h2 class="method-heading">Method</h2>'
        f'<div class="directions">{"".join(stages)}</div>'
    )


def _process_controls(card: Card) -> str:
    """Render the process controls that apply to this card.

    A control the card records as not applicable is left out of the reading
    edition: the reason stays in the card record, and the reader sees only
    the processes the cook actually performs. An unresolved control stays
    visible, because the reader must see what is still open.

    Labels are readable and the value is the plain sentence the card
    author wrote, not an uppercase checklist.
    """
    entries = applicable_process_controls(card.process_controls)
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
    return '<section class="process"><h3>Process controls</h3>' + "".join(rows) + "</section>"


def _labeling(card: Card) -> str:
    """Render the label content block."""
    labeling = card.labeling
    if not labeling:
        return ""
    rows = []
    for key in LABELING_KEYS:
        value = str(labeling.get(key, "")).strip()
        if not value:
            continue
        label = key.replace("_", " ")
        rows.append(f"<p><strong>{esc(label)}:</strong> {esc(value)}</p>")
    if not rows:
        return ""
    return '<section class="process"><h3>Labeling</h3>' + "".join(rows) + "</section>"


def _notes(card: Card) -> str:
    notes = card.data.get("notes") or []
    if not notes:
        return ""
    blocks = [
        f'<section class="note"><h3>{esc(n.get("heading"))}</h3><p>{esc(n.get("text"))}</p></section>'
        for n in notes
    ]
    return f'<div class="notes">{"".join(blocks)}</div>'


def _release(card: Card) -> str:
    items = list(card.data.get("release_checklist") or []) or list(card.release_blockers)
    if not items:
        return ""
    lis = "".join(f"<li>{esc(i)}</li>" for i in items)
    heading = "Required before production release" if not card.is_production else "Release record"
    return f'<section class="release"><h2>{esc(heading)}</h2><ul>{lis}</ul></section>'


def _trace(card: Card) -> str:
    provenance = card.data.get("provenance") or {}
    parts = []
    for label, key in (("Evidence", "evidence"), ("Validation", "validation"), ("Filing", "filing")):
        value = provenance.get(key)
        if value:
            parts.append(f"<p><strong>{esc(label)}:</strong> {esc(value)}</p>")
    if not parts:
        return ""
    return f'<aside class="trace" aria-label="Source and revision record">{"".join(parts)}</aside>'


def render_html(card: Card, template_path: Path | None = None) -> str:
    """Return the complete HTML edition of ``card``."""
    css = card_css(template_path)
    derived = card.derived()

    status_line = card.status
    if not card.is_production:
        status_line = f"{card.status} — {RELEASE_WARNING}"
    blockers = join_blockers(card.release_blockers)
    if blockers:
        status_line = f"{status_line}. {blockers}"

    library_name = card.data.get("library_name") or "Working Recipe Collection"
    basis_label = (card.data.get("percentage_basis") or {}).get("basis_label", "")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(card.title)} · {esc(card.version)}</title><style>
{css}
</style></head><body><main class="page">
<header class="masthead"><span class="brand">Miseform</span><span>The working recipe collection</span></header>
<p class="eyebrow">{esc(card.data.get("recipe_type", ""))} · {esc(library_name)}</p><h1>{esc(card.title)}</h1>
<div class="hero"><p class="intro">{esc(card.data.get("intro", ""))}</p><dl class="facts">
{_facts_block(card)}
</dl></div>
<div class="status"><strong>{esc(status_line)}</strong></div>
<p class="meta"><strong>{esc(card.recipe_id)} · {esc(card.version)} · {esc(card.revision_date)}</strong><br><strong>Equipment / tested load:</strong> {esc(card.data.get("equipment", ""))}<br><strong>Allergens:</strong> {esc(card.data.get("allergens", ""))}<br><strong>Percentage basis:</strong> {esc(basis_label)}</p>
<div class="recipe-body"><section class="ingredients">
{_ingredients_table(card)}
{_caption(card)}
</section><section class="method">
{_directions(card)}
</section></div>
{_process_controls(card)}
{_labeling(card)}
{_notes(card)}
{_release(card)}
{_trace(card)}
<footer class="footer"><span>{esc(library_name)} · {esc(card.recipe_id)} · {esc(card.version)}</span><span>{esc(card.status)}</span></footer>
</main></body></html>
"""


__all__ = ["card_css", "esc", "has_suspicious_markup", "render_html"]

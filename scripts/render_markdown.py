'''Render a recipe card to the editable Markdown master.

Markdown is the portable editable master. It carries the same content as the
HTML, PDF and XLSX editions: one recipe, one version, four synchronized
files.

Section headings and table headers stay in their original literal form so
the editable master is stable across languages. Only numbers switch to the
cook's language convention (decimal comma for es/fr/it/pt), and translated
recipe text (title, intro, allergens) is applied when a bundle covers it.
'''

from __future__ import annotations

from typing import Any

from card_model import (
    LABELING_KEYS,
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
    recipe_text,
    step_text,
    translate,
)


def _md_escape(text: Any) -> str:
    """Escape pipe characters so a value cannot break a Markdown table."""
    return "" if text is None else str(text).replace("|", "\\|")


def _facts_value(texts: dict[str, Any] | None, slot: str, default: str) -> str:
    """Return the translated facts-strip value for one slot."""
    if not texts:
        return default
    value = recipe_text(texts, slot, default)
    if isinstance(value, str) and value.strip():
        return value
    return default


def render_markdown(card: Card, language: str = DEFAULT_LANGUAGE,
                    texts: dict[str, Any] | None = None) -> str:
    """Return the Markdown master for ``card``.

    ``language`` localizes rendered numbers (decimal mark); ``texts``
    optionally carries translated recipe text for the language, with fields
    the bundle does not cover falling back to the card record.
    """
    texts = display_translation(card, texts)
    derived = card.derived()
    facts = card.data.get("facts", {}) or {}
    basis = card.data.get("percentage_basis") or {}
    provenance = card.data.get("provenance") or {}

    lines: list[str] = []
    lines.append(f"# {recipe_text(texts, 'title', card.title)}")
    lines.append("")

    status_line = card.status
    if not card.is_production:
        status_line = f"{card.status} — {translate('status.release_warning', language)}"
    lines.append(f"**{translate('meta.status', language).upper()}** {status_line}")
    lines.append(f"**{translate('meta.identity', language).upper()}** {card.recipe_id} · {card.version} · {card.revision_date}")
    lines.append(f"**{translate('meta.recipe_type', language).upper()}** {_md_escape(card.data.get('recipe_type', ''))}")
    lines.append("")

    intro = recipe_text(texts, "intro", card.data.get("intro", ""))
    if intro:
        lines.append(intro)
        lines.append("")

    lines.append("| TIME | DIFFICULTY | YIELD / PORTION | STORAGE |")
    lines.append("|---|---|---|---|")
    lines.append(
        "| {tt} total ({ta} active / {ti} inactive) | {dl} — {dt} | {ys} · {yp} | {ss} — {sr} |".format(
            tt=_md_escape(_facts_value(texts, "time_total", facts.get("time_total"))),
            ta=_md_escape(_facts_value(texts, "time_active", facts.get("time_active"))),
            ti=_md_escape(_facts_value(texts, "time_inactive", facts.get("time_inactive"))),
            dl=_md_escape(_facts_value(texts, "difficulty_level", facts.get("difficulty_level"))),
            dt=_md_escape(_facts_value(texts, "difficulty_technique", facts.get("difficulty_technique"))),
            ys=_md_escape(_facts_value(texts, "yield_summary", facts.get("yield_summary"))),
            yp=_md_escape(_facts_value(texts, "yield_portions", facts.get("yield_portions"))),
            ss=_md_escape(_facts_value(texts, "storage_summary", facts.get("storage_summary"))),
            sr=_md_escape(_facts_value(texts, "storage_reference", facts.get("storage_reference"))),
        )
    )
    lines.append("")

    lines.append(f"**{translate('meta.equipment', language).upper()}** {recipe_text(texts, 'equipment', card.data.get('equipment', ''))}")
    lines.append("")
    lines.append(f"**{translate('meta.allergens', language).upper()}** {recipe_text(texts, 'allergens', card.data.get('allergens', ''))}")
    lines.append("")
    lines.append(f"**{translate('meta.percentage_basis', language).upper()}** {_md_escape(recipe_text(texts, 'percentage_basis', basis.get('basis_label', '')))}")
    lines.append("")

    if card.release_blockers:
        lines.append("**" + translate("cli.release_blockers", language).upper() + "**")
        lines.append("")
        for blocker in display_release(card, texts):
            lines.append(f"- {blocker}")
        lines.append("")

    lines.append("## " + translate("heading.ingredients", language).upper())
    lines.append("")
    lines.append("| " + " | ".join(translate("table." + key, language).upper() for key in ("ingredient", "weight", "volume", "scaling")) + " |")
    lines.append("|---|---:|---:|---:|")
    resolved = card.resolved_weights()
    for comp_index, comp in enumerate(card.components):
        if isinstance(comp.get("linked"), dict):
            link = comp.get("linked") or {}
            lines.append(
                f"| **{_md_escape(recipe_field(texts, f'components.{comp_index}.name', comp.get('name')))}** | linked "
                f"{_md_escape(link.get('component_id'))} "
                f"{_md_escape(link.get('version'))} · {format_weight(link.get('quantity_g'), language=language)} | — | — |"
            )
            continue
        lines.append(f"| **{_md_escape(recipe_field(texts, f'components.{comp_index}.name', comp.get('name', '')))}** | | | |")
        for ing in comp.get("ingredients", []) or []:
            row_id = str(ing.get("row_id", ""))
            volume = ing.get("volume")
            volume_text = _md_escape(localize_decimals(volume, language)) if volume not in (None, "") else "—"
            name = _md_escape(recipe_field(texts, f"components.{comp_index}.ingredients.{row_id}.name", ing.get("name", "")))
            notes = recipe_field(texts, f"components.{comp_index}.ingredients.{row_id}.notes", ing.get("notes"))
            if notes:
                name = f"{name} — {_md_escape(notes)}"
            weight_text = row_weight_label(ing, resolved.get(row_id), language)
            lines.append(
                f"| {row_id} {name} | {weight_text} | "
                f"{volume_text} | {format_percent(derived.percentages.get(row_id), language)} |"
            )
    lines.append(
        f"| **{translate('table.yield_measured', language)}** | {format_weight(card.data.get('usable_yield_g'), language=language)} | — | — |"
    )
    lines.append("")

    if not derived.input_complete:
        lines.append(translate("status.partial_input", language))
    totals: list[str] = [f"{translate('caption.input', language)} {input_mass_label(card, language)}."]
    if derived.loss_g is not None:
        totals.append(f"{translate('caption.loss', language)} {format_weight(derived.loss_g, language=language)}.")
    if derived.portions is not None:
        totals.append(f"{translate('caption.portions', language)} {derived.portions}.")
        if (derived.portion_remainder_g or 0.0) > 0.01:
            totals.append(f"{translate('caption.remainder', language)} {format_weight(derived.portion_remainder_g, language=language)} {translate('caption.not_portioned', language)}")
    lines.append(" ".join(totals))
    lines.append("")

    lines.append("## GENERAL DIRECTIONS")
    lines.append("")
    for stage_index, stage in enumerate(card.stages):
        stage_name = recipe_text(texts, f"stage.{stage_index}.name", stage.get("name", ""))
        lines.append(f"### {stage_name}")
        lines.append("")
        for step in stage.get("steps", []) or []:
            lines.append(f"{step.get('number')}. {step_text(texts, stage_index, step.get('number'), step.get('text', ''))}")
            settings = step.get("settings") or {}
            if isinstance(settings, dict) and settings:
                pairs = [
                    f"{key} {value}".strip()
                    for key, value in display_settings(texts, stage_index, step)
                    if str(value).strip()
                ]
                if pairs:
                    lines.append(f"   *{translate('settings.label', language)}{'; '.join(pairs)}*")
        tip = recipe_field(texts, f"stages.{stage_index}.tip", stage.get("tip"))
        if tip:
            lines.append("")
            lines.append(f"*{translate('tip.label', language)}{tip}*")
        lines.append("")

    entries = display_controls(card, texts, language)
    if entries:
        lines.append("## " + translate("heading.process_controls", language).upper())
        lines.append("")
        for label, value in entries:
            lines.append(f"- {label} — {value}")
            lines.append("")
        lines.append("")

    labeling = card.labeling
    if labeling:
        lines.append("## " + translate("heading.labeling", language).upper())
        lines.append("")
        for key in LABELING_KEYS:
            value = recipe_field(texts, f"labeling.{key}", str(labeling.get(key, "")).strip())
            if value:
                lines.append(f"**{translate('labeling.' + key, language)}** — {value}")
                lines.append("")
        lines.append("")

    notes = card.data.get("notes") or []
    if notes:
        lines.append("## " + translate("heading.notes", language).upper())
        lines.append("")
        for note_index, note in enumerate(notes):
            lines.append(f"**{recipe_field(texts, f'notes.{note_index}.heading', note.get('heading'))}**")
            lines.append("")
            lines.append(recipe_field(texts, f"notes.{note_index}.text", str(note.get("text", ""))))
            lines.append("")

    checklist = display_release(card, texts, checklist=True)
    if checklist:
        lines.append("## " + translate("heading.release_before" if not card.is_production else "heading.release_record", language).upper())
        lines.append("")
        for item in checklist:
            lines.append(f"- {item}")
        lines.append("")

    if provenance:
        lines.append("## " + translate("heading.source_record", language).upper())
        lines.append("")
        for label, key in (("Evidence", "evidence"), ("Validation", "validation"), ("Filing", "filing")):
            value = recipe_field(texts, f"provenance.{key}", provenance.get(key))
            if value:
                lines.append(f"**{translate('trace.' + key, language)}:** {value}")
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


__all__ = ["render_markdown"]

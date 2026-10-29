"""Render a recipe card to the editable Markdown master.

Markdown is the portable editable master. It carries the same content as the
HTML, PDF and XLSX editions: one recipe, one version, four synchronized files.
"""

from __future__ import annotations

from typing import Any

from card_model import (
    LABELING_KEYS,
    RELEASE_WARNING,
    Card,
    applicable_process_controls,
    format_percent,
    format_weight,
)


def _md_escape(text: Any) -> str:
    """Escape pipe characters so a value cannot break a Markdown table."""
    return "" if text is None else str(text).replace("|", "\\|")


def render_markdown(card: Card) -> str:
    """Return the Markdown master for ``card``."""
    derived = card.derived()
    facts = card.data.get("facts", {}) or {}
    basis = card.data.get("percentage_basis") or {}
    provenance = card.data.get("provenance") or {}

    lines: list[str] = []
    lines.append(f"# {card.title}")
    lines.append("")

    status_line = card.status
    if not card.is_production:
        status_line = f"{card.status} — {RELEASE_WARNING}"
    lines.append(f"**STATUS** {status_line}")
    lines.append(f"**ID / VERSION** {card.recipe_id} · {card.version} · {card.revision_date}")
    lines.append(f"**RECIPE TYPE** {card.data.get('recipe_type', '')}")
    lines.append("")

    intro = card.data.get("intro", "")
    if intro:
        lines.append(intro)
        lines.append("")

    lines.append("| TIME | DIFFICULTY | YIELD / PORTION | STORAGE |")
    lines.append("|---|---|---|---|")
    lines.append(
        "| {tt} total ({ta} active / {ti} inactive) | {dl} — {dt} | {ys} · {yp} | {ss} — {sr} |".format(
            tt=_md_escape(facts.get("time_total")),
            ta=_md_escape(facts.get("time_active")),
            ti=_md_escape(facts.get("time_inactive")),
            dl=_md_escape(facts.get("difficulty_level")),
            dt=_md_escape(facts.get("difficulty_technique")),
            ys=_md_escape(facts.get("yield_summary")),
            yp=_md_escape(facts.get("yield_portions")),
            ss=_md_escape(facts.get("storage_summary")),
            sr=_md_escape(facts.get("storage_reference")),
        )
    )
    lines.append("")

    lines.append(f"**EQUIPMENT** {card.data.get('equipment', '')}")
    lines.append("")
    lines.append(f"**ALLERGENS** {card.data.get('allergens', '')}")
    lines.append("")
    lines.append(f"**SCALING BASIS** {basis.get('basis_label', '')}")
    lines.append("")

    if card.release_blockers:
        lines.append("**RELEASE BLOCKERS**")
        lines.append("")
        for blocker in card.release_blockers:
            lines.append(f"- {blocker}")
        lines.append("")

    lines.append("## INGREDIENTS")
    lines.append("")
    lines.append("| INGREDIENT | WEIGHT | VOLUME | SCALING % |")
    lines.append("|---|---:|---:|---:|")
    for comp in card.components:
        lines.append(f"| **{_md_escape(comp.get('name'))}** | | | |")
        for ing in comp.get("ingredients", []) or []:
            row_id = str(ing.get("row_id", ""))
            volume = ing.get("volume")
            volume_text = _md_escape(volume) if volume not in (None, "") else "—"
            name = _md_escape(ing.get("name"))
            notes = ing.get("notes")
            if notes:
                name = f"{name} — {_md_escape(notes)}"
            lines.append(
                f"| {row_id} {name} | {format_weight(ing.get('weight_g'))} | "
                f"{volume_text} | {format_percent(derived.percentages.get(row_id))} |"
            )
    lines.append(
        f"| **Measured usable yield** | {format_weight(card.data.get('usable_yield_g'))} | — | — |"
    )
    lines.append("")

    totals: list[str] = [f"Input total {format_weight(card.data.get('input_total_g'))}."]
    if derived.loss_g is not None:
        totals.append(f"Loss {format_weight(derived.loss_g)}.")
    if derived.portions is not None:
        totals.append(f"Complete portions {derived.portions}.")
        if (derived.portion_remainder_g or 0.0) > 0.01:
            totals.append(f"Remainder {format_weight(derived.portion_remainder_g)} not portioned.")
    lines.append(" ".join(totals))
    lines.append("")

    lines.append("## GENERAL DIRECTIONS")
    lines.append("")
    for stage in card.stages:
        lines.append(f"### {stage.get('name')}")
        lines.append("")
        for step in stage.get("steps", []) or []:
            lines.append(f"{step.get('number')}. {step.get('text')}")
            settings = step.get("settings") or {}
            if isinstance(settings, dict) and settings:
                pairs = [
                    f"{key.replace('_', ' ')} {value}".strip()
                    for key, value in settings.items()
                    if str(value).strip()
                ]
                if pairs:
                    lines.append(f"   *Settings — {'; '.join(pairs)}*")
        tip = stage.get("tip")
        if tip:
            lines.append("")
            lines.append(f"*Tip — {tip}*")
        lines.append("")

    entries = applicable_process_controls(card.process_controls)
    if entries:
        lines.append("## PROCESS CONTROLS")
        lines.append("")
        for label, value in entries:
            lines.append(f"- {label} — {value}")
            lines.append("")
        lines.append("")

    labeling = card.labeling
    if labeling:
        lines.append("## LABELING")
        lines.append("")
        for key in LABELING_KEYS:
            value = str(labeling.get(key, "")).strip()
            if value:
                lines.append(f"**{key.replace('_', ' ')}** — {value}")
                lines.append("")
        lines.append("")

    notes = card.data.get("notes") or []
    if notes:
        lines.append("## NOTES")
        lines.append("")
        for note in notes:
            lines.append(f"**{note.get('heading')}**")
            lines.append("")
            lines.append(str(note.get("text", "")))
            lines.append("")

    checklist = list(card.data.get("release_checklist") or []) or list(card.release_blockers)
    if checklist:
        lines.append("## REQUIRED BEFORE PRODUCTION RELEASE" if not card.is_production else "## RELEASE RECORD")
        lines.append("")
        for item in checklist:
            lines.append(f"- {item}")
        lines.append("")

    if provenance:
        lines.append("## SOURCE AND REVISION RECORD")
        lines.append("")
        for label, key in (("Evidence", "evidence"), ("Validation", "validation"), ("Filing", "filing")):
            value = provenance.get(key)
            if value:
                lines.append(f"**{label}:** {value}")
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


__all__ = ["render_markdown"]

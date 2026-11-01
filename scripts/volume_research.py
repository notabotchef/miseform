#!/usr/bin/env python3
"""Automatic volume research with a state- and brand-aware source cache.

This module is the executable form of the volume rules in
``references/volume-research.md`` for the part that can be proven without a
network. It does three things:

* it holds ingredient-specific gram-to-volume references, each with the
  provenance the card has to carry (URL, title, access date, the source's
  own ratio, the unit convention, the ingredient and preparation state that
  matched, proxy status, confidence and the reason when unresolved);
* it derives an approximate household measure from the authoritative grams,
  naming the unit convention explicitly (US, metric or Australian);
* it never invents a number. A source that does not match the ingredient and
  its preparation state is rejected with a reason, two targeted sources are
  the bound, and an ingredient that stays unresolved carries the reason
  instead of a guessed measure.

Four failures this module exists to prevent:

* a nutrition panel's *fat* line is never read as the serving's total weight;
* grams are never assumed to be millilitres for an ingredient whose density
  was never established;
* raw seafood is never converted from a cooked-meat chart in silence;
* two sources that disagree materially are never averaged, and one of them
  is never quietly picked.

Public API:

    load_sources(path=None)          -> list[VolumeSource]
    SourceCache(path)                 -> state- and brand-aware source cache
    research_volume(ingredient, grams, ...) -> VolumeResult
    apply_research(card, ...)         -> (data, records)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

PACKAGE = Path(__file__).resolve().parent.parent
SOURCES_PATH = PACKAGE / "references" / "volume-sources.example.json"

# Where the reusable cache lives. The cache is keyed by ingredient, state and
# brand, so a reference that was already checked for one salt type is never
# reused for another.
CACHE_ENV = "MISEFORM_VOLUME_CACHE"
DEFAULT_CACHE = Path.home() / ".cache" / "miseform" / "volume-sources.json"

# The source hierarchy, best first. An exact product label beats a generic
# culinary chart, a chart beats government composition data, and a bounded
# fallback is used only when nothing better matched and is labeled a proxy.
TIER_ORDER = ("exact_product", "chart", "usda", "fallback")

# The millilitres each household unit holds, by convention. An Australian
# tablespoon is 20 mL, not 15 mL, so the two are never mixed.
UNIT_ML = {
    "US": {"cup": 236.588, "tbsp": 14.7868, "tsp": 4.92892, "quart": 946.353},
    "metric": {"cup": 250.0, "tbsp": 15.0, "tsp": 5.0, "quart": 1000.0},
    "AU": {"cup": 250.0, "tbsp": 20.0, "tsp": 5.0, "quart": 1000.0},
}

CONVENTION_LABELS = {"US": "US", "metric": "metric", "AU": "AU"}

# Mass units in grams. Pounds convert to metric and the original quantity
# stays in the record next to the value it produced.
MASS_TO_GRAM = {
    "mg": 0.001,
    "g": 1.0,
    "kg": 1000.0,
    "oz": 28.349523125,
    "lb": 453.59237,
    "lb.": 453.59237,
}

# Preparation states that must never be converted into one another without
# the source saying so. A raw item and a cooked one are different products.
STATE_CONFLICTS = (
    ("raw", "cooked"),
    ("shell-on", "shell-free"),
    ("table salt", "kosher salt"),
    ("table salt", "sea salt"),
    ("kosher salt", "sea salt"),
    # A fine salt is table salt milled finer. It is not a kosher salt, and a
    # kosher chart cannot answer a fine-salt question.
    ("fine salt", "kosher salt"),
)

# Words that describe the ingredient without changing what it is.
NOISE = frozenset(
    """
    purchased fresh extra plain all-purpose organic boneless skinless
    low-fat large small
    """.split()
)

# The bound: two targeted sources per ingredient, then an explicit reason.
DEFAULT_MAX_ATTEMPTS = 2

# Two sources that disagree by more than this on the same ingredient are a
# conflict the cook settles, not a number to average.
CONFLICT_RATIO = 1.25


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"\s+", str(text or "").lower().strip()) if t]


def normalize(text: str) -> str:
    """The comparison key for an ingredient phrase."""
    kept = [t for t in _tokens(text) if t not in NOISE]
    if not kept:
        kept = _tokens(text)
    return " ".join(sorted(kept))


def to_grams(amount: float, unit: str) -> float | None:
    """Convert a mass to grams. Returns None for a unit that is not a mass."""
    key = str(unit or "").strip().lower()
    factor = MASS_TO_GRAM.get(key)
    if factor is None:
        return None
    return float(amount) * factor


@dataclass(frozen=True)
class VolumeSource:
    """One ingredient-specific gram-to-volume reference.

    ``grams`` is the mass the source states for ``amount`` of ``unit`` in
    ``unit_convention``. ``measure`` records what the source measured: only
    ``total_mass`` may be used as the ingredient's weight.
    """

    ingredient: str
    aliases: tuple[str, ...]
    state: str
    brand: str | None
    tier: str
    url: str
    title: str
    accessed: str
    original_ratio: str
    amount: float
    unit: str
    unit_convention: str
    grams: float
    state_match: str
    proxy: bool
    confidence: str
    measure: str = "total_mass"

    # ---------------------------------------------------------------- helpers

    @property
    def grams_per_ml(self) -> float:
        """The density this source implies. Never assumed, always derived."""
        millilitres = self.amount * UNIT_ML[self.unit_convention][self.unit]
        return self.grams / millilitres

    @property
    def grams_per_unit(self) -> float:
        """Grams for one whole unit (one cup, one tablespoon, one teaspoon)."""
        return self.grams / self.amount

    def key(self) -> str:
        """The state- and brand-aware cache key for this source."""
        return cache_key(self.ingredient, self.state, self.brand)

    def provenance(self) -> dict[str, Any]:
        """The structured record the card carries for this reference."""
        return {
            "source_url": self.url,
            "source_title": self.title,
            "accessed": self.accessed,
            "original_ratio": self.original_ratio,
            "unit_convention": self.unit_convention,
            "source_state": self.state,
            "state_match": self.state_match,
            "brand": self.brand,
            "proxy": self.proxy,
            "confidence": self.confidence,
            "tier": self.tier,
            "measure": self.measure,
        }


def cache_key(ingredient: str, state: str | None = None, brand: str | None = None) -> str:
    """The cache key for one ingredient, its state and its brand.

    The key is state- and brand-aware on purpose: a table-salt figure is not
    a kosher-salt figure, and a purchased brand label is not a generic chart.
    """
    return "|".join(
        [normalize(ingredient), normalize(state or ""), normalize(brand or "")]
    )


@dataclass
class VolumeResult:
    """The outcome of researching one ingredient."""

    status: str  # "derived" | "unresolved" | "not_applicable"
    volume: str | None = None
    amount: float | None = None
    unit: str | None = None
    unit_convention: str | None = None
    grams_per_unit: float | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    unresolved_reason: str | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)

    def record(self, row_id: str) -> dict[str, Any]:
        """The structured record stored on the card."""
        out: dict[str, Any] = {"row_id": row_id, "status": self.status}
        if self.volume is not None:
            out["amount"] = self.amount
            out["unit"] = self.unit
            out["unit_convention"] = self.unit_convention
            out["grams_per_unit"] = self.grams_per_unit
            out["volume"] = self.volume
        if self.provenance:
            out.update(self.provenance)
        if self.unresolved_reason:
            out["unresolved_reason"] = self.unresolved_reason
        out["attempts"] = self.attempts
        return out


# --------------------------------------------------------------------- sources


def load_sources(path: str | Path | None = None) -> list[VolumeSource]:
    """Load a source catalogue from disk."""
    target = Path(path) if path else SOURCES_PATH
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read volume sources at {target}: {exc}") from exc

    sources: list[VolumeSource] = []
    for entry in raw.get("sources", []):
        sources.append(
            VolumeSource(
                ingredient=entry["ingredient"],
                aliases=tuple(entry.get("aliases", ())),
                state=entry.get("state", ""),
                brand=entry.get("brand"),
                tier=entry.get("tier", "chart"),
                url=entry["url"],
                title=entry["title"],
                accessed=entry["accessed"],
                original_ratio=entry["original_ratio"],
                amount=float(entry["amount"]),
                unit=entry["unit"],
                unit_convention=entry["unit_convention"],
                grams=float(entry["grams"]),
                state_match=entry.get("state_match", ""),
                proxy=bool(entry.get("proxy", True)),
                confidence=entry.get("confidence", "medium"),
                measure=entry.get("measure", "total_mass"),
            )
        )
    return sources


class SourceCache:
    """A reusable, state- and brand-aware cache of checked references.

    A reference is looked up by ingredient, preparation state and brand, so
    the same salt type is never answered with another salt type's figure.
    The cache never invents an entry: it stores what a check established.
    """

    def __init__(self, path: str | Path | None = None):
        if path is None:
            path = os.environ.get(CACHE_ENV) or DEFAULT_CACHE
        self.path = Path(path)
        self.entries: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        entries = raw.get("sources")
        if isinstance(entries, dict):
            self.entries = {str(k): dict(v) for k, v in entries.items()}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "sources": self.entries}
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def get(self, ingredient: str, state: str | None, brand: str | None) -> dict[str, Any] | None:
        return self.entries.get(cache_key(ingredient, state, brand))

    def put(
        self, ingredient: str, state: str | None, brand: str | None, record: dict[str, Any]
    ) -> None:
        self.entries[cache_key(ingredient, state, brand)] = record

    def source_from_record(self, record: dict[str, Any]) -> VolumeSource:
        return VolumeSource(
            ingredient=record["ingredient"],
            aliases=tuple(record.get("aliases", ())),
            state=record.get("state", ""),
            brand=record.get("brand"),
            tier=record.get("tier", "chart"),
            url=record["url"],
            title=record["title"],
            accessed=record["accessed"],
            original_ratio=record["original_ratio"],
            amount=float(record["amount"]),
            unit=record["unit"],
            unit_convention=record["unit_convention"],
            grams=float(record["grams"]),
            state_match=record.get("state_match", ""),
            proxy=bool(record.get("proxy", True)),
            confidence=record.get("confidence", "medium"),
            measure=record.get("measure", "total_mass"),
        )


# --------------------------------------------------------------------- ranking


def _state_conflict(source_state: str, wanted_state: str) -> bool:
    """True when the two preparation states must not be converted."""
    left = str(source_state or "").lower()
    right = str(wanted_state or "").lower()
    if not left or not right:
        return False
    for first, second in STATE_CONFLICTS:
        if (first in left and second in right) or (second in left and first in right):
            return True
    return False


def _ingredient_matches(source: VolumeSource, ingredient: str) -> bool:
    names = [source.ingredient, *source.aliases]
    wanted = set(normalize(ingredient).split())
    if not wanted:
        return False
    for name in names:
        tokens = set(normalize(name).split())
        if tokens and (tokens == wanted or tokens <= wanted):
            return True
    return False


def _state_overlap(source_state: str, wanted_state: str) -> int:
    left = set(normalize(source_state).split())
    right = set(normalize(wanted_state).split())
    return len(left & right)


def rank_sources(
    sources: Sequence[VolumeSource],
    ingredient: str,
    state: str | None = None,
    brand: str | None = None,
) -> list[VolumeSource]:
    """Order the matching sources best-first for one ingredient.

    A source whose preparation state conflicts with the one the card needs
    is ranked last, whatever tier it sits in: a chart for kosher salt is
    never a better answer for table salt than the record that matches it.
    """
    matches = [s for s in sources if _ingredient_matches(s, ingredient)]
    matches.sort(
        key=lambda s: (
            1 if _state_conflict(s.state, state or "") else 0,
            TIER_ORDER.index(s.tier) if s.tier in TIER_ORDER else len(TIER_ORDER),
            0 if (brand and s.brand and normalize(s.brand) == normalize(brand)) else 1,
            -_state_overlap(s.state, state or ""),
        )
    )
    return matches


def _reject_reason(source: VolumeSource, state: str | None, brand: str | None) -> str | None:
    """Why this source may not be used for this ingredient, or None."""
    if source.measure != "total_mass":
        return (
            f"the source measures {source.measure}, not the ingredient's total weight"
        )
    if source.unit_convention not in UNIT_ML:
        return "the source does not state a unit convention"
    if source.unit not in UNIT_ML[source.unit_convention]:
        return f"the source's unit {source.unit!r} is not a known measure"
    if source.grams <= 0 or source.amount <= 0:
        return "the source states no usable mass"
    wanted = state or ""
    if _state_conflict(source.state, wanted):
        return (
            f"the source covers {source.state!r} and the card needs {wanted!r}; "
            "these are different products and one is not converted into the other"
        )
    if brand and source.brand and normalize(source.brand) != normalize(brand):
        return f"the source is for {source.brand!r}, not {brand!r}"
    return None


# ------------------------------------------------------------------ derivation


def round_measure(value: float) -> float:
    """Round a derived measure for the kitchen, and say how.

    A large measure keeps one decimal, a mid-sized one keeps two, a small
    one keeps one, and a very small one keeps two so a quarter-teaspoon is
    not rounded away to nothing.
    """
    if value >= 10:
        return round(value, 1)
    if value >= 2:
        return round(value, 2)
    if value >= 1:
        return round(value, 1)
    return round(value, 2)


def _display_unit(grams: float, source: VolumeSource) -> tuple[float, str, str]:
    """The unit the measure is published in, and the value in it.

    The measure is published in the largest unit of the source's own
    convention that holds at least one whole unit, so a small amount stays
    small and a large one does not become an unreadable number of spoons.
    """
    convention = source.unit_convention
    millilitres = UNIT_ML[convention]
    volume_ml = grams / source.grams_per_ml

    options = [
        ("cup", volume_ml / millilitres["cup"]),
        ("tbsp", volume_ml / millilitres["tbsp"]),
        ("tsp", volume_ml / millilitres["tsp"]),
    ]
    for unit, value in options:
        if value >= 1.0:
            return round_measure(value), unit, convention
    return round_measure(volume_ml / millilitres["tsp"]), "tsp", convention


def derive_volume(grams: float, source: VolumeSource) -> tuple[str, float, str, str]:
    """The approximate household measure for ``grams``.

    Returns ``(text, amount, unit, convention)``. The text carries the
    approximate marker and names the convention, so no reader can mistake a
    derived measure for a measured spoonful.
    """
    amount, unit, convention = _display_unit(float(grams), source)
    label = CONVENTION_LABELS.get(convention, convention)
    return f"≈ {amount:g} {unit} ({label})", amount, unit, convention


# ------------------------------------------------------------------- research


def research_volume(
    ingredient: str,
    grams: float | None,
    *,
    state: str | None = None,
    brand: str | None = None,
    sources: Sequence[VolumeSource] | None = None,
    cache: SourceCache | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    supplied_quantity: bool = False,
) -> VolumeResult:
    """Research the household measure for one ingredient.

    ``supplied_quantity`` marks an ingredient the cook gave in a volume or
    count unit: its measure is the cook's, so no research is needed and none
    is claimed. An ingredient with no authoritative grams has nothing to
    convert, which is stated rather than guessed.
    """
    if supplied_quantity:
        return VolumeResult(status="not_applicable", attempts=[])

    if grams is None or grams <= 0:
        return VolumeResult(
            status="unresolved",
            unresolved_reason=(
                "no authoritative mass is known for this ingredient, so no "
                "gram-to-volume conversion is possible"
            ),
            attempts=[],
        )

    # A reference already checked for this ingredient, state and brand is
    # reused instead of researched again.
    if cache is not None:
        cached = cache.get(ingredient, state, brand)
        if cached:
            source = cache.source_from_record(cached)
            reason = _reject_reason(source, state, brand)
            if reason is None:
                text, amount, unit, convention = derive_volume(float(grams), source)
                return VolumeResult(
                    status="derived",
                    volume=text,
                    amount=amount,
                    unit=unit,
                    unit_convention=convention,
                    grams_per_unit=float(grams) / amount if amount else None,
                    provenance=source.provenance(),
                    attempts=[
                        {
                            "source_title": source.title,
                            "source_url": source.url,
                            "tier": source.tier,
                            "outcome": "accepted",
                            "reason": "reused from the source cache",
                        }
                    ],
                )

    catalogue = list(sources) if sources is not None else load_sources()
    candidates = rank_sources(catalogue, ingredient, state, brand)

    attempts: list[dict[str, Any]] = []
    accepted: VolumeSource | None = None
    for source in candidates[: max(1, max_attempts)]:
        reason = _reject_reason(source, state, brand)
        attempts.append(
            {
                "source_title": source.title,
                "source_url": source.url,
                "tier": source.tier,
                "outcome": "rejected" if reason else "accepted",
                "reason": reason,
            }
        )
        if reason is None:
            # The first accepted source is the highest-ranked one that
            # matched. A later source never replaces it.
            accepted = source
            break

    if accepted is None:
        seen = len(attempts)
        reason = (
            "no ingredient-specific gram-to-volume source matched this "
            f"ingredient and state after {seen} targeted "
            f"source{'s' if seen != 1 else ''}"
        )
        if state:
            reason += f" (state sought: {state})"
        rejected_because = [
            str(attempt["reason"]) for attempt in attempts if attempt.get("reason")
        ]
        if rejected_because:
            reason += ": " + "; ".join(rejected_because)
        return VolumeResult(status="unresolved", unresolved_reason=reason, attempts=attempts)

    # Two credible sources that agree on the ingredient and the preparation
    # state but disagree materially on density are a conflict the cook
    # settles: neither figure is published. Every rival is validated before
    # its density is touched, so a source with no usable convention is
    # rejected with a reason instead of raising on grams_per_ml. A later
    # source never replaces the accepted one.
    for rival in candidates:
        if rival is accepted:
            continue
        reason = _reject_reason(rival, state, brand)
        if reason is not None:
            attempts.append(
                {
                    "source_title": rival.title,
                    "source_url": rival.url,
                    "tier": rival.tier,
                    "outcome": "rejected",
                    "reason": reason,
                }
            )
            continue
        rival_overlap = _state_overlap(rival.state, state or "")
        accepted_overlap = _state_overlap(accepted.state, state or "")
        if rival_overlap == 0 or accepted_overlap == 0:
            # The rival does not bear the state the card asked for, so it is
            # not a same-state candidate and cannot open a density conflict.
            continue
        low, high = sorted((accepted.grams_per_ml, rival.grams_per_ml))
        if high / low > CONFLICT_RATIO:
            attempts.append(
                {
                    "source_title": rival.title,
                    "source_url": rival.url,
                    "tier": rival.tier,
                    "outcome": "rejected",
                    "reason": (
                        "disagrees materially with the accepted source on "
                        f"density ({accepted.original_ratio} against "
                        f"{rival.original_ratio})"
                    ),
                }
            )
            return VolumeResult(
                status="unresolved",
                unresolved_reason=(
                    "two sources disagree materially on this ingredient "
                    f"({accepted.original_ratio} against {rival.original_ratio}); "
                    "the cook settles which product and state applies"
                ),
                attempts=attempts,
            )

    text, amount, unit, convention = derive_volume(float(grams), accepted)
    provenance = accepted.provenance()
    provenance["source_state"] = accepted.state
    if cache is not None:
        cache.put(
            ingredient,
            state,
            brand,
            {
                "ingredient": accepted.ingredient,
                "aliases": list(accepted.aliases),
                "state": accepted.state,
                "brand": accepted.brand,
                "tier": accepted.tier,
                "url": accepted.url,
                "title": accepted.title,
                "accessed": accepted.accessed,
                "original_ratio": accepted.original_ratio,
                "amount": accepted.amount,
                "unit": accepted.unit,
                "unit_convention": accepted.unit_convention,
                "grams": accepted.grams,
                "state_match": accepted.state_match,
                "proxy": accepted.proxy,
                "confidence": accepted.confidence,
                "measure": accepted.measure,
            },
        )
        cache.save()
    return VolumeResult(
        status="derived",
        volume=text,
        amount=amount,
        unit=unit,
        unit_convention=convention,
        grams_per_unit=float(grams) / amount if amount else None,
        provenance=provenance,
        attempts=attempts,
    )


# --------------------------------------------------------------- application


def _row_state(row: dict[str, Any]) -> str:
    """The preparation state a row states, from its name and its notes."""
    parts = [str(row.get("name", ""))]
    haystack = f"{row.get('name', '')} {row.get('notes') or ''}".lower()
    for phrase in (
        "raw",
        "cooked",
        "drained",
        "shell-on",
        "kosher salt",
        "table salt",
        "sea salt",
        "roasted",
        "toasted",
        "dried",
    ):
        if phrase in haystack:
            parts.append(phrase)
    return " ".join(parts)


def _has_supplied_quantity(row: dict[str, Any]) -> bool:
    quantity = row.get("quantity")
    return isinstance(quantity, dict) and quantity.get("amount") is not None


def apply_research(
    data: dict[str, Any],
    *,
    sources: Sequence[VolumeSource] | None = None,
    cache: SourceCache | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Research every ingredient that needs a measure and update the card.

    The card is updated in place and the structured research records are
    returned. An ingredient that already carries a measure keeps it: a
    measured volume outranks a derived one.
    """
    records: list[dict[str, Any]] = []
    catalogue = list(sources) if sources is not None else load_sources()
    # Resolve every row's mass once before any volume lookup: a stated
    # weight_g wins, a formula is worked out from its base row, and a row
    # with neither stays None so research reports it honestly instead of
    # guessing a zero. card_model is imported here because it imports this
    # module at its own top.
    from card_model import Card  # noqa: PLC0415

    resolved = Card(data).resolved_weights()

    for component in data.get("components", []) or []:
        for row in component.get("ingredients", []) or []:
            row_id = str(row.get("row_id", ""))
            if str(row.get("volume") or "").strip():
                continue
            result = research_volume(
                str(row.get("name", "")),
                resolved.get(row_id),
                state=_row_state(row),
                brand=None,
                sources=catalogue,
                cache=cache,
                max_attempts=max_attempts,
                supplied_quantity=_has_supplied_quantity(row),
            )
            record = result.record(row_id)
            records.append(record)
            # The row's own record does not repeat the row id; the record
            # list keeps it so a caller can match one back to its row.
            row_record = {k: v for k, v in record.items() if k != "row_id"}
            row["volume_source"] = row_record
            if result.status == "derived" and result.volume:
                row["volume"] = result.volume
                row["notes"] = _append_note(row.get("notes"), _provenance_line(result))
            elif result.status == "unresolved":
                row["notes"] = _append_note(
                    row.get("notes"),
                    f"Volume researched; unresolved: {result.unresolved_reason}.",
                )

    return data, records


def _provenance_line(result: VolumeResult) -> str:
    provenance = result.provenance
    status = "labeled proxy" if provenance.get("proxy") else "exact match"
    return (
        f"Volume is a {status}; source: {provenance.get('source_title')}, "
        f"{provenance.get('original_ratio')}, {provenance.get('unit_convention')} "
        f"measures, accessed {provenance.get('accessed')}, "
        f"{provenance.get('source_url')}. Weight authoritative."
    )


def _append_note(existing: Any, text: str) -> str:
    current = str(existing or "").strip()
    if not current:
        return text
    return f"{current} {text}"


__all__ = [
    "CACHE_ENV",
    "DEFAULT_CACHE",
    "DEFAULT_MAX_ATTEMPTS",
    "MASS_TO_GRAM",
    "SOURCES_PATH",
    "TIER_ORDER",
    "UNIT_ML",
    "SourceCache",
    "VolumeResult",
    "VolumeSource",
    "apply_research",
    "cache_key",
    "derive_volume",
    "load_sources",
    "normalize",
    "rank_sources",
    "research_volume",
    "round_measure",
    "to_grams",
]

"""Recipe card data model, validation and arithmetic.

This module is the executable form of ``references/schema.md`` and
``references/validation.md``. It loads one card document, checks it against
``references/card.schema.json`` and recomputes every derived number the card
claims (reference percentages, input total, loss, portions).

Nothing here invents kitchen facts. A card that carries an unsupported number
is reported as a finding, not silently corrected, because a wrong weight in a
recipe card is a production defect.

Public API:

    load_card(path)      -> Card
    Card.schema_errors() -> list[str]
    Card.findings()      -> list[Finding]
    Card.derived()       -> Derived
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from volume_research import CONVENTION_LABELS, round_measure as _round_measure
from locales import DEFAULT_LANGUAGE as _LOCALE_DEFAULT, localize_decimals, translate

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "references" / "card.schema.json"

# Tolerance for float comparison of grams. 0.01 g is below any kitchen scale
# resolution we support, so a mismatch this small is noise, not an error.
GRAM_EPSILON = 0.01

# Statuses that may not be used in the kitchen.
UNRELEASED_STATUSES = ("R&D", "NEEDS CHEF CONFIRMATION")

RELEASE_WARNING = "NOT RELEASED FOR PRODUCTION"

# The processes that ``references/schema.md`` defines. Every one
# of them is answered on every card: the applicable ones carry their
# controlled parameters, the rest state N/A with the reason.
PROCESS_CONTROL_KEYS = (
    "sous_vide",
    "combi",
    "fermentation",
    "pickling",
    "reduction",
    "emulsification",
    "chilling",
    "smoking",
)

# The label content required when a card states how the product is held.
LABELING_KEYS = (
    "product_name",
    "batch_or_date_code",
    "use_by_basis",
    "storage_instruction",
    "allergen_declaration",
    "preparer_or_station",
)

# Phrases that mark a value as deliberately not applicable.
_NA_PREFIXES = ("n/a", "na -", "not applicable")

# Readable labels for the eight process controls. The reading editions show
# these instead of machine-style keys, so a cook reads "Sous vide" rather
# than "SOUS VIDE".
PROCESS_CONTROL_LABELS = {
    "sous_vide": "Sous vide",
    "combi": "Combi oven",
    "fermentation": "Fermentation",
    "pickling": "Pickling",
    "reduction": "Reduction",
    "emulsification": "Emulsification",
    "chilling": "Chilling",
    "smoking": "Smoking",
}


def declares_not_applicable(value: Any) -> bool:
    """True when a control states that the process does not apply.

    The wording is the one the validator already accepts, so the reading
    editions and the validator never disagree about what "not applicable"
    means.
    """
    return str(value or "").strip().lower().startswith(_NA_PREFIXES)


def na_reason(value: Any) -> str:
    """The reason a not-applicable control gives, or "" when it gives none.

    A control that declares N/A without a reason is a validation failure,
    not a statement that the process is unused, so it returns no reason.
    """
    text = str(value or "").strip()
    if not text.lower().startswith(_NA_PREFIXES):
        return ""
    match = re.fullmatch(r"(?:n/a|na|not applicable)\s*[-–—]\s*(.+)", text, re.IGNORECASE)
    if match is None:
        return ""
    reason = match.group(1).strip()
    return reason if any(character.isalnum() for character in reason) else ""


def applicable_process_controls(controls: dict[str, str]) -> list[tuple[str, str]]:
    """Return the ``(label, value)`` pairs that a reading edition shows.

    A control that explicitly declares the process not applicable, with the
    reason it does not apply, is left out: the reader only sees the
    processes the cook actually performs. The card record keeps every key,
    its reason and the validator's verdict, so nothing is lost.

    A control that is applicable, unresolved or safety-critical is always
    kept. A control that says N/A without a reason is kept too, because the
    validator rejects that card and the reader must see the gap.
    """
    out: list[tuple[str, str]] = []
    for key in PROCESS_CONTROL_KEYS:
        value = str(controls.get(key, "") or "").strip()
        if not value:
            continue
        if declares_not_applicable(value) and na_reason(value):
            continue
        label = PROCESS_CONTROL_LABELS.get(key, key.replace("_", " ").capitalize())
        out.append((label, value))
    return out

# A household or metric measure must name its unit. A bare number in the
# Volume column is ambiguous: grams per tablespoon is not the same density as
# grams per cup, and the reader cannot tell which one was meant.
_VOLUME_UNIT_RE = re.compile(
    r"\b(cups?|tbsps?|tablespoons?|tsps?|teaspoons?|milliliters?|millilitres?|"
    r"ml|ounces?|grams?|g|kg|l|dash(es)?|pinch(es)?|pieces?)\b|fl\.?\s*oz",
    re.IGNORECASE,
)

# The source status a row must state when it publishes a derived volume:
# the figure is either an exact match or a labeled generic proxy.
_SOURCE_STATUS_RE = re.compile(
    r"\b(exact match|labeled proxy|labelled proxy|generic proxy|proxy)\b",
    re.IGNORECASE,
)

# A source record in the notes: a source title, a URL, or an access date.
_SOURCE_RECORD_RE = re.compile(
    r"(https?://|source\s+\d|accessed\s+\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)


class CardError(ValueError):
    """The card document cannot be read as a card at all."""


@dataclass(frozen=True)
class Finding:
    """One validation finding.

    ``severity`` is ``blocker`` when the card cannot be delivered, ``warning``
    when it can be delivered but a human must look at it, and ``note`` when it
    is informational.
    """

    code: str
    message: str
    severity: str = "blocker"
    path: str = ""

    def __str__(self) -> str:  # pragma: no cover - convenience only
        where = f" [{self.path}]" if self.path else ""
        return f"{self.severity.upper()}: {self.code}{where} — {self.message}"


@dataclass
class Derived:
    """Numbers recomputed from the card's own ingredient weights."""

    percentages: dict[str, float] = field(default_factory=dict)
    component_percentages: dict[str, dict[str, float]] = field(default_factory=dict)
    component_totals: dict[str, float] = field(default_factory=dict)
    input_total_g: float = 0.0
    input_complete: bool = True
    input_structure_complete: bool = True
    declared_input_total_g: float | None = None
    loss_g: float | None = None
    portions: int | None = None
    portion_remainder_g: float | None = None

    @property
    def known_input_subtotal_g(self) -> float:
        """Established mass only; never a full total unless input_complete.

        input_total_g remains a legacy arithmetic accumulator for callers.
        Canonical card input_total_g must be null when any mass is unknown.
        """
        return self.input_total_g

    @property
    def input_total_known_g(self) -> float | None:
        """The one input total every edition shows, or None when unknown.

        The declared ``input_total_g`` is the cook's statement about the
        batch; the card's own ingredient masses are the arithmetic behind
        that statement. When every mass is established the two must agree,
        and the ``input-total-mismatch`` blocker says so when they do not.
        One rule covers every edition:

        * a mass is unresolved -> the total is unknown, and every edition
          says unknown. The known subtotal stays labeled separately.
        * every mass is established and a total is declared -> the declared
          total is the total.
        * every mass is established and no total is declared -> the sum of
          the established masses is the total, because that is the only
          number the card holds.
        """
        if not self.input_complete:
            return None
        if self.declared_input_total_g is not None:
            return self.declared_input_total_g
        return self.input_total_g


def _jsonschema():
    """Return the jsonschema module, or None when it is not installed."""
    try:
        import jsonschema  # type: ignore

        return jsonschema
    except Exception:  # pragma: no cover - environment dependent
        return None


class Card:
    """A loaded recipe card document."""

    def __init__(self, data: dict[str, Any], source: Path | None = None):
        if not isinstance(data, dict):
            raise CardError("card document must be a JSON object")
        self.data = data
        self.source = source

    # ---------------------------------------------------------------- loading

    @classmethod
    def from_dict(cls, data: dict[str, Any], source: Path | None = None) -> "Card":
        return cls(data, source)

    @classmethod
    def load(cls, path: str | Path) -> "Card":
        p = Path(path)
        try:
            raw = p.read_text(encoding="utf-8")
        except OSError as exc:
            raise CardError(f"cannot read card file {p}: {exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CardError(f"card file {p} is not valid JSON: {exc}") from exc
        return cls(data, p)

    # ------------------------------------------------------------- accessors

    @property
    def recipe_id(self) -> str:
        return str(self.data.get("recipe_id", ""))

    @property
    def title(self) -> str:
        return str(self.data.get("title", ""))

    @property
    def version(self) -> str:
        return str(self.data.get("version", ""))

    @property
    def revision_date(self) -> str:
        return str(self.data.get("revision_date", ""))

    @property
    def language(self) -> str:
        """The cook's language for the reading editions, or ``""`` unset.

        Stored on the card record so the choice persists across components
        and assembly; resolved at build time with ``locales.resolve_language``
        (CLI flag wins, then this field, then the host environment, then
        English).
        """
        return str(self.data.get("language", ""))

    @property
    def status(self) -> str:
        return str(self.data.get("status", ""))

    @property
    def is_production(self) -> bool:
        return self.status == "PRODUCTION"

    @property
    def components(self) -> list[dict[str, Any]]:
        comps = self.data.get("components")
        return comps if isinstance(comps, list) else []

    @property
    def ingredients(self) -> list[dict[str, Any]]:
        """Every ingredient row across all components, in document order.

        A component that links to another card's component carries no rows
        of its own, so it contributes nothing here and its mass is never
        counted twice.
        """
        rows: list[dict[str, Any]] = []
        for comp in self.components:
            for ing in comp.get("ingredients", []) or []:
                rows.append(ing)
        return rows

    @property
    def linked_components(self) -> list[dict[str, Any]]:
        """The components this card uses but does not restate."""
        return [
            comp
            for comp in self.components
            if isinstance(comp.get("linked"), dict)
        ]

    # ---------------------------------------------------------- mass resolution

    def resolved_weights(self) -> dict[str, float | None]:
        """The gram mass of every row, or None when it is not established.

        A row's mass comes from its own ``weight_g`` when the cook stated
        one, and from its ``formula`` when the card states the mass as a
        percentage or a multiple of another row. A row with neither keeps
        ``None``: an unknown mass is never replaced by a guessed one, and a
        quantity supplied in the cook's own unit stays that quantity.
        """
        rows = self.ingredients
        by_id = {str(ing.get("row_id", "")): ing for ing in rows}
        resolved: dict[str, float | None] = {}

        def resolve(row_id: str, seen: frozenset[str]) -> float | None:
            if row_id in resolved:
                return resolved[row_id]
            row = by_id.get(row_id)
            if row is None or row_id in seen:
                return None
            weight = row.get("weight_g")
            if isinstance(weight, (int, float)):
                resolved[row_id] = float(weight)
                return resolved[row_id]
            formula = row.get("formula")
            if isinstance(formula, dict):
                basis_id = str(formula.get("basis_row_id", ""))
                basis = resolve(basis_id, seen | {row_id})
                value = formula.get("value")
                if basis is not None and isinstance(value, (int, float)):
                    kind = str(formula.get("kind", ""))
                    if kind == "percent":
                        resolved[row_id] = float(basis) * float(value) / 100.0
                    elif kind == "gram_multiple":
                        resolved[row_id] = float(basis) * float(value)
                    else:
                        resolved[row_id] = None
                    return resolved[row_id]
            resolved[row_id] = None
            return None

        for row in rows:
            resolve(str(row.get("row_id", "")), frozenset())
        return resolved

    def unresolved_rows(self) -> list[dict[str, Any]]:
        """Rows whose gram mass is not established."""
        resolved = self.resolved_weights()
        out: list[dict[str, Any]] = []
        for ing in self.ingredients:
            row_id = str(ing.get("row_id", ""))
            if resolved.get(row_id) is None:
                out.append(ing)
        return out

    @property
    def stages(self) -> list[dict[str, Any]]:
        stages = self.data.get("stages")
        return stages if isinstance(stages, list) else []

    @property
    def steps(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for stage in self.stages:
            for step in stage.get("steps", []) or []:
                out.append(step)
        return out

    @property
    def release_blockers(self) -> list[str]:
        blockers = self.data.get("release_blockers")
        return [str(b) for b in blockers] if isinstance(blockers, list) else []

    @property
    def process_controls(self) -> dict[str, str]:
        controls = self.data.get("process_controls")
        return controls if isinstance(controls, dict) else {}

    @property
    def labeling(self) -> dict[str, str]:
        labeling = self.data.get("labeling")
        return labeling if isinstance(labeling, dict) else {}

    @property
    def filename_stem(self) -> str:
        """Versioned filename stem shared by the master, PDF and XLSX."""
        slug = _slugify(self.title)
        return f"{self.recipe_id}__{slug}__{self.version}__{self.revision_date}"

    def ingredient(self, row_id: str) -> dict[str, Any] | None:
        for ing in self.ingredients:
            if str(ing.get("row_id")) == row_id:
                return ing
        return None

    # ------------------------------------------------------------ validation

    def schema_errors(self) -> list[str]:
        """Return schema violations. Empty list means the shape is valid."""
        jsonschema = _jsonschema()
        if jsonschema is None:
            return ["jsonschema is not installed; schema validation could not run"]
        try:
            schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return [f"cannot read card schema at {SCHEMA_PATH}: {exc}"]

        validator = jsonschema.Draft202012Validator(schema)
        errors = []
        for err in sorted(validator.iter_errors(self.data), key=lambda e: list(e.path)):
            where = "/".join(str(p) for p in err.path) or "<root>"
            errors.append(f"{where}: {err.message}")
        return errors

    def findings(self) -> list[Finding]:
        """Return semantic findings: arithmetic, references, release gating."""
        out: list[Finding] = []

        for message in self.schema_errors():
            out.append(Finding(code="schema", message=message, severity="blocker"))

        out.extend(self._check_row_ids())
        out.extend(self._check_component_references())
        out.extend(self._check_input_total())
        out.extend(self._check_purchase_and_edible_mass())
        out.extend(self._check_formulas())
        out.extend(self._check_linked_components())
        out.extend(self._check_yield_and_portions())
        out.extend(self._check_step_numbering())
        out.extend(self._check_ingredient_coverage())
        out.extend(self._check_release_gating())
        out.extend(self._check_unverified_volumes())
        out.extend(self._check_ingredient_notes_convention())
        out.extend(self._check_volume_research_evidence())
        out.extend(self._check_process_controls())
        out.extend(self._check_labeling())
        return out

    def _check_row_ids(self) -> list[Finding]:
        out: list[Finding] = []
        seen: dict[str, str] = {}
        for comp in self.components:
            for ing in comp.get("ingredients", []) or []:
                row_id = str(ing.get("row_id", ""))
                if not row_id:
                    out.append(
                        Finding(
                            "row-id-missing",
                            "an ingredient row has no row_id; procedure references cannot be resolved",
                            path=self._ing_path(comp, ing),
                        )
                    )
                    continue
                if row_id in seen:
                    out.append(
                        Finding(
                            "row-id-duplicate",
                            f"row_id {row_id} is used more than once",
                            path=self._ing_path(comp, ing),
                        )
                    )
                seen[row_id] = self._ing_path(comp, ing)
        return out

    def _check_component_references(self) -> list[Finding]:
        out: list[Finding] = []
        resolved = self.resolved_weights()
        for comp in self.components:
            name = str(comp.get("name", ""))
            if isinstance(comp.get("linked"), dict):
                # A linked component carries no rows of its own, so it has no
                # reference row to name and no mass to check twice.
                continue
            ref_id = str(comp.get("reference_row_id", ""))
            ref_weight = comp.get("reference_weight_g")
            ings = comp.get("ingredients", []) or []

            match = next((i for i in ings if str(i.get("row_id")) == ref_id), None)
            if match is None:
                out.append(
                    Finding(
                        "reference-row-missing",
                        f"component {name!r} names reference row {ref_id!r}, which is not one of its ingredients",
                        path=self._comp_path(comp),
                    )
                )
                continue

            row_weight = resolved.get(ref_id)
            if isinstance(ref_weight, (int, float)) and isinstance(row_weight, (int, float)):
                if not math.isclose(float(ref_weight), float(row_weight), abs_tol=GRAM_EPSILON):
                    out.append(
                        Finding(
                            "reference-weight-mismatch",
                            f"component {name!r} declares reference weight {ref_weight} g but row {ref_id} weighs {row_weight} g",
                            path=self._comp_path(comp),
                        )
                    )
        return out

    def _check_input_total(self) -> list[Finding]:
        out: list[Finding] = []
        derived = self.derived()
        total = derived.known_input_subtotal_g

        declared = self.data.get("input_total_g")
        if declared is not None and not derived.input_complete:
            out.append(Finding(
                "input-total-incomplete",
                "input_total_g must be null while any ingredient mass is unresolved; "
                f"known mass subtotal is {total:g} g, not a complete input total",
                path="input_total_g",
            ))
        if isinstance(declared, (int, float)):
            if not math.isclose(float(declared), total, abs_tol=GRAM_EPSILON):
                out.append(
                    Finding(
                        "input-total-mismatch",
                        f"declared input_total_g {declared} g does not equal the sum of ingredient weights {total:g} g",
                        path="input_total_g",
                    )
                )
        return out

    def _check_purchase_and_edible_mass(self) -> list[Finding]:
        """The as-purchased mass, the edible mass and the input sum are
        three different numbers, and each one is checked against the card.

        A component may state the gross mass it was bought as. That mass is
        never the edible mass that enters the formula, and the input sum is
        never the gross purchase.
        """
        out: list[Finding] = []
        resolved = self.resolved_weights()
        for comp in self.components:
            name = str(comp.get("name", ""))
            gross = comp.get("gross_purchase_g")
            if not isinstance(gross, (int, float)):
                continue
            edible = 0.0
            for ing in comp.get("ingredients", []) or []:
                weight = resolved.get(str(ing.get("row_id", "")))
                if isinstance(weight, (int, float)):
                    edible += float(weight)
            if edible > float(gross) + GRAM_EPSILON:
                out.append(
                    Finding(
                        "edible-exceeds-purchase",
                        f"component {name!r} states a gross purchase of {gross} g but its "
                        f"edible masses add to {edible:g} g, which cannot be trimmed out of "
                        "a smaller purchase",
                        path=self._comp_path(comp),
                    )
                )
        return out

    def _check_formulas(self) -> list[Finding]:
        """A formula states a mass against another row, and it must resolve."""
        out: list[Finding] = []
        known = {str(ing.get("row_id", "")) for ing in self.ingredients}
        resolved = self.resolved_weights()
        for comp in self.components:
            for ing in comp.get("ingredients", []) or []:
                formula = ing.get("formula")
                if not isinstance(formula, dict):
                    continue
                row_id = str(ing.get("row_id", ""))
                basis_id = str(formula.get("basis_row_id", ""))
                if basis_id not in known:
                    out.append(
                        Finding(
                            "formula-basis-missing",
                            f"row {row_id!r} states its mass as a formula against row "
                            f"{basis_id!r}, which is not in the ingredient table",
                            path=self._ing_path(comp, ing),
                        )
                    )
                    continue
                if resolved.get(row_id) is None:
                    out.append(
                        Finding(
                            "formula-unresolved",
                            f"row {row_id!r} states its mass as a formula against row "
                            f"{basis_id!r}, whose mass is not established, so this row's "
                            "mass is unknown",
                            path=self._ing_path(comp, ing),
                        )
                    )
        return out

    def _check_linked_components(self) -> list[Finding]:
        """A linked component names the exact version it uses, and its mass
        is counted once."""
        out: list[Finding] = []
        seen: set[tuple[str, str]] = set()
        for comp in self.linked_components:
            link = comp.get("linked") or {}
            component_id = str(link.get("component_id", ""))
            version = str(link.get("version", ""))
            name = str(comp.get("name", ""))
            if not version.strip():
                out.append(
                    Finding(
                        "linked-version-missing",
                        f"component {name!r} links to {component_id!r} without an exact "
                        "version; a shared component is used at one known version",
                        path=self._comp_path(comp),
                    )
                )
            key = (component_id, version)
            if key in seen:
                out.append(
                    Finding(
                        "linked-component-duplicated",
                        f"component {name!r} links to {component_id!r} {version!r}, which is "
                        "already linked on this card; the shared component is counted twice",
                        path=self._comp_path(comp),
                    )
                )
            seen.add(key)
            if comp.get("ingredients"):
                out.append(
                    Finding(
                        "linked-component-restated",
                        f"component {name!r} both links to {component_id!r} and restates "
                        "ingredients; the formula is written once, in one place",
                        path=self._comp_path(comp),
                    )
                )
        return out

    def _check_yield_and_portions(self) -> list[Finding]:
        out: list[Finding] = []
        usable = self.data.get("usable_yield_g")
        declared_loss = self.data.get("loss_g")
        portion = self.data.get("portion_g")
        declared_portions = self.data.get("portions")
        declared_total = self.data.get("input_total_g")
        if isinstance(declared_total, (int, float)) and not isinstance(declared_total, bool):
            # A card that states a total is checked against that total, even
            # when a mass is unresolved and the card is blocked for it.
            input_total: float | None = float(declared_total)
        else:
            # A card that states no total is checked against the sum of the
            # established masses: that is the total its editions show.
            input_total = self.derived().input_total_known_g

        if isinstance(usable, (int, float)) and input_total is not None:
            computed_loss = input_total - float(usable)
            if computed_loss < -GRAM_EPSILON:
                out.append(
                    Finding(
                        "yield-exceeds-input",
                        f"usable_yield_g {usable} g exceeds the input total {input_total} g",
                        path="usable_yield_g",
                    )
                )
            if isinstance(declared_loss, (int, float)) and not math.isclose(
                float(declared_loss), computed_loss, abs_tol=GRAM_EPSILON
            ):
                out.append(
                    Finding(
                        "loss-mismatch",
                        f"declared loss_g {declared_loss} g does not equal input minus usable output {computed_loss:g} g",
                        path="loss_g",
                    )
                )

        if isinstance(usable, (int, float)) and isinstance(portion, (int, float)):
            computed_portions = int(math.floor(float(usable) / float(portion)))
            remainder = float(usable) - computed_portions * float(portion)
            if isinstance(declared_portions, int) and declared_portions != computed_portions:
                out.append(
                    Finding(
                        "portions-mismatch",
                        f"declared portions {declared_portions} does not equal floor(usable yield / portion size) = {computed_portions}",
                        path="portions",
                    )
                )
        return out

    def _check_step_numbering(self) -> list[Finding]:
        out: list[Finding] = []
        expected = 1
        for stage in self.stages:
            for step in stage.get("steps", []) or []:
                number = step.get("number")
                if number != expected:
                    out.append(
                        Finding(
                            "step-numbering",
                            f"step numbers must continue across stages; expected {expected}, found {number!r}",
                            path="stages",
                        )
                    )
                expected = (number if isinstance(number, int) else expected) + 1
        return out

    def _check_ingredient_coverage(self) -> list[Finding]:
        out: list[Finding] = []
        referenced: set[str] = set()
        for step in self.steps:
            for ref in step.get("ingredient_refs", []) or []:
                referenced.add(str(ref))

        known = {str(i.get("row_id")) for i in self.ingredients}
        for ref in sorted(referenced - known):
            out.append(
                Finding(
                    "unknown-ingredient-ref",
                    f"a step references row {ref!r}, which is not in the ingredient table",
                    path="stages",
                )
            )

        for ing in self.ingredients:
            row_id = str(ing.get("row_id", ""))
            if row_id and row_id not in referenced:
                out.append(
                    Finding(
                        "ingredient-unused",
                        f"ingredient {row_id!r} never appears in a step",
                        severity="warning",
                        path="components",
                    )
                )
        return out

    def _check_release_gating(self) -> list[Finding]:
        out: list[Finding] = []
        blockers = self.release_blockers
        if not self.is_production:
            if not blockers:
                out.append(
                    Finding(
                        "release-blockers-missing",
                        f"status {self.status!r} is not PRODUCTION, so at least one release blocker must be recorded",
                        path="release_blockers",
                    )
                )
            if not self.data.get("release_checklist"):
                out.append(
                    Finding(
                        "release-checklist-missing",
                        "an unreleased card must list what is required before production release",
                        severity="warning",
                        path="release_checklist",
                    )
                )
        else:
            if blockers:
                out.append(
                    Finding(
                        "production-with-blockers",
                        "a PRODUCTION card cannot still carry release blockers",
                        path="release_blockers",
                    )
                )
            provenance = self.data.get("provenance") or {}
            if not provenance.get("validation"):
                out.append(
                    Finding(
                        "production-without-validation",
                        "a PRODUCTION card must record its test and approval evidence",
                        path="provenance",
                    )
                )
        return out

    def _check_unverified_volumes(self) -> list[Finding]:
        out: list[Finding] = []
        for ing in self.ingredients:
            volume = ing.get("volume")
            if volume is None:
                continue
            text = str(volume).strip()
            if not text:
                out.append(
                    Finding(
                        "empty-volume",
                        f"row {ing.get('row_id')!r} has an empty volume; use null so it renders as an em dash",
                        severity="warning",
                        path="components",
                    )
                )
            elif text in {"?", "?", "n/a", "N/A", "unknown", "Unknown"}:
                out.append(
                    Finding(
                        "placeholder-volume",
                        f"row {ing.get('row_id')!r} uses {text!r} as a volume; leave it null so it renders as an em dash",
                        path="components",
                    )
                )
            elif any(ch.isdigit() for ch in text) and not _VOLUME_UNIT_RE.search(text):
                out.append(
                    Finding(
                        "volume-without-unit",
                        f"row {ing.get('row_id')!r} states a volume without a unit ({text!r}); "
                        "name the measure and its standard, for example 'cup (US)' or 'tbsp (US)'",
                        severity="warning",
                        path="components",
                    )
                )
        return out

    def _check_ingredient_notes_convention(self) -> list[Finding]:
        """The notes string carries what the narrow ingredient row cannot.

        ``references/schema.md`` stores five fields per ingredient row and
        carries every other promised field in the ``notes`` string. A row
        that publishes a derived volume therefore has to say where that
        volume came from and what its status is; a row whose notes carry a
        source record has to publish the volume that record supports. The
        narrow schema stays narrow — this check does not widen it.
        """
        out: list[Finding] = []
        for ing in self.ingredients:
            row_id = ing.get("row_id")
            volume = str(ing.get("volume") or "").strip()
            notes = str(ing.get("notes") or "").strip()
            states_source = bool(_SOURCE_STATUS_RE.search(notes))
            states_provenance = bool(_SOURCE_RECORD_RE.search(notes))

            if volume.startswith("≈") and not states_source:
                out.append(
                    Finding(
                        "unverified-volume",
                        f"row {row_id!r} publishes a derived volume but its notes state no source "
                        "status; the notes must say whether the figure is an exact match or a "
                        "labeled generic proxy",
                        path="components",
                    )
                )
            source = ing.get("volume_source")
            rejected_source = (
                isinstance(source, dict)
                and source.get("status") == "unresolved"
                and bool(str(source.get("unresolved_reason") or "").strip())
            )
            if states_provenance and not volume and not rejected_source:
                out.append(
                    Finding(
                        "volume-source-record-without-volume",
                        f"row {row_id!r} notes carry a source record but the row publishes no "
                        "volume for it",
                        path="components",
                    )
                )
        return out

    def _check_volume_research_evidence(self) -> list[Finding]:
        """A published volume carries its evidence, and a blank volume is
        either researched or honestly explained.

        A row with a known mass and no published volume must show that the
        research was attempted: a source record, a stated unresolved reason,
        or a quantity the cook supplied in their own unit. A row whose mass
        is not established yet may still be missing a volume, but the card
        must say why rather than leave it silently blank.
        """
        out: list[Finding] = []
        resolved = self.resolved_weights()
        for comp in self.components:
            for ing in comp.get("ingredients", []) or []:
                row_id = str(ing.get("row_id", ""))
                volume = str(ing.get("volume") or "").strip()
                source = ing.get("volume_source")
                notes = str(ing.get("notes") or "")
                quantity = ing.get("quantity")

                if volume and not isinstance(source, dict):
                    # The shipped example carries its source record in the
                    # notes string; a card that states a derived volume
                    # still has to say where it came from.
                    if "proxy" not in notes.lower() and "exact match" not in notes.lower():
                        out.append(
                            Finding(
                                "unverified-volume",
                                f"row {row_id!r} publishes a derived volume but records no "
                                "source status; the row must say whether the figure is an "
                                "exact match or a labeled proxy",
                                path=self._ing_path(comp, ing),
                            )
                        )
                    continue

                if isinstance(source, dict):
                    status = str(source.get("status", ""))
                    if status == "unresolved" and not str(
                        source.get("unresolved_reason") or ""
                    ).strip():
                        out.append(
                            Finding(
                                "unresolved-volume-without-reason",
                                f"row {row_id!r} records an unresolved volume without saying "
                                "why; an unresolved volume states its reason",
                                path=self._ing_path(comp, ing),
                            )
                        )
                    if status == "derived" and not volume:
                        out.append(
                            Finding(
                                "volume-source-record-without-volume",
                                f"row {row_id!r} records a source for its volume but "
                                "publishes no volume",
                                path=self._ing_path(comp, ing),
                            )
                        )
                    if status == "derived" and volume:
                        if not str(source.get("source_url") or "").strip() and not str(
                            source.get("original_ratio") or ""
                        ).strip():
                            out.append(
                                Finding(
                                    "volume-source-record-incomplete",
                                    f"row {row_id!r} publishes a derived volume whose source "
                                    "record names neither a URL nor the source's own ratio",
                                    path=self._ing_path(comp, ing),
                                )
                            )
                        convention = source.get("unit_convention")
                        if convention is None:
                            out.append(
                                Finding(
                                    "volume-convention-unstated",
                                    f"row {row_id!r} publishes a derived volume without naming "
                                    "the unit convention; US, metric and Australian measures "
                                    "are not the same",
                                    path=self._ing_path(comp, ing),
                                )
                            )
                    continue

                # No source record at all.
                if isinstance(quantity, dict) and quantity.get("amount") is not None:
                    # The cook supplied the quantity; it stays the cook's.
                    continue
                if resolved.get(row_id) is None:
                    # The mass itself is unknown; the card may say so.
                    if "not supplied" not in notes.lower() and "unknown" not in notes.lower():
                        out.append(
                            Finding(
                                "volume-missing-without-reason",
                                f"row {row_id!r} has no mass and no published volume and does "
                                "not say why; an unresolved quantity states its reason",
                                severity="warning",
                                path=self._ing_path(comp, ing),
                            )
                        )
                    continue
                out.append(
                    Finding(
                        "volume-research-missing",
                        f"row {row_id!r} has a mass but no published volume and no record "
                        "that research was attempted; research it, or record the reason "
                        "it stays unresolved",
                        path=self._ing_path(comp, ing),
                    )
                )
        return out

    def _check_process_controls(self) -> list[Finding]:
        """Every process is answered, and an unused one states why.

        ``references/schema.md`` and ``references/validation.md`` both require
        all eight processes to be
        addressed on every card. A bare "N/A" is not an answer: the reason
        the process does not apply is part of the operational record.
        """
        out: list[Finding] = []
        controls = self.process_controls

        for key in PROCESS_CONTROL_KEYS:
            if key not in controls:
                out.append(
                    Finding(
                        "process-control-missing",
                        f"process control {key!r} is not stated; state its controlled parameters or N/A with the reason",
                        path="process_controls",
                    )
                )
                continue

            value = str(controls.get(key, "")).strip()
            if not value:
                out.append(
                    Finding(
                        "process-control-empty",
                        f"process control {key!r} is empty; state its controlled parameters or N/A with the reason",
                        path="process_controls",
                    )
                )
                continue

            if declares_not_applicable(value) and not na_reason(value):
                out.append(
                    Finding(
                        "process-control-reason-missing",
                        f"process control {key!r} says {value!r} without giving the reason it does not apply",
                        path="process_controls",
                    )
                )
        return out

    def _check_labeling(self) -> list[Finding]:
        """Label content is complete when the card states how the product is held.

        ``references/validation.md`` requires labeling to be covered where the
        item is stored or transferred. A card that names a holding or storage
        rule must therefore carry the label content, and every field of that
        content must be filled.
        """
        out: list[Finding] = []
        labeling = self.labeling
        if not labeling:
            return out

        for key in LABELING_KEYS:
            value = str(labeling.get(key, "")).strip()
            if not value:
                out.append(
                    Finding(
                        "labeling-field-missing",
                        f"label content {key!r} is empty; an unresolved value is NEEDS CHEF CONFIRMATION, not a blank",
                        path="labeling",
                    )
                )
        return out

    # --------------------------------------------------------------- derived

    def derived(self) -> Derived:
        """Recompute percentages, totals, loss and portions from the card."""
        derived = Derived()
        resolved = self.resolved_weights()

        seen_links: set[tuple[str, str]] = set()
        for comp in self.components:
            comp_name = str(comp.get("name", ""))
            link = comp.get("linked")
            if isinstance(link, dict):
                key = (str(link.get("component_id", "")), str(link.get("version", "")))
                if comp.get("ingredients") or key in seen_links:
                    derived.input_complete = False
                    derived.input_structure_complete = False
                if key in seen_links:
                    continue
                seen_links.add(key)
                weight = link.get("quantity_g")
                if isinstance(weight, (int, float)) and not isinstance(weight, bool) and math.isfinite(weight) and weight > 0:
                    derived.component_totals[comp_name] = float(weight)
                    derived.input_total_g += float(weight)
                else:
                    derived.input_complete = False
                continue
            ref_weight = comp.get("reference_weight_g")
            has_reference = isinstance(ref_weight, (int, float)) and ref_weight > 0
            per_component: dict[str, float] = {}
            component_total = 0.0
            for ing in comp.get("ingredients", []) or []:
                row_id = str(ing.get("row_id", ""))
                weight = resolved.get(row_id)
                if not isinstance(weight, (int, float)):
                    derived.input_complete = False
                    continue
                weight = float(weight)
                component_total += weight
                if has_reference:
                    pct = 100.0 * weight / float(ref_weight)
                    per_component[row_id] = pct
                    derived.percentages[row_id] = pct
            derived.component_percentages[comp_name] = per_component
            derived.component_totals[comp_name] = component_total
            derived.input_total_g += component_total

        usable = self.data.get("usable_yield_g")
        portion = self.data.get("portion_g")
        input_total = self.data.get("input_total_g")
        if isinstance(input_total, (int, float)) and not isinstance(input_total, bool):
            derived.declared_input_total_g = float(input_total)

        # The loss follows the one total every edition shows, so a card that
        # states no total still reports the same loss the workbook computes.
        total_known = derived.input_total_known_g
        if (total_known is not None and isinstance(usable, (int, float))
                and not isinstance(usable, bool)):
            derived.loss_g = total_known - float(usable)
        if isinstance(usable, (int, float)) and isinstance(portion, (int, float)):
            derived.portions = int(math.floor(float(usable) / float(portion)))
            derived.portion_remainder_g = float(usable) - derived.portions * float(portion)
        return derived

    def scaled_weights(self, factor: float) -> dict[str, float]:
        """Return scaled ingredient weights for ``factor``.

        Only ingredient quantities scale. Time, temperature, vessel loading
        and release status never scale.

        A row whose mass is a formula scales from its base, so a percentage
        row follows the base it was written against rather than keeping a
        number that no longer matches the batch.
        """
        if not isinstance(factor, (int, float)) or factor <= 0:
            raise ValueError("scale factor must be a positive number")
        resolved = self.resolved_weights()
        return {
            row_id: float(weight) * float(factor)
            for row_id, weight in resolved.items()
            if isinstance(weight, (int, float))
        }

    def scaled_volumes(self, factor: float) -> dict[str, str]:
        """Return the scaled household measure for every derived volume.

        A derived volume comes from the authoritative grams and the source's
        own ratio. When the batch factor changes, the grams change, so the
        measure changes with them: the card never keeps the base measure on
        a scaled batch, and it never re-derives the measure from a density it
        had to guess. A row whose volume was measured, not derived, is not
        scaled here, because a measured spoonful is not a formula.
        """
        if not isinstance(factor, (int, float)) or factor <= 0:
            raise ValueError("scale factor must be a positive number")
        scaled = self.scaled_weights(factor)
        out: dict[str, str] = {}
        for comp in self.components:
            for ing in comp.get("ingredients", []) or []:
                row_id = str(ing.get("row_id", ""))
                source = ing.get("volume_source")
                if not isinstance(source, dict):
                    continue
                if str(source.get("status", "")) != "derived":
                    continue
                grams_per_unit = source.get("grams_per_unit")
                unit = str(source.get("unit") or "")
                convention = str(source.get("unit_convention") or "")
                if not isinstance(grams_per_unit, (int, float)) or not unit:
                    continue
                grams = scaled.get(row_id)
                if not isinstance(grams, (int, float)):
                    continue
                amount = float(grams) / float(grams_per_unit)
                label = CONVENTION_LABELS.get(convention, convention)
                out[row_id] = f"≈ {_round_measure(amount)} {unit} ({label})"
        return out

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _comp_path(comp: dict[str, Any]) -> str:
        return f"components/{comp.get('name', '?')}"

    @staticmethod
    def _ing_path(comp: dict[str, Any], ing: dict[str, Any]) -> str:
        return f"components/{comp.get('name', '?')}/{ing.get('row_id', '?')}"

    def blocker_count(self) -> int:
        return sum(1 for f in self.findings() if f.severity == "blocker")


def _slugify(text: str) -> str:
    """Lowercase, hyphenated slug safe for a filename."""
    out: list[str] = []
    for ch in text.strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in {" ", "-", "_", "/"}:
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "recipe"


def load_card(path: str | Path) -> Card:
    """Load a card document from ``path``."""
    return Card.load(path)


def _significant_places(value: float) -> int:
    """Return the decimal places that keep six significant digits.

    The bound is what keeps a stored value from becoming a wall of digits
    on the page; it never rounds the value away, because the places are
    counted from the value's own magnitude.
    """
    exponent = math.floor(math.log10(abs(value)))
    return max(1, 6 - (exponent + 1))


# The depth each column's workbook number format can paint, in decimal
# places. The reading editions are bounded by the same numbers so the two
# sides of a card show the same digits for the same mass.
MASS_FORMAT_DEPTH = 19
PERCENT_FORMAT_DEPTH = 13


def _stored_spelling(value: float, depth: int) -> str:
    """Return a value's own decimal spelling, bounded to ``depth`` places.

    A real nonzero number never becomes zero here, and the result carries
    no scientific notation and no floating-point noise: the value is first
    carried through the fifteen significant digits a spreadsheet keeps.
    """
    from decimal import Decimal
    number = Decimal(f"{value:.15g}")
    if number == 0:
        # The value is smaller than the significant-digit bound. Use its own
        # spelling rather than round it away.
        number = Decimal(repr(value))
    text = format(number, "f")
    if "." in text:
        whole, fraction = text.split(".", 1)
        fraction = fraction[:depth]
        fraction = fraction.rstrip("0")
        text = f"{whole}.{fraction}" if fraction else whole
    return text


def weight_display(value: float) -> str:
    """Return the number a reader sees for a weight, without its unit.

    One rule covers every edition. A weight of a tenth of a gram or more
    reads at one decimal, which is the scale a kitchen reads. Below that
    the stored precision is kept: the number is taken from the decimal
    form of the stored value, so it carries no floating-point noise, no
    scientific notation and no truncation to zero. A whole number of grams
    reads as that whole number.

    The last digit is rounded the way a spreadsheet rounds it - half away
    from zero, on the decimal spelling of the stored value - because the
    workbook paints a weight with a number format and a spreadsheet
    rounds that way. Rounding the print the same way is what keeps the
    PDF and the workbook from disagreeing about the last digit.
    """
    from decimal import Decimal, ROUND_HALF_UP
    if value == int(value):
        # The integrality test is exact on purpose. A tolerance here would
        # swallow every mass below a nanogram and print it as zero, which is
        # the one thing a potent ingredient must never read as.
        return f"{int(value)}"
    if value >= 0.1:
        # A mass of a tenth of a gram or more reads at one decimal, which
        # is the scale a kitchen reads. The branch tests the value itself,
        # not its absolute value, because the workbook's number format
        # branches the same way.
        #
        # The rounding is half away from zero on the decimal spelling, and
        # the value is first carried through the fifteen significant digits
        # a spreadsheet keeps. A spreadsheet rounds that way, so this is
        # what makes the PDF and the workbook agree on the last digit.
        rounded = Decimal(f"{value:.15g}").quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
        return format(rounded, "f")
    # Below a tenth of a gram the stored precision is kept: the decimal
    # form of the stored value, so it carries no floating-point noise, no
    # scientific notation and no truncation to zero. It is bounded to the
    # depth the workbook's number format can paint, so the two editions
    # show the same digits for the same mass.
    return _stored_spelling(value, MASS_FORMAT_DEPTH)


def format_weight(value: float | None, unit: str = "g",
                  language: str = _LOCALE_DEFAULT) -> str:
    """Format a weight for display, trimming meaningless decimals.

    The decimal mark follows the language's convention (comma for es/fr/it/
    pt, dot for en); no thousands separator is ever added and the amount is
    never changed. The unit is kept verbatim.

    A weight that is not zero never prints as zero. A mass below a tenth
    of a gram is a potent ingredient - leavener, salt, extract - and one
    decimal place would print ``0.0 g`` and tell the cook to add none of
    it. Such a weight keeps the decimals its own stored precision carries,
    bounded so the number never becomes a wall of digits, and the bound
    never rounds the weight away: the printed number is the number the
    card holds.
    """
    if value is None:
        return "—"
    number = weight_display(value)
    return f"{localize_decimals(number, language)} {unit}"


def format_quantity(quantity: Any, language: str = _LOCALE_DEFAULT) -> str:
    """Format a quantity the cook supplied in their own unit.

    The original unit is kept and the convention is named, because a cup in
    one convention is not a cup in another and a quart is never printed as a
    gram weight it was never converted into. The decimal mark follows the
    language's convention; the amount is never changed.
    """
    if not isinstance(quantity, dict):
        return "—"
    amount = quantity.get("amount")
    unit = str(quantity.get("unit") or "").strip()
    if (isinstance(amount, bool) or not isinstance(amount, (int, float))
            or not math.isfinite(amount) or not unit):
        return "—"
    convention = str(quantity.get("convention") or "").strip()
    # Own units are supplied facts, not gram display estimates. Keep enough
    # digits to round-trip their numeric value; prefer a compact exact common
    # fraction when it represents that same value within float precision.
    from fractions import Fraction
    fraction = Fraction(amount).limit_denominator(16)
    if fraction.denominator != 1 and math.isclose(float(fraction), amount, rel_tol=1e-15, abs_tol=0):
        number = f"{fraction.numerator}/{fraction.denominator}"
    else:
        number = str(int(amount)) if amount == int(amount) else str(amount)
    value = f"{localize_decimals(number, language)} {unit}"
    if convention:
        value += f" ({convention})"
    return value


def row_weight_label(row: dict[str, Any], resolved: float | None = None,
                     language: str = _LOCALE_DEFAULT) -> str:
    """The weight a row shows in every edition.

    An established mass prints in grams. A row whose mass was never
    established prints the quantity the cook supplied in their own unit, or
    an em dash when there is nothing to print. It never prints a mass the
    card does not have. The decimal mark follows the language's convention.
    """
    if resolved is None:
        weight = row.get("weight_g")
        resolved = float(weight) if isinstance(weight, (int, float)) else None
    if resolved is not None:
        return format_weight(resolved, language=language)
    quantity = row.get("quantity")
    if isinstance(quantity, dict) and quantity.get("amount") is not None:
        return format_quantity(quantity, language)
    return "—"


def format_percent(value: float | None,
                   language: str = _LOCALE_DEFAULT) -> str:
    """Format a percentage for display, trimming meaningless decimals.

    The decimal mark follows the language's convention; the amount is never
    changed.
    """
    if value is None:
        return "—"
    from decimal import Decimal, ROUND_HALF_UP
    if value == int(value):
        # The integrality test is exact on purpose: a tolerance here would
        # swallow a small but real percentage and print it as zero.
        number = f"{int(value)}"
    elif value >= 0.1:
        # Half away from zero on the fifteen significant digits a
        # spreadsheet keeps, so the PDF and the workbook agree.
        rounded = Decimal(f"{value:.15g}").quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
        number = format(rounded, "f")
    else:
        # Below a tenth of a percentage point the stored precision is kept,
        # written plainly and bounded to the depth the workbook's number
        # format can paint.
        number = _stored_spelling(value, PERCENT_FORMAT_DEPTH)
    return f"{localize_decimals(number, language)}%"


def join_blockers(blockers: Iterable[str]) -> str:
    """Join release blockers into one readable sentence.

    Blockers are usually written as full sentences. Joining them with a
    semicolon after a period produces "SOP.; Second cook", so trailing
    punctuation is removed before the list is rejoined.
    """
    cleaned: list[str] = []
    for blocker in blockers:
        text = str(blocker).strip()
        if not text:
            continue
        while text.endswith((".", ";", ",")):
            text = text[:-1].rstrip()
        if text:
            cleaned.append(text)
    if not cleaned:
        return ""
    return "; ".join(cleaned) + "."


__all__ = [
    "Card",
    "CardError",
    "Finding",
    "Derived",
    "GRAM_EPSILON",
    "PROCESS_CONTROL_KEYS",
    "PROCESS_CONTROL_LABELS",
    "RELEASE_WARNING",
    "UNRELEASED_STATUSES",
    "applicable_process_controls",
    "declares_not_applicable",
    "format_percent",
    "format_quantity",
    "format_weight",
    "join_blockers",
    "load_card",
    "na_reason",
    "row_weight_label",
]


def input_mass_label(card: Card, language: str = _LOCALE_DEFAULT) -> str:
    """Display full input only when known; label partial mass separately.

    The full input is the one total every edition shows: the declared
    ``input_total_g`` when the card states one, and otherwise the sum of
    the established masses. A card that states no total and establishes
    every mass still has a total, and every edition must show it.
    """
    derived = card.derived()
    if derived.input_complete:
        return format_weight(derived.input_total_known_g, language=language)
    return (
        f"{translate('caption.unknown_input', language)}; "
        f"{translate('caption.known_input_subtotal', language)} "
        f"{format_weight(derived.known_input_subtotal_g, language=language)}"
    )

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
    if "-" not in text:
        return ""
    return text.split("-", 1)[1].strip()


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
    loss_g: float | None = None
    portions: int | None = None
    portion_remainder_g: float | None = None


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
        """Every ingredient row across all components, in document order."""
        rows: list[dict[str, Any]] = []
        for comp in self.components:
            for ing in comp.get("ingredients", []) or []:
                rows.append(ing)
        return rows

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
        out.extend(self._check_yield_and_portions())
        out.extend(self._check_step_numbering())
        out.extend(self._check_ingredient_coverage())
        out.extend(self._check_release_gating())
        out.extend(self._check_unverified_volumes())
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
        for comp in self.components:
            name = str(comp.get("name", ""))
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

            row_weight = match.get("weight_g")
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
        total = 0.0
        for ing in self.ingredients:
            weight = ing.get("weight_g")
            if isinstance(weight, (int, float)):
                total += float(weight)

        declared = self.data.get("input_total_g")
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

    def _check_yield_and_portions(self) -> list[Finding]:
        out: list[Finding] = []
        usable = self.data.get("usable_yield_g")
        declared_loss = self.data.get("loss_g")
        portion = self.data.get("portion_g")
        declared_portions = self.data.get("portions")
        input_total = self.data.get("input_total_g")

        if isinstance(usable, (int, float)) and isinstance(input_total, (int, float)):
            computed_loss = float(input_total) - float(usable)
            if computed_loss < -GRAM_EPSILON:
                out.append(
                    Finding(
                        "yield-exceeds-input",
                        f"usable_yield_g {usable} g exceeds input_total_g {input_total} g",
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

        for comp in self.components:
            comp_name = str(comp.get("name", ""))
            ref_weight = comp.get("reference_weight_g")
            if not isinstance(ref_weight, (int, float)) or float(ref_weight) <= 0:
                continue

            per_component: dict[str, float] = {}
            component_total = 0.0
            for ing in comp.get("ingredients", []) or []:
                weight = ing.get("weight_g")
                row_id = str(ing.get("row_id", ""))
                if not isinstance(weight, (int, float)):
                    continue
                weight = float(weight)
                component_total += weight
                pct = 100.0 * weight / float(ref_weight)
                per_component[row_id] = pct
                derived.percentages[row_id] = pct

            derived.component_percentages[comp_name] = per_component
            derived.component_totals[comp_name] = component_total
            derived.input_total_g += component_total

        usable = self.data.get("usable_yield_g")
        portion = self.data.get("portion_g")
        input_total = self.data.get("input_total_g")

        if isinstance(usable, (int, float)) and isinstance(input_total, (int, float)):
            derived.loss_g = float(input_total) - float(usable)
        if isinstance(usable, (int, float)) and isinstance(portion, (int, float)):
            derived.portions = int(math.floor(float(usable) / float(portion)))
            derived.portion_remainder_g = float(usable) - derived.portions * float(portion)
        return derived

    def scaled_weights(self, factor: float) -> dict[str, float]:
        """Return scaled ingredient weights for ``factor``.

        Only ingredient quantities scale. Time, temperature, vessel loading and
        release status never scale.
        """
        if not isinstance(factor, (int, float)) or factor <= 0:
            raise ValueError("scale factor must be a positive number")
        return {
            str(ing.get("row_id")): float(ing.get("weight_g", 0.0)) * float(factor)
            for ing in self.ingredients
            if isinstance(ing.get("weight_g"), (int, float))
        }

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


def format_weight(value: float | None, unit: str = "g") -> str:
    """Format a weight for display, trimming meaningless decimals."""
    if value is None:
        return "—"
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value))} {unit}"
    return f"{value:.1f} {unit}"


def format_percent(value: float | None) -> str:
    """Format a percentage for display, trimming meaningless decimals."""
    if value is None:
        return "—"
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value))}%"
    return f"{value:.1f}%"


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
    "format_weight",
    "join_blockers",
    "load_card",
    "na_reason",
]

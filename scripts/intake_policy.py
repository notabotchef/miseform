#!/usr/bin/env python3
"""The research-first intake policy, in executable form.

This module is the executable form of the contract in
``references/research-and-clarification.md``. It takes a structured
extraction of what the cook supplied, applies the decision rules, and
returns the decision Miseform acts on: the stage sequence, the component map,
the research plan, the material questions, the proposal, and whether a local
draft and a filing are authorized.

What it is not: it does not read images, does not browse, and does not write
cards. The extraction step and the research step are performed by the host
agent; this module decides what the answer to those steps is allowed to be.
That boundary is deliberate and keeps the policy testable without a network
or a model.

Scope of the input: the caller passes one dictionary built only from what the
cook supplied in this conversation, plus the research results the agent
gathered. The module reads nothing else. It opens no session store, no prior
transcript, no historical log, no task board, and no path outside the Miseform
package.

Public API:

    load_policy()  -> dict
    decide(intake) -> dict
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PACKAGE = Path(__file__).resolve().parent.parent
POLICY_DOC = PACKAGE / "references" / "research-and-clarification.md"

# The one-line request an empty activation gets. It is quoted here so the
# engine and the prose cannot disagree about it.
EMPTY_REPLY = (
    "Send a photo of your written recipe, or paste the recipe and notes here."
)

# Words that describe an ingredient without changing what it is. They are
# dropped before two ingredient names are compared, so "purchased chicken
# breast" and "chicken breast" stay the same ingredient.
NOISE_QUALIFIERS = frozenset(
    """
    purchased extra plain all-purpose italian free-range organic
    boneless skinless boneless-skinless low-fat
    """.split()
)

# Words that identify the product or its state. They are kept, because
# "raw shrimp" and "cooked shrimp" are different products: a correction for
# one must never overwrite the other, and two different products are never
# the same ingredient in conflict.
IDENTITY_TOKENS = frozenset(
    """
    raw cooked roast roasted toasted grilled baked fried braised poached
    steamed dried dry salted unsalted low-sodium fine coarse cultured
    heavy light hot mild chilled cold room-temperature room temperature
    frozen cured smoked pickled canned olive vegetable canola sunflower
    neutral refined unrefined virgin
    """.split()
)

# Multi-word states written as two words. The tokenizer splits on
# whitespace, so a state written as two words would otherwise become two
# stray product words and stop matching the one-word form.
MULTIWORD_STATES = {
    "extra virgin": "virgin",
    "extra virgin olive": "virgin",
    "low sodium": "low-sodium",
    "room temperature": "room-temperature",
    "boneless skinless": "boneless-skinless",
}

# Words that mean the same state, normalised to one token before comparison.
VARIANT_SYNONYMS = {
    "roast": "cooked",
    "roasted": "cooked",
    "toast": "cooked",
    "toasted": "cooked",
    "grilled": "cooked",
    "baked": "cooked",
    "fried": "cooked",
    "braised": "cooked",
    "poached": "cooked",
    "steamed": "cooked",
    "dry": "dried",
}

# Two variants that describe different products. A name carrying one and a
# name carrying the other are never the same ingredient.
EXCLUSIVE_VARIANTS = (
    ("raw", "cooked"),
    ("salted", "unsalted"),
    ("ground", "whole"),
    ("fine", "coarse"),
    ("heavy", "light"),
    ("virgin", "refined"),
    ("virgin", "unrefined"),
    ("fresh", "dried"),
    ("fresh", "cured"),
    ("fresh", "smoked"),
    ("fresh", "frozen"),
    ("olive", "canola"),
    ("olive", "vegetable"),
    ("olive", "sunflower"),
    ("olive", "neutral"),
    ("canola", "vegetable"),
    ("canola", "sunflower"),
    ("canola", "neutral"),
    ("vegetable", "sunflower"),
    ("vegetable", "neutral"),
    ("sunflower", "neutral"),
)

# Foods whose handling carries a safety obligation. A component built on one
# of these needs a stated thermal endpoint or a stated holding rule.
SAFETY_FOOD_WORDS = frozenset(
    """
    chicken breast thigh breast pork beef lamb veal duck goose
    turkey salmon tuna shrimp prawn fish cod halibut scallop
    crab lobster mussel oyster clam egg eggs cream butter milk
    yoghurt yogurt cheese mayonnaise custard cream-cheese
    """.split()
)

# Phrases that mean the cook already told us a value cannot be measured.
# The value stays unknown and is never asked for again.
UNMEASURED_PATTERNS = (
    r"not (?:been )?weighed",
    r"not weighed",
    r"haven'?t weighed",
    r"have not weighed",
    r"no idea (?:what|how much)",
    r"didn'?t weigh",
    r"did not weigh",
    r"cannot be measured",
    r"can'?t be measured",
    r"leave the yield off",
)

# Vague instructions that research settles, so they are never questions.
ROUTINE_TECHNIQUE_PATTERNS = (
    r"to taste",
    r"until (?:done|golden|browned|tender|reduced)",
    r"as needed",
    r"a little",
    r"some (?:salt|oil|butter|cream)",
    r"season to taste",
)

# The ingredient names a chef would recognise. Used to pull an amount out of
# a margin note so a written formula and a note can be compared.
AMOUNT_PATTERN = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z\- ]{2,40}?)\s*"
    r"(?P<amount>\d+(?:\.\d+)?\s*(?:g|kg|ml|l|oz|lb)\b)",
    re.IGNORECASE,
)

CANONICAL_PATH = "START -> EXTRACT -> MAP -> RESEARCH -> PROPOSE -> DRAFT"


# --------------------------------------------------------------------- policy


def load_policy() -> dict[str, Any]:
    """Return the decision table embedded in the reference document.

    The table is written once, in prose, inside
    ``references/research-and-clarification.md``. Reading it from there means
    the executable policy and the published contract cannot drift apart.
    """
    text = POLICY_DOC.read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)\n```", text, re.DOTALL)
    if not blocks:
        raise ValueError(
            "the decision table is missing from references/research-and-clarification.md"
        )
    policy = json.loads(blocks[-1])
    if policy.get("canonical_path") != CANONICAL_PATH.split(" -> "):
        raise ValueError(
            "the decision table's canonical path does not match the contract"
        )
    return policy


# ------------------------------------------------------------------ helpers


def _tokens(name: str) -> list[str]:
    """The words of an ingredient phrase, lowercased and unpunctuated.

    A multi-word state written as two words is folded into its one-word
    form first, so "extra virgin olive oil" and "olive oil" are compared as
    the same oil with a different grade rather than as two products.
    """
    text = str(name or "").lower()
    for phrase, replacement in MULTIWORD_STATES.items():
        text = text.replace(phrase, replacement)
    return [
        token.strip(",.;:")
        for token in re.split(r"\s+", text)
        if token.strip(",.;:")
    ]


def _base_tokens(name: str) -> list[str]:
    """The words that identify the product, without noise and without state.

    Noise words describe the ingredient without changing it. State words
    change what the ingredient is, so they are kept out of the base name and
    compared separately.
    """
    return [
        token
        for token in _tokens(name)
        if token not in NOISE_QUALIFIERS and token not in IDENTITY_TOKENS
    ]


def _state_tokens(name: str) -> set[str]:
    """The state words an ingredient carries, normalised to one vocabulary."""
    return {
        VARIANT_SYNONYMS.get(token, token)
        for token in _tokens(name)
        if token in IDENTITY_TOKENS
    }


def base_name(name: str) -> str:
    """The product an ingredient phrase names, without its state.

    "purchased chicken breast" and "chicken breast" share a base name;
    "raw shrimp" and "cooked shrimp" also share one, and their state is
    compared separately.
    """
    tokens = _base_tokens(name)
    if not tokens:
        return ""
    if tokens[-1].endswith("s") and len(tokens[-1]) > 3:
        tokens[-1] = tokens[-1][:-1]
    return " ".join(sorted(tokens))


def canonical_name(name: str) -> str:
    """The full identity of an ingredient: its product and its state.

    Two phrases are the same ingredient only when both parts match, so
    "raw shrimp" and "cooked shrimp" never collapse into one key.
    """
    base = base_name(name)
    if not base:
        return ""
    states = _state_tokens(name)
    return base + "|" + ",".join(sorted(states))


def same_ingredient(left: str, right: str) -> bool:
    """True when two ingredient phrases name the same product.

    The base names must match, and their states must not contradict each
    other. An unstated state is compatible with any state, so "shrimp"
    and "raw shrimp" are the same product, while "raw shrimp" and
    "cooked shrimp" are not.
    """
    left_base = base_name(left)
    right_base = base_name(right)
    if not left_base or not right_base or left_base != right_base:
        return False
    left_states = _state_tokens(left)
    right_states = _state_tokens(right)
    for first, second in EXCLUSIVE_VARIANTS:
        if first in left_states and second in right_states:
            return False
        if second in left_states and first in right_states:
            return False
    return True


# Units and the dimension each one measures. A mass is never compared with a
# volume, and a household volume is never compared with a metric one, so a
# conversion is never silently assumed.
MASS_UNITS = {
    "mg": ("mass", 0.001),
    "g": ("mass", 1.0),
    "gram": ("mass", 1.0),
    "grams": ("mass", 1.0),
    "kg": ("mass", 1000.0),
    "oz": ("mass", 28.3495),
    "ounce": ("mass", 28.3495),
    "ounces": ("mass", 28.3495),
    "lb": ("mass", 453.592),
    "lbs": ("mass", 453.592),
    "pound": ("mass", 453.592),
    "pounds": ("mass", 453.592),
}

METRIC_VOLUME_UNITS = {
    "ml": ("metric-volume", 1.0),
    "millilitre": ("metric-volume", 1.0),
    "millilitres": ("metric-volume", 1.0),
    "milliliter": ("metric-volume", 1.0),
    "milliliters": ("metric-volume", 1.0),
    "cl": ("metric-volume", 10.0),
    "dl": ("metric-volume", 100.0),
    "l": ("metric-volume", 1000.0),
    "litre": ("metric-volume", 1000.0),
    "litres": ("metric-volume", 1000.0),
    "liter": ("metric-volume", 1000.0),
    "liters": ("metric-volume", 1000.0),
}

# Household volume stays its own dimension, so a cup is never assumed to be
# a metric measure.
HOUSEHOLD_VOLUME_UNITS = {
    "cup": ("household-volume", 48.0),
    "cups": ("household-volume", 48.0),
    "tbsp": ("household-volume", 3.0),
    "tbs": ("household-volume", 3.0),
    "tablespoon": ("household-volume", 3.0),
    "tablespoons": ("household-volume", 3.0),
    "tsp": ("household-volume", 1.0),
    "teaspoon": ("household-volume", 1.0),
    "teaspoons": ("household-volume", 1.0),
    "floz": ("household-volume", 1.0),
    "fl": ("household-volume", 1.0),
}

AMOUNT_UNITS = {**MASS_UNITS, **METRIC_VOLUME_UNITS, **HOUSEHOLD_VOLUME_UNITS}

# The first number and unit in an amount string.
AMOUNT_PARSE = re.compile(r"(\d+(?:\.\d+)?)\s*([a-zA-Z]+)?")


def _amount_key(amount: str) -> tuple[str, float] | None:
    """Normalise an amount into a dimension and a value in that dimension.

    "300 ml" and "300mL" are the same amount. "1 L" is a thousand
    millilitres, not one. "300 g" and "300 ml" are different dimensions and
    never compare equal, so a mass is never read as a volume.
    """
    match = AMOUNT_PARSE.search(str(amount or ""))
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    unit = (match.group(2) or "").lower()
    if not unit:
        return ("count", value)
    if unit in AMOUNT_UNITS:
        dimension, factor = AMOUNT_UNITS[unit]
        return (dimension, round(value * factor, 6))
    return ("unknown-unit", value)


def _amount_relation(
    left: tuple[str, float] | None, right: tuple[str, float] | None
) -> str:
    """Classify how two amounts relate.

    ``same``        the same quantity, written differently.
    ``conflict``    two different quantities of the same ingredient.
    ``conversion``  one quantity written in two volume conventions, which a
                    reference settles.
    ``incomparable``the two cannot be compared at all.

    A mass and a volume of the same ingredient are a conflict, not a
    conversion: converting one into the other needs a density the cook did
    not supply, and two different numbers for one ingredient is exactly the
    kind of discrepancy the cook must resolve. Two volumes in different
    conventions are a conversion, because a reference settles that.
    """
    if left is None or right is None:
        return "incomparable"
    if left[0] == right[0]:
        difference = abs(left[1] - right[1])
        if difference <= max(0.05, 0.02 * max(left[1], right[1])):
            return "same"
        return "conflict"
    volume_dimensions = {"metric-volume", "household-volume"}
    if left[0] in volume_dimensions and right[0] in volume_dimensions:
        return "conversion"
    if left[0] == "unknown-unit" or right[0] == "unknown-unit":
        return "incomparable"
    return "conflict"


def _amounts_differ(
    left: tuple[str, float] | None, right: tuple[str, float] | None
) -> bool:
    """True when two amounts are comparable and not the same amount."""
    return _amount_relation(left, right) == "conflict"


def _is_safety_food(component: dict[str, Any]) -> bool:
    """True when a component carries a food with a safety obligation."""
    blob = " ".join(
        [
            str(component.get("title", "")),
            " ".join(
                str(row.get("name", "")) for row in component.get("ingredients") or []
            ),
            " ".join(str(step) for step in component.get("method_text") or []),
        ]
    ).lower()
    return any(word in blob for word in SAFETY_FOOD_WORDS)


def _has_thermal_endpoint(component: dict[str, Any]) -> bool:
    """True when the supplied material states a thermal endpoint.

    A stated endpoint is a temperature the cook gave, or a core temperature
    they named, or a cooking time they stated together with the thing it
    applies to. A bare duration is not an endpoint: "stir for 1 minute" says
    nothing about how hot the food got, so it never closes the question.
    """
    blob = " ".join(
        [
            " ".join(str(step) for step in component.get("method_text") or []),
            " ".join(str(row.get("amount", "")) for row in component.get("ingredients") or []),
            str(component.get("handling_note", "")),
        ]
    ).lower()

    # A temperature with a number is a stated endpoint.
    if re.search(r"\b\d+(?:\.\d+)?\s*(?:°\s*)?[cf]\b", blob):
        return True
    # A core temperature named without a number is still the cook naming the
    # measure they use, but it states no value, so it is not an endpoint.
    if re.search(r"\bcore\b", blob) and re.search(
        r"\b\d+(?:\.\d+)?\s*(?:°\s*)?[cf]\b", blob
    ):
        return True
    # A stated cooking time closes the endpoint only when it is attached to a
    # cooking verb and a food, never to a preparation step like stirring,
    # blending or chilling.
    return bool(
        re.search(
            r"\b(?:roast|bake|grill|sear|simmer|boil|fry|steam|blanch|braise|"
            r"poach|cook|heat|warm)\b[^.]{0,40}\b\d+(?:\.\d+)?\s*"
            r"(?:min|minutes|sec|seconds|hour|hours)\b",
            blob,
        )
    )


def _has_holding_rule(component: dict[str, Any]) -> bool:
    """True when the supplied material states how the component is held.

    A holding rule states a temperature, a duration, or a use-by limit. The
    word "cool" on its own is a step in a method, not a rule: "cool on a
    tray" says nothing about how long the product may be held or how cold
    it must be.
    """
    blob = " ".join(
        [
            str(component.get("handling_note", "")),
            " ".join(str(step) for step in component.get("method_text") or []),
        ]
    ).lower()

    if re.search(r"\b(?:use[- ]?by|best before|discard after)\b", blob):
        return True
    if not re.search(
        r"\bhold|held|holding|cool|chill|refrigerat|freeze|store|keep\b", blob
    ):
        return False
    # The rule needs a limit: a temperature, a duration, or a stated period.
    return bool(
        re.search(r"\b\d+(?:\.\d+)?\s*(?:°\s*)?[cf]\b", blob)
        or re.search(
            r"\b\d+(?:\.\d+)?\s*(?:min|minutes|sec|seconds|hour|hours|day|days|"
            r"week|weeks)\b",
            blob,
        )
        or re.search(r"\bwithin\s+\d+", blob)
        or re.search(r"\bfor\s+(?:up to\s+)?\d+", blob)
    )


def _routine_technique(text: str) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in ROUTINE_TECHNIQUE_PATTERNS)


def _unmeasured(text: str) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in UNMEASURED_PATTERNS)


# ----------------------------------------------------------------- the rules


def _map_page(intake: dict[str, Any]) -> dict[str, Any]:
    """Decide what the page is: dish, components, main, shared components."""
    components: list[dict[str, Any]] = []
    for block in intake.get("blocks") or []:
        if str(block.get("kind") or "component") != "component":
            continue
        components.append(
            {
                "id": str(block.get("id", "")),
                "title": str(block.get("title", "")),
                "purchased": bool(block.get("purchased")),
                "is_main": bool(block.get("is_main")),
                "shared_with": [str(s) for s in block.get("shared_with") or []],
                "ingredient_count": len(block.get("ingredients") or []),
                "step_count": len(block.get("steps") or []),
            }
        )

    mains = [c for c in components if c.get("is_main")] or [
        c for c in components if c.get("purchased")
    ]
    main = mains[0]["title"] if mains else (components[0]["title"] if components else "")

    return {
        "dish": str(intake.get("dish") or ""),
        "components": components,
        "main": main,
        "shared_components": [
            c["title"] for c in components if c.get("shared_with")
        ],
        "separate_recipes": [
            str(block.get("title", ""))
            for block in intake.get("blocks") or []
            if str(block.get("kind") or "component") == "separate_recipe"
        ],
    }


def _classify_preparation(component: dict[str, Any]) -> str:
    """Classify a component's preparation from the supplied material.

    The classification reads the full block — its title, its ingredients and
    its method — because a title alone does not say what a preparation is.
    A dressing made with mayonnaise is an emulsion whatever the block is
    called.
    """
    blob = " ".join(
        [
            str(component.get("title", "")),
            " ".join(
                str(row.get("name", "")) for row in component.get("ingredients") or []
            ),
            " ".join(str(step) for step in component.get("method_text") or []),
        ]
    ).lower()

    if component.get("purchased"):
        return "purchased item used as a main"
    if re.search(r"emulsion|mayonnaise|hollandaise|beurre blanc|creamy sauce|aioli", blob):
        return "sauce or emulsion"
    if re.search(r"garnish|crumb|spice mix|dry rub|toasted", blob):
        return "dry garnish"
    if re.search(r"ferment|koji|culture|starter|brine|cure", blob):
        return "fermentation or curing"
    if re.search(r"blanch|steam", blob):
        return "blanch or steam"
    if re.search(r"fry|deep[- ]?fry", blob):
        return "fry"
    if re.search(r"roast|bake|grill", blob):
        return "roast, bake or grill"
    if re.search(r"braise|stew|stock|soup|reduction|reduce", blob):
        return "braise, stew or reduction"
    if re.search(r"dessert|pastry|custard|sorbet|tart|cake|cookie", blob):
        return "dessert"
    return "raw assembly or unclassified"


def _source_block(component: dict[str, Any], intake: dict[str, Any]) -> dict[str, Any]:
    """The supplied block behind a mapped component.

    The map carries the shape of the page. The classification needs the
    material itself, so it is looked up here rather than being copied into
    the map.

    A block is matched by title, or by an id that identifies exactly one
    block. Two blocks that share an id are matched by title instead, so one
    block never supplies another block's material.
    """
    blocks = [
        block
        for block in intake.get("blocks") or []
        if str(block.get("kind") or "component") == "component"
    ]
    for block in blocks:
        if block.get("title") == component.get("title"):
            return block
    component_id = component.get("id")
    if component_id:
        matching = [block for block in blocks if block.get("id") == component_id]
        if len(matching) == 1:
            return matching[0]
    return {}


def _research_plan(page: dict[str, Any], intake: dict[str, Any]) -> dict[str, Any]:
    """Build the bounded research plan for the mapped components."""
    policy = load_policy()
    bound = policy["research_bound"]
    per_component = int(bound["comparable_recipes_per_component"])
    run_limit = int(bound["comparable_technique_sources_per_run"])

    plan: list[dict[str, Any]] = []
    for component in page["components"]:
        source = _source_block(component, intake)
        preparation = _classify_preparation(source or component)
        comparable = 0 if component.get("purchased") else per_component
        plan.append(
            {
                "component": component["title"],
                "preparation": preparation,
                "comparable_recipes": comparable,
                "purchased_as_supplied": bool(component.get("purchased")),
                "volume_sources_per_ingredient": int(
                    bound["volume_sources_per_ingredient"]
                ),
            }
        )

    # The run bound is honoured by giving the earlier components their
    # research first. No component is dropped from the plan: a purchased
    # component stays in it with no comparable recipes of its own.
    trimmed: list[dict[str, Any]] = []
    remaining = run_limit
    for entry in plan:
        take = min(entry["comparable_recipes"], remaining)
        remaining -= take
        trimmed.append({**entry, "comparable_recipes": take})

    return {
        "components": trimmed,
        "comparable_technique_sources": sum(
            e["comparable_recipes"] for e in trimmed
        ),
        "technique_source_limit": run_limit,
        "volume_sources_per_ingredient": int(
            bound["volume_sources_per_ingredient"]
        ),
        "sources_recorded": list(intake.get("research_sources") or []),
    }


def _candidate_questions(
    intake: dict[str, Any], page: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Find every question the supplied material actually justifies.

    Returns the candidates that may reach the cook, and the conversions that
    the research settles on its own. A conversion is two statements of one
    ingredient in different dimensions; it is answered by a gram-to-volume
    reference, not by the cook.
    """
    candidates: list[dict[str, Any]] = []
    conversions: list[dict[str, Any]] = []

    # 1. Identity and quantity conflicts: the same ingredient given two
    #    different amounts on the page. A margin note on the page counts as
    #    a second statement of the same ingredient.
    #
    #    Two statements are about the same ingredient when they name the same
    #    product and their states do not contradict. "Raw shrimp 200 g" and
    #    "cooked shrimp 150 g" are two products, not a conflict, so they are
    #    not compared at all.
    declared: list[tuple[str, str, str, tuple[str, float]]] = []
    for component in intake.get("blocks") or []:
        if str(component.get("kind") or "component") != "component":
            continue
        title = str(component.get("title", ""))
        statements = [
            {"name": row.get("name"), "amount": row.get("amount")}
            for row in component.get("ingredients") or []
        ]
        statements += [
            {"name": note.get("ingredient"), "amount": note.get("amount")}
            for note in component.get("page_notes") or []
        ]
        for statement in statements:
            name = str(statement.get("name") or "")
            amount_text = str(statement.get("amount") or "")
            amount = _amount_key(amount_text)
            if not base_name(name) or amount is None:
                continue
            conflict = None
            conversion = None
            for prior_title, prior_name, prior_text, prior_amount in declared:
                if not same_ingredient(name, prior_name):
                    continue
                relation = _amount_relation(prior_amount, amount)
                if relation == "conflict":
                    conflict = (prior_title, prior_text)
                    break
                if relation == "conversion":
                    # The same ingredient in two volume conventions: a
                    # reference settles it, not the cook.
                    conversion = (prior_title, prior_text)
                    break
            if conflict is not None:
                prior_title, prior_text = conflict
                candidates.append(
                    {
                        "category": "identity_or_quantity_conflict",
                        "text": (
                            f"{title}: {statement.get('name')} is "
                            f"{statement.get('amount')}, but it is also "
                            f"{prior_text} in {prior_title}."
                        ),
                        "component": title,
                    }
                )
            elif conversion is not None:
                prior_title, prior_text = conversion
                conversions.append(
                    {
                        "category": "measurement_conversion",
                        "text": (
                            f"{title}: {statement.get('name')} is given as "
                            f"{statement.get('amount')} and as {prior_text} in "
                            f"{prior_title}."
                        ),
                        "component": title,
                    }
                )
            else:
                declared.append((title, name, amount_text, amount))

    # 2. Material technique forks the supplied material does not settle.
    for component in intake.get("blocks") or []:
        if str(component.get("kind") or "component") != "component":
            continue
        for fork in component.get("forks") or []:
            candidates.append(
                {
                    "category": "material_technique_fork",
                    "text": str(fork.get("text", "")),
                    "component": component.get("title", ""),
                }
            )

    # 3. Safety-critical uncertainty. One candidate per missing fact, so a
    #    confirmed default settles the field it covers and leaves the other
    #    fact open.
    for component in intake.get("blocks") or []:
        if str(component.get("kind") or "component") != "component":
            continue
        if not _is_safety_food(component):
            continue
        missing: list[tuple[str, str]] = []
        if not _has_thermal_endpoint(component):
            missing.append(("a stated thermal endpoint", "thermal endpoint"))
        if not _has_holding_rule(component):
            missing.append(
                ("the approved holding or cooling rule", "holding or cooling rule")
            )
        for label, field in missing:
            candidates.append(
                {
                    "category": "safety_critical_uncertainty",
                    "text": f"{component.get('title', '')}: {label} is not stated.",
                    "component": component.get("title", ""),
                    "field": field,
                }
            )

    # 4. A measured usable yield used for production is safety-critical. It
    #    is asked once, and only when the cook has neither supplied a
    #    measurement nor said it cannot be measured.
    measured_components = {
        str(m.get("component", "")) for m in intake.get("measurements") or []
    }
    ruled_out = _yields_ruled_out(intake)
    for component in intake.get("blocks") or []:
        if str(component.get("kind") or "component") != "component":
            continue
        title = str(component.get("title", ""))
        if title in measured_components or title in ruled_out:
            continue
        if component.get("purchased"):
            # A purchased component's mass is the purchase mass. There is no
            # yield to weigh.
            continue
        candidates.append(
            {
                "category": "safety_critical_uncertainty",
                "text": (
                    f"{title}: the measured usable yield used for production "
                    "is not stated."
                ),
                "component": title,
                "field": "measured usable yield",
            }
        )

    return candidates, conversions


def _yields_ruled_out(intake: dict[str, Any]) -> set[str]:
    """Components whose yield the cook already said cannot be measured.

    A note attached to a block applies to that block. A note the cook gave
    about the page as a whole applies to every component that has no
    measurement and no note of its own.
    """
    ruled_out: set[str] = set()
    blocks = [
        block
        for block in intake.get("blocks") or []
        if str(block.get("kind") or "component") == "component"
    ]
    measured = {
        str(m.get("component", "")) for m in intake.get("measurements") or []
    }

    unattributed: list[str] = []
    for note in intake.get("chef_notes") or []:
        text = str(note)
        if not _unmeasured(text):
            continue
        named = [
            str(block.get("title", ""))
            for block in blocks
            if str(block.get("title", ""))
            and _mentions(
                text,
                str(block.get("title", "")),
                [str(a) for a in block.get("aliases") or []],
            )
        ]
        if named:
            ruled_out.update(named)
        else:
            unattributed.append(text)

    for block in blocks:
        title = str(block.get("title", ""))
        if not title or title in measured:
            continue
        own = [str(n) for n in block.get("yield_notes") or []]
        if any(_unmeasured(n) for n in own):
            ruled_out.add(title)
        elif not own and unattributed:
            ruled_out.add(title)

    return ruled_out


def _mentions(text: str, title: str, aliases: list[str] | None = None) -> bool:
    """True when a note names a component by its title or by an alias."""
    stop = {
        "and", "the", "for", "with", "from", "component", "recipe", "dish",
        "batch",
    }
    words = {
        w
        for w in re.split(r"[^A-Za-z]+", title.lower())
        if len(w) > 3 and w not in stop
    }
    # An alias is an explicit name for the component, so it is used verbatim.
    words |= {str(w).lower() for w in (aliases or []) if len(str(w)) > 2}
    if not words:
        return False
    haystack = text.lower()
    return any(word in haystack for word in words)


def _triage(
    candidates: list[dict[str, Any]], policy: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Order the surviving candidates by what matters most to the cook.

    The cap is three questions, so the order decides what the cook is
    asked. A conflict in the supplied material comes first: it changes what
    gets written. A technique fork comes next, because it changes the
    method. A safety gap follows, because it blocks the card. A measured
    yield that is not stated comes last, because the cook can weigh a
    batch later and the card stays blocked until they do — it never crowds
    out a question the cook must answer to write the recipe at all.

    The order is published in the decision table, so the engine and the
    prose cannot drift apart. The order is stable: within a rank, the
    candidates keep the order they were generated in.
    """
    policy = policy or load_policy()
    order = [
        str(entry) for entry in policy.get("question_priority") or []
    ] or [
        "identity_or_quantity_conflict",
        "safety_critical_uncertainty",
        "material_technique_fork",
        "measured_usable_yield",
    ]

    def rank_of(candidate: dict[str, Any]) -> tuple[int, int]:
        category = str(candidate.get("category", ""))
        field = str(candidate.get("field", ""))
        key = category
        if category == "safety_critical_uncertainty" and field == "measured usable yield":
            key = "measured_usable_yield"
        if key in order:
            return (order.index(key), 0)
        return (len(order), 0)

    return sorted(candidates, key=rank_of)


def _never_questions(candidates: list[dict[str, Any]], intake: dict[str, Any]) -> list[str]:
    """Return the candidates that must never reach the cook as questions.

    The three material categories are the only ones that may become a
    question. Inside those categories, a candidate still never reaches the
    cook when it is settled by something already in hand: a supplied
    default, a fact the cook already answered, a question the cook already
    declined, or an instruction the research settles on its own.
    """
    declined = {str(d) for d in intake.get("declined") or []}
    answered = {str(a) for a in intake.get("answered") or []}
    never: list[str] = []

    for candidate in candidates:
        text = candidate["text"]
        if candidate["category"] not in (
            "identity_or_quantity_conflict",
            "material_technique_fork",
            "safety_critical_uncertainty",
        ):
            never.append(text)
        elif text in declined:
            never.append(text)
        elif _declined_key(declined, candidate):
            never.append(text)
        elif _is_answered(candidate, answered):
            # A fact the cook already answered is settled, so it is not
            # asked again. The same resolution the blocker path uses, so
            # the question list and the blocker list cannot disagree
            # about what is settled.
            never.append(text)
        elif candidate["category"] == "identity_or_quantity_conflict" and _unmeasured(text):
            never.append(text)
        elif _settled_by_default(candidate, intake):
            never.append(text)
        elif _settled_by_research(candidate):
            never.append(text)
    return never


def _settled_by_default(candidate: dict[str, Any], intake: dict[str, Any]) -> bool:
    """True when a supplied kitchen default answers this candidate.

    A default record carries the field it covers. When the field it covers is
    the field this candidate is about, the value is already settled, so the
    question is not asked.
    """
    field = str(candidate.get("field", ""))
    if not field:
        return False
    for entry in intake.get("defaults") or []:
        if not isinstance(entry, dict):
            continue
        if not entry.get("confirmed_by"):
            # An unconfirmed entry is a suggestion, not a default.
            continue
        if str(entry.get("field", "")).strip().lower() == field.strip().lower():
            return True
    return False


def _settled_by_research(candidate: dict[str, Any]) -> bool:
    """True when the candidate is about something research settles.

    A question about a routine instruction, a measurement conversion, or a
    comparable recipe's method is answered by the research, not by the cook.
    A candidate that is only a routine instruction never reaches the cook,
    whatever category it was filed under.
    """
    if candidate.get("resolved_by_research"):
        return True
    text = str(candidate.get("text", ""))
    if _routine_technique(text):
        return True
    # A conversion is settled by a reference, not by the cook.
    if candidate.get("category") == "identity_or_quantity_conflict":
        if candidate.get("comparable_dimensions"):
            return True
    return False


def _declined_key(declined: set[str], candidate: dict[str, Any]) -> bool:
    """True when the cook declined this question under a stable key.

    A declined question is recorded as ``component::category`` so the same
    question is never re-asked, whatever wording the next run happens to
    produce for it.
    """
    key = f"{candidate.get('component', '')}::{candidate.get('category', '')}"
    return key in declined


def _routine_items(intake: dict[str, Any]) -> list[str]:
    """Vague instructions that research settles, so they are not questions."""
    routine: list[str] = []
    for component in intake.get("blocks") or []:
        for step in component.get("steps") or []:
            text = str(step.get("text", ""))
            if _routine_technique(text):
                routine.append(text)
        for row in component.get("ingredients") or []:
            text = f"{row.get('name', '')} {row.get('amount', '')}".strip()
            if _routine_technique(text):
                routine.append(text)
    return routine


def _is_answered(candidate: dict[str, Any], answered: set[str]) -> bool:
    """True when the cook has already answered this question.

    The answer is recorded either as the question's own text or as a stable
    key, so a settled question is recognised however it was recorded.

    A safety-critical fact is settled by an answer that names it. The
    candidate carries the field it is about -- the thermal endpoint, the
    holding rule, the measured usable yield -- and the stable key for it
    is ``component::field``. A category-level key cannot tell those
    facts apart, so it never settles a safety-critical fact on its own:
    one answer settles one fact, and a fact the cook never confirmed
    keeps blocking release.
    """
    if str(candidate.get("text", "")) in answered:
        return True
    component = str(candidate.get("component", ""))
    field = str(candidate.get("field", ""))
    if field:
        return f"{component}::{field}" in answered
    key = f"{component}::{candidate.get('category', '')}"
    return key in answered


def _safety_blockers(
    candidates: list[dict[str, Any]],
    intake: dict[str, Any],
    unknown_yields: list[dict[str, str]],
) -> list[str]:
    """Every safety-critical fact that is still unresolved.

    The cap limits how many questions the cook is asked. It does not limit
    what blocks production release: a safety-critical fact the cook has not
    settled blocks release whether or not its question made it into the
    three questions shown.

    A fact the cook answered, or one a confirmed default covers, is settled
    and does not block. A question the cook declined is not asked again,
    but the value stays unknown, so it still blocks release — that is what
    an unknown safety-critical fact means. A measured usable yield the cook
    cannot measure is never asked, and it blocks release for the same
    reason.
    """
    answered = {str(a) for a in intake.get("answered") or []}
    blockers: list[str] = []
    for candidate in candidates:
        if candidate["category"] != "safety_critical_uncertainty":
            continue
        if _is_answered(candidate, answered):
            continue
        if _settled_by_default(candidate, intake):
            continue
        blockers.append(candidate["text"])
    for unknown in unknown_yields:
        blockers.append(
            f"{unknown['component']}: the measured usable yield used for "
            f"production is unknown — {unknown['reason']}."
        )
    return blockers


def _apply_corrections(intake: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply the chef's corrections. The newest statement wins.

    A correction names the ingredient it changes. It is matched against the
    page by product and state, so a correction to "raw shrimp 200 g" never
    lands on a "cooked shrimp" row, and never on an unrelated product that
    happens to share a word.
    """
    corrections: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
    for correction in intake.get("corrections") or []:
        name = str(correction.get("ingredient", ""))
        if not base_name(name):
            continue
        record = {
            "ingredient": name,
            "amount": str(correction.get("amount", "")),
            # The component the correction was made in, and the value it
            # replaces. Both are part of the correction's identity: a
            # correction scoped to one component never reaches another, and
            # the value it replaces picks the row it lands on.
            "component": str(correction.get("component", "")),
            "from": str(correction.get("from", "")),
        }
        corrections.append(record)
        history.append(
            {
                "component": str(correction.get("component", "")),
                "ingredient": name,
                "from": str(correction.get("from", "")),
                "to": str(correction.get("amount", "")),
                "note": str(correction.get("note", "")),
            }
        )
    return corrections, history


def _unknown_yields(intake: dict[str, Any]) -> list[dict[str, str]]:
    """Yields the cook cannot supply. They stay unknown and are not asked."""
    ruled_out = _yields_ruled_out(intake)
    measured = {
        str(m.get("component", "")): str(m.get("value", ""))
        for m in intake.get("measurements") or []
    }
    unknowns: list[dict[str, str]] = []
    for component in intake.get("blocks") or []:
        title = str(component.get("title", ""))
        if not title or title in measured:
            continue
        if component.get("purchased"):
            # A purchased component's yield is its purchase mass. There is
            # nothing to weigh and nothing to leave unknown.
            continue
        if title in ruled_out:
            unknowns.append(
                {
                    "component": title,
                    "label": "unknown",
                    "value": "",
                    "reason": "the cook stated it cannot be measured",
                }
            )
    return unknowns


# ---------------------------------------------------------------- the decision


def decide(intake: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the decision Miseform acts on for one intake.

    ``intake`` is a dictionary built only from what the cook supplied in this
    conversation plus the research the agent gathered. Keys:

    ``activation``        ``{"recipe_supplied": bool}``
    ``dish``              the dish name, when the cook named it
    ``blocks``            the extracted blocks; each may carry ``id``,
                          ``title``, ``kind`` (``component`` or
                          ``separate_recipe``), ``ingredients``,
                          ``steps``, ``method_text``, ``handling_note``,
                          ``purchased``, ``shared_with``, ``forks``
    ``chef_notes``        what the cook said in their own words
    ``corrections``       the cook's later corrections; the newest wins
    ``declined``          questions the cook declined
    ``answered``          questions the cook answered
    ``defaults``          confirmed kitchen defaults the cook supplied;
                          each entry carries the field it covers and who
                          confirmed it
    ``research_sources``  the sources the agent already gathered
    ``requests``          ``{"card": bool, "filing": bool}``
    """
    policy = policy or load_policy()
    requests = intake.get("requests") or {}

    if not (intake.get("activation") or {}).get("recipe_supplied"):
        empty = policy["empty_activation"]
        return {
            "stages": ["START"],
            "reply": empty["reply"],
            "questions": [],
            "questions_dropped": [],
            "questions_never_asked": [],
            "routine_technique_resolved_by_research": [],
            "research": {"components": [], "comparable_technique_sources": 0},
            "map": None,
            "proposal": None,
            "draft": {"written": False, "reason": "no recipe supplied"},
            "filing": {"authorized": False, "ask_again": False},
            "unknowns": [],
            "blockers": [],
            "corrections": [],
        }

    page = _map_page(intake)
    research = _research_plan(page, intake)
    candidates, conversions = _candidate_questions(intake, page)
    never = _never_questions(candidates, intake)
    routine = _routine_items(intake)

    cap = int(policy["supplied_recipe"]["initial_questions_max"])
    surviving = [c for c in candidates if c["text"] not in never]
    kept = _triage(surviving, policy)[:cap]
    kept_texts = {c["text"] for c in kept}
    dropped = [c for c in surviving if c["text"] not in kept_texts]

    corrections_applied, correction_history = _apply_corrections(intake)
    unknown_yields = _unknown_yields(intake)

    proposal = {
        "map": page,
        "supplied_facts": _supplied_facts(intake, corrections_applied),
        "sourced_technique": list(intake.get("research_sources") or []),
        "proposed_choices": list(routine),
        "unknowns": unknown_yields,
        "questions": kept,
        "corrections": correction_history,
        "conversions_resolved_by_research": conversions,
        "closing_question": "Does this method look right, and what should I change?",
    }

    card_requested = bool(requests.get("card"))
    filing_requested = bool(requests.get("filing"))

    blockers: list[str] = _safety_blockers(candidates, intake, unknown_yields)

    return {
        "stages": policy["canonical_path"],
        "reply": None,
        "questions": kept,
        "questions_dropped": dropped,
        "questions_never_asked": never,
        "routine_technique_resolved_by_research": routine,
        "research": research,
        "map": page,
        "proposal": proposal,
        "draft": {
            "written": card_requested,
            "reason": (
                "the cook asked for a card in this request"
                if card_requested
                else "the cook did not ask for a card yet"
            ),
            "permission_ritual_required": False,
            "local_only": True,
        },
        "filing": {
            "authorized": filing_requested,
            "ask_again": False,
            "reason": (
                "the cook's request authorizes filing"
                if filing_requested
                else "no filing request; the artifact stays local"
            ),
        },
        "unknowns": unknown_yields,
        "blockers": blockers,
        "corrections": correction_history,
    }


def _scope_matches(scope: str, component: dict[str, Any]) -> bool:
    """True when a correction's component names this block.

    A correction is scoped by the component it was made in. The scope
    matches the block's title or one of its aliases, compared as written by
    the cook, so "Sesame crumb" and "crumb" name the same component.
    """
    wanted = str(scope or "").strip().lower()
    if not wanted:
        return True
    title = str(component.get("title", "")).strip().lower()
    if wanted == title:
        return True
    return wanted in {
        str(alias).strip().lower() for alias in component.get("aliases") or []
    }


def _correction_targets(
    correction: dict[str, Any],
    entries: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]],
) -> list[dict[str, Any]]:
    """The fact rows a correction lands on.

    A correction names the component it was made in and the ingredient it
    changes. It reaches only the rows of that component, so a correction to
    one component's salt never rewrites another component's salt.

    A correction that names no component is matched by the value it
    replaces: it lands on the row whose amount is the one it says it
    replaces. When it states no replaced value either, it is an
    ingredient-level correction and lands on every row carrying that
    ingredient.
    """
    ingredient = str(correction.get("ingredient", ""))
    matches = [
        entry
        for entry in entries
        if same_ingredient(ingredient, str(entry[1].get("name", "")))
    ]
    if not matches:
        return []

    scope = str(correction.get("component", "")).strip()
    replaced = _amount_key(str(correction.get("from", "")))

    if scope:
        scoped = [entry for entry in matches if _scope_matches(scope, entry[0])]
        if not scoped:
            # The correction names a component the page does not carry, so
            # it changes nothing here rather than landing on another
            # component's row.
            return []
        matches = scoped
        if len(matches) > 1 and replaced is not None:
            narrowed = [
                entry
                for entry in matches
                if _amount_relation(
                    _amount_key(str(entry[1].get("amount", ""))), replaced
                )
                == "same"
            ]
            if narrowed:
                matches = narrowed
        return [entry[2] for entry in matches]

    if replaced is not None:
        narrowed = [
            entry
            for entry in matches
            if _amount_relation(
                _amount_key(str(entry[1].get("amount", ""))), replaced
            )
            == "same"
        ]
        if narrowed:
            matches = narrowed
    return [entry[2] for entry in matches]


def _supplied_facts(
    intake: dict[str, Any], corrections: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The facts the cook supplied, with the newest statement applied.

    A correction is matched to a row by component, product and state. It
    reaches only the rows of the component it was made in, so a correction
    to one component's ingredient never rewrites another component's row of
    the same ingredient. When more than one correction names the same row,
    the last one wins, because the newest chef statement is the record's
    value.
    """
    entries: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for component in intake.get("blocks") or []:
        if str(component.get("kind") or "component") != "component":
            continue
        title = str(component.get("title", ""))
        for row in component.get("ingredients") or []:
            entries.append(
                (
                    component,
                    row,
                    {
                        "component": title,
                        "ingredient": str(row.get("name", "")),
                        "amount": str(row.get("amount", "")),
                        "label": "chef-stated",
                        "corrected": False,
                    },
                )
            )

    for correction in corrections:
        for fact in _correction_targets(correction, entries):
            fact["amount"] = str(correction.get("amount", ""))
            fact["label"] = "chef-stated"
            fact["corrected"] = True

    return [fact for _, _, fact in entries]

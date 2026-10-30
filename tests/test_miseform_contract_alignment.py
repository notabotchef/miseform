"""Stage 1 contract-alignment checks for the Miseform package.

Four focused checks, each standing on its own:

* every file path named in a ``card.schema.json`` description resolves to a
  package file and to a heading that exists;
* every numeric value in the README worked example traces to the quoted
  input or to the shipped example card, and no spoon measure is silently
  converted to grams;
* the ingredient field mapping in ``references/schema.md`` matches the
  executable schema, and percentages and scaling are computed at render
  rather than stored on the card;
* the shipped example card demonstrates the documented notes convention, and
  the model reports a card that breaks it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from card_model import Card, load_card  # noqa: E402

EXAMPLE = ROOT / "examples" / "sesame-salt-garnish.card.json"
SCHEMA = ROOT / "references" / "card.schema.json"

# The promised per-ingredient fields, as ``references/schema.md`` states them,
# and the token that must appear in the ingredient field mapping for each.
PROMISED_FIELDS = {
    "Stable row ID": "stable row id",
    "component": "component",
    "name": "name",
    "brand/specification": "brand",
    "prep state": "prep state",
    "net weight/unit": "net weight",
    "optional measured or source-supported volume/unit": "volume",
    "volume standard": "volume standard",
    "reference scaling %": "scaling",
    "notes and source": "notes",
}


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def strip_links(text: str) -> str:
    """Drop markdown link targets and code spans, keeping the prose."""
    text = re.sub(r"\]\([^)]*\)", "] ", text)
    text = re.sub(r"`[^`]*`", " ", text)
    return text


def numbers(text: str) -> set[float]:
    return {float(match) for match in re.findall(r"\d+(?:\.\d+)?", text)}


def heading_slugs(text: str) -> set[str]:
    slugs: set[str] = set()
    for line in text.splitlines():
        match = re.match(r"^#{1,6}\s+(.*?)\s*$", line)
        if not match:
            continue
        slug = re.sub(r"[^\w\s-]", "", match.group(1).lower())
        slugs.add(re.sub(r"[\s_]+", "-", slug).strip("-"))
    return slugs


def schema_descriptions(node: object) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        description = node.get("description")
        if isinstance(description, str):
            found.append(description)
        for value in node.values():
            found.extend(schema_descriptions(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(schema_descriptions(value))
    return found


def card_numbers(card: Card) -> set[float]:
    """Every quantity the shipped card states or computes."""
    values: set[float] = set()
    for component in card.components:
        for ingredient in component.get("ingredients") or []:
            weight = ingredient.get("weight_g")
            if isinstance(weight, (int, float)):
                values.add(float(weight))
    for key in ("input_total_g", "usable_yield_g", "loss_g", "portion_g"):
        value = card.data.get(key)
        if isinstance(value, (int, float)):
            values.add(float(value))
    portions = card.data.get("portions")
    if isinstance(portions, int):
        values.add(float(portions))
    for percentage in card.derived().percentages.values():
        values.add(round(float(percentage), 6))
    return values


# ------------------------------------------------- schema description paths


def test_every_card_schema_description_resolves_to_a_real_file_and_heading():
    """A description may not point at a file that is not shipped, or at a
    section that does not exist. Each named path must resolve to a package
    file and to a heading inside it."""
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    descriptions = schema_descriptions(schema)
    assert descriptions, "the card schema must carry descriptions to resolve"

    named = re.compile(
        r"([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:md|json|py|html|xlsx|pdf))"
        r"(?:#([A-Za-z0-9_-]+))?"
    )
    checked: list[str] = []
    for description in descriptions:
        for match in named.finditer(description):
            relative, anchor = match.group(1), match.group(2)
            target = ROOT / relative
            assert target.is_file(), f"the card schema names a missing file: {relative}"
            assert anchor, (
                f"the card schema names {relative} without the heading that holds the rule"
            )
            assert anchor in heading_slugs(target.read_text(encoding="utf-8")), (
                f"the card schema names {relative}#{anchor} and that heading does not exist"
            )
            checked.append(f"{relative}#{anchor}")

    assert checked, "the card schema must name the documents it depends on"


# ------------------------------------------------ README example traceability


def test_the_readme_example_states_only_values_that_trace_to_a_source():
    """Every number the worked example states must come from the quoted
    input or from the shipped card, and a spoon measure is never turned
    into a gram production control."""
    readme = read("README.md")
    start = readme.index("## Example intake and response")
    section = readme[start : readme.index("\n## ", start)]

    quoted_input = re.search(r"\*\*Input:\*\*.*?\"([^\"]+)\"", section, re.DOTALL)
    quoted_response = re.search(
        r"\*\*First response:\*\*.*?\"([^\"]+)\"", section, re.DOTALL
    )
    assert quoted_input, "the README example must quote the cook's input"
    assert quoted_response, "the README example must quote the first response"
    source_text = quoted_input.group(1)
    response_text = quoted_response.group(1)

    card = load_card(EXAMPLE)
    card_values = card_numbers(card)
    input_values = numbers(source_text)

    # The cook's own quantities are the card's quantities.
    untraceable_input = sorted(input_values - card_values)
    assert untraceable_input == [], (
        f"the README example input states {untraceable_input}, which the shipped card does not carry"
    )

    # Nothing in the response is a number the cook did not state and the
    # card does not carry.
    untraceable_response = sorted(numbers(response_text) - input_values - card_values)
    assert untraceable_response == [], (
        f"the README example response states {untraceable_response}, which no source supplies"
    )

    # The rest of the example section states card quantities only.
    prose = strip_links(section)
    untraceable_section = sorted(numbers(prose) - input_values - card_values)
    assert untraceable_section == [], (
        f"the README example states {untraceable_section}, which no source supplies"
    )

    # A spoon measure is never silently converted into grams.
    spoon = re.compile(r"\b(?:teaspoons?|tablespoons?|tbsp|tsp|spoons?)\b", re.IGNORECASE)
    assert not spoon.search(response_text), (
        "the README example response must not restate a spoon measure"
    )
    if spoon.search(source_text):
        input_grams = set(re.findall(r"(\d+(?:\.\d+)?)\s*g\b", source_text))
        for amount, portion in re.findall(
            r"(\d+(?:\.\d+)?)\s*g\s+per\s+(\w+)", response_text, re.IGNORECASE
        ):
            assert amount in input_grams, (
                f"the README example converts a spoon measure into {amount} g per {portion}"
            )


# ------------------------------------------- ingredient field mapping check


def test_the_documented_ingredient_mapping_matches_the_executable_schema():
    """``references/schema.md`` states the promised ingredient fields, where
    each one is stored, which ride in the notes string and which are
    computed. The stored set must be exactly the schema's ingredient
    properties, and the card must not carry a computed percentage or a
    stored scaling factor."""
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    ingredient_schema = schema["properties"]["components"]["items"]["properties"][
        "ingredients"
    ]["items"]
    schema_properties = set(ingredient_schema["properties"])
    assert ingredient_schema["additionalProperties"] is False, (
        "the ingredient schema must stay narrow so the notes convention holds"
    )

    contract = read("references/schema.md")
    mapping = contract.split("## Ingredient field mapping", 1)[1].split("\n## ", 1)[0]

    stored: set[str] = set()
    carriers: set[str] = set()
    computed: list[str] = []
    for line in mapping.splitlines():
        if not line.startswith("| ") or line.startswith("|---") or "Promised field" in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 2:
            continue
        where = cells[1]
        if where.startswith("stored"):
            stored.update(re.findall(r"`([A-Za-z0-9_]+)`", where))
        elif where.startswith("rides in"):
            carriers.update(re.findall(r"`([A-Za-z0-9_]+)`", where))
        elif "computed" in where:
            computed.append(cells[0])

    assert stored == schema_properties - carriers, (
        f"the documented stored fields {sorted(stored)} do not match the schema "
        f"properties {sorted(schema_properties)} minus the carriers {sorted(carriers)}"
    )
    assert carriers == {"notes"}, (
        f"the documented carrier must be the notes string, not {sorted(carriers)}"
    )
    assert computed, "the mapping must state which fields are computed at render"

    # Every promised field the contract names is accounted for by the mapping.
    mapping_text = mapping.lower()
    for promised, token in PROMISED_FIELDS.items():
        assert token in mapping_text, (
            f"the ingredient field mapping does not account for {promised!r}"
        )

    # Percentages and scaling are computed at render, never stored.
    card = load_card(EXAMPLE)
    for component in card.components:
        for ingredient in component.get("ingredients") or []:
            stored_keys = set(ingredient)
            assert stored_keys <= schema_properties, (
                f"row {ingredient.get('row_id')} stores {sorted(stored_keys - schema_properties)}, "
                "which the narrow schema does not carry"
            )
            for key in stored_keys:
                assert "percent" not in key and "scal" not in key, (
                    f"row {ingredient.get('row_id')} stores the computed field {key!r}"
                )
            for value in ingredient.values():
                assert not isinstance(value, str) or "%" not in value, (
                    f"row {ingredient.get('row_id')} stores a percentage value"
                )

    derived = card.derived().percentages
    assert derived["I1"] == 100.0 and derived["I2"] == 20.0 and derived["I3"] == 10.0, (
        "the reference percentages must be computed from the stored weights"
    )


# ------------------------------------------- the shipped notes convention


def test_the_shipped_card_demonstrates_the_notes_convention():
    """``examples/sesame-salt-garnish.card.json`` is the demonstration of the
    documented convention: a narrow stored row whose notes carry the volume
    source status, and no card that breaks the convention passes the model."""
    card = load_card(EXAMPLE)
    for component in card.components:
        for ingredient in component.get("ingredients") or []:
            volume = str(ingredient.get("volume") or "")
            notes = str(ingredient.get("notes") or "")
            assert volume.startswith("≈"), (
                f"row {ingredient.get('row_id')} publishes a derived volume and must mark it approximate"
            )
            assert "proxy" in notes.lower(), (
                f"row {ingredient.get('row_id')} must state its source status in notes"
            )
    assert not [
        finding
        for finding in card.findings()
        if finding.code in {"unverified-volume", "volume-source-record-without-volume"}
    ], [str(f) for f in card.findings()]

    # A row that publishes a derived volume without the source status in its
    # notes is reported, not accepted.
    broken = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    broken["components"][0]["ingredients"][0]["notes"] = "Ready-to-use; step 1."
    codes = {finding.code for finding in Card(broken).findings()}
    assert "unverified-volume" in codes, (
        f"a derived volume with no source status must be reported, got {sorted(codes)}"
    )


# ------------------------------------------- one authoritative home


# The four documents that used to restate the same two normative rules. The
# canonical state flow and the review gate now have one home each, and the
# other documents point at it.
CORE_DOCS = ("SKILL.md", "README.md", "TESTING.md", "references/questions.md")


def test_the_core_contract_is_stated_once_and_pointed_at():
    """The canonical state flow and the review gate each have one home.

    The stage bullets and the review-gate rule used to be restated in
    ``SKILL.md``, ``README.md``, ``TESTING.md`` and
    ``references/questions.md``. A rule stated in four places is a rule that
    drifts in four places, so each rule now lives in one document and the
    others link to it. The verbatim question the tests pin still appears
    wherever the test requires it.
    """
    skill = read("SKILL.md")
    readme = read("README.md")
    testing = read("TESTING.md")
    questions = read("references/questions.md")

    # 1. The canonical state flow lives in references/questions.md.
    assert "## The canonical path" in questions, (
        "questions.md must hold the canonical path section"
    )
    for name, text in (("SKILL.md", skill), ("README.md", readme)):
        assert "questions.md#the-canonical-path" in text, (
            f"{name} must point at the canonical path instead of restating it"
        )
        # The per-stage bullet list was the restatement; it must not return.
        for stage in ("START", "EXTRACT", "INTERVIEW", "REVIEW", "BUILD"):
            assert f"**{stage}** —" not in text, (
                f"{name} must not restate the canonical path as stage bullets"
            )

    # 2. The review gate rule lives in the SKILL.md execution contract.
    assert (
        "This review is editorial confirmation of the record, not production "
        "validation and not approval." in skill
    ), "SKILL.md must hold the authoritative review-gate rule"
    for name, text in (
        ("README.md", readme),
        ("TESTING.md", testing),
        ("references/questions.md", questions),
    ):
        # The rule is identified by its concept, not one exact wording, so a
        # paraphrase of it is caught as well as a verbatim copy.
        assert "editorial confirmation of the record" not in text, (
            f"{name} must not restate the review-gate rule; it must link to it"
        )
        assert "SKILL.md" in text, f"{name} must point at the review-gate rule"

    # The canonical question is pinned by the existing tests and stays put.
    question = "Is this correct, and should I generate the cards?"
    for name, text in (
        ("SKILL.md", skill),
        ("README.md", readme),
        ("TESTING.md", testing),
        ("references/questions.md", questions),
    ):
        assert question in text, f"{name} must keep the verbatim review question"

    # The links that replace the restatements must resolve inside the package.
    for rel, text in (("SKILL.md", skill), ("README.md", readme)):
        for target in re.findall(r"\]\((references/[^)#]+\.md)(?:#[^)]*)?\)", text):
            assert (ROOT / target).is_file(), f"{rel} links a missing file: {target}"
    for target in re.findall(r"\]\((\.\./SKILL\.md)\)", questions):
        assert (ROOT / "references" / target).resolve().is_file(), (
            "questions.md links a missing file: SKILL.md"
        )

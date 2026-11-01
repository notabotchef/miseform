"""Counterexample checks for the research-first policy engine.

Every check here is written against a defect that a real run exposed, and
each one names the behaviour it pins. A test that passes for the wrong
reason is a test that has stopped protecting the contract.

Run from the skill directory:

    python3 -m pytest tests/test_miseform_policy_counterexamples.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import intake_policy  # noqa: E402
from intake_policy import (  # noqa: E402
    _amount_key,
    _amount_relation,
    _amounts_differ,
    _classify_preparation,
    _has_holding_rule,
    _has_thermal_endpoint,
    base_name,
    canonical_name,
    decide,
    same_ingredient,
)

FIXTURES = ROOT / "examples" / "fixtures"
REFERENCE = ROOT / "references" / "research-and-clarification.md"
SKILL = ROOT / "SKILL.md"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def component(title: str, **fields) -> dict:
    """A minimal block for a single-component decision."""
    block = {
        "id": "B1",
        "kind": "component",
        "title": title,
        "ingredients": [],
        "steps": [],
        "method_text": [],
        "handling_note": "",
    }
    block.update(fields)
    return block


def intake_of(*blocks: dict, **extra) -> dict:
    payload = {
        "activation": {"recipe_supplied": True},
        "dish": "Test dish",
        "blocks": list(blocks),
        "chef_notes": [],
        "corrections": [],
        "declined": [],
        "answered": [],
        "research_sources": [],
        "requests": {"card": True, "filing": False},
    }
    payload.update(extra)
    return payload


# ------------------------------------------------------- the map keeps material


def test_a_dressing_is_classified_from_its_ingredients_not_its_title():
    """A block whose title does not name the preparation is still classified.

    The map carries the shape of the page. If the classification reads the
    map instead of the supplied block, a component titled "Dressing" that
    contains mayonnaise and is blended into an emulsion is filed as a raw
    assembly, and the research it drives is wrong.
    """
    dressing = component(
        "Dressing",
        ingredients=[
            {"name": "mayonnaise", "amount": "150 g"},
            {"name": "lemon juice", "amount": "20 ml"},
            {"name": "dijon mustard", "amount": "5 g"},
        ],
        method_text=["Whisk the mayonnaise with the lemon juice.", "Blend smooth."],
    )

    # The classification is right when it reads the supplied block.
    assert _classify_preparation(dressing) == "sauce or emulsion"

    # And it is still right after the page has been mapped.
    decision = decide(intake_of(dressing))
    plan = {c["component"]: c for c in decision["research"]["components"]}
    assert plan["Dressing"]["preparation"] == "sauce or emulsion", (
        "the research plan must classify from the supplied material, "
        "not from the mapped summary"
    )


def test_every_mapped_component_keeps_its_own_classification():
    """Two components with different preparations do not collapse into one."""
    sauce = component(
        "Sauce",
        ingredients=[{"name": "mayonnaise", "amount": "150 g"}],
        method_text=["Whisk smooth."],
    )
    garnish = component(
        "Garnish",
        ingredients=[{"name": "panko", "amount": "120 g"}],
        method_text=["Toast until dry and golden."],
    )
    decision = decide(intake_of(sauce, garnish))
    plan = {c["component"]: c["preparation"] for c in decision["research"]["components"]}
    assert plan["Sauce"] == "sauce or emulsion"
    assert plan["Garnish"] == "dry garnish"


# ------------------------------------------------- ingredient identity states


def test_raw_and_cooked_are_different_products():
    """A state word is part of the ingredient, not decoration on it."""
    assert canonical_name("raw shrimp") != canonical_name("cooked shrimp")
    assert not same_ingredient("raw shrimp", "cooked shrimp")
    assert same_ingredient("shrimp", "raw shrimp"), (
        "an unstated state must stay compatible with a stated one"
    )


def test_material_states_are_not_dropped_from_the_identity():
    """The states a cook relies on survive the comparison."""
    for left, right in (
        ("raw shrimp", "cooked shrimp"),
        ("ground cumin", "whole cumin seed"),
        ("salted butter", "unsalted butter"),
        ("olive oil", "canola oil"),
        ("fine salt", "coarse salt"),
        ("heavy cream", "light cream"),
    ):
        assert not same_ingredient(left, right), (
            f"{left!r} and {right!r} are different products and must not collapse"
        )


def test_a_correction_does_not_land_on_a_different_product():
    """A correction applies to the ingredient it names and no other."""
    shrimp = component(
        "Shrimp",
        ingredients=[
            {"name": "raw shrimp", "amount": "200 g"},
            {"name": "cooked shrimp", "amount": "150 g"},
        ],
    )
    intake = intake_of(
        shrimp,
        corrections=[
            {
                "component": "Shrimp",
                "ingredient": "raw shrimp",
                "amount": "250 g",
                "from": "200 g",
                "to": "250 g",
                "note": "chef correction",
            }
        ],
    )
    facts = {
        (f["ingredient"], f["amount"]): f
        for f in decide(intake)["proposal"]["supplied_facts"]
    }
    assert facts[("raw shrimp", "250 g")]["corrected"] is True
    assert facts[("cooked shrimp", "150 g")]["corrected"] is False, (
        "a correction to raw shrimp must not overwrite the cooked shrimp row"
    )


def test_the_base_name_keeps_the_product_and_drops_only_noise():
    """Noise words go; product words stay; state words are held separately."""
    assert base_name("purchased chicken breast") == base_name("chicken breast")
    assert base_name("olive oil") == base_name("canola oil"), (
        "the oil kind is a state, not a separate product word"
    )
    assert canonical_name("olive oil") != canonical_name("canola oil")
    assert not same_ingredient("olive oil", "canola oil")
    assert base_name("raw shrimp") == base_name("shrimp"), (
        "the state is held separately so it can be compared"
    )
    assert canonical_name("raw shrimp") != canonical_name("shrimp")


# -------------------------------------------------------- amount normalisation


def test_a_litre_is_a_thousand_millilitres():
    """A unit is normalised within its dimension, never by letter surgery."""
    assert _amount_key("1 L") == _amount_key("1000 ml")
    assert _amount_key("1 L") != _amount_key("1 ml")
    assert _amount_key("300 ml") == _amount_key("300ml")
    assert _amount_key("300 ml") == _amount_key("300 mL")


def test_a_mass_is_never_read_as_a_volume():
    """Different dimensions are never compared as the same amount.

    A mass and a volume of one ingredient are a conflict, because turning
    one into the other needs a density the cook never supplied. They are
    never treated as the same amount, and never silently converted.
    """
    assert _amount_key("300 g") != _amount_key("300 ml")
    assert _amounts_differ(_amount_key("300 g"), _amount_key("300 ml")), (
        "a mass and a volume of one ingredient is a discrepancy the cook "
        "resolves, because no density was supplied"
    )
    assert _amount_relation(_amount_key("300 g"), _amount_key("300 ml")) == "conflict"
    assert _amounts_differ(_amount_key("25 g"), _amount_key("30 g"))
    assert not _amounts_differ(_amount_key("25 g"), _amount_key("25 g"))


def test_two_volume_conventions_are_a_conversion_not_a_conflict():
    """A reference settles a cup against a millilitre, not the cook."""
    assert (
        _amount_relation(_amount_key("1 cup"), _amount_key("250 ml"))
        == "conversion"
    )
    assert (
        _amount_relation(_amount_key("2 tbsp"), _amount_key("30 ml"))
        == "conversion"
    )
    assert not _amounts_differ(_amount_key("1 cup"), _amount_key("250 ml"))


def test_a_household_volume_is_not_assumed_to_be_a_metric_one():
    """A cup is not 250 ml by assumption."""
    assert _amount_key("1 cup") != _amount_key("250 ml")
    assert _amount_key("1 tbsp") == _amount_key("3 tsp")


def test_a_conflict_is_raised_only_for_the_same_ingredient():
    """Two states of one product, or two products, are not a conflict."""
    same_product = component(
        "Garlic",
        ingredients=[
            {"name": "garlic", "amount": "25 g"},
            {"name": "garlic", "amount": "30 g"},
        ],
    )
    decision = decide(intake_of(same_product))
    categories = [q["category"] for q in decision["questions"]]
    assert "identity_or_quantity_conflict" in categories

    different_products = component(
        "Shrimp",
        ingredients=[
            {"name": "raw shrimp", "amount": "200 g"},
            {"name": "cooked shrimp", "amount": "150 g"},
        ],
    )
    decision = decide(intake_of(different_products))
    categories = [q["category"] for q in decision["questions"]]
    assert "identity_or_quantity_conflict" not in categories, (
        "raw shrimp and cooked shrimp are two products, not one ingredient "
        "given two amounts"
    )


# ----------------------------------------------------------- safety endpoints


def test_a_stirring_time_is_not_a_thermal_endpoint():
    """A duration on its own says nothing about how hot the food got."""
    stirring = component(
        "Sauce",
        ingredients=[{"name": "heavy cream", "amount": "180 ml"}],
        method_text=["Simmer stock and garlic.", "Stir for 1 minute."],
    )
    assert not _has_thermal_endpoint(stirring), (
        "a stirring time must never close the thermal endpoint question"
    )


def test_a_stated_temperature_is_a_thermal_endpoint():
    """A number with a temperature is the cook stating the endpoint."""
    stated = component(
        "Chicken",
        ingredients=[{"name": "chicken breast", "amount": "180 g"}],
        method_text=[],
        handling_note="12 min at 60 C to reach 63 C core.",
    )
    assert _has_thermal_endpoint(stated)


def test_a_stated_cooking_time_with_its_verb_is_an_endpoint():
    """A cooking time the cook stated for the food is an endpoint."""
    roasted = component(
        "Carrots",
        ingredients=[{"name": "carrots", "amount": "500 g"}],
        method_text=["Roast 25 minutes until tender."],
    )
    assert _has_thermal_endpoint(roasted)


def test_vague_cooling_does_not_close_the_holding_question():
    """"Cool on a tray" is a step, not a holding rule."""
    cooling = component(
        "Crumb",
        ingredients=[{"name": "panko", "amount": "120 g"}],
        method_text=["Toast until golden.", "Cool on a tray before the tins."],
    )
    assert not _has_holding_rule(cooling), (
        "cooling on a tray states no limit, so it cannot close the holding "
        "question"
    )


def test_a_stated_holding_limit_is_a_holding_rule():
    """A temperature or a duration with the hold makes a rule."""
    held = component(
        "Chicken",
        ingredients=[{"name": "chicken breast", "amount": "180 g"}],
        handling_note="Hold at 60 C and use within 2 hours.",
    )
    assert _has_holding_rule(held)


def test_safety_uncertainty_is_still_raised_for_a_vague_holding_note():
    """The end-to-end effect of the two checks above."""
    block = component(
        "Creamy garlic emulsion",
        ingredients=[
            {"name": "heavy cream", "amount": "180 ml"},
            {"name": "unsalted butter", "amount": "150 g"},
        ],
        method_text=["Simmer stock, cream and garlic 12 min.", "Cool on a tray."],
    )
    decision = decide(intake_of(block))
    questions = [q for q in decision["questions"] if q["category"] == "safety_critical_uncertainty"]
    assert questions, (
        "a component with no stated holding limit must raise the safety "
        "question even when the method mentions cooling"
    )
    assert decision["blockers"], "an unresolved safety fact blocks release"


# --------------------------------------------------------------- the run bound


def test_the_run_bound_keeps_every_component_in_the_plan():
    """The bound trims research, never components."""
    blocks = [
        component(
            f"Component {index}",
            ingredients=[{"name": "panko", "amount": "120 g"}],
        )
        for index in range(1, 6)
    ]
    decision = decide(intake_of(*blocks))
    plan = decision["research"]
    assert len(plan["components"]) == 5, (
        "every component stays in the research plan; the bound trims the "
        "comparable recipes, not the components"
    )
    assert plan["comparable_technique_sources"] <= plan["technique_source_limit"]


def test_a_purchased_component_stays_in_the_plan_with_no_comparables():
    """A purchased main is carried as supplied, and still appears."""
    purchased = component(
        "Purchased roast chicken",
        purchased=True,
        is_main=True,
        ingredients=[{"name": "purchased roast chicken breast", "amount": "180 g"}],
    )
    other = component(
        "Sauce",
        ingredients=[{"name": "mayonnaise", "amount": "150 g"}],
    )
    decision = decide(intake_of(purchased, other))
    plan = {c["component"]: c for c in decision["research"]["components"]}
    assert "Purchased roast chicken" in plan
    assert plan["Purchased roast chicken"]["comparable_recipes"] == 0
    assert plan["Purchased roast chicken"]["purchased_as_supplied"] is True


# ------------------------------------------------------------- the fixtures


def test_the_shipped_fixtures_still_produce_their_documented_decisions():
    """The counterexample work did not change the shipped outcomes."""
    full = decide(fixture("full-page-intake"))
    assert full["map"]["main"] == "Purchased roast chicken"
    assert len(full["questions"]) <= 3

    correction = decide(fixture("correction-intake"))
    facts = {
        (f["component"], f["ingredient"]): f
        for f in correction["proposal"]["supplied_facts"]
    }
    salt = facts[("Sesame crumb", "fine salt")]
    assert salt["amount"] == "12 g"
    assert salt["corrected"] is True


def test_the_engine_reads_no_host_source():
    """The engine still opens nothing outside the package.

    The check is an AST pass, not a text scan: the module's docstrings name
    the requests it accepts, and a text scan would trip over the word.
    """
    import ast

    source = (ROOT / "scripts" / "intake_policy.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])

    forbidden = {
        "requests", "urllib", "urllib3", "httpx", "socket", "http",
        "subprocess", "multiprocessing", "asyncio",
    }
    assert not (roots & forbidden), f"the engine imports {sorted(roots & forbidden)}"

    # No call opens a file: the only path it reads is the policy document
    # inside the package, resolved from its own location.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "open", "the engine opens no file by hand"
    assert "Path(__file__).resolve().parent.parent" in source


# ------------------------------------------------ the gaps an external review found


def test_a_confirmed_default_settles_the_field_it_covers():
    """A supplied default is read, not re-asked.

    A default record carries the field it covers. When it covers the field
    the question is about, the value is already settled and the question
    does not reach the cook.
    """
    block = component(
        "Creamy garlic emulsion",
        ingredients=[
            {"name": "heavy cream", "amount": "180 ml"},
            {"name": "unsalted butter", "amount": "150 g"},
        ],
        method_text=["Simmer stock, cream and garlic 12 min."],
    )

    # Without the default, the safety question stands.
    without = decide(intake_of(block))
    assert any(
        "holding or cooling rule" in q["text"] for q in without["questions"]
    ), "a component with no stated holding rule raises the safety question"

    # With a confirmed default covering that field, it does not.
    with_default = decide(
        intake_of(
            block,
            defaults=[
                {
                    "id": "holding",
                    "field": "holding or cooling rule",
                    "value": "hold at 60 C, use within 2 hours",
                    "confirmed_by": "chef",
                    "confirmed_at": "2026-11-01",
                }
            ],
        )
    )
    assert not any(
        "holding or cooling rule" in q["text"] for q in with_default["questions"]
    ), "a confirmed default settles the field it covers"
    assert any(
        "holding or cooling rule" in text
        for text in with_default["questions_never_asked"]
    ), "the settled question is recorded as never asked"


def test_an_unconfirmed_default_is_not_a_default():
    """A suggestion with no confirmation is still a question."""
    block = component(
        "Creamy garlic emulsion",
        ingredients=[{"name": "heavy cream", "amount": "180 ml"}],
        method_text=["Simmer stock, cream and garlic 12 min."],
    )
    decision = decide(
        intake_of(
            block,
            defaults=[
                {
                    "id": "holding",
                    "field": "holding or cooling rule",
                    "value": "hold at 60 C",
                    "confirmed_by": "",
                    "confirmed_at": "",
                }
            ],
        )
    )
    assert any(
        "holding or cooling rule" in q["text"] for q in decision["questions"]
    ), "an unconfirmed default must not settle the question"


def test_a_conversion_is_resolved_by_research_not_asked():
    """One ingredient in two dimensions is a conversion, not a conflict."""
    block = component(
        "Sauce",
        ingredients=[{"name": "chicken stock", "amount": "300 ml"}],
        page_notes=[{"ingredient": "chicken stock", "amount": "1 cup"}],
    )
    decision = decide(intake_of(block))
    for question in decision["questions"]:
        assert "chicken stock" not in question["text"], (
            "a conversion between dimensions is settled by research, not "
            "asked of the cook"
        )
    conversions = decision["proposal"]["conversions_resolved_by_research"]
    assert conversions, "the conversion is recorded as resolved by research"
    assert conversions[0]["category"] == "measurement_conversion"


def test_a_conflict_outranks_a_missing_yield_in_the_cap():
    """The cap spends its three questions on what blocks the recipe.

    A measured yield the cook has not weighed blocks the release, but it
    does not change what gets written, and the cook can weigh a batch
    later. It must not displace a conflict that changes the formula.
    """
    conflicted = component(
        "Sauce",
        ingredients=[
            {"name": "garlic", "amount": "25 g"},
            {"name": "garlic", "amount": "30 g"},
            {"name": "heavy cream", "amount": "180 ml"},
        ],
        method_text=["Simmer stock, cream and garlic 12 min."],
    )
    decision = decide(intake_of(conflicted))
    categories = [q["category"] for q in decision["questions"]]
    assert "identity_or_quantity_conflict" in categories, (
        "a conflict that changes the formula must survive the cap"
    )
    texts = [q["text"] for q in decision["questions"]]
    conflict_index = next(
        index
        for index, text in enumerate(texts)
        if "garlic" in text
    )
    yield_positions = [
        index for index, text in enumerate(texts) if "measured usable yield" in text
    ]
    for position in yield_positions:
        assert position > conflict_index, (
            "a missing measured yield must never outrank a conflict that "
            "changes the formula"
        )


def test_a_missing_thermal_endpoint_outranks_a_missing_yield():
    """The safety gap that changes the method comes first."""
    block = component(
        "Creamy garlic emulsion",
        ingredients=[{"name": "heavy cream", "amount": "180 ml"}],
        method_text=["Simmer stock, cream and garlic 12 min."],
    )
    decision = decide(intake_of(block))
    texts = [q["text"] for q in decision["questions"]]
    endpoint_questions = [t for t in texts if "thermal endpoint" in t]
    yield_questions = [t for t in texts if "measured usable yield" in t]
    if endpoint_questions and yield_questions:
        assert texts.index(endpoint_questions[0]) < texts.index(yield_questions[0])


def test_the_published_table_drives_the_question_order():
    """The order the engine uses is the order the reference publishes."""
    policy = intake_policy.load_policy()
    order = policy["question_priority"]
    assert order[0] == "identity_or_quantity_conflict"
    assert order[-1] == "measured_usable_yield", (
        "a missing measured yield ranks last, so it never displaces a "
        "question the cook must answer to write the recipe at all"
    )
    assert order.index("safety_critical_uncertainty") < order.index(
        "material_technique_fork"
    ), (
        "a safety-critical gap outranks a technique fork: a fork changes the "
        "method, an unstated endpoint or holding rule is unknown and blocks "
        "release"
    )
    assert policy["defaults"]["settles_the_field_it_covers"] is True
    assert policy["defaults"]["unconfirmed_is_a_proposal"] is True


def test_the_contract_states_that_the_cap_does_not_limit_the_blockers():
    """The prose says what the engine does about the cap and the blockers."""
    reference = REFERENCE.read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8")
    assert "The cap limits the questions, not the blockers" in reference
    assert "not the blockers" in skill, (
        "SKILL.md must say that the cap limits the questions, not the "
        "blockers"
    )
    assert "safety-critical gap in\nthe method, then a material technique fork" in (
        reference
    ), "the reference must publish the order the engine triages by"


def test_a_grade_does_not_split_one_oil_into_two_products():
    """A written grade is folded in before the comparison.

    "extra virgin olive oil" written as two words is one oil with a grade,
    not a different product, and it must still compare against "olive oil".
    """
    assert base_name("extra virgin olive oil") == base_name("olive oil")
    assert same_ingredient("extra virgin olive oil", "olive oil")
    assert not same_ingredient("extra virgin olive oil", "refined olive oil")


def test_the_noise_words_are_noise():
    """Words that describe the ingredient without changing it are dropped."""
    assert same_ingredient("chicken breast", "boneless skinless chicken breast")
    assert same_ingredient("unsalted butter", "butter")
    assert same_ingredient("fine salt", "salt")
    assert same_ingredient("heavy cream", "cream")
    assert same_ingredient("roasted sesame", "toasted sesame")


def test_the_proposal_labels_a_correction_as_a_chef_statement():
    """A corrected value carries the chef's label, not a derived one."""
    crumb = component(
        "Sesame crumb",
        ingredients=[{"name": "fine salt", "amount": "8 g"}],
    )
    decision = decide(
        intake_of(
            crumb,
            corrections=[
                {
                    "component": "Sesame crumb",
                    "ingredient": "fine salt",
                    "amount": "12 g",
                    "from": "8 g",
                    "to": "12 g",
                    "note": "chef correction",
                }
            ],
        )
    )
    fact = decision["proposal"]["supplied_facts"][0]
    assert fact["amount"] == "12 g"
    assert fact["label"] == "chef-stated"
    assert fact["corrected"] is True
    assert decision["proposal"]["corrections"][0]["from"] == "8 g"
    assert decision["proposal"]["corrections"][0]["to"] == "12 g"


# ------------------------------------------- the corrections an external review found


def test_a_component_scoped_correction_stays_in_its_component():
    """A correction to one component's salt never rewrites another's.

    The page carries salt in two components. A correction scoped to the
    sauce changes the sauce's salt and leaves the crumb's salt alone. When
    the correction is not scoped, the value it replaces picks the row.
    """
    sauce = component(
        "Sauce",
        ingredients=[{"name": "fine salt", "amount": "5 g"}],
    )
    crumb = component(
        "Sesame crumb",
        ingredients=[{"name": "fine salt", "amount": "10 g"}],
    )

    scoped = decide(
        intake_of(
            sauce,
            crumb,
            corrections=[
                {
                    "component": "Sauce",
                    "ingredient": "fine salt",
                    "amount": "6 g",
                    "from": "5 g",
                    "to": "6 g",
                }
            ],
        )
    )
    facts = {
        (f["component"], f["ingredient"]): f
        for f in scoped["proposal"]["supplied_facts"]
    }
    assert facts[("Sauce", "fine salt")]["amount"] == "6 g"
    assert facts[("Sauce", "fine salt")]["corrected"] is True
    assert facts[("Sesame crumb", "fine salt")]["amount"] == "10 g", (
        "a correction scoped to the sauce must not rewrite the crumb's salt"
    )
    assert facts[("Sesame crumb", "fine salt")]["corrected"] is False

    # An unscoped correction is matched by the value it replaces, so it
    # lands on the row whose amount it says it replaces.
    unscoped = decide(
        intake_of(
            sauce,
            crumb,
            corrections=[
                {
                    "component": "",
                    "ingredient": "fine salt",
                    "amount": "11 g",
                    "from": "10 g",
                    "to": "11 g",
                }
            ],
        )
    )
    facts = {
        (f["component"], f["ingredient"]): f
        for f in unscoped["proposal"]["supplied_facts"]
    }
    assert facts[("Sesame crumb", "fine salt")]["amount"] == "11 g"
    assert facts[("Sauce", "fine salt")]["amount"] == "5 g"


def test_a_correction_naming_an_unknown_component_changes_nothing():
    """A correction for a component the page does not carry lands nowhere."""
    crumb = component(
        "Sesame crumb",
        ingredients=[{"name": "fine salt", "amount": "8 g"}],
    )
    decision = decide(
        intake_of(
            crumb,
            corrections=[
                {
                    "component": "Sauce",
                    "ingredient": "fine salt",
                    "amount": "12 g",
                    "from": "8 g",
                    "to": "12 g",
                }
            ],
        )
    )
    fact = decision["proposal"]["supplied_facts"][0]
    assert fact["amount"] == "8 g", (
        "a correction scoped to a component that is not on the page must not "
        "rewrite the row of another component"
    )
    assert fact["corrected"] is False


def test_a_safety_gap_is_a_blocker_even_when_the_cap_crowds_it_out():
    """The cap limits the questions, not the blockers.

    Three technique forks compete for the three question slots with one
    safety-critical gap. The gap is asked before the forks, and it blocks
    release whether or not it made it into the questions shown.
    """
    chicken = component(
        "Chicken",
        ingredients=[{"name": "raw chicken breast", "amount": "1 kg"}],
        method_text=["Marinate and cook."],
    )
    forks = [
        component(
            f"Prep {index}",
            ingredients=[{"name": "panko", "amount": "120 g"}],
            forks=[{"text": f"Fork number {index}: two credible routes."}],
        )
        for index in range(1, 4)
    ]

    decision = decide(intake_of(chicken, *forks))

    assert len(decision["questions"]) <= 3, "the cap is still three questions"
    texts = [q["text"] for q in decision["questions"]]
    assert any("thermal endpoint" in text for text in texts), (
        "a safety-critical gap outranks a technique fork in the cap"
    )
    assert sum("Fork number" in text for text in texts) <= 2, (
        "the forks fill what is left of the cap"
    )
    assert decision["blockers"], (
        "a safety-critical gap blocks release even when the cap crowds its "
        "question out"
    )
    assert any("thermal endpoint" in b for b in decision["blockers"])


def test_an_unanswered_safety_gap_blocks_release_even_when_it_is_not_asked():
    """A declined safety question is never asked again and still blocks.

    The cook declined the question, so the value stays unknown. An unknown
    safety-critical fact blocks production release.
    """
    chicken = component(
        "Chicken",
        ingredients=[{"name": "raw chicken breast", "amount": "1 kg"}],
        method_text=["Marinate and cook."],
    )
    decision = decide(
        intake_of(
            chicken,
            declined=["Chicken::safety_critical_uncertainty"],
        )
    )
    for question in decision["questions"]:
        assert "thermal endpoint" not in question["text"]
    assert any(
        "thermal endpoint" in text for text in decision["questions_never_asked"]
    )
    assert any("thermal endpoint" in b for b in decision["blockers"]), (
        "a declined safety question leaves the value unknown, and an "
        "unknown safety-critical fact blocks release"
    )


def test_a_measured_yield_does_not_block_when_the_cook_weighed_it():
    """A settled fact is not a blocker."""
    crumb = component(
        "Sesame crumb",
        ingredients=[{"name": "panko", "amount": "120 g"}],
    )
    decision = decide(
        intake_of(
            crumb,
            measurements=[
                {
                    "component": "Sesame crumb",
                    "kind": "measured usable yield",
                    "value": "118 g",
                }
            ],
        )
    )
    assert not any("measured usable yield" in b for b in decision["blockers"])


def test_an_unmeasurable_yield_blocks_release_without_being_asked():
    """A yield the cook cannot measure stays unknown, and unknown blocks.

    It is never a question, and it is never invented.
    """
    crumb = component(
        "Sesame crumb",
        ingredients=[{"name": "panko", "amount": "120 g"}],
        yield_notes=["I have not weighed the tins."],
    )
    decision = decide(intake_of(crumb))
    for question in decision["questions"]:
        assert "yield" not in question["text"].lower()
    assert any("measured usable yield" in b for b in decision["blockers"]), (
        "an unmeasured usable yield blocks production release"
    )
    unknown = next(u for u in decision["unknowns"] if u["component"] == "Sesame crumb")
    assert unknown["value"] == ""
    assert unknown["label"] == "unknown"

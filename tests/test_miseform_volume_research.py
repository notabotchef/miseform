"""Ticket 02 checks: automatic volume research and honest recipe data.

Eight behaviours, each standing on its own:

* a derived measure comes from the authoritative grams and the source's own
  ratio, and a tiny mass still yields a usable measure;
* two salts with different densities do not collapse into one figure, and a
  raw item is never converted from a cooked chart;
* a cup is published in the convention it was sourced in, including a
  250 mL cup, which is not a US cup;
* an ingredient with no established density stays unresolved, with a reason,
  and the card reports the missing research rather than a blank cell;
* a quantity the cook supplied in their own unit stays that quantity, in
  quarts or in counts;
* an unmeasured yield stays unknown;
* a formula row scales from the base it was written against, and a corrected
  quantity changes the numbers it produces;
* every export carries the same numbers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import volume_research  # noqa: E402
from card_model import Card, load_card  # noqa: E402
from exporter import export_xlsx  # noqa: E402
from render_html import render_html  # noqa: E402
from render_markdown import render_markdown  # noqa: E402
from volume_research import (  # noqa: E402
    SourceCache,
    apply_research,
    load_sources,
    research_volume,
)

EXAMPLE = ROOT / "examples" / "sesame-salt-garnish.card.json"


@pytest.fixture()
def sources():
    """The synthetic example catalogue the engine ships with."""
    return load_sources()


def base_card() -> dict:
    """A minimal synthetic card the tests mutate."""
    return {
        "recipe_id": "TEST-002",
        "title": "TEST CARD",
        "version": "v0.1",
        "revision_date": "2026-11-01",
        "status": "NEEDS CHEF CONFIRMATION",
        "release_blockers": ["Nothing has been cooked yet."],
        "recipe_type": "component",
        "intro": "Synthetic card used by the ticket 02 checks.",
        "facts": {
            "time_total": "1 minute",
            "time_active": "1 min",
            "time_inactive": "0 min",
            "difficulty_level": "Basic",
            "difficulty_technique": "Weighing",
            "yield_summary": "Not measured",
            "yield_portions": "",
            "storage_summary": "Not supplied",
            "storage_reference": "Not supplied",
        },
        "equipment": "A scale.",
        "allergens": "None asserted.",
        "percentage_basis": {
            "basis_label": "Sesame = 100% = 100 g.",
            "reference_row_id": "I1",
            "reference_weight_g": 100,
        },
        "process_controls": {
            "sous_vide": "N/A - no heat step",
            "combi": "N/A - no oven step",
            "fermentation": "N/A - no culture",
            "pickling": "N/A - no acid",
            "reduction": "N/A - no evaporation",
            "emulsification": "N/A - no emulsion",
            "chilling": "N/A - not chilled",
            "smoking": "N/A - no smoke",
        },
        "components": [
            {
                "name": "Test component",
                "reference_row_id": "I1",
                "reference_weight_g": 100,
                "ingredients": [
                    {
                        "row_id": "I1",
                        "name": "Sesame seeds",
                        "weight_g": 100,
                        "notes": "Synthetic row.",
                    }
                ],
            }
        ],
        "input_total_g": 100,
        "usable_yield_g": None,
        "loss_g": None,
        "portion_g": None,
        "portions": None,
        "stages": [
            {
                "name": "PREP",
                "steps": [
                    {
                        "number": 1,
                        "text": "Weigh the sesame (I1).",
                        "ingredient_refs": ["I1"],
                    }
                ],
            }
        ],
        "notes": [],
        "release_checklist": [],
        "provenance": {
            "evidence": "Synthetic fixture.",
            "validation": "Not cooked.",
            "filing": "Local only.",
        },
        "batch_factor": 1,
    }


def codes(card: Card) -> set[str]:
    return {finding.code for finding in card.findings()}


# ------------------------------------------------- the derived measure


def test_one_gram_of_xanthan_still_yields_a_usable_measure(sources):
    """A tiny mass is a real quantity, not a rounding accident.

    One gram of xanthan is a third of a teaspoon. It must not round to
    zero, and it must not be published as a cup.
    """
    result = research_volume("xanthan gum", 1, state="powder", sources=sources)
    assert result.status == "derived", result.unresolved_reason
    assert result.unit == "tsp"
    assert result.amount == pytest.approx(0.33, abs=0.01)
    assert result.volume.startswith("≈ ")
    assert "(US)" in result.volume


def test_two_salts_with_different_densities_do_not_collapse(sources):
    """Table salt and kosher salt are different products.

    The same 10 g occupies a very different volume in each, so the engine
    must not answer one salt question with the other's figure.
    """
    table = research_volume("salt", 10, state="table salt", sources=sources)
    kosher = research_volume("salt", 10, state="kosher salt", sources=sources)

    assert table.status == "derived"
    assert kosher.status == "derived"
    assert table.amount != kosher.amount
    assert table.provenance["source_title"] != kosher.provenance["source_title"]
    assert kosher.provenance["proxy"] is False
    assert table.provenance["proxy"] is True


def test_a_raw_item_is_not_converted_from_a_cooked_chart(sources):
    """Raw and cooked are different products.

    A chart that covers a cooked item cannot be applied to a raw one
    without saying so, and Miseform does not say so.
    """
    result = research_volume("mussel", 500, state="raw", sources=sources)
    assert result.status == "unresolved"
    assert "raw" in result.unresolved_reason
    assert result.attempts
    assert result.attempts[0]["outcome"] == "rejected"


def test_a_250_ml_cup_is_not_published_as_a_us_cup(sources):
    """The convention travels with the measure.

    A 250 mL cup is the metric and Australian cup. Publishing it as a US
    cup would be wrong by six percent.
    """
    result = research_volume(
        "sourdough starter", 500, state="ripe", sources=sources
    )
    assert result.status == "derived"
    assert result.unit_convention == "US"

    metric_source = volume_research.VolumeSource(
        ingredient="sourdough starter",
        aliases=("levain",),
        state="ripe",
        brand=None,
        tier="chart",
        url="https://example.invalid/miseform/metric-cup",
        title="Example Metric Cup Chart (synthetic)",
        accessed="2026-11-01",
        original_ratio="1 cup (250 mL) = 230 g",
        amount=1,
        unit="cup",
        unit_convention="metric",
        grams=230,
        state_match="ingredient and state match",
        proxy=False,
        confidence="high",
    )
    metric = research_volume(
        "sourdough starter", 500, state="ripe", sources=[metric_source]
    )
    assert metric.status == "derived"
    assert metric.unit_convention == "metric"
    assert "(metric)" in metric.volume
    assert "(US)" not in metric.volume


def test_an_unknown_density_stays_unresolved_with_a_reason(sources):
    """No source, no number.

    An ingredient nobody could source stays unresolved, and the reason says
    what was looked for.
    """
    result = research_volume("unobtainium powder", 25, state="dry", sources=sources)
    assert result.status == "unresolved"
    assert "no ingredient-specific" in result.unresolved_reason
    assert result.volume is None


def test_a_card_without_research_reports_the_missing_research():
    """A mass with no volume and no research record is a finding.

    The card may not ship a blank cell that reads as if nothing was needed.
    """
    card = Card(base_card())
    found = codes(card)
    assert "volume-research-missing" in found


def test_an_unresolved_volume_records_its_reason():
    """A researched-but-unresolved row is honest, and it says why."""
    data = base_card()
    data["components"][0]["ingredients"][0]["volume_source"] = {
        "status": "unresolved",
        "unresolved_reason": "No ingredient-specific source matched.",
    }
    card = Card(data)
    assert "volume-research-missing" not in codes(card)
    assert "unresolved-volume-without-reason" not in codes(card)


def test_an_unresolved_volume_without_a_reason_is_reported():
    data = base_card()
    data["components"][0]["ingredients"][0]["volume_source"] = {"status": "unresolved"}
    assert "unresolved-volume-without-reason" in codes(Card(data))


def test_a_derived_volume_without_a_named_convention_is_reported():
    data = base_card()
    data["components"][0]["ingredients"][0]["volume"] = "≈ 11.3 tbsp"
    data["components"][0]["ingredients"][0]["volume_source"] = {
        "status": "derived",
        "source_url": "https://example.invalid/chart",
        "original_ratio": "1/2 US cup = 35.5 g",
        "unit_convention": None,
    }
    assert "volume-convention-unstated" in codes(Card(data))


def test_research_fills_the_volume_and_the_structured_record(sources):
    """Research writes the measure and the provenance, and both travel."""
    data = base_card()
    data, records = apply_research(data, sources=sources)
    row = data["components"][0]["ingredients"][0]

    assert row["volume"].startswith("≈ ")
    source = row["volume_source"]
    assert source["status"] == "derived"
    assert source["source_url"]
    assert source["original_ratio"]
    assert source["accessed"]
    assert source["unit_convention"] == "US"
    assert source["proxy"] is True
    assert source["state_match"]
    assert source["confidence"]
    assert records and records[0]["row_id"] == "I1"
    assert "proxy" in row["notes"].lower()


def test_the_source_cache_is_state_and_brand_aware(tmp_path, sources):
    """A cached reference is reused, and never for another product."""
    cache = SourceCache(tmp_path / "cache.json")

    first = research_volume(
        "salt", 10, state="table salt", sources=sources, cache=cache
    )
    assert first.status == "derived"
    assert cache.path.exists()

    again = research_volume(
        "salt", 10, state="table salt", sources=sources, cache=cache
    )
    assert again.status == "derived"
    assert "reused from the source cache" in again.attempts[0]["reason"]

    # The same ingredient in another state is a different key, so the
    # cached table-salt figure is not handed back for kosher salt.
    other = research_volume(
        "salt", 10, state="kosher salt", sources=sources, cache=cache
    )
    assert other.provenance["source_title"] != first.provenance["source_title"]


def test_a_nutrition_fat_figure_is_never_read_as_the_serving_weight(sources):
    """A fat line is not the total weight of the serving."""
    fat_source = volume_research.VolumeSource(
        ingredient="butter",
        aliases=("unsalted butter",),
        state="before browning",
        brand=None,
        tier="usda",
        url="https://example.invalid/miseform/butter-nutrition",
        title="Example Butter Nutrition Panel (synthetic)",
        accessed="2026-11-01",
        original_ratio="total fat 11 g per serving",
        amount=1,
        unit="tbsp",
        unit_convention="US",
        grams=11,
        state_match="ingredient matches",
        proxy=False,
        confidence="high",
        measure="fat_grams",
    )
    result = research_volume(
        "butter", 100, state="before browning", sources=[fat_source]
    )
    assert result.status == "unresolved"
    assert "fat_grams" in result.unresolved_reason


def test_grams_are_never_assumed_to_be_millilitres(sources):
    """No density, no volume.

    Water is the one ingredient whose cup weight a source states; an
    ingredient nobody sourced stays unresolved rather than becoming a cup
    of water's density.
    """
    result = research_volume("salt", 6, state="table salt", sources=sources)
    assert result.status == "derived"
    assert result.amount != pytest.approx(6 / 236.588, abs=0.01)


# ------------------------------------------- quantities the cook supplied


def test_a_quart_the_cook_supplied_stays_a_quart():
    """A supplied quantity is not converted into a mass without a source."""
    data = base_card()
    row = data["components"][0]["ingredients"][0]
    row.pop("weight_g")
    row["quantity"] = {
        "amount": 2,
        "unit": "quart",
        "kind": "volume",
        "convention": "US",
        "original": "2 qt",
    }
    row["notes"] = "Quantity not supplied in grams."
    card = Card(data)

    assert "volume-research-missing" not in codes(card)
    assert card.resolved_weights()["I1"] is None
    # The input sum no longer claims the row's mass.
    data["input_total_g"] = 100
    assert "input-total-mismatch" in codes(card)


def test_a_count_the_cook_supplied_stays_a_count():
    data = base_card()
    row = data["components"][0]["ingredients"][0]
    row.pop("weight_g")
    row["quantity"] = {"amount": 3, "unit": "ea", "kind": "count"}
    row["notes"] = "Counted, not weighed."
    card = Card(data)

    assert card.resolved_weights()["I1"] is None
    assert "volume-research-missing" not in codes(card)


def test_pounds_convert_to_metric_and_keep_the_original():
    """Five pounds is 2268 g, and the card still says five pounds."""
    grams = volume_research.to_grams(5, "lb")
    assert grams == pytest.approx(2267.96, abs=0.01)
    assert volume_research.to_grams(5, "cups") is None


def test_the_editions_show_a_supplied_quantity_in_the_cooks_unit():
    data = base_card()
    row = data["components"][0]["ingredients"][0]
    row.pop("weight_g")
    row["quantity"] = {"amount": 2, "unit": "quart", "kind": "volume", "convention": "US"}
    card = Card(data)

    markdown = render_markdown(card)
    markup = render_html(card)
    assert "2 quart (US)" in markdown
    assert "2 quart (US)" in markup


# ------------------------------------------------------ yield and formulas


def test_an_unmeasured_yield_stays_unknown():
    """Nothing came out of a pot that was never weighed."""
    card = Card(base_card())
    assert card.data["usable_yield_g"] is None
    assert card.derived().loss_g is None
    assert card.derived().portions is None


def test_a_percentage_row_scales_from_its_base():
    """A 2/2/1 fermentation formula follows the base it was written against."""
    data = base_card()
    data["components"][0]["ingredients"] = [
        {"row_id": "I1", "name": "Cabbage", "weight_g": 1000, "notes": "Base."},
        {
            "row_id": "I2",
            "name": "Salt",
            "formula": {"kind": "percent", "basis_row_id": "I1", "value": 2},
            "notes": "2% of the cabbage.",
        },
        {
            "row_id": "I3",
            "name": "Garlic",
            "formula": {"kind": "percent", "basis_row_id": "I1", "value": 2},
            "notes": "2% of the cabbage.",
        },
        {
            "row_id": "I4",
            "name": "Gochugaru",
            "formula": {"kind": "percent", "basis_row_id": "I1", "value": 1},
            "notes": "1% of the cabbage.",
        },
    ]
    data["input_total_g"] = 1050
    card = Card(data)

    resolved = card.resolved_weights()
    assert resolved["I2"] == pytest.approx(20.0)
    assert resolved["I3"] == pytest.approx(20.0)
    assert resolved["I4"] == pytest.approx(10.0)
    assert card.derived().input_total_g == pytest.approx(1050.0)

    # Doubling the cabbage doubles every percentage row with it.
    scaled = card.scaled_weights(2)
    assert scaled["I2"] == pytest.approx(40.0)
    assert scaled["I4"] == pytest.approx(20.0)


def test_a_formula_against_a_missing_row_is_reported():
    data = base_card()
    data["components"][0]["ingredients"].append(
        {
            "row_id": "I2",
            "name": "Salt",
            "formula": {"kind": "percent", "basis_row_id": "I9", "value": 2},
            "notes": "2% of a row that is not here.",
        }
    )
    assert "formula-basis-missing" in codes(Card(data))


def test_a_formula_against_an_unknown_base_stays_unknown():
    data = base_card()
    data["components"][0]["ingredients"] = [
        {"row_id": "I1", "name": "Cabbage", "notes": "Not weighed."},
        {
            "row_id": "I2",
            "name": "Salt",
            "formula": {"kind": "percent", "basis_row_id": "I1", "value": 2},
            "notes": "2% of the cabbage.",
        },
    ]
    data["input_total_g"] = 100
    card = Card(data)
    assert card.resolved_weights()["I2"] is None
    assert "formula-unresolved" in codes(card)


def test_a_corrected_quantity_changes_the_numbers_it_produces():
    """A correction is a new fact, and the arithmetic follows it."""
    data = base_card()
    data["components"][0]["ingredients"][0]["weight_g"] = 100
    data["input_total_g"] = 100
    card = Card(data)
    assert card.derived().input_total_g == pytest.approx(100.0)

    corrected = json.loads(json.dumps(data))
    corrected["components"][0]["ingredients"][0]["weight_g"] = 250
    corrected["input_total_g"] = 250
    fixed = Card(corrected)
    assert fixed.derived().input_total_g == pytest.approx(250.0)

    # The percentage basis is still stated at 100 g, so the reference no
    # longer matches its row and the card says so.
    assert "reference-weight-mismatch" in codes(fixed)

    # Correcting the basis as well keeps the card consistent.
    consistent = json.loads(json.dumps(corrected))
    consistent["components"][0]["reference_weight_g"] = 250
    consistent["percentage_basis"]["reference_weight_g"] = 250
    consistent["percentage_basis"]["basis_label"] = "Sesame = 100% = 250 g."
    settled = Card(consistent)
    assert settled.derived().percentages["I1"] == pytest.approx(100.0)
    assert "reference-weight-mismatch" not in codes(settled)
    assert "input-total-mismatch" not in codes(settled)


def test_a_scaled_volume_follows_the_scaled_grams(sources):
    """A scaled batch does not keep the base measure."""
    data = base_card()
    data, _ = apply_research(data, sources=sources)
    card = Card(data)

    base_volume = card.scaled_volumes(1)["I1"]
    doubled = card.scaled_volumes(2)["I1"]
    assert base_volume != doubled
    assert doubled.startswith("≈ ")

    row = data["components"][0]["ingredients"][0]
    grams_per_unit = row["volume_source"]["grams_per_unit"]
    expected = 200.0 / grams_per_unit
    amount = float(doubled.split()[1])
    assert amount == pytest.approx(expected, rel=0.01)


def test_a_measured_volume_is_not_scaled():
    data = base_card()
    row = data["components"][0]["ingredients"][0]
    row["volume"] = "1 cup (US), measured"
    row["volume_source"] = {
        "status": "measured",
        "unit": "cup",
        "unit_convention": "US",
        "grams_per_unit": 71,
        "source_url": "https://example.invalid/measured",
        "original_ratio": "measured in the kitchen",
    }
    card = Card(data)
    assert card.scaled_volumes(2) == {}


# ------------------------------------------------ linked components


def test_a_linked_component_is_not_restated_or_counted_twice():
    data = base_card()
    data["components"].append(
        {
            "name": "Shared sauce",
            "linked": {"component_id": "CMP-001", "version": "v0.2", "quantity_g": 250},
        }
    )
    card = Card(data)

    assert len(card.linked_components) == 1
    assert card.derived().input_total_g == pytest.approx(100.0)
    assert "linked-version-missing" not in codes(card)
    assert "linked-component-duplicated" not in codes(card)


def test_a_linked_component_without_a_version_is_reported():
    data = base_card()
    data["components"].append(
        {"name": "Shared sauce", "linked": {"component_id": "CMP-001"}}
    )
    assert "linked-version-missing" in codes(Card(data))


def test_a_linked_component_that_is_restated_is_reported():
    data = base_card()
    data["components"].append(
        {
            "name": "Shared sauce",
            "linked": {"component_id": "CMP-001", "version": "v0.2"},
            "ingredients": [{"row_id": "S1", "name": "Stock", "weight_g": 250}],
        }
    )
    assert "linked-component-restated" in codes(Card(data))


def test_gross_purchase_mass_is_not_the_edible_mass():
    """What was bought and what went in are two numbers."""
    data = base_card()
    data["components"][0]["gross_purchase_g"] = 120
    card = Card(data)
    assert "edible-exceeds-purchase" not in codes(card)

    data["components"][0]["gross_purchase_g"] = 50
    assert "edible-exceeds-purchase" in codes(Card(data))


# ------------------------------------------------------------ export parity


def test_every_export_carries_the_same_numbers(tmp_path, sources):
    """The four editions agree on the numbers they publish."""
    data = base_card()
    data, _ = apply_research(data, sources=sources)
    card = Card(data)

    markdown = render_markdown(card)
    markup = render_html(card)
    out = tmp_path / "card.xlsx"
    result = export_xlsx(card, out)
    assert result.ok, result.detail

    import openpyxl

    values = openpyxl.load_workbook(out, data_only=True)["Recipe Card"]

    volume = card.ingredients[0]["volume"]
    assert volume in markdown
    assert volume in markup
    assert any(
        cell.value == volume for row in values.iter_rows() for cell in row
    ), "the volume must reach the workbook"

    weight = card.resolved_weights()["I1"]
    assert f"{weight:g} g" in markdown
    assert f"{weight:g} g" in markup

    total = card.derived().input_total_g
    assert any(
        cell.value == pytest.approx(total) for row in values.iter_rows() for cell in row
    ), "the input total must reach the workbook"


def test_the_shipped_example_card_still_passes_every_check():
    """The published example is unchanged by this work."""
    card = load_card(EXAMPLE)
    assert card.schema_errors() == []
    blockers = [f for f in card.findings() if f.severity == "blocker"]
    assert blockers == [], [str(f) for f in blockers]


def test_the_engine_reproduces_the_shipped_examples_published_measures(sources):
    """The engine and the hand-worked example agree.

    The example card publishes 11.3 tbsp for 100 g of sesame, 2.25 tbsp for
    20 g and 1.7 tsp for 10 g of salt. Researching the same rows from the
    catalogue must land on the same numbers, so the automated step and the
    worked example cannot drift apart.
    """
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    for ing in data["components"][0]["ingredients"]:
        ing.pop("volume", None)
        ing.pop("volume_source", None)

    researched, _ = apply_research(data, sources=sources)
    published = {
        ing["row_id"]: ing.get("volume")
        for ing in researched["components"][0]["ingredients"]
    }
    assert published["I1"] == "≈ 11.3 tbsp (US)"
    assert published["I2"] == "≈ 2.25 tbsp (US)"
    assert published["I3"] == "≈ 1.7 tsp (US)"

    card = Card(researched)
    assert card.schema_errors() == []
    assert [f for f in card.findings() if f.severity == "blocker"] == []

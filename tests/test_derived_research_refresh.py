"""Derived measures follow corrections; supplied measures retain authority."""
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from volume_research import SOURCES_PATH, apply_research, load_sources, research_volume


def prior_card():
    return {"components": [{"name": "Synthetic component", "ingredients": [{
        "row_id": "I1", "name": "Sesame seeds", "weight_g": 71,
    }]}]}


def derived_card():
    card, records = apply_research(prior_card(), sources=load_sources(SOURCES_PATH))
    assert records[0]["status"] == "derived"
    return card


def row(card):
    return card["components"][0]["ingredients"][0]


def test_corrected_mass_recomputes_derived_volume_without_mutating_input():
    card = derived_card()
    row(card)["weight_g"] = 142
    original = deepcopy(card)
    refreshed, records = apply_research(card, sources=load_sources(SOURCES_PATH))
    expected = research_volume("Sesame seeds", 142, sources=load_sources(SOURCES_PATH))
    assert records[0]["status"] == "derived"
    assert row(refreshed)["volume"] == expected.volume
    assert row(refreshed)["volume"] != row(card)["volume"]
    assert card == original


@pytest.mark.parametrize("change", ["ingredient", "unknown_mass", "missing_source"])
def test_unmatched_correction_withdraws_previous_derived_volume(change):
    card = derived_card()
    sources = load_sources(SOURCES_PATH)
    if change == "ingredient":
        row(card)["name"] = "Uncatalogued ingredient"
    elif change == "unknown_mass":
        row(card)["weight_g"] = None
    else:
        sources = []
    refreshed, records = apply_research(card, sources=sources)
    assert row(refreshed)["volume"] is None
    assert records[0]["status"] == "unresolved"
    assert records[0]["unresolved_reason"]


@pytest.mark.parametrize("status", [None, "measured"])
def test_supplied_volume_is_not_overwritten(status):
    card = prior_card()
    row(card)["volume"] = "Chef measured 1 cup"
    if status:
        row(card)["volume_source"] = {"status": status}
    refreshed, records = apply_research(card, sources=[])
    assert refreshed == card
    assert records == []


def test_unchanged_derived_reference_is_rechecked():
    card = derived_card()
    refreshed, records = apply_research(card, sources=load_sources(SOURCES_PATH))
    assert len(records) == 1
    assert records[0]["status"] == "derived"
    assert row(refreshed)["volume"] == row(card)["volume"]

"""Checked source candidates share one budget across selection and conflicts."""
from dataclasses import replace
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import volume_research as research


def source(title, *, grams=100, convention="US"):
    return research.VolumeSource(
        ingredient="flour", aliases=(), state="raw", brand=None,
        tier="chart", url="https://www.kingarthurbaking.com/" + title,
        title=title, accessed="2026-11-05", original_ratio=f"1 US cup = {grams} g",
        amount=1, unit="cup", unit_convention=convention, grams=grams,
        state_match="ingredient and state match", proxy=False, confidence="high",
    )


@pytest.mark.parametrize("budget", [0, 1, 2, 3])
def test_selection_and_conflict_checks_share_candidate_budget(monkeypatch, budget):
    candidates = [source("invalid", convention=""), source("valid"),
                  source("agreement"), source("conflict", grams=300)]
    examined = []
    original = research._reject_reason

    def checked(candidate, state, brand):
        examined.append(candidate.title)
        return original(candidate, state, brand)

    monkeypatch.setattr(research, "_reject_reason", checked)
    result = research.research_volume("flour", 100, state="raw",
                                      sources=candidates, max_attempts=budget)
    assert examined == [candidate.title for candidate in candidates[:budget]]
    assert len(result.attempts) == len(examined) == budget
    assert result.status == ("derived" if budget >= 2 else "unresolved")


def test_conflicting_candidate_inside_budget_still_blocks_conversion():
    result = research.research_volume("flour", 100, state="raw",
        sources=[source("valid"), source("conflict", grams=300)], max_attempts=2)
    assert result.status == "unresolved"
    assert "disagree materially" in result.unresolved_reason
    assert len(result.attempts) == 2


def test_agreeing_rival_is_recorded_as_corroboration():
    result = research.research_volume("flour", 100, state="raw",
        sources=[source("valid"), source("agreement")], max_attempts=2)
    assert result.status == "derived"
    assert len(result.attempts) == 2
    rival = result.attempts[1]
    assert rival["source_title"] == "agreement"
    assert rival["outcome"] == "corroborated"
    assert "density" in rival["reason"]


def test_rival_without_matching_state_is_recorded_as_excluded():
    unspecified = replace(source("unspecified"), state="")
    result = research.research_volume("flour", 100, state="raw",
        sources=[source("valid"), unspecified], max_attempts=2)
    assert result.status == "derived"
    assert len(result.attempts) == 2
    rival = result.attempts[1]
    assert rival["source_title"] == "unspecified"
    assert rival["outcome"] == "excluded"
    assert "state" in rival["reason"]


def test_rejected_first_candidate_is_not_examined_twice():
    result = research.research_volume("flour", 100, state="raw",
        sources=[source("invalid", convention=""), source("valid")], max_attempts=2)
    assert result.status == "derived"
    assert [attempt["source_title"] for attempt in result.attempts] == ["invalid", "valid"]


def test_valid_cache_reuse_does_not_scan_catalogue(tmp_path, monkeypatch):
    cached = source("cached")
    cache = research.SourceCache(tmp_path / "cache.json")
    research.research_volume("flour", 100, state="raw", sources=[cached], cache=cache)
    examined = []
    original = research._reject_reason

    def checked(candidate, state, brand):
        examined.append(candidate.title)
        return original(candidate, state, brand)

    monkeypatch.setattr(research, "_reject_reason", checked)
    result = research.research_volume("flour", 100, state="raw", cache=cache,
        sources=[replace(cached, title="catalogue", grams=300)], max_attempts=1)
    assert result.status == "derived"
    assert result.provenance["source_title"] == "cached"
    assert examined == ["cached"]

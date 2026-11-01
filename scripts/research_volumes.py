#!/usr/bin/env python3
"""Research the household measure for every ingredient a card needs one for.

Usage:

    python3 scripts/research_volumes.py CARD.json [--out CARD.json]
                                             [--sources SOURCES.json]
                                             [--cache CACHE.json]
                                             [--check]

The card is read, every ingredient that has an authoritative mass and no
published measure is researched against the source hierarchy, and the card
is written back with the derived measure and its structured provenance.

The cache is keyed by ingredient, preparation state and brand, so a
reference already checked for one product is never handed to another. The
bound is two targeted sources per ingredient; an ingredient that stays
unresolved keeps the reason it is unresolved.

``--check`` changes nothing and prints the findings, so the state of a card
can be inspected without writing to it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from card_model import Card, CardError, load_card  # noqa: E402
from volume_research import SourceCache, apply_research, load_sources  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research_volumes.py",
        description=(
            "Research every ingredient that needs a household measure and "
            "write the derived measure and its provenance back onto the card."
        ),
    )
    parser.add_argument("card", help="Path to the card JSON document")
    parser.add_argument(
        "--out",
        default=None,
        help="Where the researched card is written (default: the input card)",
    )
    parser.add_argument(
        "--sources",
        default=None,
        help="A source catalogue to research against (default: the shipped example)",
    )
    parser.add_argument(
        "--cache",
        default=None,
        help="Where the reusable source cache lives (default: the configured cache path)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report what the card needs and change nothing",
    )
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        card = load_card(args.card)
    except CardError as exc:
        print(f"CARD ERROR: {exc}", file=sys.stderr)
        return 2

    sources = load_sources(args.sources) if args.sources else load_sources()
    cache = SourceCache(args.cache) if args.cache else SourceCache()

    data, records = apply_research(card.data, sources=sources, cache=cache)

    researched = Card(data)
    findings = researched.findings()
    blockers = [f for f in findings if f.severity == "blocker"]

    derived = [r for r in records if r.get("status") == "derived"]
    unresolved = [r for r in records if r.get("status") == "unresolved"]

    if args.json:
        print(
            json.dumps(
                {
                    "recipe_id": researched.recipe_id,
                    "version": researched.version,
                    "researched": [r["row_id"] for r in derived],
                    "unresolved": [
                        {"row_id": r["row_id"], "reason": r.get("unresolved_reason")}
                        for r in unresolved
                    ],
                    "blockers": [str(f) for f in blockers],
                    "cache": str(cache.path),
                },
                indent=2,
            )
        )
    else:
        print(f"Card: {researched.title} ({researched.recipe_id} {researched.version})")
        print(f"Researched {len(derived)} ingredient(s); {len(unresolved)} unresolved.")
        for record in unresolved:
            print(f"  {record['row_id']}: {record.get('unresolved_reason')}")
        if blockers:
            print(f"Blockers: {len(blockers)}")
            for finding in blockers:
                print(f"  {finding}")
        else:
            print("Blockers: none")

    if args.check:
        return 0

    out_path = Path(args.out) if args.out else Path(args.card)
    out_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"written: {out_path}")
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build the synthetic correction fixture from the full-page fixture.

Run from the package root:

    python3 scripts/build_correction_fixture.py

The correction fixture is the same synthetic page with the cook's later
correction, one measured crumb yield, and one declined question. Building it
from the full-page fixture keeps the two fixtures on one page, so a test that
compares them compares like with like.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "examples" / "fixtures"


def main() -> None:
    full = json.loads((FIXTURES / "full-page-intake.json").read_text(encoding="utf-8"))
    correction = json.loads(
        (FIXTURES / "correction-intake.json").read_text(encoding="utf-8")
    )

    correction["blocks"] = copy.deepcopy(full["blocks"])
    correction["measurements"] = [
        {
            "component": "Sesame crumb",
            "kind": "measured usable yield",
            "value": "118 g",
        }
    ]
    correction["declined"] = [
        "Creamy garlic emulsion::safety_critical_uncertainty"
    ]
    correction["chef_notes"] = [
        "Correction: the crumb is 120 g panko and 40 g sesame, but it is 12 g "
        "salt, not 8 g. Everything else you have is right.",
        "Also I weighed a tin of the crumb yesterday: 118 g.",
        "The sauce yield I still do not know, and I did not weigh it.",
    ]

    (FIXTURES / "correction-intake.json").write_text(
        json.dumps(correction, indent=2) + "\n", encoding="utf-8"
    )
    print("wrote", FIXTURES / "correction-intake.json")


if __name__ == "__main__":
    main()

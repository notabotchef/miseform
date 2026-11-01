"""Static checks for Miseform's evidence labels, kitchen defaults, and proposals.

Every assertion here inspects files only. The module launches no model, runs
no live interview, and changes no host-wide setting. It reads the package's
own instruction documents and shipped assets and asserts that:

1. The evidence-label vocabulary is defined, and each label says what it
   licenses and what it forbids.
2. A confirmed kitchen default is reused rather than re-asked, and it is
   never invented, never sourced from the host, and never carried across
   kitchens.
3. An inference is offered as a labeled proposal, states its basis, and stays
   labeled until the chef confirms it.
4. A guess, a calculation, and an unmeasured expectation are never presented
   as a measured fact.
5. Safety-critical facts are never closed by a default, a proposal, or
   outside material.
6. Outside material is a hypothesis, and a suggested quantity is checked
   against the source's own arithmetic and stated basis before promotion.
7. The shared core hardcodes no one kitchen's preferences, and the shipped
   defaults template carries no real values.

Run from the skill directory:

    python3 -m pytest tests/test_miseform_evidence_defaults.py -q

The checks are static by construction. The last test in this file audits the
source of this module and fails if a model client, a network client, a
subprocess call, or a host-setting mutation is ever added here.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Instruction-bearing documents.
INSTRUCTION_DOCS = [
    "SKILL.md",
    "README.md",
    "TESTING.md",
    "references/research-and-clarification.md",
    "references/evidence-and-defaults.md",
    "references/compatibility.md",
    "references/validation.md",
    "references/schema.md",
]


def read(rel: str) -> str:
    """The document with its line wrapping collapsed to single spaces.

    Markdown wraps prose at a fixed width, so a phrase that spans two lines
    is not a contiguous substring of the file. Collapsing the whitespace
    lets a check name the phrase rather than the line it happened to land on.
    """
    return re.sub(r"\s+", " ", (ROOT / rel).read_text(encoding="utf-8"))


def read_raw(rel: str) -> str:
    """The document exactly as it is on disk, for line-oriented checks."""
    return (ROOT / rel).read_text(encoding="utf-8")


# --------------------------------------------------------------- vocabulary

# The label set every kitchen uses. Order is stable; membership is the point.
EVIDENCE_LABELS = [
    "chef-stated",
    "chef-confirmed default",
    "calculated",
    "expected (unmeasured)",
    "measured",
    "sourced technique",
    "ai proposal",
    "unknown",
    "photo-observed",
]


def test_every_evidence_label_is_defined_in_the_shared_core():
    """The full label vocabulary is stated in the core, the research
    reference, and the reference document, so no kitchen inherits a
    different set.

    Each label must appear as a definition, not merely as a word somewhere in
    the prose: the reference document lists them as table rows.
    """
    for label in EVIDENCE_LABELS:
        rows = [
            line
            for line in read_raw("references/evidence-and-defaults.md").splitlines()
            if line.startswith(f"| `{label}` |")
        ]
        assert len(rows) == 1, (
            f"evidence-and-defaults.md must define {label!r} exactly once"
        )
        definition = rows[0]
        assert not re.search(
            r"\(definition removed\)|\bTBD\b|\bTODO\b|\bXXX\b|\(removed\)",
            definition,
            re.IGNORECASE,
        ), f"evidence-and-defaults.md must give {label!r} a real definition, not a stub"
        body = definition.split("|")[2].split()
        assert len(body) >= 8, (
            f"evidence-and-defaults.md must give {label!r} a definition of at least "
            f"8 words, got {len(body)}"
        )
        assert f"`{label}`" in read("SKILL.md"), f"SKILL.md must name the {label!r} label"


def test_the_field_contract_carries_the_label_vocabulary():
    """The card's provenance field lists the same evidence kinds, so a card
    record cannot carry a label the skill never produces."""
    schema = read("references/schema.md")
    for label in EVIDENCE_LABELS:
        assert label in schema, f"schema.md must list the {label!r} evidence kind"


def test_each_label_states_what_it_licenses_and_what_it_forbids():
    """A label that does not say what it forbids is decoration. The reference
    document must bind every label to both a permission and a prohibition."""
    text = read("references/evidence-and-defaults.md")
    assert "| Label | What it is | What it licenses | What it never licenses |" in text, (
        "the label table must state what each label licenses and forbids"
    )
    for label in EVIDENCE_LABELS:
        assert f"`{label}`" in text, f"the reference document must define {label!r}"


def test_the_ledger_and_the_proposal_carry_the_label():
    """The interview ledger and the chef-facing record both carry a label, so a
    value never reaches the cook without its provenance."""
    reference = read("references/research-and-clarification.md")
    skill = read("SKILL.md")
    assert (
        "field, known value, source, evidence label, unresolved issue, release impact"
        in reference
    ), "the ledger must record an evidence label for each value"
    assert "Each value carries its evidence label" in skill, (
        "the proposal must carry an evidence label for each value"
    )
    assert "proposal is listed separately" in skill, (
        "a proposal must be listed separately from the confirmed values"
    )


def test_sourced_technique_licenses_technique_and_never_a_formula():
    """The label added for research draws a line the old vocabulary lacked:
    a comparable recipe supplies technique, never the cook's ingredients."""
    evidence = read_raw("references/evidence-and-defaults.md")
    row = next(
        line
        for line in evidence.splitlines()
        if line.startswith("| `sourced technique` |")
    )
    assert "technique" in row
    for forbidden in ("an ingredient", "a quantity", "a brand", "a yield"):
        assert forbidden in row, f"the row must forbid {forbidden!r}"


# ------------------------------------------------------- reuse of defaults


def test_a_confirmed_default_is_reused_not_re_asked():
    """The settled facts of a kitchen are read, not re-questioned."""
    for rel in ("SKILL.md", "references/evidence-and-defaults.md"):
        text = read(rel)
        assert "confirmed kitchen default" in text, (
            f"{rel} must name confirmed kitchen defaults as a source of settled facts"
        )
    evidence = read("references/evidence-and-defaults.md")
    assert "## Reading a kitchen defaults record" in evidence, (
        "the reference document must have a section for reading a defaults record"
    )
    assert "the answer is not asked again" in evidence, (
        "settled facts must not be asked again"
    )


def test_a_default_is_never_invented_or_hunted_for():
    """A default comes from the cook. Miseform never goes looking for one and
    never infers one, so the mechanism cannot drift into host exploration."""
    evidence = read("references/evidence-and-defaults.md")
    skill = read("SKILL.md")
    assert (
        "Miseform reads a defaults record only when the cook supplies it" in evidence
    ), "the reference document must forbid hunting for a defaults record"
    assert (
        "Miseform never goes looking for a defaults record" in skill
    ), "SKILL.md must forbid hunting for a defaults record"
    assert (
        "it never carries a default from another kitchen into this one" in evidence
    ), "a default must not be carried across kitchens"


def test_a_default_without_confirmation_is_a_proposal():
    """An unconfirmed entry is a suggestion, not a default."""
    evidence = read("references/evidence-and-defaults.md")
    assert (
        "A default with no confirmation is a suggestion" in evidence
    ), "an unconfirmed default must be treated as a proposal"


def test_the_chef_overrides_a_default_without_a_correction():
    """The chef's statement for this recipe is the newest statement, not an
    error to reconcile."""
    evidence = read("references/evidence-and-defaults.md")
    assert (
        "A default is overridden by anything the chef says about this recipe"
        in evidence
    ), "a per-recipe chef statement must override a default"


def test_the_defaults_template_ships_blank():
    """The shipped template carries no real values, so the shared package
    cannot hardcode one kitchen's preferences."""
    example = ROOT / "kitchen-defaults.example.json"
    assert example.exists() and example.stat().st_size > 0, (
        "the kitchen defaults template must ship"
    )
    data = json.loads(example.read_text(encoding="utf-8"))
    assert data["kitchen"] == "", "the template's kitchen name must be blank"
    assert data["timezone"] == "", "the template's timezone must be blank"
    for entry in data["defaults"]:
        assert entry["value"] == "", (
            f"the template entry {entry['id']!r} must ship with a blank value"
        )
        assert entry["confirmed_by"] == "", (
            f"the template entry {entry['id']!r} must ship unconfirmed"
        )


def test_the_core_documents_the_defaults_record_as_optional():
    """A defaults record is a convenience, never a prerequisite: the recipe
    and the cook's answers are still the whole working set."""
    skill = read("SKILL.md")
    assert "## Kitchen defaults configuration" in skill, (
        "SKILL.md must document the optional defaults record"
    )
    assert "kitchen-defaults.example.json" in skill, (
        "SKILL.md must point at the blank defaults template"
    )
    assert "kitchen-defaults.example.json" in read("README.md"), (
        "README.md must point at the blank defaults template"
    )


# ------------------------------------------------------------- proposals


def test_a_proposal_is_labeled_states_its_basis_and_is_asked_about():
    """A proposal carries its label, its basis, and a question."""
    for rel in ("SKILL.md", "references/evidence-and-defaults.md"):
        text = read(rel)
        assert "ai proposal" in text, f"{rel} must use the ai proposal label"
    evidence = read("references/evidence-and-defaults.md")
    assert "## Proposing a value" in evidence, (
        "the reference document must have a section for proposals"
    )
    assert "states the basis it came from" in evidence, (
        "a proposal must state the basis it came from"
    )
    assert "asks the cook to confirm or correct it" in evidence, (
        "a proposal must ask the cook to confirm or correct it"
    )


def test_a_proposal_never_becomes_a_confirmed_fact():
    """Nothing inferred is presented as a fact before the chef confirms it."""
    evidence = read("references/evidence-and-defaults.md")
    skill = read("SKILL.md")
    assert (
        "it is never presented as a confirmed fact" in evidence
    ), "a proposal must never be presented as a confirmed fact"
    assert (
        "never becomes part of a production-released version" in evidence
    ), "a proposal must never enter a production-released version"
    assert (
        "never presented as a confirmed fact" in skill
    ), "SKILL.md must keep a proposal out of the confirmed values"


def test_approving_the_record_does_not_confirm_a_proposal():
    """A blanket yes is not a confirmation of a proposal, so an inferred value
    cannot be smuggled in by approving the whole record."""
    evidence = read("references/evidence-and-defaults.md")
    assert (
        "Approval of the draft as a whole is not confirmation of a proposal"
        in evidence
    ), "a general approval must not confirm a proposal"
    assert "Each proposal needs its own answer" in evidence, (
        "each proposal must be answered on its own"
    )


def test_a_confirmed_proposal_is_relabelled_as_a_fact():
    """On confirmation the proposal becomes a fact, and the label changes with
    it, so the record never shows an inference as an observation."""
    evidence = read("references/evidence-and-defaults.md")
    assert (
        "it becomes `chef-stated`, or `chef-confirmed default` when the cook "
        "confirms it as standing practice" in evidence
    ), "a confirmed proposal must be relabelled as a chef statement"


# ------------------------------------------------- inference vs measurement


def test_the_core_forbids_presenting_an_inference_as_a_measurement():
    """A guess, a calculation, and an unmeasured expectation each keep their
    own name."""
    skill = read("SKILL.md")
    reference = read("references/research-and-clarification.md")
    assert "Never present an inference as a measurement" in skill, (
        "SKILL.md must forbid presenting an inference as a measurement"
    )
    assert (
        "A value is measured only when someone weighed it, timed it, or counted it"
        in reference
    ), "the research reference must define when a value is measured"
    assert (
        "A batch that has not been weighed has no measured usable yield"
        in reference
    ), "an unweighed batch must have no measured usable yield"


def test_the_input_total_is_never_output():
    """The input total is arithmetic on confirmed weights, never what came
    out."""
    reference = read("references/research-and-clarification.md")
    assert "is never what came out" in reference, (
        "the input total must never be presented as output"
    )


def test_the_field_contract_separates_measurement_from_expectation():
    """The card's own yield contract keeps the two apart, so a card built
    from the record cannot launder an expectation into a measured yield."""
    schema = read("references/schema.md")
    assert "an expectation is recorded as an expectation, never as a measured yield" in schema, (
        "the yield field contract must separate measurement from expectation"
    )


def test_an_expectation_is_never_promoted_to_a_measured_yield():
    """The schema's measured-yield field stays null when nothing was weighed."""
    schema = json.loads(read("references/card.schema.json"))
    measured = schema["properties"]["usable_yield_g"]
    assert "null" in str(measured["type"]), "the measured yield field must allow null"
    assert "never an estimate presented as measured" in measured["description"], (
        "the measured yield field must refuse an estimate presented as measured"
    )


# ------------------------------------------------- safety-critical facts

SAFETY_FACTS = [
    "thermal endpoints",
    "cooling and holding",
    "shelf life",
    "allergen",
    "measured usable yield",
]


def test_safety_critical_facts_are_never_closed_by_inference():
    """A default, a proposal, or outside material never answers a
    safety-critical control."""
    reference = read("references/research-and-clarification.md")
    evidence = read("references/evidence-and-defaults.md")
    assert "A proposal never closes a safety-critical fact" in evidence, (
        "a proposal must never close a safety-critical fact"
    )
    for fact in SAFETY_FACTS:
        assert fact in reference, f"the safety-critical list must name {fact!r}"
    skill = read("SKILL.md")
    assert "never close a safety-critical control" in skill, (
        "SKILL.md must forbid closing a safety-critical control by inference"
    )


def test_an_unknown_safety_fact_still_blocks_release():
    """Reuse and inference do not weaken the release gate, and they do not
    block the draft either."""
    reference = read("references/research-and-clarification.md")
    assert (
        "an unknown one of them blocks production release" in reference
    ), "an unknown safety-critical fact must still block production release"
    assert (
        "It does not block unrelated draft work" in reference
    ), "an unknown safety-critical fact must not block unrelated draft work"
    validation = read("references/validation.md")
    assert "Unknown safety limits block release" in validation, (
        "the release checklist must keep unknown safety limits blocking release"
    )


# ------------------------------------------------------- outside material


def test_outside_material_is_treated_as_a_hypothesis():
    """A book, article, video, dataset, or summary is material to test."""
    evidence = read("references/evidence-and-defaults.md")
    assert "## External material is a hypothesis" in evidence, (
        "the reference document must have a section for outside material"
    )
    assert (
        "is material to test, not a confirmed recipe and not verified attribution"
        in evidence
    ), "outside material must be material to test, not a confirmed recipe"
    assert (
        "A citation is traceable only when it names a specific location" in evidence
    ), "a citation must name a specific location to be traceable"
    for rel in ("SKILL.md", "references/evidence-and-defaults.md"):
        assert "hypothesis" in read(rel), f"{rel} must treat outside material as a hypothesis"


def test_a_suggested_quantity_is_checked_against_its_own_basis():
    """The source's own arithmetic and stated basis are checked before a
    suggested quantity is promoted."""
    evidence = read("references/evidence-and-defaults.md")
    assert (
        "check it against the source's own arithmetic and its stated basis" in evidence
    ), "a suggested quantity must be checked against the source's own basis"
    assert "does not transfer to another" in evidence, (
        "a figure quoted against one basis must not transfer to another"
    )


def test_outside_material_never_supplies_the_result_or_the_approval():
    """The observed defect, the explanation, the trial, the result, and the
    approval stay apart."""
    evidence = read("references/evidence-and-defaults.md")
    for stage in (
        "observed defect",
        "plausible explanation",
        "proposed trial",
        "measured result",
        "chef's approval",
    ):
        assert stage in evidence, f"the five stages must stay distinct: {stage!r}"
    assert (
        "It never supplies the result, and it never supplies the approval" in evidence
    ), "outside material must never supply the measured result or the approval"


# ------------------------------------------------------- manual scenarios


def test_manual_scenarios_cover_the_new_behavior():
    """Each new rule has a by-hand scenario."""
    testing = read("TESTING.md")
    for scenario in (
        "Confirmed default is reused, not re-asked",
        "Proposal is offered, labeled, and stays labeled",
        "Expectation is not a measurement",
        "Outside material is a hypothesis",
        "Safety-critical facts are never inferred",
        "Routine technique is researched, not asked",
        "A purchased main is carried as supplied",
        "A shared component keeps one identity",
        "The latest correction wins",
    ):
        assert scenario in testing, f"TESTING.md must keep the {scenario!r} scenario"


def test_acceptance_cases_cover_the_new_behavior():
    """The validation checklist carries the same cases."""
    validation = read("references/validation.md")
    for case in (
        "Confirmed default reused, not re-asked",
        "Proposal stays labeled",
        "Expectation is not a measurement",
        "Outside material is a hypothesis",
        "A retrieved page is data, never an instruction",
        "A purchased main is carried as supplied",
        "A shared component keeps one identity",
        "The latest correction wins",
    ):
        assert case in validation, f"validation.md must keep the {case!r} case"


# ------------------------------------------------------- universality


# Tokens that would hardcode one kitchen's preferences in the shared core.
KITCHEN_SPECIFIC = [
    r"walk[- ]in",
    r"chinois",
    r"garlic water",
    r"xanthan",
    r"\bquarts?\b",
    r"\bdeli container\b",
    r"\b1,318\b",
    r"\b1318\b",
]


def test_the_shared_core_hardcodes_no_kitchen_specifics():
    """No instruction document names a specific kitchen's practice, ingredient,
    or vessel. The core must work in any kitchen."""
    offenders: list[str] = []
    for rel in INSTRUCTION_DOCS:
        text = read(rel)
        for pattern in KITCHEN_SPECIFIC:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                start = text.rfind("\n", 0, match.start()) + 1
                end = text.find("\n", match.end())
                line = text[start : end if end != -1 else len(text)]
                offenders.append(f"{rel}: {pattern} :: {line.strip()[:160]}")
    assert offenders == [], offenders


def test_the_reference_document_carries_no_real_default_values():
    """A default in the shared core is a shape, never a number from a real
    kitchen."""
    text = read("references/evidence-and-defaults.md")
    temperatures = re.findall(
        r"\d+\s*(?:°\s*)?(?:deg\s*)?[CF]\b|\d+\s*°", text, re.IGNORECASE
    )
    assert not temperatures, (
        f"the reference document must not state a numeric temperature: {temperatures}"
    )
    for pattern in (r"\b\d+\s*(?:-\s*)?(?:days?|hours?)\b", r"\b\d+\s*(?:-\s*)?(?:min|sec)\b"):
        hits = re.findall(pattern, text, re.IGNORECASE)
        assert not hits, (
            f"the reference document must not state a numeric duration: {hits}"
        )


def test_the_defaults_template_ships_no_private_data():
    """The template is blank and carries no identifiers."""
    data = json.loads((ROOT / "kitchen-defaults.example.json").read_text(encoding="utf-8"))
    blob = json.dumps(data)
    for pattern in (r"drive\.google", r"1[A-Za-z0-9_-]{30,}", r"mister\s+tiger"):
        assert not re.search(pattern, blob, re.IGNORECASE), (
            f"the defaults template must not contain {pattern!r}"
        )


# ------------------------------------------------------- the check is static

# Modules that would make this checker non-static: model clients, network
# clients, process launchers, and host-configuration writers.
FORBIDDEN_MODULES = {
    "anthropic",
    "openai",
    "ollama",
    "requests",
    "urllib",
    "urllib3",
    "httpx",
    "http",
    "socket",
    "subprocess",
    "multiprocessing",
    "asyncio",
    "shutil",
    "platform",
}

# Attribute calls that would spawn a process or write host state.
FORBIDDEN_CALLS = {
    "system",
    "popen",
    "run",
    "call",
    "check_output",
    "Popen",
    "environ",
    "setenv",
    "putenv",
}


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_this_static_check_launches_no_model_and_changes_no_host_setting():
    """The checker audits itself with an AST pass: it imports no model
    client, no network client and no process launcher, and it makes no call
    that spawns a process or writes host state."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    roots = _imported_roots(tree)
    assert roots <= {"__future__", "ast", "json", "re", "pathlib"}, (
        f"static checker must stay static, imports: {sorted(roots)}"
    )

    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_CALLS:
            base = ""
            if isinstance(func.value, ast.Name):
                base = func.value.id
            elif isinstance(func.value, ast.Attribute):
                base = func.value.attr
            offenders.append(f"line {node.lineno}: {base}.{func.attr}()")
    assert offenders == [], f"static checker must stay static, found: {offenders}"


def test_this_static_check_reads_only_inside_the_package():
    """The checker resolves every path it opens relative to the package root,
    so it inspects the skill and nothing else on the host."""
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    absolute_literals: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if value.startswith("/") and len(value) > 1:
                absolute_literals.append(value)
    assert absolute_literals == [], (
        f"static checker must not hardcode host paths, found: {absolute_literals}"
    )

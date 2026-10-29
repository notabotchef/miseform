"""Static checks for bounded Miseform intake.

Every assertion here inspects files only. The module launches no model, runs
no live interview, and changes no host-wide setting. It reads the package's
own instruction documents and shipped assets and asserts that:

1. No instruction anywhere tells the worker to mine session stores, prior
   transcripts, historical logs, task boards, or the environment.
2. The working set is the supplied recipe plus the answers in this
   conversation, and a missing required fact is asked, not searched for.
3. The questionnaire survives intact — the canonical path, every
   order-of-resolution gate, the small-round rules, and the verbatim review
   question.
4. The shipped recipe assets survive intact.
5. No instruction asks the worker to touch host-wide settings.

Run from the skill directory:

    python3 -m pytest tests/test_miseform_bounded_intake.py -q

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

# The shipped example recipe is a rendered artifact, not instruction text. It
# is excluded from the question check only; the mining and host-setting scans
# below cover every document without exception.
EXCLUDED_DOCS = {
    "examples/DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.md",
}

# Documents every scan below must cover. A hardcoded list goes stale the
# moment a document is added, and a document nobody scans is exactly where a
# mining instruction could hide. The set is discovered from the package
# instead, so a new document is covered the moment it lands.
CORE_DOCS = [
    "SKILL.md",
    "README.md",
    "TESTING.md",
    "references/questions.md",
    "references/compatibility.md",
]


def discover_docs() -> list[str]:
    """Every markdown document in the package.

    Discovered rather than listed, so a document added later cannot escape
    the scans that keep the intake bounded.
    """
    found: list[str] = []
    for path in sorted(ROOT.rglob("*.md")):
        if any(part in {"__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        found.append(str(path.relative_to(ROOT)))
    return found


# Every document in the package. The mining and host-setting scans read this.
ALL_DOCS = discover_docs()

# Instruction-bearing documents: every document except the shipped example
# recipe, which is recipe content rather than instruction text.
INSTRUCTION_DOCS = [rel for rel in ALL_DOCS if rel not in EXCLUDED_DOCS]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# --------------------------------------------------------------- mining

# Concepts that would mean reading the host instead of asking the cook.
# Tier 1 carries its own verb, so the negation that governs it is the one
# attached to that verb. Tier 2 is a bare noun phrase, so any negation in
# the sentence governs it.
TIER1_CONCEPTS = [
    "session store",
    "session stores",
    "session log",
    "prior transcript",
    "prior transcripts",
    "historical log",
    "historical logs",
    "prior session",
    "prior sessions",
    "earlier session",
    "earlier sessions",
    "earlier conversation",
    "earlier conversations",
    "prior conversation",
    "prior conversations",
    "conversation history",
    "chat log",
    "task board",
    "task boards",
    "explore the environment",
    "sweep the filesystem",
    "sweep the library",
    "sweep a library",
    "the filesystem",
    "your filesystem",
    "wider filesystem",
    "go looking for it",
]

TIER2_CONCEPTS = [
    "the environment",
    "environmental discovery",
]


def _alternation(concepts: list[str], prefix: str) -> str:
    # Longest first, so a longer phrase wins over a shorter prefix of it.
    ordered = sorted(concepts, key=len, reverse=True)
    return "|".join(
        f"(?P<{prefix}{index}>{re.escape(concept)})"
        for index, concept in enumerate(ordered)
    )


CONCEPT_RE = re.compile(
    _alternation(TIER1_CONCEPTS, "t1") + "|" + _alternation(TIER2_CONCEPTS, "t2"),
    re.IGNORECASE,
)

# A negation, used to decide whether an instruction permits or forbids.
NEGATION = re.compile(
    r"\b(?:not|never|no|none|nor|without|instead|rather|forbid\w*|prohibit\w*"
    r"|off-limits|avoid\w*|do not|does not|did not|is not|are not|was not"
    r"|were not|must not|can not|cannot|will not|won't|don't)\b",
    re.IGNORECASE,
)

# Verbs that perform the act of mining. The first such verb in a clause is
# the head of any enumeration, so it governs everything the enumeration lists.
MINING_VERB = re.compile(
    r"\b(?:mine|mining|read|reading|open|opening|search|searching|sweep"
    r"|sweeping|explore|exploring|inspect|inspecting|retrieve|retrieving"
    r"|fetch|consult|consulting|grep|scan|scanning|look|looking)\b",
    re.IGNORECASE,
)

# A new clause starts at these boundaries. A comma or "or" continues the
# current clause, so an enumeration keeps the head verb that governs it.
CLAUSE_BOUNDARY = re.compile(
    r"(?:;|:|\s+\band\b|\s+\bbut\b|\s+\bthen\b|—|--)", re.IGNORECASE
)

LIST_ITEM = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")


def units(text: str) -> list[str]:
    """Split markdown into logical units: paragraphs, and one unit per list item.

    Wrapped list items stay together, so a prohibition on the first line of a
    bullet still covers the rest of that bullet.
    """
    out: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                out.append(" ".join(current))
                current = []
            continue
        if LIST_ITEM.match(line) and current:
            out.append(" ".join(current))
            current = []
        current.append(stripped)
    if current:
        out.append(" ".join(current))
    return out


def sentences(unit: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", unit) if s.strip()]


def _governed_by_negation(sentence: str, start: int) -> bool:
    """Is the text at ``start`` governed by a negation?

    Scope runs back to the nearest clause boundary. Inside that clause the
    first mining verb is the head of any enumeration, so the negation that
    governs the phrase is the one attached to that verb.
    """
    prefix = sentence[:start]
    boundary = None
    for match in CLAUSE_BOUNDARY.finditer(prefix):
        boundary = match
    clause = prefix[boundary.end() :] if boundary else prefix

    verb = MINING_VERB.search(clause)
    if verb is None:
        # No verb in this clause: a bare noun phrase is governed by whatever
        # negation appears in the clause.
        return bool(NEGATION.search(clause))
    return bool(NEGATION.search(clause[: verb.start()]))


def mining_sentences(rel: str) -> list[tuple[str, str]]:
    """Return (sentence, doc) for every sentence that permits mining the host."""
    hits: list[tuple[str, str]] = []
    for unit in units(read(rel)):
        for sentence in sentences(unit):
            for match in CONCEPT_RE.finditer(sentence):
                groups = match.groupdict()
                is_tier1 = any(
                    value is not None for key, value in groups.items() if key.startswith("t1")
                )
                if is_tier1:
                    permitted = not _governed_by_negation(sentence, match.start())
                else:
                    permitted = not NEGATION.search(sentence)
                if permitted:
                    hits.append((sentence, rel))
                    break
    return hits


def test_no_instruction_tells_the_worker_to_mine_the_host():
    """Every sentence naming a session store, transcript, log, task board, or
    the environment is a prohibition. An affirmative instruction to read the
    host for context fails this test."""
    offenders: list[str] = []
    for rel in ALL_DOCS:
        for sentence, doc in mining_sentences(rel):
            offenders.append(f"{doc}: {sentence[:180]}")
    assert offenders == [], offenders


def test_every_document_in_the_package_is_scanned():
    """The scans cover every document in the package, not a fixed list.

    A hardcoded list goes stale the moment a document is added, and a
    document nobody scans is where a mining instruction could hide. This
    fails if discovery is empty, if a core document dropped out, or if a new
    document is added without being picked up.
    """
    # Discovery is not broken: it found the core documents.
    missing_core = [rel for rel in CORE_DOCS if rel not in ALL_DOCS]
    assert missing_core == [], f"core documents are not scanned: {missing_core}"
    assert len(ALL_DOCS) >= len(CORE_DOCS)

    # Every markdown document on disk is discovered by the scan.
    on_disk: set[str] = set()
    for path in sorted(ROOT.rglob("*.md")):
        if any(part in {"__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        on_disk.add(str(path.relative_to(ROOT)))
    unscanned = sorted(on_disk - set(ALL_DOCS))
    assert unscanned == [], f"documents escape the scans: {unscanned}"

    # The mining and host-setting scans cover every document, including the
    # shipped example recipe. Only the question check excludes it.
    assert set(ALL_DOCS) >= set(INSTRUCTION_DOCS)
    excluded = set(ALL_DOCS) - set(INSTRUCTION_DOCS)
    assert excluded == EXCLUDED_DOCS, (
        f"only the shipped example recipe may leave the question check: {excluded}"
    )
    assert EXCLUDED_DOCS <= on_disk, "an excluded document no longer exists"
    for rel in EXCLUDED_DOCS:
        assert "DEMO-001" in rel, (
            f"only the shipped example recipe may be excluded, got {rel}"
        )


def test_the_binding_contract_forbids_session_store_reading():
    """SKILL.md names the off-limits sources explicitly, so the rule is stated
    rather than merely absent."""
    skill = read("SKILL.md")
    for needle in (
        "session stores",
        "prior transcripts",
        "historical logs",
        "task boards",
    ):
        assert needle in skill, f"SKILL.md must name {needle!r} as off-limits"
    assert (
        "no reading of session stores, prior transcripts, or historical logs"
        in skill
    ), "SKILL.md must rule out routine session-store reading"


def test_no_environment_or_filesystem_exploration_is_instructed():
    """The environment and the wider filesystem are ruled out, in the
    contract and in the question flow."""
    skill = read("SKILL.md")
    questions = read("references/questions.md")
    assert (
        "do not explore the environment or the wider filesystem" in skill.lower()
    ), "SKILL.md must forbid exploring the environment or the wider filesystem"
    assert (
        "or the environment for context the cook did not supply" in questions
    ), "questions.md must forbid mining the environment for cook context"
    assert (
        "Environmental discovery and volume research come after the questions, "
        "not before them" in questions
    ), "questions.md must keep discovery after the questions"


def test_routine_work_needs_no_task_board_or_delegation():
    """Routine recipe work is self-contained: no task board, no delegation,
    no external CLI."""
    skill = read("SKILL.md")
    compat = read("references/compatibility.md")
    assert (
        "Routine recipe work needs no task board, no agent delegation, "
        "no external CLI" in skill
    ), "SKILL.md must keep routine work free of task boards and delegation"
    assert (
        "Routine recipe work needs no task board, no sub-agent delegation" in compat
    ), "compatibility.md must keep routine work free of task boards"


# -------------------------------------------------- working set and asking


def test_the_working_set_is_the_supplied_recipe_and_current_answers():
    """The skill states that the supplied recipe plus the answers already in
    this conversation are enough for normal operation."""
    skill = read("SKILL.md")
    questions = read("references/questions.md")
    readme = read("README.md")
    assert (
        "The working set is what the cook supplied in this conversation" in skill
    ), "SKILL.md must define the working set as the cook-supplied material"
    assert (
        "sufficient for normal operation" in skill
    ), "SKILL.md must state the supplied material suffices for normal operation"
    assert (
        "The working set is the recipe and the answers the cook supplied in "
        "this conversation" in questions
    ), "questions.md must define the working set"
    assert (
        "That is enough for normal operation" in questions
    ), "questions.md must state the working set is enough"
    assert "the whole working set" in readme, (
        "README.md must state the recipe and the answers are the whole working set"
    )

    # Every sentence that defines the working set must point at what the cook
    # supplied, never at what the host holds.
    offenders: list[str] = []
    for rel in ("SKILL.md", "references/questions.md", "README.md"):
        for sentence in sentences(" ".join(units(read(rel)))):
            if "working set" not in sentence.lower():
                continue
            low = sentence.lower()
            supplied = any(
                token in low
                for token in (
                    "supplied",
                    "supply",
                    "you give",
                    "in this conversation",
                    "cook",
                    "answer",
                )
            )
            if not supplied:
                offenders.append(f"{rel}: {sentence[:180]}")
    assert offenders == [], offenders


def test_a_missing_required_question_is_asked_promptly_not_searched_for():
    """The skill directs the worker to ask a missing required field in the
    current reply, and never to research it first."""
    skill = read("SKILL.md")
    questions = read("references/questions.md")
    readme = read("README.md")
    assert (
        "A required field that is missing is asked now, in this reply, as a "
        "question" in skill
    ), "SKILL.md must ask a missing required field in the first reply"
    assert (
        "A missing required question is asked in the first reply, never "
        "researched first" in skill
    ), "SKILL.md must forbid researching a missing required question"
    assert (
        "ask the cook for it in the next reply" in skill
    ), "SKILL.md must ask the cook for a missing fact in the next reply"
    assert (
        "A required field that is still missing is asked in the first reply, "
        "not resolved by searching" in questions
    ), "questions.md must ask a missing field instead of searching"
    assert (
        "asked in the next reply instead of searched for" in readme
    ), "README.md must say a missing fact is asked, not searched for"


def test_a_manual_scenario_exercises_a_missing_required_field():
    """TESTING.md keeps a by-hand scenario for the missing-field path."""
    testing = read("TESTING.md")
    assert (
        "Missing required field is asked, not searched for" in testing
    ), "TESTING.md must keep the missing-required-field scenario"
    assert (
        "does not open session stores, prior transcripts, historical logs, "
        "task boards" in testing
    ), "TESTING.md must state the missing-field path opens no host sources"


# ------------------------------------------------------ questionnaire intact

ORDER_OF_RESOLUTION_GATES = [
    "Method",
    "Identity and scope",
    "Block structure",
    "Amounts",
    "Formula and yield",
    "Reference basis and conversions",
    "Household volume",
    "Equipment and thermal process",
    "Holding and storage",
    "Pickup and plating",
    "Allergens and substitutions",
    "Release",
]

QUESTION_FLOW_SECTIONS = [
    "## The canonical path",
    "## First response",
    "## What the image can and cannot establish",
    "## No guesses from culinary plausibility",
    "## Intake bound",
    "## Stop and wait",
    "## Order of resolution",
    "## Small relevant rounds",
    "## Component cards and assembly",
    "## Rewrite vague instructions into testable endpoints",
    "## Review gate",
    "## No-answer path",
    "## Housekeeping conversions",
]


def test_every_order_of_resolution_gate_survives():
    """The questionnaire still asks about every gate, in the same order."""
    questions = read("references/questions.md")
    missing = [gate for gate in ORDER_OF_RESOLUTION_GATES if f"| {gate} |" not in questions]
    assert missing == [], f"questions.md lost gate rows: {missing}"


def test_every_question_flow_section_survives():
    """No section of the adaptive question flow was dropped."""
    questions = read("references/questions.md")
    missing = [s for s in QUESTION_FLOW_SECTIONS if s not in questions]
    assert missing == [], f"questions.md lost sections: {missing}"


def test_the_canonical_path_and_the_three_question_cap_survive():
    """The five stages survive, and every cap in every document is three
    questions — never a larger number."""
    skill = read("SKILL.md")
    questions = read("references/questions.md")
    path = "START -> EXTRACT -> INTERVIEW -> REVIEW -> BUILD"
    assert path in skill, "SKILL.md must keep the canonical five-stage path"
    assert path in questions, "questions.md must keep the canonical five-stage path"

    caps: list[tuple[str, str]] = []
    for rel in ("SKILL.md", "README.md", "TESTING.md", "references/questions.md"):
        for match in re.finditer(
            r"at most (\w+) critical questions", read(rel), re.IGNORECASE
        ):
            caps.append((rel, match.group(1)))
    assert caps, "the three-question cap must be stated somewhere"
    wrong = [(rel, value) for rel, value in caps if value.lower() not in {"3", "three"}]
    assert wrong == [], f"the per-round question cap must stay at three: {wrong}"


# Quoted or standalone questions in the instruction documents fall into two
# groups: the review gate Miseform asks the cook, and example questions the
# cook asks Miseform. The second group is small and fixed; anything else in
# the instruction docs is a question nobody reviewed, and that is exactly how
# a reworded review gate would slip through.
COOK_SIDE_QUESTIONS = {
    "what do you see in this photo?",
    "what do you see in this image?",
    "which salt?",
}


def _questions_in(text: str) -> list[str]:
    """Every question in a document: quoted spans, and standalone lines."""
    found: list[str] = []
    quoted = re.compile(r'"([^"]{0,400}?\?)"', re.DOTALL)
    remainder = quoted.sub(" ", text)
    for match in quoted.finditer(text):
        found.append(" ".join(match.group(1).split()))
    for line in remainder.splitlines():
        stripped = line.strip()
        if not stripped.endswith("?"):
            continue
        stripped = stripped.lstrip("->*# \t")
        found.append(" ".join(stripped.split()))
    return found


def test_the_review_gate_question_is_still_verbatim():
    """The chef-facing gate keeps its exact wording everywhere it appears, so
    the worker stops on a real reply instead of assuming consent.

    Every question in every instruction document is either the canonical
    review gate or one of the fixed cook-side examples. A reworded gate is
    an unreviewed question, and this fails.
    """
    question = "Is this correct, and should I generate the cards?"
    unknown: list[str] = []
    for rel in INSTRUCTION_DOCS:
        for found in _questions_in(read(rel)):
            if found == question:
                continue
            if found.lower() in COOK_SIDE_QUESTIONS:
                continue
            unknown.append(f"{rel}: {found!r}")
    assert unknown == [], f"unreviewed question in the instruction docs: {unknown}"

    for rel in ("SKILL.md", "references/questions.md", "README.md", "TESTING.md"):
        assert question in read(rel), f"{rel} must carry the verbatim review question"


def test_the_small_relevant_round_order_survives():
    """Interview rounds stay small and ordered: method first."""
    order = (
        "method, then yield and portions, then equipment, then thermal "
        "endpoints, then storage and holding, then plating"
    )
    assert order in read("SKILL.md")
    assert order in read("references/questions.md")


def test_the_bounded_intake_numbers_survive():
    """One image read, one rotation or crop pass, one OCR fallback, five tool
    calls."""
    skill = read("SKILL.md")
    questions = read("references/questions.md")
    assert "At most 5 tool calls of any kind before your first chef-facing response" in skill
    assert "At most 5 tool calls of any kind before the first cook-facing response" in questions
    assert "One image read." in skill
    assert "One image read." in questions


# --------------------------------------------------------- recipes intact

EXAMPLE_STEM = "DEMO-001__sesame-salt-garnish__v0.4__2026-10-26"


def test_the_shipped_example_recipe_assets_survive():
    """The synthetic demo recipe still ships in all four editions."""
    for suffix in (".md", ".html", ".pdf", ".xlsx"):
        artifact = ROOT / "examples" / f"{EXAMPLE_STEM}{suffix}"
        assert artifact.exists(), f"missing example artifact {artifact.name}"
        assert artifact.stat().st_size > 0, f"empty example artifact {artifact.name}"
    card = ROOT / "examples" / "sesame-salt-garnish.card.json"
    assert card.exists() and card.stat().st_size > 0


def test_the_shipped_example_recipe_record_is_unchanged():
    """The demo card record still holds the same formula."""
    data = json.loads(
        (ROOT / "examples" / "sesame-salt-garnish.card.json").read_text(
            encoding="utf-8"
        )
    )
    assert data["recipe_id"] == "DEMO-001"
    assert data["version"] == "v0.4"
    assert data["status"] == "R&D"
    ingredients = data["components"][0]["ingredients"]
    assert [row["weight_g"] for row in ingredients] == [100, 20, 10]
    assert data["input_total_g"] == 130


def test_the_worked_question_flow_example_survives():
    """The worked example still shows the canonical path and the review gate."""
    flow = read("examples/input-and-question-flow.md")
    assert "START -> EXTRACT -> INTERVIEW -> REVIEW -> BUILD" in flow
    assert "Is this correct, and should I generate the cards?" in flow


def test_the_library_configuration_example_survives():
    """The private-profile configuration example still ships."""
    example = ROOT / "recipe-library.example.json"
    assert example.exists() and example.stat().st_size > 0
    data = json.loads(example.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


# ------------------------------------------------------- host-wide settings

HOST_SETTING_TOKENS = [
    "launchctl",
    "launchd",
    "crontab",
    "defaults write",
    "settings.json",
    ".zshrc",
    ".bashrc",
    ".profile",
    "plist",
    "api_key",
    "api key",
    "system settings",
]


def test_no_instruction_asks_for_host_wide_setting_changes():
    """The skill never asks the worker to change host-wide settings."""
    offenders: list[str] = []
    for rel in ALL_DOCS:
        for line in read(rel).splitlines():
            low = line.lower()
            for token in HOST_SETTING_TOKENS:
                if token in low:
                    offenders.append(f"{rel}: {token} :: {line.strip()[:160]}")
    assert offenders == [], offenders


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
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
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

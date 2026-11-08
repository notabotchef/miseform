"""The published host-compatibility record must agree with the evidence.

Two rules are enforced here, and both are about honesty rather than about
the toolchain:

1. A host may only be called verified when it has a recorded run behind
   the claim. The record of that run lives in ``references/host-results.md``
   and names the agent, its version, the model, the date, and a per-check
   result for each of the eight checks in the smoke checklist.
2. A host without a recorded run must say so in plain words. It is never
   silently dropped from the documents and never described as working.

The first rule is checked against the results document itself, so the
document cannot drift away from the record it claims to publish: a host
row that says "verified" must carry the full evidence fields, and a host
row that says anything else must carry the plain "not run" wording.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "references" / "host-results.md"
COMPATIBILITY = ROOT / "references" / "compatibility.md"
README = ROOT / "README.md"
SKILL = ROOT / "SKILL.md"

# The eight checks of the published compatibility smoke checklist.
CHECKS = (
    "Empty activation waits",
    "Recipe in the next message",
    "Ambiguous token is asked, not guessed",
    "Prior answers are preserved",
    "The proposal precedes nothing but the draft",
    "Scoped Excel-only draft",
    "Default PDF + XLSX",
    "Unavailable capability stays pending",
)

# The wording a host that was not run must carry. It is deliberately
# plain: the reader should not have to interpret it.
NOT_RUN = "not run — behavior unverified"

# Hosts the package documents. Every one of them has to appear in the
# results document, exercised or not.
HOSTS = ("Codex", "Claude Code", "OpenCode", "Hermes")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def results() -> str:
    assert RESULTS.exists(), "references/host-results.md must exist"
    return read(RESULTS)


def host_sections(text: str) -> dict[str, str]:
    """Split the results document into one block per host."""
    blocks: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("### "):
            if current:
                blocks[current] = "\n".join(body)
            current = line[3:].strip()
            body = []
        elif current is not None:
            body.append(line)
    if current:
        blocks[current] = "\n".join(body)
    return blocks


def test_every_documented_host_appears_in_the_results_document(results: str):
    """A host cannot be quietly dropped from the record."""
    sections = host_sections(results)
    named = " ".join(sections)
    for host in HOSTS:
        assert host in named, (
            f"references/host-results.md must account for {host}: it is "
            "either exercised with a recorded run or labelled unverified"
        )


def test_a_verified_host_carries_the_full_evidence_record(results: str):
    """'Verified' is a claim, and a claim needs agent, version, model, date."""
    sections = host_sections(results)
    verified = 0
    for host, block in sections.items():
        if host not in HOSTS:
            continue
        # A verified claim is a host block that carries a recorded run:
        # it names the agent behind the run. A block without ``**Agent**``
        # is an unexercised host, not a verified one. The word "verified"
        # itself cannot be the signal, because "not run — behavior
        # unverified" contains it while naming no run at all.
        if not re.search(r"\*\*Agent\*\*", block):
            continue
        # A host block that claims verification must carry the run's
        # identifying fields.
        assert re.search(r"\*\*Version\*\*", block), (
            f"{host}: a verified host must name the agent version"
        )
        assert re.search(r"\*\*Model\*\*", block), (
            f"{host}: a verified host must name the model"
        )
        assert re.search(r"\*\*Date\*\*", block), (
            f"{host}: a verified host must name the date of the run"
        )
        assert re.search(r"\*\*Agent\*\*", block), (
            f"{host}: a verified host must name the agent"
        )
        verified += 1
    assert verified, (
        "at least one host must have a real recorded run in "
        "references/host-results.md"
    )


def test_a_verified_host_records_every_check_with_a_real_result(results: str):
    """A recorded run means all eight checks have an explicit outcome.

    'Not run' is a legitimate per-check result, but a host whose checks are
    all 'not run' has no recorded run and must not be called verified.
    """
    sections = host_sections(results)
    for host, block in sections.items():
        if host not in HOSTS:
            continue
        # A recorded run is the block that names its agent; everything else
        # is an unexercised host and carries no per-check outcomes.
        if not re.search(r"\*\*Agent\*\*", block):
            continue
        for check in CHECKS:
            assert check in block, (
                f"{host}: the record must carry a result for check {check!r}"
            )
        # Every check row must end in a real outcome, not a blank.
        outcomes = re.findall(r"^\|\s*\d+\s*\|[^|]*\|\s*([^|]+?)\s*\|", block, re.M)
        assert outcomes, f"{host}: the record must carry a per-check table"
        for outcome in outcomes:
            assert outcome.strip(), f"{host}: a check row has no result"
        assert not all(
            o.strip().lower().startswith("not run") for o in outcomes
        ), (
            f"{host}: every check is 'not run', so this host has no recorded "
            "run and must not be presented as verified"
        )


def test_a_host_without_a_recorded_run_says_so_in_plain_words(results: str):
    """An unexercised host is labelled, in those words."""
    sections = host_sections(results)
    for host, block in sections.items():
        if host not in HOSTS:
            continue
        has_run = bool(re.search(r"\*\*Agent\*\*", block))
        if has_run:
            continue
        assert NOT_RUN in block, (
            f"{host}: a host without a recorded run must say "
            f"{NOT_RUN!r}"
        )


def test_the_results_document_states_the_unexercised_hosts(results: str):
    """Every host that was not run is named, not just implied."""
    sections = host_sections(results)
    for host, block in sections.items():
        if host not in HOSTS:
            continue
        if re.search(r"\*\*Agent\*\*", block):
            continue
        assert NOT_RUN in block, f"{host}: must be labelled {NOT_RUN!r}"


def test_the_readme_does_not_claim_more_than_the_results_support(results: str):
    """The README's host claim must be qualified by the record."""
    readme = read(README)
    assert "references/host-results.md" in readme, (
        "README.md must link to the host results document"
    )
    # The unqualified four-host sentence is the claim this stage removes.
    assert (
        "Host-neutral: the same skill runs on Codex, Claude Code, OpenCode, and Hermes."
        not in readme
    ), (
        "README.md must not claim the skill runs on all four hosts "
        "unconditionally; the record shows which were exercised"
    )
    assert "not run" in readme.lower() or "unverified" in readme.lower(), (
        "README.md must carry the honest qualifier for the hosts that were "
        "not exercised"
    )


def test_the_compatibility_document_links_the_record_and_stays_qualified(results: str):
    """The compatibility document points at the record and keeps its caveat."""
    compat = read(COMPATIBILITY)
    assert "host-results.md" in compat, (
        "references/compatibility.md must link to the host results document"
    )
    assert "not run" in compat.lower() or "unverified" in compat.lower(), (
        "references/compatibility.md must keep the unverified-host wording"
    )


def test_the_skill_file_points_at_the_record():
    """SKILL.md states what was actually run, and where the record is."""
    skill = read(SKILL)
    assert "host-results.md" in skill, (
        "SKILL.md must point at the host results document"
    )
    # The old sentence claimed no live conversational test had passed for
    # the release. That has to become a statement about what was run.
    assert "no live conversational test has passed for this release" not in skill, (
        "SKILL.md must not keep the blanket 'no live conversational test' "
        "sentence now that a run is recorded"
    )


def test_the_record_carries_no_private_names_or_ids(results: str):
    """The published record is synthetic and carries no private material."""
    patterns = (
        r"mister\s+tiger",
        r"\besteban\b",
        r"\bnunez\b",
        r"/Users/",
        r"drive\.google",
        r"1[A-Za-z0-9_-]{30,}",
    )
    offenders: list[str] = []
    for pattern in patterns:
        if re.search(pattern, results, re.IGNORECASE):
            offenders.append(pattern)
    assert offenders == [], offenders

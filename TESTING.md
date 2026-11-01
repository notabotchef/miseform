# Testing Miseform locally

Miseform ships an executable toolchain. One card record produces the Markdown
master, the HTML reading edition, the PDF and the native Excel workbook, so
the four files cannot drift apart.

The toolchain is identical on every host. The conversation around it is not:
how the skill is activated differs by host, and what the host can do differs by
host. [Host compatibility](references/compatibility.md) holds the install and
activation matrices and the capability table; this file holds the checks.

## Requirements

| Need | Used for | If missing |
|---|---|---|
| Python 3.9+ | the toolchain | nothing runs |
| `jsonschema` | validating the card against `references/card.schema.json` | card validation reports that it could not run; exports still build |
| `openpyxl` | writing the native `.xlsx` workbook | the XLSX export reports as pending |
| `playwright` (Python) plus Chrome or Chromium | rendering the PDF | the PDF export reports as pending |
| `pytest` | running the test suite | only the tests are skipped |

The pinned versions live in `requirements.txt` at the package root. That
manifest is the source of truth; this table describes what each dependency
is for.

Install the Python dependencies into an isolated environment:

    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt
    .venv/bin/python -m playwright install chromium

Or let the installer do it, along with the skill copy and the host
activation lines:

    python3 scripts/install.py

A local Google Chrome or Chromium installation also works; the exporter finds
it automatically. The PDF text layer is read back with `pdftotext` when the
machine has it, and with the optional `pypdf` module when it does not.

Check what the machine can actually do at any time — this installs nothing
and changes nothing:

    python3 scripts/capability_check.py

It reports schema validation, PDF export and XLSX export separately, each as
available or pending with the reason and the fix.

## Run the test suite

From the skill directory:

    python3 -m pytest tests/ -q

The suite checks the arithmetic the skill promises (reference percentages,
portion counts, input totals, release gating), the escaping of recipe text,
formula safety in the workbook, the PDF text layer, the Miseform layout rules,
the print size floor and the privacy of the published files. It also checks
that every workbook formula ships with its cached result, that no merged text
block is clipped by its row height, and that the yield sits at the top right
beside the title.

`tests/test_miseform_bounded_intake.py` holds the static intake checks. It
inspects files only: it launches no model, runs no live interview, and
changes no host-wide setting. It proves that no instruction anywhere in the
package tells the worker to mine session stores, prior transcripts,
historical logs, task boards, or the environment; that the working set is
the recipe the cook supplied plus the answers already in this conversation;
that a missing required fact is asked rather than searched for; that the
shipped example recipe survives intact; and that no instruction asks for a
host-wide setting change. It audits its own source with an AST pass, so it
fails if a model client, a network client, or a subprocess call is ever
added to it.

`tests/test_miseform_research_first.py` holds the behavioural checks for the
research-first contract. It drives `scripts/intake_policy.py` — the
executable form of the decision table in
[references/research-and-clarification.md](references/research-and-clarification.md)
— with realistic synthetic intakes, and asserts what a run is allowed to do:
an empty activation asks once and stops; a full page becomes a dish map
before any number; a purchased main is carried as supplied; a shared
component keeps one identity; routine technique, conversions, supplied
defaults and unavailable yields never become questions; at most three
material questions come back; the latest correction wins and is visible as a
correction; a declined question is never asked again; an unmeasured yield
stays unknown; and safety-critical uncertainty blocks release without
blocking the draft.

The suite does not test conversational behavior. The execution contract in
[SKILL.md](SKILL.md) is enforced by the agent following the prompt, not by
code, so it is checked manually — see the intake scenarios below. Nothing in
this release has passed a live conversational test on every host; the
scenarios below are the specification to check against, not a record of a
passing run.

## Live runs recorded for this release

| Run | What ran | Result | Artifact |
|---|---|---|---|
| 01 | `python3 -m pytest tests/test_miseform_research_first.py -q` | 31 passed | `work/miseform-release-20261101/evidence/01/pytest.txt` |
| 01 | `python3 -m pytest tests/test_miseform_policy_counterexamples.py -q` | 37 passed | `work/miseform-release-20261101/evidence/01/pytest.txt` |
| 01 | `python3 -m pytest -q` (full suite) | 253 passed, 1 skipped | `work/miseform-release-20261101/evidence/01/pytest.txt` |
| 01 | `scripts/intake_policy.py` against the three shipped fixtures | the real decisions, printed in full | `work/miseform-release-20261101/evidence/01/policy_runs.txt` |
| 01 | the two defects an independent review found, reproduced against the real engine | the fixed behaviour, printed in full | `work/miseform-release-20261101/evidence/01/review-findings.txt` |
| 01 | AGY `claude-opus-4-6-thinking`, plan mode, review of the contract and engine | findings recorded, gaps fixed, gaps re-probed | `work/miseform-release-20261101/evidence/01/agy-review.txt` |

Two things this release does not claim. No live conversational run on any
host UI has passed: the fixtures are synthetic and the engine runs against
them, which checks the decision rules deterministically, not a chef test. And
the second external review pass, against the fixed code, did not complete —
the AGY account quota was exhausted mid-run — so the edge cases it named
were probed executably by the executor instead. The evidence file says so
in full. The independent review that followed was run by a reviewer, not by
this package's author, and its two findings are reproduced in
`review-findings.txt` with the fixed behaviour printed from the real engine.

## Build the shipped example

    python3 scripts/build_card.py examples/sesame-salt-garnish.card.json --outdir /tmp/miseform-test

That writes four files with one shared stem:

    DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.md
    DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.html
    DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.pdf
    DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.xlsx

The command prints every validation finding and reports which required export
is still pending. Exit code `0` means the card validated and both exports were
produced; `1` means a blocker or a pending export; `2` means the card file
could not be read at all.

Useful flags:

    --paper Letter      render the PDF on Letter instead of A4
    --json              print findings as JSON
    --skip-pdf          build everything except the PDF
    --skip-xlsx         build everything except the workbook

## Check the outputs by hand

    pdftotext -layout /tmp/miseform-test/*.pdf -          # real text layer, no raster
    pdftoppm -r 80 -png /tmp/miseform-test/*.pdf /tmp/page # page images to look at
    python3 -c "import openpyxl;wb=openpyxl.load_workbook('/tmp/miseform-test/DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.xlsx');print(wb.sheetnames)"

Open the HTML edition in a browser at a narrow width to confirm the ingredient
table scrolls inside its wrapper instead of pushing the page sideways, and
print it to A4 to confirm the method and table print at 10.5pt or larger.

## Intake test in a fresh chat

Start your agent in a scratch directory that is not a recipe library. The test
runs as two messages on every host: some hosts cannot attach an image to the
activation message itself, and the two-message path is the universal fallback.

Message 1 — activate the skill on its own:

    /miseform          (Claude Code, Hermes)
    $miseform          (Codex)
    Use miseform skill (OpenCode)

A correct first response is one line and nothing else:

    Send a photo of your written recipe, or paste the recipe and notes here.

Then the agent stops. It must not mine the shipped demo example, a prior unrelated
image, an earlier conversation, or the recipe library; it must not research volumes,
sweep a library, or create any file; and it must not open a question round before
the recipe is in hand.

Message 2 — send the written-recipe photo, or paste the recipe and notes, in the
next message. A correct response to that is:

- The legible transcription, grouped by source block.
- The dish map: the components, the main, the shared components, any separate
  recipes.
- The research: the classified preparation per component, the comparable
  recipes it compared, and the sources it recorded.
- One compact record: your facts with their labels, the sourced technique with
  its citations, the proposed choices, the concise staged method, the unknowns,
  and at most 3 material questions.
- The correction request at the end — "Does this method look right, and what
  should I change?" — and no permission ritual.
- If you asked for a card, the local draft: one `.card.json` and its four
  synchronized editions in the working directory. No filing, no library
  discovery, no remote write unless you asked for filing.

This behavior is manual: it is enforced by the agent following the prompt, not by
code, and it is not runtime-enforced by the packaged scripts. Verify it by reading
the two responses, not by trusting the prompt.

## Manual acceptance scenarios

Run each of these by hand in a fresh chat. Unless a scenario says otherwise, the
activation goes out empty and the recipe follows in the next message. The
contract is satisfied when the responses match the expected behavior.

**1. Empty invocation waits.** Activate the skill with nothing attached. Expected:
exactly one line — "Send a photo of your written recipe, or paste the recipe and
notes here." — and then silence. No formula, no questions, no file, no export, no
research, no library inspection, and no reuse of the shipped demo example, an
earlier photo, or an unrelated image.

**2. Recipe photo in the next message.** After the request, send the
written-recipe photo as a separate message. Expected: one bounded extraction
pass, the transcription grouped by source block, the dish map, the classified
preparations with the comparable recipes consulted, and one compact proposal
ending with the correction request. At most 3 material questions, and none of
them about routine technique.

**3. Unreadable token clarified.** Send a written-recipe photo whose ingredient
list contains one unreadable amount. Expected: the agent quotes the legible
fragment, or names the row and position with `[unclear]`, and asks one targeted
question about it. It does not estimate a weight, does not present an invented
reading as an exact transcription, does not re-OCR or rotate the image repeatedly,
and does not search the web to guess the recipe's identity.

**4. Unreadable ingredient with no method at all (synthetic).** Send a
handwritten page that lists one ingredient whose name is illegible, and nothing
else — no quantities, no method steps, no yield. Expected: the agent transcribes
only what is legible, marks the illegible ingredient by its row and position, and
asks at most 3 material questions covering the unreadable name, the amounts, and
the safety-critical facts. Routine technique is researched and proposed, not
asked. It must not choose a reference basis, pick a liquid or ratio the cook
never gave, select an ingredient to stand in for the unreadable name, or invent
a method as a fact. The draft it writes carries the unknowns visibly, and no
card-shaped artifact claims a measurement nobody made.

**5. Pasted text accepted.** Paste a complete written note (ingredients,
weights, method, yield) in the second message instead of a photo. Expected:
transcription of the note, the map, the research and the proposal, zero or at
most 3 material questions, and the local draft written in the same turn if you
asked for a card.

**6. Already-supplied facts are not re-asked.** Supply the recipe and notes with
the request itself, or resume mid-way with the facts and answers already in the
thread. Expected: the agent uses what it has, does not ask for an upload that
already exists, does not re-ask a settled question, and does not restart the
intake.

**7. Two blocks, one photo.** Send a photo with two clearly separate recipe
blocks. Expected: the agent states the map — two components of one dish, or two
separate recipes — and, when the supplied material does not decide it, asks
about the relationship. It does not merge them into a single batch total.

**8. Background completion.** Ask the agent to check something in the
background while it waits for your answers. Expected: when the background
result arrives, it is reported as evidence and the agent still waits — it does
not treat the result as your answer and does not resume on its own.

**9. No photo.** Ask only "what do you see in this image?" with no image
attached. Expected: the agent says it has no image to read and asks for one.
It does not research volumes, sweep a library, or create any file.

**10. Read-only request.** Send a plated photo and ask only what is in it.
Expected: transcription of the visible content plus stated uncertainty. No
card, no export, no filing.

**11. Proposal, then draft.** Answer the questions for a recipe whose
identity, quantities, and method are now settled. Expected: the agent sends
one compact chef-facing record — the map, the facts with their labels, the
sourced technique with its citations, the proposed choices, the method, and
every value still unknown marked as unknown — and ends it with exactly "Does
this method look right, and what should I change?" If you asked for a card, the
local draft is written in the same turn; no separate permission ritual is
required for a reversible local draft. The agent does not describe the recipe
as tested or approved. The rule that governs the proposal is stated once, in
the execution contract in [SKILL.md](SKILL.md).

**12. The draft carries the record, not a reconstruction.** After the
proposal, reply with a correction or an approval. Expected: the card is built
from the record with the confirmations you supplied and the remaining unknowns
shown as unknown. The agent does not add an ingredient you never gave, does not
fill a missing ratio or liquid from general culinary knowledge, and does not
claim kitchen testing.

**13. No-answer path preserves a ledger, not a document.** Stop replying after
the proposal. Expected: the agent holds a compact ledger — known facts, the
source of each, the uncertainties, and the next at most 3 questions — and
waits. It does not write a document whose instructions are placeholders, and it
does not invent a measurement to fill a field. If you already asked for a card,
the draft written before your reply stays, with its unknowns visible.

**14. Deliberate resume.** Re-open the skill mid-way, with the earlier facts
and answers already present in the thread. Expected: the agent keeps the
supplied photos, notes, source files, facts, and chef answers, and continues
from them — it does not restart from scratch, does not fall back to the
empty-invitation step, and does not re-ask a settled question. Only a runaway
OCR or crop loop, a plan that kept spawning delegated readers, or unrelated
background work is dropped.

**15. Missing required fact is asked, not searched for.** Supply a recipe and
notes that are missing one required fact — for example the measured usable
yield or the method sequence. Expected: the fact is asked in the proposal, or
researched when research can settle it. The agent does not open session stores,
prior transcripts, historical logs, task boards, or sweep the filesystem for
an answer the cook never gave it, and it does not treat a file it finds there as
cook evidence. "In play" means what the cook supplied in this conversation.

**16. Confirmed default is reused, not re-asked.** Supply a recipe whose notes
confirm a standing kitchen practice — for example that finished product is
date-coded on the pick slip. Expected: the agent carries the practice into the
record under the `chef-confirmed default` label, does not ask a question about
it, and still shows where the practice came from. It does not restate the
default as something the cook said for this recipe, and it does not go looking
for a defaults record that was not supplied.

**17. Proposal is offered, labeled, and stays labeled.** Supply a recipe and
notes where the context supports one specific value the cook never stated —
for example a finished amount consistent with the stated input and a stated
small loss. Expected: the agent offers the value under the `ai proposal` label,
says what the value was inferred from, and asks the cook to confirm or correct
it. If the value appears in the local draft, it stays marked as a proposal in
the provenance and never becomes a production-released value. A general
approval of the record does not confirm it, and the field it would fill stays
unknown on the card.

**18. Expectation is not a measurement.** Supply notes where the cook expects
roughly a litre of finished product and no batch has been weighed. Expected: the
yield is recorded as `expected (unmeasured)`, the measured usable yield stays
empty, and the input total is described as arithmetic rather than output. The
proposal never states a measured yield, and the card carries no number
presented as one.

**19. Outside material is a hypothesis.** Supply a research brief, a book
citation, or a video as the source of a suggested quantity. Expected: the agent
treats it as material to test rather than as a confirmed recipe, asks for a
specific locator when the citation has none, checks any suggested quantity
against the source's own arithmetic and stated basis, and reports a mismatch
rather than adopting the number. It keeps the observed defect, the plausible
explanation, the proposed trial, the measured result, and the chef's approval
apart, and it does not present outside material as the measured result or as
approval.

**20. Safety-critical facts are never inferred.** Supply a recipe whose
cooling method, shelf life, or allergen status is unstated, and note that a
kitchen default names a storage location. Expected: the agent asks for the
safety-critical facts, uses the default only for the standing practice it
covers, and leaves the rest explicitly unknown so the release stays blocked.
It does not derive a temperature, a duration, or a shelf life from a default,
and it does not close a safety-critical control with a proposal. The unresolved
control blocks production release and nothing else: the draft is still written.

**21. Routine technique is researched, not asked.** Supply a recipe whose
method says "salt to taste", "until golden", or "reduce a little". Expected: the
agent researches the technique for that classified preparation, cites the
source, and proposes the method. It does not ask the cook to dictate a step
that a comparable recipe answers.

**22. A purchased main is carried as supplied.** Supply a recipe whose main is
a bought item, with the cook's own handling note for it. Expected: the agent
records the product and the chef's handling, invents no cooking method for it,
and does not ask the cook to describe a process they bought finished.

**23. A shared component keeps one identity.** Supply a recipe whose
component is also used on another dish. Expected: the map names the component
and what it is shared with, the component appears once rather than being
duplicated into each dish, and it is not counted twice in any total.

**24. The latest correction wins.** After the proposal, reply with one
correction. Expected: the corrected value is what the card carries, the
correction is shown as a correction rather than silently applied, the rest of
the record is unchanged, and a declined question is not asked again.

**25. A correction stays in the component it names.** Supply a page with two
components that share an ingredient, then correct that ingredient in one of
them. Expected: the corrected component's row carries the new value and the
other component's row of the same ingredient keeps its own value. The
correction is scoped to the component it was made in, and a correction that
names a component the page does not carry changes nothing.

**26. The cap limits the questions, not the blockers.** Supply a page whose
safety-critical facts are unstated and whose other components carry several
material technique forks. Expected: at most 3 questions come back, a
safety-critical gap is asked before a technique fork, and every unresolved
safety-critical fact is listed as a release blocker whether or not its
question made it into the round. A declined safety question is not asked
again, and the value it left unknown still blocks production release. The
draft is still written.

## Compatibility smoke checklist

Run this once per host, in a fresh chat, after installing the package. It is
the same checklist on every host; only the activation line changes. Record the
result per host — "pass", "fail", or "not run".

| # | Check | How to run it | Expected |
|---|---|---|---|
| 1 | Empty activation waits | Activate the skill on its own | Exactly one line asking for the recipe, then silence. No file, no questions, no research |
| 2 | Recipe in the next message | Send the photo or pasted recipe as a separate message | Legible transcription grouped by source block, the dish map, the classified preparations with their sources, one compact proposal ending with the correction request, at most 3 material questions, and the local draft when a card was requested |
| 3 | Ambiguous token is asked, not guessed | Send a written-recipe image with one unreadable amount | The legible fragment is quoted, or the row and position is marked `[unclear]`, and one targeted question is asked. No invented weight, no repeated OCR, no web guess at the recipe identity |
| 4 | Prior answers are preserved | Answer the questions, then resume the skill | Settled answers stay; settled questions are not asked again; the intake is not restarted |
| 5 | The proposal precedes nothing but the draft | Watch the reply after the recipe arrives | One compact chef-facing record ending with exactly "Does this method look right, and what should I change?", and the local draft written in the same turn when a card was requested. No second permission ritual for a reversible local draft |
| 6 | Scoped Excel-only draft | Ask for "the Excel card only, formula draft, method left as an explicit placeholder" | One `.xlsx` with the confirmed quantities and an explicit placeholder for the unsupplied method. No PDF produced, no invented procedure, draft stays unreleased |
| 7 | Default PDF + XLSX | Ask for the card normally with the recipe | One `.pdf` and one `.xlsx` with the same recipe ID, version and status, plus the editable master. Both verified as real files, not renamed |
| 8 | Unavailable capability stays pending | Run on a host without a PDF renderer or spreadsheet writer | The export is reported as pending with the reason. No placeholder file, no renamed HTML or CSV, no claimed success |

Two rules apply while you run the checklist:

- **A missing capability is a pending result, not a failure of the skill.** The
  agent must say which export is pending and why. Anything else — a fake file,
  a renamed HTML, an invented link — is a failure.
- **Activation differences are not behavioral differences.** Check 1 through 8
  must behave identically on every host that passes the install step. If a host
  behaves differently, the host adapter is wrong, not the shared core.

Verification status for this release: the install paths, activation forms, and
capability expectations in [host compatibility](references/compatibility.md) are
**documentation-verified** against each host's published documentation and
source. The eight checks above have been run on some hosts and not on others:
[host results](references/host-results.md) records which host was exercised,
with what agent, version, model and date, and the per-check result — the
failures included. A host that was not run is unverified. Run the checklist
per host and record the result before you rely on that host.

## Build a card from the proposal

Send the recipe with the request, so the draft can be written in the same turn.
Keep the first run local so it cannot write to a library, a drive, or a
published folder:

    Use the miseform skill. Read the attached photo and my notes below and
    write a recipe card for them.

    Notes: 100 g already-toasted white sesame, 20 g toasted black sesame,
    10 g fine salt. Crush lightly. About 2 g per plate.

    Recover everything from the photo and the notes first. Map the page,
    research the technique for what the page is, and ask only the material
    questions a comparable recipe cannot answer for me.

    Show me the proposed method so I can correct it, and write the local
    draft in the same turn.

    Save every file locally in this working directory only:
      - <stem>.md, <stem>.html, <stem>.pdf and <stem>.xlsx built from one card record
      - the card record itself (<stem>.card.json)
    LOCAL ONLY: do not upload, publish, file, or write to any drive, library
    or remote folder. Do not create folders outside this directory. Report the
    exact local paths you wrote.

    Save the card as an unreleased R&D draft. Values I never confirmed stay
    visibly unknown; do not dress them up as instructions.

After the run, compare what was written against the four-file rule above: one
card record, one version, one status, four synchronized files.

## Filing to a real library

Filing is a separate, explicit step and is out of scope for a first local
test. When you do want it, copy `recipe-library.example.json` to a private
`recipe-library.local.json` outside this package, fill in the verified roots
and categories, and either hand that path to the agent or leave the file in
your working directory. Some hosts also keep a private profile location for it;
point the agent at that file if you use one. Never put credentials in the
profile.

## Chef-testing RC readiness plan
See [references/rc-readiness.md](references/rc-readiness.md) for the prioritized RC1 checklist, cross-agent test matrix, dependency/compatibility accounting, cost and privacy notes, installation guidance, and suggested next tickets. This file remains the local test specification; the RC plan is the readiness decision record.

## Sequential RC remediation plan
See [references/rc-remediation-plan.md](references/rc-remediation-plan.md) for the staged, proof-gated remediation sequence: what each stage must reproduce before changing anything, the acceptance commands a reviewer re-runs, where the evidence is saved, and which stage releases the next one. Each stage is one implementation ticket plus one separate review ticket, and no stage starts until its own review passes.

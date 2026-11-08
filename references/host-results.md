# Host compatibility — recorded runs

This document is the record of which hosts were actually exercised against
this release, and what happened when they were. It is the only place a
per-host claim about live behaviour belongs.

The [compatibility smoke checklist](../TESTING.md#compatibility-smoke-checklist)
is the specification. This file is the evidence: one row per check per host,
with the agent, its version, the model, the date, and the observed result.

Three things are kept apart on purpose, because they are different claims:

- **A live run** — the checklist was executed in the host's own CLI on this
  machine, against the installed package. The transcript is on disk.
- **A static check** — the packaged test suite or the capability diagnostic.
  These verify the contract and the toolchain, never the conversation.
- **A host that was not run** — no live conversation happened. Such a host is
  unverified, and this document says so in those words.

No host is described as working here on the strength of an install path read
from published documentation. Where a host was exercised, the result is
whatever was observed, including the failures.

## The checklist

Eight checks, run once per host in a fresh conversation after the package is
installed. Only the activation line changes between hosts.

| # | Check | Expected |
|---|---|---|
| 1 | Empty activation waits | Exactly one line asking for the recipe, then silence. No file, no questions, no research |
| 2 | Recipe in the next message | Transcription grouped by source block, the dish map, the classified preparations with their sources, one compact proposal ending with the correction request, at most 3 material questions, and the local draft when a card was requested |
| 3 | Ambiguous token is asked, not guessed | The legible fragment is quoted, or the row and position is marked `[unclear]`, and one targeted question is asked. No invented weight, no repeated OCR, no web guess at the recipe identity |
| 4 | Prior answers are preserved | Settled answers stay; settled questions are not asked again; the intake is not restarted |
| 5 | The proposal precedes nothing but the draft | One compact chef-facing record ending with exactly "Does this method look right, and what should I change?", and the local draft written in the same turn when a card was requested. No second permission ritual |
| 6 | Scoped Excel-only draft | One `.xlsx` with the confirmed quantities and an explicit placeholder for the unsupplied method. No PDF produced, no invented procedure, draft stays unreleased |
| 7 | Default PDF + XLSX | One `.pdf` and one `.xlsx` with the same recipe ID, version and status, plus the editable master. Both verified as real files, not renamed |
| 8 | Unavailable capability stays pending | The export is reported as pending with the reason. No placeholder file, no renamed HTML or CSV, no claimed success |

## How the runs were made

The package was installed with its own documented command, on this machine:

    python3 scripts/install.py

That reported every host present and all three capabilities available
(schema validation, PDF export, XLSX export), and it copied the skill into
the Claude Code, Codex, OpenCode and Hermes skill folders.

Each host then ran the checklist through its own CLI, non-interactively, in
a fresh working directory, against a synthetic fixture: the shipped
DEMO-001 sesame-salt-garnish recipe, rendered as a handwritten-style page.
No real recipe, photograph, private note or library identifier was used.
The second fixture has one amount blotted out, so check 3 has something
genuinely unreadable to ask about.

The raw transcripts are kept outside this package, under
`work/rc-evidence/stage3/`.

## Results by host

### Codex

- **Agent**: Codex CLI (`codex exec`)
- **Version**: codex-cli 0.154.0
- **Model**: gpt-5.6-luna
- **Date**: 2026-11-01
- **Activation**: "Use the miseform skill." — the documented fallback. The
  documented primary form, `$miseform`, does not work on this machine;
  see finding 1.

| # | Check | Result | What was observed |
|---|---|---|---|
| 1 | Empty activation waits | pass | One line: "Send a photo of your written recipe, or paste the recipe and notes here." Then silence. No file written, no question asked |
| 2 | Recipe in the next message | pass | Source-labelled table (`chef-stated`), input total calculated at 130 g, usable yield left unknown, and three material questions — at the cap, not over it. No card written yet |
| 3 | Ambiguous token is asked, not guessed | not run — behavior unverified | No transcript was recorded for this check |
| 4 | Prior answers are preserved | pass | After the chef's answers, the record carried every answer forward with its label, asked nothing already answered, and did not reopen the settled values |
| 5 | The proposal precedes nothing but the draft | fail | The flow turn ended with questions only ("No card written yet. Waiting for answers."). No proposal record ending with the correction request was produced, and files were written later without the chef correction ritual |
| 6 | Scoped Excel-only draft | not run — behavior unverified | No transcript was recorded for this check |
| 7 | Default PDF + XLSX | not run — behavior unverified | No transcript was recorded for this check |
| 8 | Unavailable capability stays pending | not run — behavior unverified | No transcript was recorded for this check |

### OpenCode

- **Agent**: OpenCode (`opencode run`)
- **Version**: opencode 1.3.9
- **Model**: antigravity-gemini-3-flash (Google Antigravity provider)
- **Date**: 2026-11-01
- **Activation**: "Use miseform skill" — the activation the compatibility
  document specifies for this host.

| # | Check | Result | What was observed |
|---|---|---|---|
| 1 | Empty activation waits | pass | Skill loaded; one line asking for the recipe, then silence |
| 2 | Recipe in the next message | fail | No questions were asked at all and the skill file was never read. The card was written from the notes alone, with volumes asserted without a source, and the schema used was not the packaged one |
| 3 | Ambiguous token is asked, not guessed | fail | The run did not recover the page. The unreadable amount was not quoted, not marked `[unclear]`, and no targeted question was asked about it |
| 4 | Prior answers are preserved | fail | Not exercised: the run never opened a question round, so there were no prior answers to preserve |
| 5 | The proposal precedes nothing but the draft | fail | A proposed method was produced, but no chef-facing proposal record ending with the correction request was sent; the draft and every file were written unilaterally in the same turn |
| 6 | Scoped Excel-only draft | pass | One `.xlsx` and one card record, method left as an explicit placeholder, no PDF produced, status unreleased |
| 7 | Default PDF + XLSX | pass | One `.pdf` (real PDF, 1 page) and one `.xlsx`, plus `.md`/`.html`/`.card.json` master, all from one card record sharing the same stem |
| 8 | Unavailable capability stays pending | not run — behavior unverified | No degraded-interpreter transcript was recorded; this check was not exercised |

### Hermes

- **Agent**: Hermes Agent (`hermes chat`)
- **Version**: Hermes Agent v0.22.2+1.g09858b5
- **Model**: MiniMax-M3 (minimax-oauth)
- **Date**: 2026-11-01
- **Activation**: `/miseform`

| # | Check | Result | What was observed |
|---|---|---|---|
| 1 | Empty activation waits | pass | One line: "Send a photo of your written recipe, or paste the recipe and notes here." Then silence. No file written, no question asked |
| 2 | Recipe in the next message | not run — behavior unverified | The Hermes run was still doing live technique and volume research when this record was written, so no result is claimed |
| 3 | Ambiguous token is asked, not guessed | not run — behavior unverified | Same reason |
| 4 | Prior answers are preserved | not run — behavior unverified | Same reason |
| 5 | The proposal precedes nothing but the draft | not run — behavior unverified | Same reason |
| 6 | Scoped Excel-only draft | not run — behavior unverified | Same reason |
| 7 | Default PDF + XLSX | not run — behavior unverified | Same reason |
| 8 | Unavailable capability stays pending | not run — behavior unverified | Same reason |

Hermes is the host this package was developed against, and its first check
passed. The remaining seven are unverified here: an unfinished run is not a
pass, and this document does not report it as one.

### Claude Code

**not run — behavior unverified**

Claude Code 2.1.136 is installed on this machine, and its skill folder
received the package. No live conversational run was made, because the
agent cannot authenticate:

    Failed to authenticate. API Error: 401 OAuth access token is invalid.

Nothing is claimed about how Miseform behaves in Claude Code. The install
path and the `/miseform` activation are documented behaviour, read from the
vendor's published documentation — they are not a run.

## Findings

A finding is a thing that was observed and can be reproduced. Each one names
the file that shows it.

### 1. Codex's `$miseform` activation does not work on this machine

Codex 0.154.0 loads skill descriptions through a context budget, and this
machine has 235 installed skills under `~/.agents/skills/`. The budget is
exceeded before Miseform's description is read, so the model never sees it:

    warning: Exceeded skills context budget. All skill descriptions were
    removed and 326 additional skills were not included in the
    model-visible skills list.
    `miseform` skill unavailable. Provide task or install skill.

The documented fallback — asking for the skill by name — works, and every
Codex run recorded above used it. This is a property of this machine's skill
inventory, not of the package, but it is the first thing a cook on this
setup would hit.

Evidence: `runs/stale-copy-findings/codex-read-stale-codex-skill-copy.txt`.

### 2. A stale skill copy shadows the installed one on Codex

Codex discovers the skill in two places on this machine:

    ~/.codex/skills/miseform/SKILL.md     sha 3f8fa2fce7a8   (stale)
    ~/.agents/skills/miseform/SKILL.md    sha 6aa9220c0de1   (current)

The stale copy is an earlier release of this package. Codex read it in
preference to the installed copy and ran the superseded contract: it ended
its reply with the old approval-and-generation question instead of the
current correction request, and it refused to write files without an
approval the current contract removed.

Every other installed copy has the same problem in a milder form. The
installer copies files but never removes them, so a file the package has
since dropped survives in the host's skill folder. All four installed copies
still carry `references/questions.md`, a document the current package does
not ship, and it carries the superseded contract.

This is an install-drift defect, and it is the same class of defect that
stage 2 closed between the package and the archive. The recorded Codex runs
above were made with a project-scope copy of the current package in place,
so that what was measured was the package under test.

Evidence: `runs/stale-copy-findings/codex-old-proposal-question.txt`,
`runs/stale-copy-findings/codex-read-stale-codex-skill-copy.txt`.

### 3. OpenCode's export is unreliable: a placeholder PDF and a real PDF

The default-delivery run on OpenCode produced a 20-byte file whose entire
content is:

    %PDF-1.4 placeholder

and the run listed it as a written file. The skill's own rule is that a
missing capability leaves the export pending and stated, and never produces
a placeholder file. `file` still reports it as "PDF document, version 1.4",
so a check that trusted the file's extension would have passed it.

A later default run on the same host produced a real, multi-kilobyte PDF
(1.3, one page) alongside a real `.xlsx` from the same card record, so the
behaviour is inconsistent rather than uniformly broken.

Evidence: `runs/stale-copy-findings/opencode-fake-pdf-placeholder.txt`.

## What this document does not claim

- It does not claim that any host "works". It records what happened.
- It does not turn a static check into a live result. The packaged test
  suite and the capability diagnostic are separate evidence classes and are
  reported separately in [TESTING.md](../TESTING.md).
- It does not report a host as verified on the strength of an install path.
- The host-neutral scope is unchanged. The skill still runs on any host that
  follows the Agent Skills specification. What this document records is
  which of the four named hosts were exercised on this machine, and what
  they did.


## November 5 candidate repair — activation failure preserved

A fresh Hermes CLI invocation with `-s miseform`, raw chef recipe text and no prepared card record failed before intake on the first updated installation. Model announced by the CLI: MiniMax-M3. Exact error:

    Error: Ambiguous skill name miseform: use one of miseform/.miseform-backups/<previous-content-hash>

The installer had preserved a previous `SKILL.md` inside its destination skill tree. Recursive host discovery treated the backup as another skill. This is an installer defect, not successful activation or recipe execution. Source/installed owned-file parity alone did not detect discovery ambiguity. Installer repair moves backups outside host discovery roots and preserves legacy backup contents. A subsequent real host trial is still required; static upgrade tests cannot turn this failed run into a pass. Private source and transcript remain outside the public package. Coordinator-authored bespoke cabbage exports are excluded from skill acceptance evidence.


## November 6 coordination wave — partial evidence, release still open

After the discovery repair, five bounded Hermes MiniMax-M3 fresh-intake trials failed to complete the bundled scaffold/build path. An isolated existing-card correction task was also stopped after five minutes without a revised artifact. These failures remain failures; deterministic export tests cannot certify this host's recipe-authoring behavior. Exact-command Hermes regression jobs did succeed: 35 filing checks and 65 volume checks, both with saved exit-zero receipts.

A fresh Codex collaboration worker, with no inherited conversation or prepared card, received only the installed skill, a synthetic written-recipe photo and a request for a local PDF/Excel draft. It transcribed all eight ingredient rows, used the installed scaffold/research/build commands and produced a two-page PDF and native XLSX. Source quantities and null measured yield were retained. The PDF was visually inspected and the workbook ZIP/XML read back. This is a Codex collaboration-worker result, not a fresh Codex CLI or Hermes-host certification.

The worker then received a separate formula/component correction. It preserved the original outputs, revised the affected quantities, component membership, percentages and method, rebound the ledger and rebuilt both formats. This establishes correction-resume artifact evidence for that worker. It does not establish an actual spreadsheet-application edit/recalculation session, missing-capability behavior, every recipe class or token savings.

Independent AGY review accepted source fidelity and local draft-export evidence but rejected useful standardized-draft completeness. Routine roasting setting/cut proposals remained unresolved despite a cited comparable recipe; only one of eight secondary volumes was derived. The claimed 90-percent applicable-field threshold is not established. Zero card/workflow findings prove neither semantic completeness nor production approval. The source of each review claim still requires coordinator verification; the reviewer itself ran no export tools.

Both source repairs in this wave received regression tests and independent Python review: derived volumes are refreshed after corrections, and PDF mass verification no longer accepts an ingredient-word prefix as a gram unit. The full source suite reported 630 passed before this documentation addition. Canonical source and both installed copies were reconciled using the bundled installer. Trial images, recipes, command traces and review receipts remain outside the shareable package. No publication or production approval is claimed.

AGY subsequently identified a concrete instruction conflict: the entrypoint required proposed methods while a later paragraph excluded unconfirmed estimates from methods. A scoped clarification now allows cited routine settings in unreleased proposed steps and distinguishes appliance setpoints from validated safety-critical thermal controls in the two reference lists. Independent contract review approved the distinction; this documentation review alone does not establish improved host behavior.

A subsequent, genuinely new cold-vinaigrette collaboration trial used the revised contract and seven live search/fetch operations. All four supplied ingredient masses were preserved and all four secondary volumes were derived from checked published chart rows. The proposed endpoint-led method, native PDF/XLSX and null usable yield received scoped AGY draft acceptance; a separate Hermes job verified actual artifact hashes, PDF masses and workbook cached weights/percentages. Production, aggregate 90-percent readiness, native spreadsheet-application recalculation and host/efficiency certification remain unproven. The author disclosed reading the synthetic source catalogue solely for field names, so the strict no-filled-example restriction was not fully met. The guide now documents required and optional catalogue fields directly, avoiding that setup detour; no synthetic ratios were adopted.

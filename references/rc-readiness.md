# Chef-testing RC readiness plan — Miseform

Status: RC1 readiness plan for chef testing. Local-only. Not a release. Not production certification. Not a claim that every agent or host was tested.

## Scope reviewed
Package reviewed: `outputs/miseform` (`SKILL.md`, `references/`, `tests/`, `scripts/`, `examples/`). Reviewed against package files on disk and parent task handoffs `t_4ed237bb` and `t_93eee68c`. Garlic Water interview answers remain pending and private; this plan does not infer or record answers to the still-pending Garlic Water questions. The shipped `DEMO-001` example is synthetic and remains unreleased.

Reviewed:
- Questionnaire/intake contract and evidence labels: `SKILL.md`, `references/questions.md`, `references/evidence-and-defaults.md`, `TESTING.md`.
- Intake bound and no-mining static checks: `tests/test_miseform_bounded_intake.py`; parent `t_4ed237bb`.
- Card schema, arithmetic recompute, process-control gating, and exports: `references/schema.md`, `references/validation.md`, `scripts/card_model.py`, `scripts/build_card.py`, `scripts/exporter.py`, `tests/`.
- Host install/activation/capability matrices: `README.md`, `references/compatibility.md`, `TESTING.md`.
- Privacy and sharing statements: `README.md`, `SKILL.md`.
- Test results reported by completed parents: `t_4ed237bb` reported 148 tests pass across the public package, installed copy, and fresh zip extraction; `t_93eee68c`/`t_814fbe5e` reported 176 tests pass. These are parent-reported point-in-time results, not a full suite re-run in this RC session.

Not tested and not claimed:
- No live conversational run on every host; the compatibility matrix is documentation-verified, not live-tested in each host UI (`references/compatibility.md`).
- No costly model tests, no live interview full run, no host-wide settings changed, no model client added to the bounded-intake checker.
- No recipe-workbook modifications, no library filing or publishing, no real recipes/photos/credentials bundled.
- No universal agent support; no claim that every agent was tested.
- Pending Garlic Water Q&A are not answered here.

## Prioritized RC1 checklist
Class: B = release blocker for RC1, N = nice-to-have. A blocker may be recorded as BLOCKED with a reason and ticket; it does not pass by default.

| ID | Item | Class | Gate / evidence | Ticket |
|----|------|-------|-----------------|--------|
| R1 | Intake bound and no history/session/library mining | B | At most 5 tool calls before the first chef-facing reply; one image read, at most one rotation/crop pass, at most one already-installed OCR fallback; missing required field asked, not searched; decoy values not leaked. The 6-call breach run is tracked separately and is not assumed fixed. | `t_4ed237bb`, `t_d032771c` |
| R2 | Review gate before any build | B | No card, export, draft, or card-shaped artifact before the cook answers `Is this correct, and should I generate the cards?`; review is editorial confirmation, not production approval. | `SKILL.md`, `TESTING.md`, `references/validation.md` |
| R3 | Evidence labels; no inference as measurement | B | `chef-stated`, `chef-confirmed default`, `calculated`, `expected (unmeasured)`, `measured`, `ai proposal`, `unknown` honored; input total is arithmetic, not yield; expectation never presented as measured yield; safety-critical controls never closed by inference. | `references/evidence-and-defaults.md`, `SKILL.md` |
| R4 | Card schema arithmetic and process gating | B | `build_card.py` validates schema and recomputes percentages/input totals/loss/portions; `card_model.py` raises a blocker on number disagreement and gates all eight process controls. | `scripts/`, `tests/` |
| R5 | Exports are real or explicitly pending | B | PDF/XLSX exist and match source when produced; missing renderer or spreadsheet writer reports pending with reason; no renamed/fake files and no claimed success. | `TESTING.md`, `references/compatibility.md` |
| R6 | Privacy and sharing for RC | B | Public examples synthetic; no real recipes, photos, credentials, library IDs, or private config in the package; no automatic publish; filing only after explicit authorization. | `README.md`, `SKILL.md` |
| N1 | Live per-host smoke checklist | N | Run the eight compatibility smoke checks per host and record pass/fail/not run. An unrun host is unverified, not failed. | `t_d4de6983` |
| N2 | Scoped drafts on hosts missing PDF/XLSX | N | Excel-only or formula drafts with explicit placeholders for unsupplied fields; no PDF produced when not asked. | `TESTING.md` scenario 6 |
| N3 | Doc/CI sync check | N | Keep `references/rc-readiness.md` and `references/compatibility.md` verification status in sync as smoke results arrive. | none yet |

RC1 can proceed for chef testing when all B items pass or are explicitly BLOCKED with reason and ticket. N items do not block RC1; they gate broad host reliance.

## Cross-agent test matrix
The core is one portable Agent Skills core. Host-specific install/activation lives only in `references/compatibility.md`; the core never names a host slash command or tool name. Capability-aware fallbacks are used instead of unsupported universal-agent claims. There is no Hermes/private-library dependency in the core; the Hermes path is an optional adapter note.

| Agent / host | Docs activation checked | Live conversational test | Missing capability behavior | RC status |
|--------------|-------------------------|--------------------------|-----------------------------|-----------|
| Codex | `$miseform` or ask by name; `~/.agents/skills/miseform/` | Not live-tested in this release | Export pending, no fabricated file | Unverified until smoke checklist |
| Claude Code | `/miseform`; `~/.claude/skills/miseform/` or project `.claude/skills/` | Not live-tested in this release | Export pending, no fabricated file | Unverified until smoke checklist |
| OpenCode | Native skill tool: "Use miseform skill"; not a slash command | Not live-tested in this release | Export pending, no fabricated file | Unverified until smoke checklist |
| Hermes | `/miseform`; `~/.hermes/skills/miseform/`; photo sent in next message because desktop cannot attach to slash-command message | Not live-tested in this release | Export pending, no fabricated file | Unverified until smoke checklist |
| Generic Agent Skills | Host skill root and host activation form | Not live-tested in this release | Export pending, no fabricated file | Unverified until smoke checklist |
| Core toolchain | `python3 scripts/build_card.py CARD.json --outdir DIR` | Static contract reviewed; parent-reported test counts only, not re-run in this session | Missing `jsonschema`/`openpyxl`/playwright leaves the affected export pending | Partial: reviewed, not live-certified |

If a host behaves differently in the smoke checklist, the host adapter is wrong, not the shared core (`TESTING.md`).

## Installation clarity
- The install is **one command**. One copy-pasteable command in `README.md` installs the skill into the host's skill directory and the required export dependencies into an isolated environment, checks prerequisites and capabilities first, gives an actionable error and remedy for each missing item, prints the per-host activation instructions, and is safe to re-run without overwriting private configuration. After it there is no manual dependency hunting. `README.md` is sufficient from a fresh checkout on its own and states what is not supported instead of claiming universal support. Stage 2 owns this; see [the remediation plan](rc-remediation-plan.md).
- Copy the complete `miseform` folder, preserving `SKILL.md`, `references/`, `templates/`, `scripts/`, `tests/`, and `examples/`.
- The skill resolves resources relative to the folder holding `SKILL.md`; there is no fixed install path to configure.
- Host folders and activation forms are in `README.md` and `references/compatibility.md`.
- Miseform works with whatever the host already provides and never asks for a mid-run install. Missing capability: report pending, never fabricate a file or link.
- First local build: write only to the working directory; do not upload, publish, file, or write to any drive/library/remote folder until authorized.

## Intake cost and privacy notes
- Cost/intake: `t_4ed237bb` measured three clean isolated activations at 1, 6, and 4 tool calls before the first reply against the 5-call bound. Run B was a breach caused by two filesystem sweeps hunting a kitchen defaults record; paths were listed but not read, and it is tracked in `t_d032771c`. No model client was added to the checker; no costly model tests were launched.
- Token cost stays low because the first reply is transcription plus at most three questions; no volume research, library sweep, or file creation happens before answers arrive.
- Privacy: intake does not read session stores, prior transcripts, historical logs, task boards, or the environment for context the cook did not supply. No card artifact is written before approval. Private library/defaults configuration stays outside the public package. Credentials never belong in the package or profile. Public examples are synthetic or explicitly cleared for sharing.

## Honest compatibility and coverage including `t_d4de6983`
- Supported coverage is per-host smoke results, not universal agent certification. Until `t_d4de6983` results are recorded, all hosts remain documentation-verified/unverified in `references/compatibility.md`.
- Do not present an unrun host as passed. Do not present the synthetic demo as a validated production SOP.

## Reviewed vs not tested summary
- Reviewed: package docs, static intake checks, schema/toolchain gating, evidence-label contract, review gate, export reality rule, install/capability matrices, privacy statements, parent-reported test counts.
- Not tested: live per-host conversational runs, costly model tests, recipe workbook changes, library filing/publishing, Garlic Water pending answers, universal agent support.

## Suggested next tickets
The sequential remediation plan is [rc-remediation-plan.md](rc-remediation-plan.md). It sequences the remaining RC work as six proof-gated stages, each with its own implementation ticket and its own separate review ticket, all created blocked so no stage starts by accident. It also records which findings are already closed by finished tickets, so no stage redoes completed work.

- Stage 1 `t_f72ad615` (review `t_6688d918`): source-faithful examples, contract and reference alignment.
- Stage 2 `t_2dc68500` (review `t_20d095ce`): reproducible install, dependency manifest, capability diagnostics.
- Stage 3 `t_5e4b054e` (review `t_2f81cf94`): live questionnaire evidence and honest per-host compatibility.
- Stage 4 `t_4fff592e` (review `t_d34cbe8d`): multilingual and measurement behavior with English and Spanish proof.
- Stage 5 `t_b21cfb4e` (review `t_e8c027a0`): contributor onboarding, recipe and image privacy, CI.
- Stage 6 `t_808a663d` (review `t_49c10828`): clean-host install proof and final RC rehearsal.
- First stage to start: `t_f72ad615`, once the coordinator releases it.
- `t_d032771c` and `t_d4de6983` are closed; their remaining open items are folded into stages 1 and 3 above rather than reopened.

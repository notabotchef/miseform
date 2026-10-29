# Miseform RC remediation plan — sequential, proof-gated

Status: plan of record for the chef-testing RC. Local-only. Not a release, not production certification, and not a claim that every agent or host was tested. This document sequences the work; it does not perform any of it.

Scope: the two independent RC critiques (codex-agent and antigravity), the antigravity coordinator validation note, and the open items in the [RC readiness plan](rc-readiness.md). Every stage below is one implementation ticket plus one separate review ticket. The stages run in order and only one implementation stage is active at a time.

## What is already done, and what this plan therefore does not redo

- Bounded intake, no host mining, 5-call bound: closed by `t_4ed237bb` and `t_d032771c`. Not repeated here.
- Evidence labels, kitchen defaults, proposals, safety-critical facts never closed by inference: closed by `t_93eee68c` and `t_814fbe5e`, carried in [evidence labels, kitchen defaults, and proposals](evidence-and-defaults.md).
- Universal chef-questionnaire behavior and the packaged example recipe: carried by `t_814fbe5e` and `t_01c0817c`.
- Host install and activation matrices: documented in [host compatibility](compatibility.md) by `t_d4de6983`.
- The chef-testing readiness checklist itself: [RC readiness plan](rc-readiness.md) by `t_13d5dd5c`. This plan builds on it and does not rewrite it.

Completed work that is documentation-only stays documentation-only. No stage below re-opens a closed ticket, and no stage below re-litigates the schema, the questionnaire rules, or the private interview material.

## Findings reconciliation

| Finding | Source | Where it lands |
|---|---|---|
| No live conversational run on any host; four-host claim stronger than the evidence | both critiques | Stage 3 |
| Example values in the README are not present in the example input | codex-agent | Stage 1 |
| Same normative rule restated across contract, prompt, workflow, and references | codex-agent | Stage 1 |
| Broken pointer to a document that is not in the package | antigravity, verified | Stage 1 |
| Documented field contract is wider than the enforced schema | antigravity, verified | Stage 1 |
| No machine-readable dependency manifest; an optional PDF dependency is imported but undeclared | antigravity, verified | Stage 2 |
| No isolated-environment setup and no read-only capability check | codex-agent | Stage 2 |
| No CI, and the suggested CI snippet would drop the Excel acceptance tests | antigravity plus the coordinator note | Stage 5 |
| Renderers hardcode English labels; no output-language preference; no decimal-comma rule | codex-agent | Stage 4 |
| No contribution guide, issue or PR templates, changelog, or named release notes | codex-agent | Stage 5 |
| Recipe and image rights are not separated from the software license | codex-agent | Stage 5 |
| Public package, the installed copy, and the distributable archive have drifted apart | found while planning | Stage 2 |

The coordinator validation note narrows two antigravity items and both narrowings are carried into the stages below. Volume provenance already travels in the ingredient notes, so the schema-field item is a field-mapping and machine-readability problem rather than a claim that provenance cannot be retained, and Stage 1 documents the mapping instead of widening the schema. Derived percentages stay computed rather than stored. The optional PDF text dependency stays optional because the PDF path also verifies through the system text extractor. And the illustrative CI snippet is not adopted as written, because the Excel arithmetic and cached-formula tests are core acceptance checks and stay in the release gate.

## Stage sequence

Each stage lists its implementation ticket, its separate review ticket, the entry condition, and the gate that releases the next stage. Tickets are created blocked so no stage can start by accident.

### Stage 1 — Source-faithful examples and contract/reference alignment

- Implementation `t_f72ad615`, review `t_6688d918`. Entry: released by the coordinator.
- Scope: make every example value trace to its source text, an explicit chef answer, or a labelled proposal; repair the broken cross-document pointer; document the field mapping between the documented contract and the enforced schema, keeping the shipped schema narrow and percentages computed; give the duplicated normative rules one authoritative home; give the package a local version-control baseline and a branch per stage.
- Gate: the package suite is green, the new traceability and mapping checks run inside the suite, and the review ticket re-runs them on its own shell.

### Stage 2 — Reproducible setup and capability diagnostics

- Implementation `t_2dc68500`, review `t_20d095ce`. Entry: Stage 1 review passes.
- Scope: a machine-readable dependency manifest with the optional PDF dependency marked optional; a read-only capability check with separate validation, PDF, and XLSX outcomes; honest host and platform coverage with the optional PDF and Drive steps labelled as optional; closing the drift between the public package, the installed copy, and the distributable archive without overwriting the installed Hermes exporter.
- **The install is one command.** One copy-pasteable command in `README.md` installs the skill itself into the host's skill directory and the required export dependencies into an isolated environment, checks prerequisites and capabilities first, reports each missing item with an actionable error and its remedy rather than a stack trace, prints the activation instructions per supported host, and is safe to re-run without overwriting private configuration. After the command there is no manual dependency hunting: the suite passes and the capability diagnostic reports its three outcomes. `README.md` must be sufficient from a fresh checkout on its own, with no private path and no hidden setup knowledge, and it states what is not supported rather than claiming universal support.
- Gate: a fresh isolated environment plus the documented command produces a green suite, the capability check changes nothing, and the review ticket reproduces both.

### Stage 3 — Live questionnaire evidence and honest per-host compatibility

- Implementation `t_5e4b054e`, review `t_2f81cf94`. Entry: Stage 2 review passes.
- Scope: run the eight-check compatibility smoke checklist on the hosts available here, record agent, version, model, date, and a per-check result, and publish the record as a package document; mark every host that was not exercised as unverified; align the README, the compatibility document, and the skill file with what was actually run; use only synthetic or redacted material.
- Gate: at least one recorded host run reproduces on the reviewer's own shell, and no host is claimed stronger than its record.

### Stage 4 — Multilingual and measurement behavior with English and Spanish proof

- Implementation `t_4fff592e`, review `t_d34cbe8d`. Entry: Stage 3 review passes.
- Scope: one optional output-language preference on the card with English as the default and Spanish supported; English and Spanish labels in the HTML and Excel editions with grams still authoritative; the original ingredient names preserved; an explicit spoon units convention wherever a spoon measure appears; a documented decimal-comma rule that never changes an amount silently.
- Gate: the English and Spanish exports of the same synthetic recipe carry identical numbers and identical ingredient names, the decimal-comma rule behaves as documented, and the layout and formula rules still hold.

### Stage 5 — Contributor onboarding, recipe and image privacy, and CI

- Implementation `t_b21cfb4e`, review `t_e8c027a0`. Entry: Stage 4 review passes.
- Scope: a contribution guide that separates software contributions from recipe and image rights and requires synthetic or permissioned examples; issue and PR templates; a changelog and release notes; a CI workflow whose required job runs the full suite including the Excel arithmetic and cached-formula tests, with the browser-dependent PDF check in a separate job; a local rehearsal of the documented flow.
- **The stage-5 rehearsal is local.** It runs the documented flow on this workstation to catch defects before the clean-host run is spent. Stage 6 is the clean-host rehearsal and the authoritative RC proof. Stage 5's artifacts are provisional; stage 6's are the evidence the RC cites. Neither replaces the other, and stage 6 depends on this stage's review gate passing.
- Gate: the review ticket proves the CI required job includes the Excel suite and that a removed Excel suite fails the workflow check.

### Stage 6 — Clean-host install proof and final RC rehearsal

- Implementation `t_808a663d`, review `t_49c10828`. Entry: Stage 5 review passes.
- Scope: on a clean host, prove the single documented install command from a fresh checkout, then run the full documented flow end to end — empty activation, recipe intake, the question rounds, the review gate, chef approval, and the requested Excel and PDF outputs — and save the setup log and the produced artifacts. Synthetic material only. No publishing and no push.
- **Proof order is fixed.** The clean-host run happens only after the stage 1 through 5 gates pass. A clean host means a fresh machine or container with only a base Python and a browser, not a warmed workstation; `hermes-vps` (alias `vps`) or an equivalent fresh container qualifies. If a genuinely clean host cannot be provisioned, the stage blocks with the reason rather than substituting this workstation.
- Gate: the review ticket confirms the artifacts are real files from one card record, the scope override still produces no PDF when none is requested, and the setup log records the version and date.

## Dependency map

    t_7cbe1e6f  (this plan)
      └─ t_f72ad615  stage 1 implementation
          └─ t_6688d918  stage 1 review
              └─ t_2dc68500  stage 2 implementation
                  └─ t_20d095ce  stage 2 review
                      └─ t_5e4b054e  stage 3 implementation
                          └─ t_2f81cf94  stage 3 review
                              └─ t_4fff592e  stage 4 implementation
                                  └─ t_d34cbe8d  stage 4 review
                                      └─ t_b21cfb4e  stage 5 implementation
                                          └─ t_e8c027a0  stage 5 review
                                              └─ t_808a663d  stage 6 implementation
                                                  └─ t_49c10828  stage 6 review

First stage to start: Stage 1 implementation `t_f72ad615`. It is blocked until the coordinator releases it.

## Proof rules that apply to every stage

- **Reproduction before change.** Each stage records the failing state before touching anything, in an evidence file, and the evidence shows the defect rather than describing it.
- **Concrete acceptance.** Each stage states the commands a reviewer can re-run, and the expected result, so acceptance is a re-run rather than a summary.
- **Saved evidence.** Each stage writes its evidence under `work/rc-evidence/stage<N>/`, with a pre-change file, an after file, and a review subdirectory. The evidence lives outside the public package, so nothing private is shipped.
- **Independent review.** Each stage has its own review ticket with its own workspace. The reviewer re-runs the acceptance commands from the artifacts rather than trusting the implementation summary, and a failed or inconclusive review leaves the next stage blocked.
- **Evidence classes stay distinct.** A live run on a named host, a manual script or static check, and a host that was not exercised are three different things and are labelled as such. A static check never stands in for conversational behavior, and an unexercised host is never reported as passing.
- **Goal judge.** Implementation stages run with the goal judge enabled; review tickets do not, so a review that cannot reach a verdict stops instead of looping.
- **One stage at a time.** Only one implementation stage is active at a time. Each stage is created blocked with a sticky block, so closing the plan does not dispatch any stage: the coordinator releases stage 1 explicitly, and each later stage is released by its own review gate passing. A failed or inconclusive review leaves the next stage blocked.

## What this plan does not do

It does not widen the card schema to carry provenance. It does not change the universal agent-neutral scope or the chef questionnaire's rules, and it invents no facts about any kitchen. It does not touch private recipe material, the private recipe workbook, or the installed Hermes exporter. It does not publish, push, open a repository, or access a remote host during planning. It does not run costly cross-model comparisons, and it does not treat a self-reported success or a static check as proof of live interview behavior.

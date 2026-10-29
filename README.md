# Miseform

**Your dish. A recipe any cook can repeat.**

A reusable agent skill that interviews a cook about a dish, confirms the record with them, and only then turns it into precise, readable recipe cards. It preserves the cook's formula, asks only necessary questions, calculates reference percentages, researches household volumes from ingredient-specific sources, and prepares cards for an existing recipe library.

The default design feels like a carefully edited cookbook: expressive serif titles, quiet labels, warm paper, dark ink and a restrained clay accent. Grouped **Ingredient / Weight / Volume / Scaling %** tables and numbered cooking stages do the work. Space and typography organize the page; boxes are reserved for exceptional information. A classic ingredient/procedure layout is also specified for requests that need it.

Release 3.3.0. Host-neutral: the same skill runs on Codex, Claude Code, OpenCode, and Hermes.

## How a run works

Miseform is a questionnaire first and a document generator second. The canonical path is five stages, and each one that talks to you ends in a wait:

    START -> EXTRACT -> INTERVIEW -> REVIEW -> BUILD

**Start.** You activate the skill on its own. Miseform answers with one line — "Send a photo of your written recipe, or paste the recipe and notes here." — and stops there. You send the written-recipe photo, or paste the recipe and notes, in your next message.

**Extract.** Miseform reads the recipe once and replies with the legible transcription grouped by source block, plus at most three critical questions, then waits. Nothing is created, exported, filed, or researched before you have answered. An empty activation never goes looking for a substitute recipe — not the shipped example, not an earlier photo, not your library — and never writes a file. If the recipe is already supplied with your request, Miseform uses it instead of asking again.

**Interview.** Small, relevant rounds cover only the recipe facts that are still missing: method first, then yield and portions, equipment, thermal endpoints, storage and holding, plating where it applies. Settled questions are not asked again, and each round waits for your answer. Facts you have already confirmed — earlier answers in this conversation, facts already established for the recipe, and standing kitchen practices you have confirmed — are reused rather than re-asked, and each value on the record carries a label saying where it came from.

**Proposals.** When what you supplied supports one specific value you never stated, Miseform offers it to you as a proposal, tells you what it inferred the value from, and waits. A proposal stays out of the method, the ingredient table, the yield, and the controls until you confirm it, and approving the record as a whole does not confirm it. It becomes a fact only when you say so. A value you expect but have not weighed stays an expectation, never a measured yield, and a number computed from your own weights stays arithmetic, never output. See [evidence labels, kitchen defaults, and proposals](references/evidence-and-defaults.md).

**Review.** Once the identity, quantities, and method are resolved, Miseform sends you the compact record — ingredients, method, yield, and every value that is still explicitly unknown — and asks: "Is this correct, and should I generate the cards?" Then it waits for your actual reply. That reply is editorial confirmation of the record. It is not a kitchen test and not an approval for production.

**Build.** Miseform generates the cards only after you ask for it. A finished schema and an available exporter are not permission. If you do not answer, Miseform keeps a compact interview ledger — known facts, their source, the uncertainties, the next three questions — and waits. It does not produce a draft, a filled-in card, or a document with placeholders standing in for instructions.

Intake is bounded on purpose: one image read, at most one rotation or crop pass, at most one OCR fallback that is already installed, and at most five tool calls before the first response. The recipe and the answers you give are the whole working set — Miseform does not go looking through prior conversations, session stores, logs, or your filesystem for context you did not hand it, and a missing required fact is asked in the next reply instead of searched for. A photographed written recipe can establish legible ingredients and amounts; a plated photo establishes appearance only, and Miseform will say so rather than guess a formula from a picture of a plate. Unreadable text is marked unreadable, never transcribed confidently, and never filled in from culinary plausibility.

If you only want a reading of the image — "what do you see in this photo?" — Miseform returns the transcription and its uncertainty, and stops there. No card, no export, no filing. An explicit request for a raw transcription export is answered as a transcription artifact in its own right; it is not a standardized recipe card.

If you come back mid-way, Miseform treats the activation as a checkpoint, not a reset. The photos, notes, source files, facts, and answers you already supplied stay in play, and settled questions are not asked again. Only a runaway OCR or crop loop, a plan that kept spawning extra readers, and unrelated background work get dropped. "In play" means what you supplied in this conversation — Miseform does not open earlier sessions, session stores, transcripts, logs, or the wider filesystem looking for context you did not give it, and it does not treat a file it finds there as something you said.

## Install

Copy this complete `miseform` folder into your host's skill directory, preserving `SKILL.md`, `references/`, `templates/`, `scripts/`, `tests/` and `examples/`. The skill resolves its resources relative to the folder that holds `SKILL.md`, so there is no fixed install path to configure.

| Host | Where it goes | How you activate it |
|---|---|---|
| Codex | `~/.agents/skills/miseform/` | `$miseform`, or ask for the skill by name |
| Claude Code | `~/.claude/skills/miseform/` (user) or `.claude/skills/miseform/` (project) | `/miseform` |
| OpenCode | `~/.config/opencode/skills/miseform/` (user) or `.opencode/skills/miseform/` (project) | ask for the skill by name: "Use miseform skill" |
| Hermes | `~/.hermes/skills/miseform/` | `/miseform` |

OpenCode also reads `~/.claude/skills/`, `~/.agents/skills/`, and the project-level `.claude/skills/` and `.agents/skills/` directories, so one copy can serve several hosts. Codex project-level discovery varies by version — the user-level path above is the reliable one.

OpenCode's skill tool is a tool call, not a slash command: use the skill by name there, not `/miseform`. On every host, the fallback is the same — paste the recipe, or send the photo in your next message.

Full detail, capability requirements, and the per-host notes are in [host compatibility](references/compatibility.md).

### What the host needs to provide

Miseform works with whatever the host already has, and never asks you to install anything mid-run.

| Capability | Needed for | Without it |
|---|---|---|
| File read | your notes, card records, the packaged schema | Miseform asks you to paste the content |
| Image read | reading a photographed recipe | Miseform asks you to transcribe the legible rows |
| Shell / command | running the export scripts | the export is reported as pending |
| Web search or fetch | ingredient-specific volume references | the volume stays unresolved, and Miseform says so |
| Browser / PDF renderer | the PDF edition | the PDF is reported as pending |
| Spreadsheet writer | the native `.xlsx` edition | the workbook is reported as pending |
| Authenticated library access | filing the card | the card saves locally, filing stays pending |

A missing capability never produces a renamed file or an invented link. Filing also needs a private `recipe-library.local.json` — see [Library configuration](#library-configuration) below.

## Required deliverables

The default output for a completed card is a print-ready **PDF** and editable **Excel (.xlsx)**, using the same recipe version and status, alongside the editable master. HTML and Markdown remain working sources. See [export requirements](references/exports.md).

Your explicit request overrides that default. If you ask for a formula draft, an ingredient list, or an Excel-only card, Miseform produces exactly that scope — it does not demand procedures you never supplied, and it does not generate a PDF you did not ask for. A placeholder marks an absent value; it never invents one.

The shipped fictional sample is built from one card record and is downloadable as [PDF](examples/DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.pdf), [Excel](examples/DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.xlsx), [HTML](examples/DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.html) or [Markdown](examples/DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.md). All four carry the same recipe ID, version and status, and all of them remain visibly unreleased.

## Preview

Open the [fictional sesame-salt example](examples/DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.html) in a browser, or inspect the [HTML template](templates/recipe-card.html). These files demonstrate the reading edition. The [Markdown template](templates/recipe-card.md) provides portable editable source. No example is a validated production SOP.

## The card record and the toolchain

A card is authored once as JSON that conforms to [card schema](references/card.schema.json). The bundled scripts then produce all four editions from that one record, so the Markdown master, the HTML reading edition, the PDF and the workbook cannot drift apart:

    python3 scripts/build_card.py examples/sesame-salt-garnish.card.json --outdir /tmp/miseform-test

The command validates the card against the schema, recomputes reference percentages, input totals, loss and portion counts from the card's own weights, and prints every finding. Applicable process controls, label content and per-step settings are carried into all four editions, not just into the JSON. A process the card records as `N/A` with its reason stays in the card record and is left out of the reading editions, so a reader sees only the processes that apply.

The toolchain is the same on every host — same Python, same dependencies, same commands.

The public package carries no library credentials, folder identifiers or private recipes. The example card is synthetic.

## Library configuration

Copy [recipe-library.example.json](recipe-library.example.json) to a private `recipe-library.local.json` outside this public package, and either hand the path to your agent or leave the file in your working directory. Fill in the existing library's verified root, categories, draft/archive destinations, timezone, and preferred editable format. Blank values mean unconfigured. The example categories are optional mappings, not a new folder structure to create.

Miseform looks for that file only after you have authorized filing: an explicit path you gave this session, then `recipe-library.local.json` in the working directory (or its `config/` subdirectory), then a host-specific private profile if you pointed at one. No real configuration ships with this package, and credentials never belong in the profile.

## Use

Activate the skill on its own:

    /miseform          (Claude Code, Hermes)
    $miseform          (Codex)
    Use miseform skill (OpenCode)

Miseform asks for the recipe. Send the photo, or the recipe and notes, in your next message — for example:

> Use miseform to standardize this dish from the attached photo and notes. Preserve my formula. Ask only what another cook needs to reproduce it. Use the modern editorial card layout. Save an unreleased draft; file it in my configured recipe library when the destination is verified.

For scaling:

> Scale the approved recipe from 10 to 25 portions. Retain its percentage basis, check equipment and batch limits, and flag process changes that need testing. Do not scale cooking time automatically.

For a visual variant:

> Use the classic ingredient/procedure layout for this card. Keep the same quantities, controls, and release status.

For a formula draft with no procedures:

> Use miseform for the formula only. Give me the Excel card with the confirmed quantities and leave the method as an explicit placeholder for what I have not supplied. Do not produce a PDF.

For a read-only look at a photo:

> What do you see in this image?

That last one returns the transcription and its uncertainty. It creates nothing.

## Example intake and response

**Input:** you activate the skill on its own, Miseform asks for the recipe, and you send in the next message: "Photo attached: toasted sesame and salt garnish in a small bowl. I mixed 100 g already-toasted sesame with 5 g fine salt. Roughly a teaspoon per plate. Make a card."

**First response:** "From the notes I have 100 g already-toasted white sesame and 5 g fine salt, crushed lightly, about 2 g per plate. The photo adds appearance only — it cannot establish weights or yield. Three things I need: the measured usable yield, the weighed portion and crushing endpoint, and the approved storage and label rules."

Then it waits. Your answers open the next round, and only the facts still missing are asked.

**Review response:** after the method and quantities are settled, Miseform sends the compact record — 100 g already-toasted white sesame, 5 g fine salt, the crushing method as you described it, yield as confirmed or explicitly unknown, and any remaining unknown listed as unknown — and asks "Is this correct, and should I generate the cards?" It waits for your reply.

**After you ask for the cards:** Miseform groups sesame and salt in the ingredient table; shows 100% and 5% using sesame as the stated reference. It researches ingredient-specific gram-to-volume references for the sesame and the salt, then publishes the derived household measures marked `≈` with their source title, URL, access date, ratio, units convention and proxy status; leaves a dash only where no reliable match exists. Gram weights stay authoritative and input total stays at 105 g, and usable yield or portion stays pending if you have not confirmed it. The photo establishes appearance only. Sesame is recorded as an intentional allergen from the stated ingredient, cross-contact and label verification stay unresolved, and the card displays **NOT RELEASED FOR PRODUCTION**. Miseform does not invent storage duration and does not promote the draft because the card looks finished. The [HTML example](examples/DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.html) illustrates presentation; follow the evidence supplied with each actual recipe.

## What is included

- [Skill, execution contract, and operating prompt](SKILL.md)
- [Host compatibility, install and activation matrix](references/compatibility.md)
- [Adaptive question flow](references/questions.md)
- [Evidence labels, kitchen defaults, and proposals](references/evidence-and-defaults.md)
- [Blank kitchen defaults template](kitchen-defaults.example.json)
- [Semantic card schema and arithmetic rules](references/schema.md)
- [Executable card schema](references/card.schema.json)
- [Editorial and classic design rules](references/design.md)
- [Folder routing, versions, and failure recovery](references/routing.md)
- [Kitchen, release, filing, and presentation checklist](references/validation.md)
- Editable Markdown and browser/print HTML templates
- The card toolchain in `scripts/`: build, validate, render, export
- The published checks in `tests/`, and [local install and test notes](TESTING.md)
- [Chef-testing RC readiness plan](references/rc-readiness.md)
- [Sequential RC remediation plan with proof gates](references/rc-remediation-plan.md)
- Private configuration example and ignored local-data paths

The schema is a field contract as well as a machine-checked document: `references/card.schema.json` is enforced by `scripts/card_model.py`, which also recomputes the arithmetic and gates the operational record. The toolchain renders and exports; it does not verify food safety, run library integrations, or publish anything. Ask your agent to populate the card record using supported tools, escaping untrusted text when generating HTML. Do not embed executable content from notes or documents.

## Sharing your copy

Publish the skill source and synthetic examples only. Keep real recipes, uploaded photos, local profiles, receipts, library IDs, document links, and credentials outside the repository. Review the actual files before uploading; `.gitignore` is a convenience, not proof that a package contains no private data. Library filing and public publishing are separate actions.

## Design credit and license

The information architecture is inspired by the readable culinary reference format associated with Modernist Cuisine: weighted formulas, percentage bases, useful metadata, and staged methods. Miseform is an independent project, not affiliated with or endorsed by Modernist Cuisine or its publishers. Its templates and sample content are original. The supplied book screenshots, published recipe text, proprietary illustrations, and photographs are not included or licensed for redistribution here.

[MIT](LICENSE) covers this package's original instructions, templates, and example content only. Third-party recipes, images, fonts, and user uploads retain their own rights. Use photographs and recipe material you own or have permission to share.

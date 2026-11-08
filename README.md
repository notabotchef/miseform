# Miseform

**Your dish. A recipe any cook can repeat.**

A reusable agent skill that reads a cook's dish photo or notes, maps the whole page into a dish and its components, researches the technique that preparation needs, and turns the result into precise, readable recipe cards with weights, volumes, reference percentages, staged methods, and verified library filing. It preserves the cook's formula, asks only what research cannot settle, calculates reference percentages, researches household volumes from ingredient-specific sources, and prepares cards for an existing recipe library.

The default design feels like a carefully edited cookbook: expressive serif titles, quiet labels, warm paper, dark ink and a restrained clay accent. Grouped **Ingredient / Weight / Volume / Scaling %** tables and numbered cooking stages do the work. Space and typography organize the page; boxes are reserved for exceptional information. A classic ingredient/procedure layout is also specified for requests that need it.

Release 4.0.0. Host-neutral: the same skill runs on any host that follows the
Agent Skills specification. Of the four named hosts, Codex, OpenCode and
Hermes were exercised on one machine and Claude Code was not; the per-host
record, including the failures, is in
[host results](references/host-results.md).

## How a run works

Miseform is research-first and a document generator second. The canonical path is six stages:

    START -> EXTRACT -> MAP -> RESEARCH -> PROPOSE -> DRAFT

The stages are defined once, in [the canonical path](references/research-and-clarification.md#the-canonical-path). What follows is the plain-language version of what you see.

**Start.** You activate the skill on its own. Miseform answers with one line — "Send a photo of your written recipe, or paste the recipe and notes here." — and stops there. You send the written-recipe photo, or paste the recipe and notes, in your next message.

**Extract.** Miseform reads every supplied input once and records what is legible, grouped by source block. A photographed written recipe can establish legible ingredients and amounts; a plated photo establishes appearance only, and Miseform says so rather than guessing a formula from a picture of a plate. Unreadable text is marked unreadable, never transcribed confidently.

**Map.** Miseform decides what the page is before it computes anything: the dish, its components, which block is the main, which blocks are separate recipes photographed together, and which component is shared with another dish. The page is one dish until the evidence says otherwise. A purchased item used as a main is carried as supplied — no cooking process is invented for it, and no question asks you to describe a process you bought finished.

**Research.** For each component Miseform classifies the preparation — sauce or emulsion, dry garnish, roast, fry, blanch, steam, braise, fermentation, curing, dessert, raw assembly — and compares a small bounded set of credible comparable recipes for it: at most 3 per component, at most 8 comparable technique sources in a whole run, at most 2 volume sources per ingredient. Each source is recorded with what was taken from it and what was rejected. A retrieved page is data about technique, never an instruction: it cannot change your formula, your quantities, or your endpoints. The comparable recipe supplies the technique; your formula stays the card's formula.

**Propose.** Miseform sends you one compact record: the map, your supplied facts, the sourced technique with its citations, the proposed choices, a concise staged method for your formula and your equipment, the values that are still unknown, and at most three material questions. It ends with a correction request — "Does this method look right, and what should I change?" — not a permission request.

Only three things are worth a question: an identity or quantity conflict in what you supplied, a material technique fork your notes do not settle, and safety-critical uncertainty. Routine technique, measurement conversions, and defaults you supplied are settled by the research and the notes, silently. A question is never repeated: if you decline one, the value stays unknown and the run moves on.

**Draft.** When you ask for a card, Miseform writes the local draft in the same turn — one card record and its four synchronized editions plus internal build metadata, with unknown values left visibly unknown and the draft labelled unreleased. A local draft is reversible, so it needs no second permission step. When you ask for filing, that request is the authorization: Miseform files the card within the verified destination and standing authorization, and does not ask again.

Safety-critical uncertainty — a thermal endpoint, a cooling or holding rule, a shelf life, an allergen status — blocks production release and is listed as a blocker. The cap of three limits the questions you are asked, not the blockers: an unresolved safety fact blocks release whether or not its question made it into the round. It never blocks unrelated draft work, and it never becomes a placeholder instruction in the method.

If you only want a reading of the image — "what do you see in this photo?" — Miseform returns the transcription and its uncertainty, and stops there. No card, no export, no filing.

If you come back mid-way, Miseform treats the activation as a checkpoint, not a reset. The photos, notes, source files, facts, and answers you already supplied stay in play, and settled questions are not asked again. Only a runaway OCR or crop loop, a plan that kept spawning extra readers, and unrelated background work get dropped. The recipe and the answers you give are the whole working set — Miseform does not open earlier sessions, session stores, transcripts, logs, or the wider filesystem looking for context you did not give it, and it does not treat a file it finds there as something you said. A missing required fact is asked in the next reply instead of searched for.

## Install

### One command

From the folder that holds `SKILL.md`, run:

```
python3 scripts/install.py
```

That single command does the whole setup: it checks that Python and the
tools you need are present, creates an isolated environment for the
dependencies, installs them from `requirements.txt`, installs the Chromium
build used for the PDF edition, copies the skill into your host's skill
folder, and prints the activation line for every supported host. It never
writes to your system Python, never asks for `sudo`, and it is safe to run
again — a second run updates what belongs to Miseform and leaves everything
else alone.

The installer records its isolated interpreter inside each installed skill.
Use its launcher for exports and diagnostics, without changing your host's shell
or system Python (replace `<skill-folder>` with the printed install folder):

```
python3 <skill-folder>/scripts/run.py build_card.py <card.json> --outdir <output-directory>
```

Customized installed files, including an older exporter, are copied to
`.miseform-backups/<original-sha256>/<relative-path>` before update. Private
profiles and unrelated files remain untouched; compare the backup with the new
file before reapplying a customization. Rerunning an unchanged install writes
no source files. Installation copies only the same public file set used by the
release archive.

After it finishes, check what this machine can do:

```
python3 <skill-folder>/scripts/run.py capability_check.py
```

It reports three things separately — schema validation, PDF export, and
XLSX export — each as available or pending with the reason and the fix.
It installs nothing and changes nothing.

If you would rather install by hand, the same three steps are: create a
virtual environment, `python3 -m pip install -r requirements.txt`, and
`python3 -m playwright install chromium`. The manifest is the source of
truth for what gets installed; the prose in this file never drifts from it.

### Where the skill goes

The skill resolves its resources relative to the folder that holds
`SKILL.md`, so there is no fixed install path to configure. The installer
copies the folder into the skill directory of every supported host it finds
on your machine.

| Host | Where it goes | How you activate it |
|---|---|---|
| Codex | `~/.agents/skills/miseform/` | `$miseform`, or ask for the skill by name |
| Claude Code | `~/.claude/skills/miseform/` (user) or `.claude/skills/miseform/` (project) | `/miseform` |
| OpenCode | `~/.config/opencode/skills/miseform/` (user) or `.opencode/skills/miseform/` (project) | ask for the skill by name: "Use miseform skill" |
| Hermes | `~/.hermes/skills/miseform/` | `/miseform` |

OpenCode also reads `~/.claude/skills/`, `~/.agents/skills/`, and the project-level `.claude/skills/` and `.agents/skills/` directories, so one copy can serve several hosts. Codex project-level discovery varies by version — the user-level path above is the reliable one.

OpenCode's skill tool is a tool call, not a slash command: use the skill by name there, not `/miseform`. On every host, the fallback is the same — paste the recipe, or send the photo in your next message.

Full detail, capability requirements, and the per-host notes are in [host compatibility](references/compatibility.md).

### What is supported, and what is not

Supported hosts are Codex, Claude Code, OpenCode and Hermes, plus any host
that reads a skill folder in the Agent Skills layout. The toolchain itself
is host-independent: same Python, same dependencies, same commands.

Not supported, stated plainly:

- **Not every platform is verified.** The install command is written for
  macOS and Linux with Python 3.9 or newer. It has not been run on Windows,
  and Windows paths are not handled.
- **Not every host has been run live.** The install paths and activation
  forms are read from each host's own documentation. Treat a host you have
  not run yourself as unverified until you have.
- **The PDF edition needs a browser.** Without Chrome, Chromium, Edge, or
  the Chromium build Playwright installs, the PDF export is reported as
  pending. The HTML, Markdown and Excel editions still work.
- **Filing to a library is optional and needs your own credentials.** The
  package ships no credentials and no library client. Remote filing stays pending
  because no authenticated library client ships here. A private profile
  describes your destination but does not add a remote integration — see
  [Library configuration](#library-configuration).
- **Miseform does not verify food safety and does not publish.** It
  produces records; it does not approve them, and it does not upload
  anything.

### Optional steps

The PDF edition and library filing are optional. Nothing else is.

- **PDF (optional).** `python3 -m playwright install chromium` provides the
  browser. A Chrome, Chromium or Edge you already have is found
  automatically and used instead.
- **PDF text layer (optional).** The exporter reads the text back out of a
  finished PDF with the `pdftotext` binary when your machine has it, and
  falls back to the optional `pypdf` module when it does not. Install
  `pypdf` only if you have neither.
- **Filing to a library (optional).** Needs a private
  `recipe-library.local.json` with your own verified paths and credentials.
  Nothing is filed without it, and nothing is filed automatically.

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

The shipped fictional sample is built from one card record and is downloadable as [PDF](examples/DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.pdf), [Excel](examples/DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.xlsx), [HTML](examples/DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.html) or [Markdown](examples/DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.md). The card record itself ships as [canonical JSON](examples/DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.json). All five carry the same recipe ID, version and status, and all of them remain visibly unreleased.

## Preview

Open the [fictional sesame-salt example](examples/DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.html) in a browser, or inspect the [HTML template](templates/recipe-card.html). These files demonstrate the reading edition. The [Markdown template](templates/recipe-card.md) provides portable editable source. No example is a validated production SOP.

## Editorial themes

A card can be rendered in any of five editorial themes without changing the
recipe data: weights, volumes, scaling %, method steps, status and workbook
formulas are identical in every theme.

* Miseform Original — approved rust/cream editorial default (the default for records without a theme)
* Paper — minimal black/white, extra whitespace, single-column reading rhythm
* Atelier — restrained teal editorial, cool paper tone
* Service — high-contrast compact kitchen, red alert accent
* Ledger — precise tabular prep, full table grid and tabular figures

Select a theme with `build_card.py --theme <theme>`, or store `theme` on the
card record (CLI flag wins, then the card field, then the original default).
Run `scripts/preview_gallery.py` to render one synthetic card in all five
themes as HTML, PDF and Excel plus a preview gallery page. Themes are
presentation only: the card record, its arithmetic and its release semantics
are shared across every theme.

## The card record and the toolchain

A card is authored once as JSON that conforms to [card schema](references/card.schema.json). The bundled scripts then produce all four editions from that one record, and the build manifest binds their actual bytes to the complete canonical record:

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

**Input:** you activate the skill on its own, Miseform asks for the recipe, and you send in the next message: "Photo attached: toasted sesame and salt garnish in a small bowl. I mixed 100 g purchased roasted white sesame, 20 g roasted black sesame and 10 g fine salt. Crush lightly. About 2 g per plate. Make a card."

**The map:** one dish, one component. The garnish is a dry garnish: toasted seeds and salt, crushed. Nothing on the page is a separate recipe, nothing is shared with another dish, and nothing is a purchased main.

**The proposal:** Miseform compares a small bounded set of comparable recipes for a dry garnish, researches the gram-to-volume references the sesame and the salt need, and sends one record: the map, your supplied facts with their labels, the sourced technique with its citation, the proposed choices, the concise staged method, the values still unknown, and at most three material questions. The questions are the ones research cannot settle — here, the approved storage and label rules. "Crush lightly" is routine technique for this preparation, so it is researched and proposed rather than asked, and the derived household measures are published rather than asked for.

The record ends with "Does this method look right, and what should I change?" — a correction request, not a permission request.

**After you ask for the cards:** Miseform groups sesame and salt in the ingredient table; shows the reference percentages computed against the stated sesame basis — 100% for the 100 g white sesame row, 20% for the 20 g black sesame row and 10% for the 10 g salt row. It publishes the researched household measures marked `≈` with their source title, URL, access date, ratio, units convention and proxy status; leaves a dash only where no reliable match exists. Gram weights stay authoritative and input total stays at 130 g, and usable yield or portion stays pending if you have not confirmed it. The photo establishes appearance only. Sesame is recorded as an intentional allergen from the stated ingredient, cross-contact and label verification stay unresolved, and the card displays **NOT RELEASED FOR PRODUCTION**. Miseform does not invent storage duration and does not promote the draft because the card looks finished. The [HTML example](examples/DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.html) illustrates presentation; follow the evidence supplied with each actual recipe.

## What is included

- [Skill, execution contract, and operating prompt](SKILL.md)
- [Host compatibility, install and activation matrix](references/compatibility.md)
- [Research, mapping, and minimal clarification](references/research-and-clarification.md)
- [Evidence labels, kitchen defaults, and proposals](references/evidence-and-defaults.md)
- [Blank kitchen defaults template](kitchen-defaults.example.json)
- [Semantic card schema and arithmetic rules](references/schema.md)
- [Executable card schema](references/card.schema.json)
- [Editorial and classic design rules](references/design.md)
- [Folder routing, versions, and failure recovery](references/routing.md)
- [Kitchen, release, filing, and presentation checklist](references/validation.md)
- Editable Markdown and browser/print HTML templates
- The card toolchain in `scripts/`: build, validate, render, export
- The intake policy engine in `scripts/intake_policy.py`, which executes the decision rules
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


## Languages

Select `--lang en|es|fr|pt|it`, or record `language` in canonical JSON. CLI choice
wins over the record and host locale. Labels are localized; recipe prose uses a
matching `<card-stem>.lang-<code>.json` sidecar when supplied, otherwise the
canonical recipe text. This is not automatic recipe translation. Emitted JSON
embeds the effective overlay with its language for a portable same-language
rebuild. Switching languages drops a mismatched overlay. Theme choice uses
`--theme original|paper|atelier|service|ledger`.

## Update and uninstall

To update, unpack a new source archive or checkout and run the same
`python3 scripts/install.py` command. It backs up locally modified owned files
before replacing them, preserves private configuration, and never deletes
unrelated files. Restore a customization from `.miseform-backups/` only after
reviewing compatibility with the new exporter.

To uninstall, first copy any private files, customizations or backups you need
outside the printed installed skill directory, then remove that Miseform
directory from each host you installed. The isolated environment is normally
`~/.local/share/miseform/venv`; remove it only if it is dedicated to Miseform.
Do not remove an explicit or previously active environment shared by other tools.
No host configuration or credentials need changing.

## Troubleshooting and local release preparation

Run `python3 <skill-folder>/scripts/run.py capability_check.py`. Missing browser,
schema validator or spreadsheet writer is reported separately with a remedy.
If the interpreter was moved or deleted, rerun installation. An export command
can exit 1 while producing valid unreleased draft files; read its blockers and
pending-export messages. Network failures during dependency/browser setup leave
an actionable message; rerun after fixing connectivity. Linux browser system
libraries may require your administrator's package install.

Version is recorded in `VERSION` and skill metadata. From a checkout, run
`python3 scripts/release_package.py --outdir <outside-package-directory>` to
create a deterministic source ZIP, complete SHA-256 source manifest and archive
checksum. An extracted release can check itself with
`python3 scripts/release_package.py --verify`; any selected-file hash or version
mismatch returns nonzero. The installer performs this check before changing an
environment when release metadata is present. Installation records the copied
file hashes in `.miseform-install.json`; runtime interpreter paths stay in an
excluded `.miseform-runtime.json`. Only public source, contributor files and synthetic examples enter
the archive; runtime state, evidence, private paths and duplicate copies are
excluded. Inspect artifacts before sharing. This command does not publish.
See [contributing](CONTRIBUTING.md), [changelog](CHANGELOG.md) and
[recipe/photo permissions](CONTENT_POLICY.md).

# Host compatibility

Miseform's workflow is identical on every host. What changes is where the skill
folder lives, how you activate it, and which host capabilities are available.

This file is the only place host-specific detail belongs. The core in
[SKILL.md](../SKILL.md) never names a host, a slash command, or a tool name.

## What has been verified, and what has not

- **Documentation verified.** The install paths and activation forms below were
  read from the hosts' own published documentation and source. They are
  documented behavior, not a claim that this release was run inside each UI.
- **Some hosts have a live recorded run; the rest do not.** The
  [host results](host-results.md) record which hosts were exercised on one
  machine, with the agent, its version, the model, the date and a per-check
  result for each of the eight smoke checks — including the failures. A host
  that was not run is unverified here, and that document says so in those
  words. Treat an unrun host as unverified until you have run the checklist
  yourself.
- **The toolchain is host-independent.** The Python renderer, schema, and
  exporters are the same files on every host, and their output does not depend
  on the host. Only the conversation around them differs.

## Install matrix

| Host | Skill folder | Activation | Notes |
|---|---|---|---|
| Codex | `~/.agents/skills/miseform/` | `$miseform`, or ask for the skill by name | User-level root. Project-level discovery varies by Codex version — verify it in your build before relying on it. |
| Claude Code | `~/.claude/skills/miseform/` (user) or `.claude/skills/miseform/` (project) | `/miseform` | Project scope is the directory Claude Code runs in. |
| OpenCode | `~/.config/opencode/skills/miseform/` (user) or `.opencode/skills/miseform/` (project) | Ask for the skill by name through the native skill tool | Also reads `~/.claude/skills/` and `~/.agents/skills/`, plus project `.claude/skills/` and `.agents/skills/`. |
| Hermes | `~/.hermes/skills/miseform/` | `/miseform` | See the Hermes note below for the attachment limitation. |
| Any Agent Skills host | the host's skill root | the host's own activation form | The folder layout follows the Agent Skills specification. |

All four hosts read the same `SKILL.md` with the same `name` and `description`
frontmatter, plus an optional flat `metadata` map of string values. No
host-specific frontmatter field is required, and none is present.

Copy the whole `miseform` folder. Keep `SKILL.md`, `references/`,
`templates/`, `scripts/`, `tests/` and `examples/` together — the skill
resolves its resources relative to the folder that holds `SKILL.md`.

## Activation matrix

| Host | How to activate | If the host has no native slash command |
|---|---|---|
| Codex | `$miseform` | Ask for the skill by name in plain language. |
| Claude Code | `/miseform` | — |
| OpenCode | "Use miseform skill" | The native skill tool is a tool call, not a slash command. Ask for the skill by name and let the skill tool load it. Do not assume `/miseform` exists in the OpenCode command list. |
| Hermes | `/miseform` | — |

**Universal fallback.** Every host, regardless of how it was activated, accepts
the recipe in the cook's *next* message: paste the text, or attach the photo
as a separate message. A host that cannot attach an image to the activation
message itself still works through this path. If the recipe was already
supplied with the activation, use it and do not ask for an upload that exists.

**Empty activation waits.** An activation carrying no recipe gets exactly one
line — "Send a photo of your written recipe, or paste the recipe and notes
here." — and then stops. It does not open a question round, research volumes,
inspect a library, or write a file.

## Capability matrix

The skill works with whatever the host provides. It never names a tool; it
asks for a capability.

| Capability | Needed for | Without it |
|---|---|---|
| File read | supplied notes, card records, the packaged schema and references | ask the cook to paste the content |
| Image read | reading a photographed recipe | ask the cook to transcribe the legible rows |
| Shell / command | running `scripts/build_card.py` | report the export as pending; the card record still saves |
| Web search or fetch | ingredient-specific gram-to-volume references | leave the volume unresolved and say why |
| Authenticated library write | filing the card into the recipe library | save locally, report filing pending |
| Browser / PDF renderer | the PDF edition of a card | report the PDF as pending; never rename an HTML or CSV file into a `.pdf` |
| Spreadsheet writer | the native `.xlsx` edition | report the workbook as pending; never rename a CSV into `.xlsx` |

Rules that hold everywhere:

- Discover capabilities by using what is already installed. Do not install a
  package, download a server, start a service, or compare models to obtain a
  missing capability.
- A missing capability leaves work pending and stated. It never produces a
  fabricated file, a fake export path, or an invented link.
- Routine recipe work needs no task board, no sub-agent delegation, no external
  CLI, and no reading of session stores, prior transcripts, or historical logs.
  Those are optional conveniences, never prerequisites.
- Never type credentials into the conversation or the skill folder.

## Hermes adapter note

Hermes-specific detail, kept here on purpose:

- Install path: `~/.hermes/skills/miseform/`. Activation: `/miseform`.
- **Hermes Desktop cannot attach an image to a slash-command message.** Send
  the photo in the following message instead. The skill's own flow already
  works this way on every host, so the limitation costs nothing.

## Codex adapter note

- Install path: `~/.agents/skills/miseform/`. Activate with `$miseform`, or
  ask for the skill by name.
- Project-level skill discovery depends on the Codex version in use. The
  user-level path above is the reliable one; check the project path in your
  own build before depending on it.

## Claude Code adapter note

- Install path: `~/.claude/skills/miseform/` for the user, or
  `.claude/skills/miseform/` inside the project.
- Activation: `/miseform` invokes the skill directly.

## OpenCode adapter note

- Install path: `~/.config/opencode/skills/miseform/` for the user, or
  `.opencode/skills/miseform/` inside the project. OpenCode also reads
  `~/.claude/skills/`, `~/.agents/skills/`, and the project-level
  `.claude/skills/` and `.agents/skills/` directories, so a copy already
  placed for another host can be reused.
- Activation: ask for the skill by name — "Use miseform skill" — and let the
  native skill tool load it. The skill tool is not a slash command; do not
  promise the cook a `/miseform` command in OpenCode.

## Configuration discovery

The private library configuration is looked up in this order, and only after
filing is authorized:

1. A path the cook gave explicitly this session.
2. `recipe-library.local.json` in the current working directory, or in a
   `config/` subdirectory of it.
3. A host-specific private profile location, if the host provides one and the
   cook has pointed you at it. On Hermes the existing private profile is
   `recipe-profiles/miseform.local.json` under the active Hermes home; that
   lookup stays an optional adapter fallback and is never part of the core.

No real configuration file ships with this package. `recipe-library.example.json`
is the blank template.

## Sources

- Agent Skills specification — https://agentskills.io/specification
- Codex skills — https://github.com/openai/codex (`codex-rs/ext/skills/src/host_roots.rs`, `codex-rs/ext/skills/src/catalog_prompt.rs`)
- Claude Code skills — https://code.claude.com/docs/en/skills
- OpenCode skills — https://opencode.ai/docs/skills/

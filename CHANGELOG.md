# Changelog

## 4.0.0 — 2026-11-08

Release candidate; publication and live-host acceptance remain separate gates.

- Research-first intake contract: one bounded read of the whole page, the dish
  map before any number, and at most three material questions.
- Bounded comparable-recipe research with recorded sources. At most 3 comparable
  recipes per component, at most 8 comparable technique sources in a run, at
  most 2 volume sources per ingredient, and a whole-run budget of 12 search or
  fetch attempts or 4 minutes. Each source records what was taken from it and
  what was rejected.
- Ingredient-specific volume research with source records: title, URL, access
  date, ratio, units convention, state match, proxy status and confidence.
  Weights stay authoritative; potent ingredients are weighed, not spooned.
- Component cards with independent percentage bases, computed from the stored
  weights within the component and never stored on the card.
- One canonical card record produces the Markdown master, the HTML edition, a
  native PDF and a native XLSX, with a build manifest binding the emitted
  bytes to that record.
- Five editorial themes and five languages, with language-tagged portable
  translations.
- Workflow completeness ledger: declared coverage with required dispositions,
  validated against the card.
- Null-yield and spreadsheet arithmetic guards with real recalculation checks.
- Build-time artifact manifest and retry-safe local filing integrity checks.
- Isolated dependency install, customized-file backup, public source selection,
  deterministic release archive and source SHA-256 manifest.
- One-command install: `python3 scripts/install.py`, with the activation line
  printed for every supported host.
- Per-host run records in `references/host-results.md`, including the checks
  that failed and the checks that were not run. No host is certified by this
  release.
- Contributor guidance, MIT software license, content permission policy and CI.

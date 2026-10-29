# Library routing and version control

## Configure without imposing a new library

Copy [configuration example](../recipe-library.example.json) to `recipe-library.local.json` outside the public repository, or a private ignored profile directory. Blank values are unset, not destinations. Populate only verified roots, categories, timezone, formats, and SOP references. Category names in the example are illustrative; map existing folders instead of creating them by default. Keep credentials in the environment's credential store, never in this profile.

Look for the configuration only after the cook has authorized filing, in this order:

1. A path the cook gave explicitly this session.
2. `recipe-library.local.json` in the current working directory, or in a `config/` subdirectory of it.
3. A host-specific private profile location, if the host offers one and the cook has pointed at it.

No real configuration ships with this package, and no configuration path is hardcoded into the skill.

Before filing, inspect root identity, parentage, existing category folders, an adjacent card, current index structure, and names/aliases. Verify actual access. A matching folder name alone is not sufficient. Existing conventions take priority; record any proposed convention change explicitly.

## Routing decisions

1. Resolve an exact existing recipe/component ID and version before relying on its name. Preserve event variants and similarly named dishes as separate candidates until confirmed.
2. New unreleased recipes/revisions go to the configured verified draft destination. Retain intended culinary category in metadata. If no draft destination exists, save locally pending route clarification; do not create folders implicitly.
3. Released components go to their configured category; assemblies link exact component versions. An event-specific assembly may use an existing verified event folder. Reusable components remain in their culinary categories.
4. Preserve existing files in their current locations. A historical card's folder does not prove production status. A draft revision does not replace the approved current version.
5. Archive only after an explicit replacement decision and verified replacement. Never delete originals. If identity, category, authorization, or destination remains ambiguous, keep a local pending artifact of the card the cook already reviewed and asked for, and ask only the resolving question. A pending filing state is never a reason to build a card the cook has not asked for.

## Naming and versions

Honor an established library convention first. Otherwise propose this forward convention:

- Human-readable title: `DISH NAME — REC-ID — v0.1 — YYYY-MM-DD`.
- Portable file: `REC-ID__dish-slug__v0.1__YYYY-MM-DD.md`; reading edition uses the same stem with `.html` or `.pdf`.
- Photo: same stem plus `__plating-01` and its real image extension.
- Strip path separators, control characters, and traversal tokens from filenames. Constrain output to the configured staging/library root. Preserve original spelling in card text.
- Use existing recipe ID for a revision. Allocate a new ID only after a complete current index scan including pagination and a collision recheck; serialize allocation. Without reliable allocation, use `TEMP-YYYYMMDD-<unique-token>` locally. Do not guess a sequential ID.
- New drafts: v0.1, v0.2. First chef-approved release: v1.0. Revision draft: v1.1-draft.1. Minor versions clarify or refine the same production standard; major versions change the material formula, process, portion, or allergen profile. Operational changes require relevant retesting regardless of version size.
- Keep legacy source versions verbatim in provenance. No automatic reinterpretation of old dates or labels.
- Same recipe/version and identical content: reuse the verified artifact. Occupied version with different content: create the next appropriate version; never overwrite silently.
- Use the kitchen's confirmed timezone for dates. If unavailable, record the date basis rather than assuming a location.

## Save transaction

Save editable source, provenance, and receipt outside the skill package first. Persist a deterministic retry key from recipe identity, version, and normalized content digest; exclude remote IDs, timestamps, and filing receipt fields. Preserve that key across interrupted runs.

Confirm filing is within current or standing authorization. A request to standardize and file authorizes that scoped operation; drafting alone does not authorize publication, permission changes, or broader reorganization. Do not ask again when authorization already exists.

Inspect available tool schemas. Preserve the library's native editable format if supported; otherwise retain portable source and mark conversion/filing pending. A PDF must not be the only editable master. Search exact identity/version and retry key before creating a file, especially after a timeout. Read saved content back to verify title, status, formula, procedure, version, and parent destination.

Update only the relevant index record, preserving existing columns and unrelated rows. Keep the current approved version distinct from pending revisions. Update a review queue/component map only when it exists and the authorized scope covers it. Verify each change independently. If indexing fails after card creation, retry indexing, not card creation.

Receipt fields: recipe ID, version, status, retry key, local artifact paths, verified intended destination, observed remote file ID/link, card/index/review-queue/component-map states, last verified timestamp, unresolved error, and next action. Do not claim filed/indexed when only a draft exists.

## Required companion files

Apply [export requirements](exports.md): save the PDF and Excel cards with the same versioned filename stem as the editable master. Verify each artifact and its index link independently. HTML/Markdown alone does not complete delivery. When the cook explicitly requests a narrower scope, follow that scope and say what was left out.

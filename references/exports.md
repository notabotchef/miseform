# Required completion outputs: PDF and Excel

The default for a completed recipe-card workflow is BOTH a real `.pdf` reading/print card and a real `.xlsx` editable Excel card, in addition to the library's existing editable master. HTML/Markdown are sources or companions, not substitutes. Apply this default to final cards and to any deliberately saved draft; preserve R&D/NEEDS CHEF CONFIRMATION warnings in both exports. Export completion and production release are different gates. When the cook requests a card or standardization, generate the local unreleased draft in the same turn as the proposal, even when chef corrections are pending. No separate review approval is required to save that reversible draft. An empty activation with no recipe input still produces no draft. Production release remains a separate gate.

## Scope follows the explicit request

The default above is a default, not a demand. When the cook asks for a narrower deliverable — a formula draft, an ingredient list, an Excel-only card — produce exactly that scope:

- Do not demand procedures the cook never supplied, and do not ask for them as a condition of delivering the requested scope.
- Do not produce a PDF that was not asked for.
- A placeholder marks an absent value and states its reason. It never invents a method step, a ratio, a liquid, a yield, a temperature, or an allergen claim to satisfy the schema.
- A scoped draft is an authorized formula draft. It keeps the supplied or confirmed quantities and any chef-supplied method, keeps the unreleased status, and shows the unsupplied fields as explicit placeholders. A formula draft may carry no method at all — when the cook supplied none, the method stays a placeholder and the draft is still delivered.
- Scoped output never weakens a gate: chef editorial confirmation stays separate from production approval, and a formula draft is never a production release.

Report the delivered scope plainly, including what was deliberately left out and why. When an export capability is missing, that export is pending — see [Filing and partial failure](#filing-and-partial-failure).

## One recipe, one version, two synchronized files

Build both files from the same validated recipe data. Use the same recipe ID, version, revision date, status, ingredient quantities, percentage bases, steps, yield evidence, allergens, storage rules and unresolved questions. Use one filename stem with `.pdf` and `.xlsx` extensions. Regenerate both when the source changes. Do not overwrite historical versions. Keep provenance and test/release records available in both formats, on continuation pages/sheets when needed.

## PDF reading card

Render the modern HTML layout with print styles using an available real PDF renderer. Default to the library's chosen paper size; use A4 when none is set, with Letter supported. Keep ingredient headings, staged numbering, critical controls and status legible. Add recipe/version and page numbering to multi-page PDFs. Do not force one page or rasterize the entire recipe as an image. Use selectable text and embedded or reliably substituted fonts. Inspect every rendered page for clipping, cut rows, orphaned headings, blank trailing pages and missing steps. Confirm PDF text contains the expected quantities and release warning.

## Excel card

- Create a native `.xlsx` workbook, not CSV or HTML renamed as Excel. No macros, external workbook links or embedded executable content.
- First worksheet is a readable recipe card: title/status/facts, grouped Ingredient / Weight / Volume / Scaling % table, staged directions, equipment, allergens, service/storage and release notes. Use column widths, wrapped cells and explicit row heights that show all text. Match the restrained serif/clay design where spreadsheet constraints allow.
- Store weights and factors as numeric values with unit number formats; calculate reference percentages as formulas against the named reference weight. Keep an unresolved volume as `—`. A researched volume shows its approximate household measure with the unit, and the source record travels with the card in the notes block, so a derived measure is never read as a measured exact value. Never fabricate density conversions. Formula denominators must be positive and explicitly linked to each component's reference.
- Every formula cell ships with the value it evaluates to, beside the live formula. Excel recalculates on open, so the formula is enough for a cook with Excel; a preview, a PDF converter or a `data_only` reader never recalculates and shows an empty cell without a cached result. The workbook is verified by reading the numbers back from the saved file, not from the generator.
- Size every merged text row from the text it holds. Excel never auto-fits a merged cell, so a fixed row height clips long notes and source records and the reader has to drag the row border. Derive the height from the text, the font size and the columns the block spans.
- A separate Batch Scaling sheet is appropriate for editable factor and scaled ingredient weights. Distinguish editable inputs from formulas. Require a positive numeric factor; blanks, zero, text and negatives must yield a visible input error rather than plausible weights. Test base and changed factors, restore the delivered default, recalculate and scan formula errors.
- A measured base yield remains measured only at the base batch. Scaled output, if shown, must be labeled a projection and never overwrite actual yield. Do not multiply time, temperature, appliance capacity or approval. Show process validation requirements beside scaled quantities. Repeating a validated batch is different from increasing its vessel load.
- Treat imported notes as text, including strings beginning with `=`, `+`, `-` or `@`; do not turn source text into spreadsheet formulas. Only trusted generated formulas belong in formula cells.
- Set sensible print area, orientation, repeating table headers where useful, and fit one page wide with unrestricted page height. Never compress a long method onto one printed page. Check the saved workbook's contents and render each sheet. Native Excel execution should be reported separately from validation in a generation engine.

## Filing and partial failure

File both exports beside the same recipe/version in the existing destination, unless that library has a verified exports subfolder convention. Do not invent new folder architecture. Preserve the native editable master. Add PDF and Excel links to the existing index's notes/link fields without dropping the master link. For privacy-sensitive exports, omit private receipt identifiers from shareable copies while retaining necessary recipe provenance.

Use separate content/version retry keys and receipt states for `master`, `pdf`, and `xlsx`. Record local paths, actual remote IDs/links and readback checks independently. Verify each uploaded file has the expected MIME type, filename, parent and nonzero content. A PDF failure must not cause duplicate Excel or master creation. A spreadsheet failure must not trigger a production-status change.

If a renderer or workbook tool is unavailable, preserve the recipe source and any successful export, report exactly which required file is pending, and request only the missing capability. Never claim the workflow is complete with HTML/Markdown alone. Do not invent an export URL or provide an empty placeholder file.

A missing capability is never worked around by renaming, by substituting another format, or by installing something mid-run.

## Final receipt

Return PDF and Excel links plus recipe/version/status. State whether filing and indexing are verified or pending for each file. A finished draft may be fully exported while remaining unreleased for kitchen production.


## Build integrity and filing

`build_card.py` emits internal `<stem>.manifest.json` metadata alongside requested
editions. It binds the complete canonical JSON record digest, effective language,
theme and paper settings, effective translation overlay and digest, requested
edition list, and SHA-256 bytes of every produced edition including JSON.
Failed requested exports remain unbound; files left by previous builds do not
become valid replacements. Skipped PDF/XLSX editions are not required for filing.

File the emitted canonical JSON when CLI language/theme overrides or translation
sidecars are used. This record embeds the effective translation overlay, so copying
and rebuilding the canonical JSON preserves translated recipe content for the same language. The embedded overlay
is tagged with its language and is discarded when another language is selected;
without a matching sidecar that build falls back to canonical recipe text. An existing
sidecar at the current record location takes precedence on rebuild; changes
require a new build and manifest.

Filing validates the manifest and source bytes before staging, then checks staged
bytes against build hashes and performs format readbacks. Every retry repeats
source verification; a missing staged file is recovered only from a verified
build source. Missing manifests, changed records, mixed or altered editions, and
changed available translation sidecars fail recoverably. Rebuild exports to retry.
The manifest is local accidental-staleness integrity, not cryptographic
attestation against someone replacing both metadata and artifacts. It is internal
metadata, not an extra chef deliverable. Remote filing remains pending.

### Source-bound recipe translation overlays

Sidecars may use the strict contract `schema_version: 1`, `language`,
`source_record_digest`, `fields` (canonical dotted prose paths to translated
strings), and optional `verbatim` (path to a nonempty review reason, instead of
an entry in `fields`). `scripts/translation.py` supplies `source_digest`,
`translation_inventory`, `normalize_translation`, and `translation_coverage`.
The source digest excludes only rendering settings/overlays and binds canonical
status, quantities, approvals and evidence. Built JSON embeds the effective
sidecar unchanged for portable rebuilds. Build manifest schema 2 binds and
recomputes coverage as well as the existing exact artifact/overlay hashes;
older manifests require a rebuild.

Prose paths cover scalar recipe text, `facts.KEY`,
`percentage_basis.basis_label`, `components.INDEX.name`,
`components.INDEX.ingredients.ROW_ID.name`/`.notes`, stage names/tips,
`stages.INDEX.steps.NUMBER.text`/`.settings.KEY`, controls, prose labeling,
notes, blocker/checklist descriptions and narrative provenance. Ingredient IDs
are unique within their component and step numbers within their stage. Numeric
settings, IDs, raw statuses/source objects, dates, batch codes and preparer or
station identities are not translatable fields. Control applicability and
blocker membership always come from the original canonical record before any
translated display is selected; translated N/A cannot hide an applicable control.

Unknown/protected paths, stale source/language, blank/non-string strict values,
and obvious changed/dropped numeric, physical-unit, ID, URL or quoted-text tokens
fail the build before artifacts are written. Decimal punctuation may localize.
These checks do **not** certify semantic equivalence: negation, uncertainty,
mandatory wording and approval meaning require independent semantic review.
Coverage reports exact required, covered, verbatim and missing paths; only a
complete strict overlay (or the unchanged canonical English baseline) reports
complete. Legacy partial sidecars remain usable drafts and cannot claim complete
translation. Legacy scalar/facts/component/stage aliases resolve to the same
field paths; conflicting or ambiguous aliases fail rather than pick a winner.

# Contributing

Use synthetic recipes, photographs and names in changes, tests and issues. Keep
real kitchen records, local profiles, uploads, receipts and credentials outside
this package. See [content permissions](CONTENT_POLICY.md).

From a checkout, run `python3 scripts/install.py`, activate the interpreter it
prints, and run `python3 -m pytest tests/ -q`. Install the optional `formulas`
dependency for real workbook recalculation checks and `pypdf` for PDF text
readback when `pdftotext` is absent; the installer includes both by default.

Add a failing regression before changing behavior. Run the full suite after the
focused checks. Arithmetic, null-yield guards, spreadsheet formula recalculation,
PDF text readback, theme/language parity and filing integrity must remain green.
Inspect representative PDF and workbook outputs when presentation changes.

Keep recipe evidence distinct from proposals, preserve unknown values, and never
silently change quantities or release status. Cite sources for researched values.
Update existing documentation when commands or behavior change. MIT covers our
original software; do not add material you lack permission to redistribute.

Use a focused branch and a descriptive commit. Pull requests should state the
problem, resulting behavior, tests actually run, and any remaining limitations.
No fixed upstream URL is assumed: submit through the repository where you found
this checkout, or share a patch with its maintainer.

For release preparation, keep `VERSION` equal to `SKILL.md` metadata version and
run `python3 scripts/release_package.py --outdir <outside-package-directory>`.
Inspect the ZIP and its source manifest before sharing. The command creates
artifacts locally; publishing remains a separate explicit action.

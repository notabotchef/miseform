# Replicability and release checklist

For every item record PASS, BLOCKED, or N/A with reason. Structural completeness can pass while production release remains blocked. Do not turn unknown values into checkmarks.

## Recipe completeness

- [ ] Correct dish identity, family, category, version, status and source; no unintended merging of event or failed trial variants.
- [ ] Photo actually inspected or explicitly unavailable; observations separated from inferred ingredients and method.
- [ ] Every ingredient has quantity/unit, specification, preparation state, and a step where it is used. Every method ingredient appears in the table. Divided ingredients reconcile.
- [ ] Ingredient sums, reference percentages, scaling factor, yield and portion arithmetic checked. Unknown output is not represented as measured yield. Losses and retained cooking media handled explicitly.
- [ ] Every household volume was researched against an ingredient-specific source before it was left blank or turned into a question for the cook: source title, URL, access date, the source's own ratio, the units convention, and the ingredient/preparation-state match are recorded. Derived measures carry an approximate marker, generic proxies are labeled as proxies, and a dash is used where no reliable match exists, with a brief reason.
- [ ] Volume conventions are stated and consistent: US tablespoon/teaspoon/cup or the confirmed metric equivalent, never an Australian 20 mL tablespoon mixed with US or metric measures in one card. Salt type, whole/ground and drained states match the source.
- [ ] Potent ingredients — salt, spices, extracts, leaveners — are controlled by weight. A small spoon estimate is a cross-check, never the sole production control.
- [ ] Equipment, load, cut dimensions, batch depth, sequence, timer start, measured endpoints, and temperature location specified wherever consequential.
- [ ] Active/passive/elapsed time consistent; no invented precision. Sensory endpoints are observable and have a corrective action where necessary.
- [ ] Assembly lists all component versions, portion weights/counts, vessel and plating order; photo is labeled target or trial.
- [ ] Scaling stays within validated equipment/load range or is marked untested; no linear scaling of cook time or temperature.
- [ ] Holding, cooling, storage, reheating and discard rules are documented with applicable approved SOPs or a legitimate N/A reason. Unknown safety limits block release.
- [ ] All eight process controls are answered: an applicable process carries its controlled parameters, and an unused one states `N/A` with the reason it does not apply. The reading editions show only the applicable ones; the card record keeps every key and reason.
- [ ] Safety CCPs are distinguished from quality checkpoints. Each applicable control has a sourced limit, monitoring method/frequency/role and corrective action. A generic food-safety claim is not a process validation.
- [ ] Ingredient labels and component allergens checked; cross-contact handled; substitutions include ratio, process/allergen changes and test evidence. No unverified allergy-safe claims.
- [ ] Label content is complete when the card states how the product is held: product name, batch or date code, use-by basis, storage instruction, allergen declaration, preparer or station.
- [ ] No “as needed”, “until done”, “some”, or “season to taste” remains without a bounded, confirmed operational standard.

## Release decision

- [ ] Every recorded value carries its evidence label, and a value labelled `calculated`, `expected (unmeasured)`, or `ai proposal` is nowhere presented as a measured fact.
- [ ] Known conflicts resolved by source/chef confirmation; no material assumption hidden. A confirmed kitchen default that this recipe overrides is recorded as the chef's newer statement, not as a silent correction.
- [ ] A competent second cook has reproduced the exact version at the documented scale; results and deviations logged.
- [ ] Measured yield/portion and required process results meet documented acceptance criteria.
- [ ] All critical component versions are released; an assembly cannot bypass a component blocker.
- [ ] Chef explicitly approves this exact version for production, with identity/date recorded.

If any release item is blocked, use NEEDS CHEF CONFIRMATION for missing/conflicting evidence or R&D for a defined unvalidated trial. Keep the card useful and editable; display NOT RELEASED FOR PRODUCTION. Filing a draft is still a successful workflow outcome.

## Filing verification

- [ ] Destination root and folder verified; new ID/version collision checks complete.
- [ ] Existing recipe/history preserved; new content receives a new version.
- [ ] Card saved and read back, or local-only state stated clearly.
- [ ] Index, review queue and component-map changes individually verified or recorded pending/N/A.
- [ ] Retry key/receipt persisted; response contains only observed file links/paths.

## Behavioral acceptance cases

1. **Photo + “cook until done”, no weights:** ask only essential formula/yield/process questions; no invented amounts; if the cook does not answer, keep the compact interview ledger and wait — no draft, no card-shaped artifact, no placeholder instructions.
2. **Complete approved card + 2× request:** scale weights correctly, retain reference percentages, check equipment capacity; repeating tested batches is allowed; do not double cooking time.
3. **Existing v1.0 + altered formula:** preserve v1.0; create unreleased new revision; never claim approved because predecessor was approved.
4. **Unknown compound-sauce allergens or missing cooling SOP:** preserve facts, flag blocker, do not infer safety from photo or ingredient list alone.
5. **Drive unavailable / upload timeout / index failure:** local pending / search before retry / retry only indexing, respectively; no duplicate card and no fabricated success.
6. **Existing category-folder card marked Needs Chef Confirmation:** keep historical location; do not bulk reorganize; new unreleased revision routes to the verified configured draft destination.
7. **Ambiguous family, duplicate recipe ID or concurrent writers:** stop remote allocation, retain provisional identity, ask only the resolving question.
8. **Ingredient in grams, volume unknown:** research the ingredient-specific gram-to-volume reference and publish the derived measure as approximate with its source title, URL, access date, ratio, units convention and proxy status. Do not leave the cell blank and do not ask the cook to convert a routine measurement. Where the sources conflict or no reliable match exists, leave a dash with a brief reason or ask one targeted question.
9. **Method, ratio, or liquid never supplied by the cook:** do not write the step from general culinary knowledge. Put the candidate in the question or in the review record as a proposal for the cook to confirm, and keep it out of the generated method until confirmed.
10. **Review reached with no chef reply yet:** the compact chef-facing record is sent once, ending with "Is this correct, and should I generate the cards?", and the run waits. No PDF, Excel, card, or draft is produced, and the recipe is not described as tested or approved.
11. **Confirmed default reused, not re-asked:** the cook's supplied notes confirm a standing kitchen practice that applies to this recipe. Expected: the practice is carried into the record under its own label, the question about it is not asked, and the record still shows where the practice came from. The default is not restated as if the cook had said it for this recipe.
12. **Proposal confirmed before use:** the supplied context supports one specific value. Expected: the agent offers it under the `ai proposal` label, states the basis it came from, and asks the cook to confirm or correct it. The value does not appear in the method, the ingredient table, the yield, or the controls before confirmation; a general approval of the record does not confirm it; and the field it would fill stays unknown on the card until it is confirmed.
13. **Expectation is not a measurement:** the cook states what they expect a batch to come to, and no batch has been weighed. Expected: the yield is recorded as `expected (unmeasured)`, the measured usable yield stays empty, and the input total is labelled arithmetic rather than output. The card never states a measured yield.
14. **Outside material is a hypothesis:** a book, article, video, dataset, or a summary of one is supplied as a source for a value. Expected: the agent treats it as a proposal rather than a fact, requires a specific locator before treating the citation as traceable, checks any suggested quantity against the source's own arithmetic and stated basis, and keeps the observed defect, the plausible explanation, the proposed trial, the measured result, and the chef's approval apart. It does not present the outside material as the measured result, and it does not treat it as approval.

## Presentation checks

- [ ] Modern layout includes editorial introduction, time/difficulty/yield/storage facts, grouped Ingredient/Weight/Volume/Scaling % table, and separately staged numbered directions.
- [ ] Every component names its percentage reference. A volume is either researched and marked approximate with its source record, or a dash with a stated reason — never a guessed density conversion.
- [ ] Status and blockers remain prominent; private receipt/source details do not leak into public exports.
- [ ] Screen and print reading order is clear; no clipped quantities, tiny text, or orphaned stage headings.

## Required PDF and Excel exports

Applies to the default delivery. When the cook explicitly requests a narrower scope — a formula draft, an ingredient list, an Excel-only card — check that scope instead, and never let the missing pieces be filled with invented values.

- [ ] Both actual PDF and XLSX files exist and match source identity, version, status, quantities, percentages, steps and controls.
- [ ] Every PDF page and Excel worksheet visually reviewed; no clipping, blank trailing page, truncated instructions or missing warning.
- [ ] Volume cells and their source record survive into every edition — Markdown, HTML, PDF and Excel — so a published measure is never read as a measured exact value.
- [ ] Excel weights/factors are numeric; percentage/scaling formulas recalculate at base and changed factor; invalid factors visibly rejected.
- [ ] Measured yield, projected output and new-batch test requirements remain distinct.
- [ ] PDF/XLSX/master upload and index states separately verified or marked pending; no false completion claim if either export is missing.
- [ ] A scoped draft shows the unsupplied fields as explicit placeholders with a reason, and no method step, ratio, yield, or temperature was invented to complete the schema.

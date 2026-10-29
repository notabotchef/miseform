# Recipe-card field contract

This is the semantic contract for the card. `references/card.schema.json` is its machine-checked form: `scripts/card_model.py` validates a card record against that schema, recomputes the arithmetic listed below from the card's own weights, and gates the operational record. All sections are required; an irrelevant section may state `N/A — reason`. An unknown value is `NEEDS CHEF CONFIRMATION`, never a plausible default. Source evidence may be grouped when the same note supports multiple fields.

| Field/group | Type and constraints |
|---|---|
| Identity | Stable existing recipe ID or unique provisional ID; uppercase title; aliases; dish family; component/assembly designation; configured category; event/menu |
| Version | New-record version, date, source version verbatim, predecessor link, change summary; never reinterpret an old date as semantic version |
| Status | PRODUCTION, R&D, NEEDS CHEF CONFIRMATION, SUPERSEDED; separate blocked-release reason and filing state |
| Yield | Input mass; measured usable output mass/count; trim/cook/transfer loss separately; measurement vs estimate — an expectation is recorded as an expectation, never as a measured yield; portions and mass per portion; leftover reserve |
| Difficulty | Confirmed difficulty level and the skill or technique that warrants it; unknown is explicit |
| Layout | Editorial default or classic on request; short supported introduction; four-part facts strip; grouped ingredient table; staged continuous step numbers |
| Time | Active, passive and elapsed total in minutes/hours; account for overlapping steps instead of blindly summing |
| Equipment | Appliance/model where consequential; capacity, mode, vessel dimensions, batch limit, fill depth, utensils, scale resolution and probe |
| Ingredients[] | Stable row ID, component, name, brand/specification, prep state, net weight/unit, optional measured or source-supported volume/unit, volume standard, reference scaling %, notes and source |
| Volume research | For a published household measure: the derived value marked `≈`, the source title, URL, access date, the source's own ratio (for example grams per tablespoon), the units convention (US tablespoon/teaspoon/cup or the confirmed metric equivalent), how the ingredient and preparation state match, and whether the figure is an exact match or a labeled generic proxy |
| Scaling | Per-component reference row ID (or flour-blend row IDs for baker percentages) and reference mass > 0; factor > 0; tested batch range; rounding rule; process changes requiring a test |
| Procedure[] | Step number; ingredient row IDs/amounts; action; equipment/load; time and start condition; temperature value/unit/location; measurable endpoint; corrective action where relevant |
| Service | Per-portion component quantities; total portion mass; plate specification; assembly order; photo reference and its status; service window and temperature |
| Holding/storage | Approved SOP reference/version; cooling method and limits; storage temperature; container/label/use-by; thaw/reheat/hot or cold hold; monitoring and discard rules; N/A rationale where absent |
| Controls[] | Hazard or quality defect; distinguish safety CCP from quality checkpoint; approved limit/source; measurement method; frequency; responsible role; corrective action; log location |
| Process controls | Every card answers all eight processes — sous vide, combi oven, fermentation, pickling, reduction, emulsification, chilling, smoking. An applicable process carries its controlled parameters; an unused one states `N/A — reason`, never a bare `N/A`. The reading editions show only the applicable processes; every key and its reason stay in the card record |
| Labeling | Product name, batch or date code, use-by basis, storage instruction, allergen declaration, preparer or station. A card that states how the product is held carries the label content; an unresolved field is `NEEDS CHEF CONFIRMATION` |
| Allergens | Intentional allergens per ingredient and component; label verification evidence; cross-contact controls; unresolved labels; no unsupported free-from claims |
| Substitutions[] | Approved replacement, ratio, functional changes, method changes, allergen changes, test/approval evidence; otherwise none approved |
| Components[] | Stable ID, exact version, link, quantity used, status; an assembly cannot be released with unresolved critical component specifications |
| Provenance[] | Source note/photo/document link and date; evidence kind: chef-stated / chef-confirmed default / calculated / expected (unmeasured) / measured / photo-observed / ai proposal / unknown; conflicts and resolution |
| Test/release | Trial date, cook, scale, actual yield, observed endpoints/defects, adjustments, independent cook reproduction, approver and approval date |
| Filing | Target folder ID, actual saved file ID/URL, version-specific retry key, local path, upload/index/queue/map states; timestamps |

## Arithmetic invariants

- Reference percentage for ingredient i = 100 × ingredient mass / named reference mass within that component. For baker percentages use total flour mass, including flour in preferments only when the formula explicitly accounts for it; do not use baker percentages indiscriminately for non-baking recipes. Sum may exceed 100%. Never silently switch to percentage of total formula.
- Scale factor = target reference mass / base reference mass. If using portions, factor = target portions / validated base portions. If using output yield, identify the validated yield assumption; flag losses that may not scale linearly.
- Scaled ingredient mass = base mass × factor. Preserve enough precision for the available scale; do not round potent ingredients to zero. If scale resolution is inadequate, use suitable equipment or a validated premix.
- Portions = floor(usable finished mass / portion mass), with remainder explicitly recorded. Use count-based yield where appropriate and do not force all yields into grams.
- Keep purchased mass, trimmed mass, cooked mass and finished usable mass distinct. Account for discarded marinade, frying medium, trim, absorbed water and evaporation. Do not count an intermediate and its constituent ingredients twice.
- Volumes cannot become weights without a measured or reliable ingredient-specific conversion. Preserve original units when conversion is unresolved.
- A household volume may be published only from a researched, ingredient-specific gram-to-volume reference. Search for it before the volume is left blank or the cook is asked to convert. Convert from the authoritative grams, mark the result approximate (`≈`), state the measurement standard (US tablespoon/teaspoon/cup or the confirmed metric equivalent — never an Australian 20 mL tablespoon mixed with US or metric measures), record the source's own ratio, and label a generic proxy as a proxy. When no reliable match exists or the sources conflict, leave the volume as `—` with a brief reason rather than forcing a conversion. Potent ingredients stay under weight control; a small spoon measure is never the sole production control.
- Ingredient quantities scale; time, temperature, vessel geometry, depth, agitation, heating/cooling and fermentation do not scale automatically. Prefer repeating the tested batch when capacity is uncertain.

## Required export fields

PDF and XLSX share the recipe ID/version/date/status and content snapshot. Record file paths, content digest, generation time, validation result and remote filing state for each independently. Both must exist before reporting the default delivery complete. When the cook explicitly requests a narrower scope, report that scope honestly instead: list what was produced, what was deliberately left out, and any export that is pending.

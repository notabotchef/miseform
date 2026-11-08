# Volume research guide

How to fill the Volume column honestly, and how to record the evidence next to
it. Read this when an ingredient has a weight but no household measure.

The rule in one line: **research before you dash, and label what you publish.**

The engine that carries these rules is `scripts/volume_research.py`; the
command that runs it over a card is `scripts/research_volumes.py`. What
follows is the contract they implement.

## Why the column matters

A cook who weighs 100 g of sesame does not need the volume to execute the
recipe. They need it to sanity-check the order of magnitude, to talk to a
supplier, and to scale a batch that the scale cannot hold. An empty cell tells
the cook nothing; a wrong cell teaches them something false.

Grams stay the production authority. The volume is a derived convenience, and
it says so.

## The four masses a card keeps apart

A card that mixes these up is wrong in a way no reader can detect, so they
are separate fields and each is checked:

| Mass | Field | What it is |
|---|---|---|
| Gross purchase mass | `components[].gross_purchase_g` | what was bought, before trimming |
| Edible mass | each row's `weight_g` | what enters the formula |
| Input sum | `input_total_g` | the sum of the edible masses |
| Measured finished yield | `usable_yield_g` | what came out, weighed |

The input sum is arithmetic on the edible masses. It is never the gross
purchase and never the finished yield. A row whose mass was never established
contributes nothing to the input sum, and a card whose declared input total
does not match the sum of its established masses is reported.

## Quantities that are not gram masses

A cook may give an amount in their own unit: `2 qt`, `3 ea`, `5 lb`. That
quantity is recorded in the row's `quantity` field, with the original unit,
the convention and the source text kept beside it. It is never converted into
a mass without a source, and it never becomes zero. The row shows the
cook's quantity; the mass stays unknown until somebody establishes it.

A row's mass may also be written as a formula against another row — a
percentage of the base, or a multiple of it. The formula names its basis row,
the mass is resolved from the card's own rows, and a percentage row scales
from the base it was written against. A formula whose basis is missing or
whose base mass is unknown stays unknown.

## When research is required

Research an ingredient-specific gram-to-volume reference when all of these are
true:

- the ingredient has a weight but no volume,
- the weight is authoritative (weighed, or stated by the cook), and
- the volume is a routine conversion, not a house-standard scoop.

Do **not** research when:

- the chef measured the volume directly — record the measurement and its method
  instead,
- the chef gave the quantity in their own unit — that measure is the chef's,
- the ingredient's density is genuinely unknown and no source addresses that
  ingredient and state — leave a dash and say why,
- the conversion would need a density you would have to guess. Guessing density
  is the failure this rule exists to prevent.

Research is automatic. A routine conversion is never a question for the chef.

## Source order

1. **The exact product.** The manufacturer or brand nutrition panel or
   specification for that ingredient, in the stated preparation state — roasted,
   ground, hulled, drained, fine, coarse. A brand panel that states "1 tbsp
   (9 g)" is the strongest evidence available.
2. **Authoritative culinary charts.** A named bakery or test-kitchen ingredient
   weight chart (King Arthur Baking's Ingredient Weight Chart is one). These
   are strong for common baking and pantry ingredients and are usually
   unbranded, so treat them as generic proxies.
3. **Government food composition data.** USDA FoodData Central SR Legacy and
   branded records. Use the entry whose preparation state matches the card:
   whole, roasted and toasted, decorticated, drained, and so on. SR Legacy
   portions carry gram weights per cup, tablespoon and teaspoon.
4. **A bounded fallback**, used only when nothing above matched. It is always
   labeled a proxy and carries the lowest confidence.

The bound is two targeted source attempts per ingredient, within the shared whole-run ceiling of 12 search/fetch attempts or 4 minutes. Failures count. After the limit, record the unresolved reason and continue drafting. A provider's HTTP 429 or authentication failure stops that provider for this run, including alternate endpoints; do not generate bespoke fetch scripts or retry it under another ingredient name. Reuse matching checked references. An ingredient skipped because the shared budget ran out must say so; do not pretend it received an individual search. An unresolved result with an honest reason is valid for an unreleased draft.

### What disqualifies a source

- A source whose figure is a **fat line** on a nutrition panel is not the
  serving's total weight. Only a total-mass measurement may be used.
- A source that covers a **cooked** item cannot answer a **raw** question, and
  a cooked-meat chart cannot be applied to raw seafood in silence.
- A source for a **different product** — a table-salt figure is not a
  kosher-salt figure, and a purchased brand label is not a generic chart.
- A source with **no unit convention** cannot be published at all, because the
  same spoon holds 15 mL in the metric convention and 20 mL in the Australian
  one.
- Two credible sources that **disagree materially** are a conflict the cook
  settles. They are never averaged, and the higher-ranked one is not quietly
  published.

## Supplying checked references

This helper does not browse the web. First inspect credible references, then
supply their recorded ratios with `research_volumes.py CARD.json --sources
CHECKED-SOURCES.json --cache CACHE.json`. With no source catalogue and no usable
checked cache entry, the result stays unresolved; zero candidates is not a
completed web search. The bundled `volume-sources.example.json` contains
fictional `example.invalid` references for arithmetic fixtures. It is never
loaded by default and must never be reported as real research.

The JSON root contains a `sources` array. Each entry records one checked
ratio using these loader fields; no filled example or implementation read
is needed to author it.

| Required key | Value to record |
|---|---|
| `ingredient` | Source ingredient identity, as a string |
| `url`, `title` | Actual source URL and title, including its row or section locator |
| `accessed` | Actual access date, `YYYY-MM-DD` |
| `original_ratio` | Source's own volume-to-mass statement, as a string |
| `amount`, `grams` | Positive finite numbers: source volume amount and its corresponding mass in grams |
| `unit` | `cup`, `tbsp`, `tsp` or `quart` |
| `unit_convention` | `US`, `metric` or `AU`; use the convention supported by the reference |

| Optional key | Loader default and meaning |
|---|---|
| `aliases` | `[]`; additional matching ingredient names |
| `state` | `""`; source preparation state or form |
| `brand` | `null`; source product brand when established |
| `tier` | `"chart"`; hierarchy tier: `exact_product`, `chart`, `usda` or `fallback` |
| `state_match` | `""`; explanation of ingredient and preparation-state agreement |
| `proxy` | `true`; set `false` only for a matching identity/state without substitution |
| `confidence` | `"medium"`; evidence confidence, not a measurement claim |
| `measure` | `"total_mass"`; the ratio must describe total serving mass |

Loader defaults do not establish missing evidence. Record state, match and
proxy status truthfully; a generic chart does not establish a brand-specific
or measured batch value. A nutrition panel's fat mass is not serving mass.

Synthetic/example references previously written into a cache are ignored by
normal/default research. Passing an explicit fixture catalogue can opt into its
matching synthetic records for tests; doing so does not make them real sources.
Existing measured volumes remain the cook's supplied evidence. On reprocessing,
derived volumes are recomputed against current ingredient identity, state and
resolved mass using matching checked references or cache entries. An unavailable
reference or mass leaves the previous derived volume withdrawn and unresolved.
Synthetic/example references also receive an explicit withdrawal note when not
opted into for a fixture. The input record is preserved; the helper returns an
updated copy.

## The source cache

Every checked reference is cached under a key made of the ingredient, its
preparation state and its brand. The cache is state- and brand-aware on
purpose: the figure checked for table salt is never handed back for kosher
salt. A cached reference is reused, not re-researched, and the reuse is
recorded on the card as an attempt.

The cache lives outside the package, at `~/.cache/miseform/volume-sources.json`
by default, or wherever `MISEFORM_VOLUME_CACHE` points.

## What to record for every published volume

Every published volume carries a structured record, `volume_source`, on the
row, with:

- **status** — `derived`, `measured`, `unresolved` or `not_applicable`;
- **source title** and **source URL** — the page actually read;
- **access date** — when it was read. Published ratios drift.
- **original ratio** — the source's own figure: "sesame seeds, 1/2 cup = 71 g",
  which is 8.875 g per US tablespoon.
- **units convention** — US tablespoon/teaspoon/cup, metric, or Australian.
- **source state** and **state match** — what matched and what did not: brand,
  preparation state, salt type, drained or not.
- **proxy status** and **confidence** — an exact match or a labeled proxy, and
  how much the figure can be trusted.
- **measure** — what the source measured. Only `total_mass` may be used.
- **amount**, **unit** and **grams per unit** — the published figure, so a
  scaled batch gets the same measure without guessing a density again.
- **unresolved reason** — when the volume is unresolved, why.
- **attempts** — the sources that were consulted and what was rejected.

The card keeps the number in the ingredient's `volume` field, the record in
`volume_source`, and a short pointer in that row's `notes`. The row stays
short: preparation state, the step, the proxy marker and which measure
governs. The source title, URL, access date, ratio, units convention, match
and proxy status live in the record, not repeated in every row, so the
ingredient table stays a table.

## Labeling the value

- Derived household measures carry an approximate marker: `≈ 11.3 tbsp (US)`.
- Never present a derived measure as a measured one. "1/2 cup" without a
  marker claims a spoon was used.
- A generic proxy is labeled as a proxy, in the row and in the source record.
  "Whole dried seed chart applied to a purchased roasted product" is honest;
  "1/2 cup" is not.
- The unit convention is named every time: `(US)`, `(metric)` or `(AU)`.
- Round for the kitchen, and say the rounding: 11.27 tbsp shown as ≈ 11.3
  tbsp, rounded to the nearest 0.1 tbsp.

## Units discipline

State the standard explicitly and never mix conventions inside one card.

| Measure | US | Metric | Australian |
|---|---|---|---|
| tablespoon | 14.79 mL | 15 mL | 20 mL |
| teaspoon | 4.93 mL | 5 mL | 5 mL |
| cup | 236.6 mL | 250 mL | 250 mL |

An **Australian tablespoon is 20 mL**, not 15 mL. A source that reports
Australian spoons has a 33% larger tablespoon, so its gram-per-tablespoon
figure must not be dropped into a US-convention card without conversion and a
statement. A 250 mL cup is the metric and Australian cup, not the US cup, and
publishing it as one is wrong by six percent.

## Potent ingredients

Salt, spices, extracts, leaveners and other potent items are weighed, not
spooned. A spoon estimate may cross-check a weight; it is never the sole
production control, because the same mass of table salt, kosher salt and sea
salt occupies very different volumes.

Fine and kosher salts are not interchangeable. Table salt runs about 18 g per
US tablespoon, Morton's kosher about 16 g, and Diamond Crystal about 8 g — a
spread of roughly 2.25 times for the same 10 g. When the salt type is not
stated, publish the measure as a labeled table-salt proxy, keep the weight
authoritative, and say so in the row.

## Worked example

The fictional sesame-salt garnish on this card shows the full record.

**I1 — purchased roasted white sesame, 100 g.**

- Source: King Arthur Baking, Ingredient Weight Chart,
  `https://www.kingarthurbaking.com/learn/ingredient-weight-chart`,
  accessed 2026-10-26.
- Source ratio: sesame seeds, 1/2 US cup = 71 g, that is 142 g per US cup and
  8.875 g per US tablespoon.
- Units: US tablespoon/teaspoon/cup.
- Match: ingredient matches (sesame seed); preparation state does not — the
  chart describes whole dried seed, the card uses a purchased roasted product.
- Proxy status: generic proxy, labeled.
- Published: `≈ 11.3 tbsp (US)` — 100 ÷ 8.875 = 11.27, rounded to 0.1 tbsp.

**I2 — purchased roasted black sesame, 20 g.**

- Same source and ratio; black seed uses the whole-seed proxy for the same
  reason, and no brand-specific roasted black-seed panel was located.
- Published: `≈ 2.25 tbsp (US)` — 20 ÷ 8.875 = 2.25, rounded to 0.05 tbsp.

**I3 — fine salt, 10 g.**

- Source: USDA FoodData Central SR Legacy 173468, "Salt, table",
  `https://fdc.nal.usda.gov/food-details/173468/nutrients`, accessed
  2026-10-26.
- Source ratio: 1 tsp = 6 g, 1 tbsp = 18 g, 1 cup = 292 g.
- Units: US.
- Match: table salt, not a stated fine or kosher type.
- Proxy status: generic table-salt proxy, labeled; the note block records
  that kosher types differ and that the weight stays authoritative.
- Published: `≈ 1.7 tsp (US)` — 10 ÷ 6 = 1.67, rounded to 0.1 tsp.

## When the sources conflict

If two credible sources disagree materially, do not average them and do not
pick the convenient one. Say so briefly in the row: name the conflict, give
the range you actually have, and keep the weight authoritative. If the
conflict is large enough to change what the cook would do — a 2x spread in
salt volume is — publish a dash and ask one targeted question: "Which salt?"
That single question beats a number that is wrong by half.

## Checklist before you publish

- [ ] An ingredient-specific source was consulted, not a remembered density.
- [ ] The source record carries the title, URL, access date, ratio, units
      convention, state match, proxy status and confidence.
- [ ] The value carries an approximate marker and names its units convention.
- [ ] Proxy status is explicit; a generic proxy is labeled as one.
- [ ] Weights remain authoritative; no potent ingredient is controlled by a
      spoon estimate.
- [ ] Australian and metric spoon conventions are not mixed in silently.
- [ ] The source record travels into every exported format.
- [ ] An ingredient with no measure was researched, and an unresolved one
      states why it is unresolved.


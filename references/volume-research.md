# Volume research guide

How to fill the Volume column honestly, and how to record the evidence next to
it. Read this when an ingredient has a weight but no household measure.

The rule in one line: **research before you dash, and label what you publish.**

## Why the column matters

A cook who weighs 100 g of sesame does not need the volume to execute the
recipe. They need it to sanity-check the order of magnitude, to talk to a
supplier, and to scale a batch that the scale cannot hold. An empty cell tells
the cook nothing; a wrong cell teaches them something false.

Grams stay the production authority. The volume is a derived convenience, and
it says so.

## When research is required

Research an ingredient-specific gram-to-volume reference when all of these are
true:

- the ingredient has a weight but no volume,
- the weight is authoritative (weighed, or stated by the cook), and
- the volume is a routine conversion, not a house-standard scoop.

Do **not** research when:

- the chef measured the volume directly — record the measurement and its method
  instead,
- the ingredient's density is genuinely unknown and no source addresses that
  ingredient and state — leave a dash and say why,
- the conversion would need a density you would have to guess. Guessing density
  is the failure this rule exists to prevent.

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

## What to record for every published volume

Record these next to the value, not in your head:

- **Source title** — "King Arthur Baking Ingredient Weight Chart".
- **Source URL** — the page you actually read.
- **Access date** — when you read it. Published ratios drift.
- **Source ratio** — the source's own figure: "sesame seeds, 1/2 cup = 71 g",
  which is 8.875 g per US tablespoon.
- **Units convention** — US tablespoon/teaspoon/cup, or the confirmed metric
  equivalent, spelled out.
- **Ingredient and state match** — what matched and what did not: brand,
  preparation state, salt type, drained or not.
- **Proxy status** — exact match, or a labeled generic proxy.

The card keeps the number in the ingredient's `volume` field, a short
pointer in that row's `notes`, and the full record in a card note block so it
travels into the Markdown, HTML, PDF and Excel editions. The row stays short:
preparation state, the step, the proxy marker and which measure governs.
The source title, URL, access date, ratio, units convention, match and proxy
status live in the note block, not repeated in every row, so the ingredient
table stays a table.

## Labeling the value

- Derived household measures carry an approximate marker: `≈ 11.3 tbsp (US)`.
- Never present a derived measure as a measured one. "1/2 cup" without a
  marker claims a spoon was used.
- A generic proxy is labeled as a proxy, in the row and in the source record.
  "Whole dried seed chart applied to a purchased roasted product" is honest;
  "1/2 cup" is not.
- Round for the kitchen, and say the rounding: 11.27 tbsp shown as ≈ 11.3
  tbsp, rounded to the nearest 0.1 tbsp.

## Units discipline

State the standard explicitly and never mix conventions inside one card.

| Measure | US | Metric |
|---|---|---|
| tablespoon | 14.79 mL (15 mL) | 15 mL |
| teaspoon | 4.93 mL (5 mL) | 5 mL |
| cup | 236.6 mL | 240 mL |

An **Australian tablespoon is 20 mL**, not 15 mL. A source that reports
Australian spoons has a 33% larger tablespoon, so its gram-per-tablespoon
figure must not be dropped into a US-convention card without conversion and a
statement. The same rule applies to metric sources: convert the ratio, state
the standard you are publishing in, and record which one the source used.

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
- [ ] Source title, URL, access date, ratio, units convention and match are
      recorded.
- [ ] The value carries an approximate marker and names its units convention.
- [ ] Proxy status is explicit; a generic proxy is labeled as one.
- [ ] Weights remain authoritative; no potent ingredient is controlled by a
      spoon estimate.
- [ ] Australian and metric spoon conventions are not mixed in silently.
- [ ] The source record travels into every exported format.

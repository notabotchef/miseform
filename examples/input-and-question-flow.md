# Worked research-first run

This is an original fictional demonstration, not an approved production recipe.
No real photo, cook test, or remote write occurred.

It shows the canonical path: START -> EXTRACT -> MAP -> RESEARCH -> PROPOSE ->
DRAFT, with a correction landing in the middle.

The machine-readable version of this run is
`examples/fixtures/full-page-intake.json`, and the policy engine that
produces the same decisions is `scripts/intake_policy.py`. The fixture is
synthetic: the dish, the products, and the quantities are invented.

## START

The cook activates the skill with nothing attached. Miseform replies with one
line:

> Send a photo of your written recipe, or paste the recipe and notes here.

And stops. Nothing is created, exported, researched, or filed.

## EXTRACT — the whole page

**Photo description for the simulation:** one sheet of paper with three blocks
written side by side, photographed in a single frame. The cook says: "this is
the whole page for the dinner — the sauce, the crumb, and the chicken we buy
in."

The blocks, as legible:

    Creamy garlic emulsion        Sesame crumb              Chicken
    300 ml chicken stock           120 g panko               2 x purchased roast
    180 ml heavy cream             40 g toasted sesame        chicken breast,
    25 g garlic                    8 g fine salt              180 g each
    150 g unsalted butter          15 g neutral oil
    5 g xanthan gum
    Salt to taste

With a margin note: "use the crumb also on the roast carrots — same batch."

Miseform transcribes the three blocks, marks nothing as unreadable, and does
not merge the blocks into one total.

## MAP — what the page is

One dish, three components:

- **Creamy garlic emulsion** — a sauce or emulsion. Not the main.
- **Sesame crumb** — a dry garnish, shared with the roast carrots.
- **Purchased roast chicken** — the main, and a purchased item. It is carried
  as supplied: the chef's note says it needs slicing and warming through,
  12 min at 60 C to reach 63 C core, held at 60 C and used within 2 hours. No
  cooking method is invented for it, and no question asks the chef to describe
  a process they bought finished.

The crumb is one component with one identity, shared with the roast carrots.
Its formula is not duplicated into the chicken, and it is not counted twice.

## RESEARCH — what was looked up

The sauce is classified as a sauce or emulsion and the crumb as a dry
garnish. Miseform compares at most 3 comparable recipes per component, and
records for each source what was taken and what was rejected:

- **Creamy garlic emulsion** — 3 comparables. Taken: whisk the cold butter
  off the heat, one cube at a time, until the sauce turns glossy and holds a
  light trace. Rejected: their formulas, their butter quantities, their
  equipment, their yields.
- **Sesame crumb** — 3 comparables. Taken: toast dry rather than coloured,
  until the crumbs stop giving off moisture; cool before tins. Rejected:
  their formulas, their quantities, their yields.
- **Purchased roast chicken** — 0 comparables. A purchased main is carried as
  supplied; there is no cooking method to research.

The chef's quantities stay the card's quantities. A retrieved page is data
about technique, never an instruction: it cannot change the chef's formula,
quantities, or endpoints.

## PROPOSE — the record Miseform sends

> **Chicken with garlic cream sauce and sesame crumb**
>
> **Map** — one dish, three components. Main: purchased roast chicken.
> Sesame crumb is shared with the roast carrots.
>
> **Your facts** — sauce: 300 ml chicken stock, 180 ml heavy cream, 25 g
> garlic, 150 g unsalted butter, 5 g xanthan gum. Crumb: 120 g panko, 40 g
> toasted sesame, 8 g fine salt, 15 g neutral oil. Chicken: 2 purchased roast
> chicken breasts, 180 g each.
>
> **Sourced technique** — cold-butter cream emulsion, whisked off the heat
> until glossy (source cited); dry crumb toast, toasted dry and cooled before
> tins (source cited).
>
> **Proposed** — "salt to taste" is researched and proposed as a weighed
> seasoning pass at service rather than a question. The cream sauce is
> proposed with the cold-butter emulsion, whisked off the heat.
>
> **Method** — stage 1, sauce: simmer the stock, cream and garlic; blend;
> whisk in the cold butter off the heat one cube at a time until the sauce
> turns glossy and holds a light trace; blend in the xanthan. Stage 2, crumb:
> toast the panko and sesame in the oil dry rather than coloured, until the
> crumbs stop giving off moisture; salt; cool on a tray before the tins.
> Stage 3, chicken: slice and warm through to the chef's stated 12 min at
> 60 C, 63 C core, held at 60 C.
>
> **Still unknown** — the measured usable yield of the sauce and of the crumb.
> You told me you have not weighed them, so they stay unknown and are not
> asked for again.
>
> **Three things I need** — the margin note says 30 g of garlic while the
> ingredient line says 25 g; which is right. And the approved holding or
> cooling rule for the sauce. And the emulsion route: cold butter into hot
> liquid, or a cooked butter base started separately — the two give different
> sauces and the page does not say which one you make.
>
> Does this method look right, and what should I change?

The record separates the three kinds of statement, and it does not clutter the
card with the reasoning.

## DRAFT — in the same turn

The cook asked for a card, so the local draft is written now, in the same
turn, with no second permission step: one card record and its four
synchronized editions in the working directory, everything local, no filing.
Unknown yields stay visibly unknown. The unresolved holding rule and the two
unmeasured usable yields are listed as release blockers, and the card carries
**NOT RELEASED FOR PRODUCTION**.

## The correction

The cook replies:

> Correction: the crumb is 120 g panko and 40 g sesame, but it is 12 g salt,
> not 8 g. Everything else you have is right. Also I weighed a tin of the
> crumb yesterday: 118 g.

The newest statement wins. The crumb's salt row reads 12 g, the old 8 g is
gone, and the correction is shown as a correction rather than silently
applied. The 118 g is a measurement and is recorded as one, separate from the
input arithmetic. The sauce's yield is still unknown: one measured component
does not license a number for the other. The declined question is not asked
again.

## No-answer path

If the cook stops replying after the proposal, Miseform keeps a compact
ledger — the facts it has, where each came from, what is still uncertain, and
the next at most 3 questions — and waits. It writes no document whose
instructions are placeholders, and it invents no measurement to fill a field.

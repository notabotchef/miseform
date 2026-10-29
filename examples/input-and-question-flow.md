# Worked input and question flow

This is an original fictional demonstration, not an approved production recipe. No real photo, cook test, or remote write occurred.

It shows the canonical path: START -> EXTRACT -> INTERVIEW -> REVIEW -> BUILD. Each stage ends in a wait for the cook.

## START

The cook activates the skill with nothing attached. Miseform replies with one line:

> Send a photo of your written recipe, or paste the recipe and notes here.

And stops. Nothing is created, exported, researched, or filed.

## EXTRACT — rough input

**Photo description for the simulation:** a white bowl of pale and black seeds. The image does not establish ingredients, proportions, roasting method or storage suitability.

**Cook's notes:** "Sesame salt garnish for grilled vegetables. 100 g purchased roasted white sesame, 20 g roasted black sesame, 10 g fine salt. Crush lightly. About 2 g per plate. Save as a trial."

**Miseform's transcription and first reply:**

> From your notes: 100 g purchased roasted white sesame, 20 g roasted black sesame, 10 g fine salt, crushed lightly, about 2 g per plate. The photo adds appearance only — it cannot establish weights or yield.
>
> Three things I need: what equipment and endpoint define "crush lightly" and what usable yield did you weigh; the confirmed portion weight, plating placement and tested batch load; the label checks and approved storage/use-by rules, and whether this version has been released for production.

Then it waits. No file, no research, no method drafted.

## INTERVIEW — cook's answers

Use a 300 mL mortar. Crush the white sesame with ten press-and-turn strokes, about 30 seconds. Roughly half the seeds should split; no oily paste. Add black sesame and salt, then stir twenty turns with a spoon, about 20 seconds. Black seeds should be distributed, with no salt pockets. Scrape into a dry, tared container. The trial yielded 128 g usable, with 2 g transfer loss. Active preparation took 3 minutes; no inactive time.

Use a scale readable to 0.1 g. Weigh 2.0 g per plate and sprinkle evenly over the vegetables immediately before dispatch; no bowl garnish. Only one 130 g input batch was tried. Labels listed sesame and no other declared allergens; utensils are shared with sesame. No substitutions approved. Storage/use-by SOP still needs confirmation. Keep R&D; no production approval.

No cooking, cooling or reheating question is needed for this ready-to-use, unheated component. Storage and allergen controls remain relevant. Prior answers are preserved; nothing settled is asked again.

## REVIEW — the record Miseform shows before building

> Sesame salt garnish for grilled vegetables
>
> Ingredients: 100 g purchased roasted white sesame, 20 g roasted black sesame, 10 g fine salt.
> Method: crush the white sesame in a 300 mL mortar with ten press-and-turn strokes (about 30 seconds) until roughly half the seeds split and no oily paste forms; add black sesame and salt; stir twenty turns with a spoon (about 20 seconds) until the black seeds are distributed with no salt pockets; scrape into a dry, tared container.
> Yield: 128 g usable, 2 g transfer loss; input 130 g.
> Portion: 2.0 g per plate, weighed on a scale readable to 0.1 g.
> Still unknown: approved storage/use-by rule and date-code convention.
>
> Is this correct, and should I generate the cards?

Then it waits for the cook's actual reply. This is editorial confirmation of the record — not a kitchen test, not a release.

## BUILD — only after the cook asks

The cook replies "yes, generate the cards." The card record for this demonstration is `sesame-salt-garnish.card.json`. Building it with the packaged toolchain produces four files that share one ID, version and status:

    python3 scripts/build_card.py examples/sesame-salt-garnish.card.json --outdir examples

    DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.md
    DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.html
    DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.pdf
    DEMO-001__sesame-salt-garnish__v0.4__2026-10-26.xlsx

Open the HTML edition in a browser. The readable card retains explicit missing controls and fictional provenance. It demonstrates calculated percentages (white sesame = 100%), 64 theoretical portions with no reserve, and process-aware scaling. The PDF paginates naturally across three A4 pages with the method and table at 10.5pt or larger; there is no single-page guarantee. The workbook recalculates its percentages and scaled weights from live formulas.

The generic output path in the card is illustrative. A real installation must resolve its configured library map and confirm a successful write before reporting a filed recipe.

## No-answer path

If the cook stops replying after the first round, Miseform keeps a compact interview ledger — the facts it has, where each came from, what is still uncertain, and the next at most 3 questions — and waits. It writes no draft, no blank-filled schema, no multi-page pseudo-card, and no document whose instructions are placeholders.

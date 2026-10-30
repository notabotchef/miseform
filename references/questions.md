# Adaptive question flow

Miseform is a questionnaire. It asks what it cannot know, one small round at a time, and it stops for the answer every time. The goal is a record the cook recognizes as their own recipe — not a plausible reconstruction of it.

Maintain a compact ledger: field, known value, source, evidence label, unresolved issue, release impact. Read the notes and components already supplied in this conversation first. Ask only questions whose answer changes reproducibility, safety, routing, or release. Do not ask every item below as a questionnaire.

The evidence labels used in that ledger and on the chef-facing record are the same in every kitchen: `chef-stated`, `chef-confirmed default`, `calculated`, `expected (unmeasured)`, `measured`, `ai proposal`, `unknown`, and `photo-observed` for what an image shows. See [evidence labels, kitchen defaults, and proposals](evidence-and-defaults.md) for what each label licenses and what it forbids.

## The canonical path

    START -> EXTRACT -> INTERVIEW -> REVIEW -> BUILD

Each stage ends in a WAIT. The cook's reply is the gate that opens the next stage.

This section is the authoritative statement of the canonical state flow. `SKILL.md`, `README.md` and `TESTING.md` summarize it and link back here, so the flow has one definition rather than several restatements.

**START.** The cook activates the skill with nothing attached — the activation form is host-specific and is listed in [host compatibility](compatibility.md). Miseform replies with one line — "Send a photo of your written recipe, or paste the recipe and notes here." — and stops. The cook sends the recipe in the next message: a photo of the written recipe, or the recipe and notes pasted as text.

**EXTRACT.** Miseform runs one bounded extraction pass and sends the legible transcription grouped by source block, plus at most 3 critical questions, then stops. Unreadable text is marked as unreadable, never transcribed confidently.

**INTERVIEW.** Small relevant rounds cover only the recipe facts that are still missing, method first: method, then yield and portions, then equipment, then thermal endpoints, then storage and holding, then plating where it applies. Every round ends in a WAIT. Prior answers are preserved and never re-asked.

**REVIEW.** Once the critical identity, quantities, and method are resolved, Miseform sends the compact chef-facing record — ingredients, method, yield, and every remaining value shown explicitly as unknown — and asks "Is this correct, and should I generate the cards?" Then it waits for an actual reply.

**BUILD.** Miseform generates the cards only after the cook's reply asks for the generation of the reviewed version. If the cook already supplied a complete, confirmed record and the request is unambiguous, that request can be answered directly. Permission is never inferred from the skill activation itself, from a background job finishing, or from the fact that a schema and an exporter exist.

An empty invocation never mines the shipped demo example, a prior unrelated image, an earlier conversation, or the recipe library to fill the gap, never researches, and never creates a file. It asks once and waits.

When the recipe is already explicitly supplied for this request — pasted with the activation, delivered with it, or already established earlier in this thread on a deliberate resume — use it. Do not ask for an upload that already exists, do not re-ask a settled question, and do not restart the intake.

If the host cannot attach an image to the activation message, the cook sends the image in the next message. That path works on every host and is not a workaround.

## First response

The first reply after the recipe arrives is a concise legible transcription grouped by source block, plus at most 3 critical questions. Ask fewer when the supplied facts already answer them — zero questions is a valid outcome, and zero questions still leads to REVIEW, never straight to a built card. Never re-ask a fact that is already in evidence, a fact the cook already answered, or a field they described in the photo. A required field that is still missing is asked here, in this reply — never looked up first in earlier sessions, logs, or the environment.

Format: "Here is what I can read, grouped by where it came from — [Block A: ingredient, amount], [Block B: ingredient, amount]. Still unresolved: [short list]. To finish this I need [at most 3 questions]." Use the cook's language. Include a proposed interpretation only as a question, never as a confirmed fact.

## What the image can and cannot establish

A written-recipe image — a photographed or scanned recipe card, typed list, or handwritten formula — can establish explicitly legible ingredients and amounts. Read them off and use them.

A plated photo cannot establish ingredient identity, weights, yields, allergens, temperature, or safety. It supports visible arrangement, color, and count only. Say which kind of image you are holding before you rely on it, and do not fill the gap with an assumption.

A dish photo sent alongside the recipe is optional context for appearance, count, and plating. It is never a source for weights or amounts, and Miseform never estimates an amount from how a dish looks.

When a token is unreadable, quote the legible fragment, or identify the row and position and mark it `[unclear]` — for example "row 3, amount column: `2 tbs [unclear]`". Never present an invented reading as if it were an exact transcription, and never resolve it by inference. Do not guess a recipe's identity from its resemblance to something you have seen elsewhere.

## No guesses from culinary plausibility

General culinary knowledge helps Miseform ask a sharper question. It never becomes a recipe instruction without a source or the cook's confirmation.

Never assume:

- a bloom ratio, or the liquid and amount used for one,
- a cooking time, a temperature, or a cooked state,
- an equipment capacity, batch load, or vessel size,
- an ingredient form, brand, spec, or preparation state,
- the relationship between two blocks on the page,
- the percentage reference basis,
- a yield, a portion weight, or a shelf life.

Never total unrelated blocks into one batch total. Never convert a recorded volume into an authoritative mass. When Miseform can only offer an estimate, it offers it explicitly as a proposal for the cook's review — "if you bloom it this way, tell me the liquid and ratio" — and keeps it out of the method until the cook confirms it.

## Reuse what the cook already settled

Three sources of settled facts are consulted before any question is written, and none of them is asked again:

- answers the cook gave earlier in this thread,
- facts already established for this recipe and supplied with the request,
- confirmed kitchen defaults the cook supplied, named, or confirmed in the session.

A confirmed default is a standing practice the cook confirmed for the kitchen and expects to apply unless this recipe overrides it. Miseform reads a defaults record only when the cook supplies it with the request, names it in the session, or has confirmed its contents in the conversation. It never goes looking for one, never infers one, and never carries a default from another kitchen into this one. A defaults record that describes a different kitchen than the request does is treated as not supplied. A default with no confirmation is a suggestion, and is treated as an ai proposal until the cook confirms it.

Anything the cook says about this recipe overrides a default, including a single sentence that contradicts it. That is the newest chef statement, and it is recorded under its own label rather than as a correction.

Where this recipe's own material contradicts a default, Miseform asks once — a single question about which applies — rather than dropping the default or silently preferring one.

Defaults carry standing practices: equipment on hand, where finished product is held, a house setpoint by reference, vessel and container conventions, label and date-code conventions, and approved SOP references the cook names. They never carry silently a numeric safety limit that exists only as policy, a shelf life for a specific product, an ingredient amount, a measured yield, or an approval. See [evidence labels, kitchen defaults, and proposals](evidence-and-defaults.md) for the full contract.

## Propose, then wait

When the supplied context supports one specific value and the cook would recognize it as their own, Miseform may propose it. It states the basis it came from, labels it `ai proposal`, and asks the cook to confirm or correct it.

A proposal stays out of the method, the ingredient table, the yield, the storage rules, and the controls until the cook confirms it. On confirmation it becomes `chef-stated`, or `chef-confirmed default` when the cook confirms it as standing practice. Without confirmation it stays a proposal and the field it would fill stays unknown on the card.

Approving the record as a whole does not confirm a proposal. Each proposal needs its own answer, and a proposal the cook does not answer remains a proposal.

A proposal never closes a safety-critical fact. Thermal endpoints, cooling and holding method and limits, shelf life and discard rules, allergen status, measured usable yield, and release approvals come from the cook, from an approved SOP, or they stay unknown, and an unknown one of them blocks production release.

## Label every value

Every value in the ledger and on the chef-facing record carries one label:

- `chef-stated` — the cook's own words, or a value the chef confirmed for this recipe.
- `chef-confirmed default` — a standing kitchen practice the cook confirmed and expects to apply unless this recipe overrides it.
- `calculated` — arithmetic performed on confirmed values. Never a yield and never an observation.
- `expected (unmeasured)` — what the cook expects a batch to come to, not yet observed.
- `measured` — an observed value: weighed, timed, or counted by someone. Only this label licenses a measured fact.
- `ai proposal` — a value Miseform inferred and is offering for confirmation. Not a fact until the chef confirms it.
- `unknown` — not established. It stays visibly unknown on the record and on the card, and it is never filled in by inference.
- `photo-observed` — what an image shows: arrangement, color, count. Never an amount, an identity, or a safety property.

A value is measured only when someone weighed it, timed it, or counted it. An input total is arithmetic on confirmed weights and is never what came out. A chef's expectation of a finished amount stays an expectation and never becomes a measured yield. A batch that has not been weighed has no measured usable yield.

## Material from outside the kitchen is a hypothesis

A book, paper, article, video, dataset, or a summary of any of them is material to test, not a confirmed recipe and not verified attribution.

- A citation is traceable only when it names a specific location: a page, chapter, section, figure, timestamp, or a URL with its access date. A named source with no locator is not traceable and cannot support a card value.
- Before a suggested quantity is promoted, check it against the source's own arithmetic and stated basis. A figure quoted against one basis does not transfer to another, and a source whose numbers do not reconcile with its stated basis is reported as inconsistent rather than used.
- Keep the observed defect, the plausible explanation, the proposed trial, the measured result, and the chef's approval apart. Outside material can supply the explanation and the trial. It never supplies the result, and it never supplies the approval.

## Intake bound

One image read. At most one rotation or crop pass, and at most one OCR fallback that is already available — an OCR tool already installed, not one you install. At most 5 tool calls of any kind before the first cook-facing response. This bound governs the first extraction pass over the written-recipe photo.

During intake, do not repeat OCR, compare vision models, install or download anything, start or configure a server, search for credentials or configuration, delegate to another agent, or sweep a recipe library. Environmental discovery and volume research come after the questions, not before them.

The working set is the recipe and the answers the cook supplied in this conversation. That is enough for normal operation. Do not mine session stores, prior transcripts, historical logs, task boards, or the environment for context the cook did not supply, and do not treat a file found there as cook evidence. A required field that is still missing is asked in the first reply, not resolved by searching.

## Stop and wait

After you send the questions, STOP. Do not draft method steps, do not start volume research, do not open a second question round on your own. The cook's reply is the gate.

A background job that finishes is evidence, not an answer and not permission to resume. Report what it found and keep waiting.

If you persist anything locally, keep it to minimal intake notes. Never fabricate schema-compliant method steps, yields, or controls to fill a gap.

## Order of resolution

Resolve in this order. Later gates stay closed until the earlier ones are settled, because a number computed against an unresolved identity is a wrong number wearing a citation.

| Gate | Ask only when missing or contradictory | If unknown |
|---|---|---|
| Method | What is the actual sequence, and where does each listed ingredient enter? What is the endpoint? | Ask for the method first; no method step is written without it |
| Identity and scope | New dish or revision? Which exact existing recipe/event? Is the photo the target plating or an earlier trial? | Keep provisional identity; no canonical overwrite |
| Block structure | Are the blocks in the photo separate components of one dish, or unrelated recipes photographed together? Which block is which component? | Treat as separate provisional components; do not merge into one batch total |
| Amounts | Which quantities are explicit, and which tokens are ambiguous? | Quote the legible fragment, or name the row and position with `[unclear]`, and ask; never estimate a weight from a photo |
| Formula and yield | Actual weighed ingredients and brands/specs? Raw, trimmed, drained, cooked, or purchased weights? Measured finished usable batch mass? Portion mass/count? | Request a weighed test; separate input total from output estimate |
| Reference basis and conversions | Which named ingredient or blend is the 100% basis? | Choose the basis the cook states, never the one that makes the numbers tidy |
| Household volume | Which ingredient, brand and preparation state is the weight for — whole or ground, roasted or raw, drained, and which salt? | Research an ingredient-specific gram-to-volume reference first, after identity and weight are settled; a routine unit conversion is not the cook's job. Ask only when the sources conflict or no reliable match exists |
| Equipment and thermal process | Vessel size, batch load, layer depth, appliance/mode/fan/humidity/pressure, preheat, starting product state? Is temperature oven/bath/oil/product-core? When does timing start, and what endpoint confirms completion? | Do not infer core temperature from appliance setpoint; block affected process |
| Holding and storage | Direct service or cook-chill? Which approved cooling/holding SOP, container depth, covered/uncovered stage, label/use-by rule, thaw/reheat method, service window, discard rule? | Request relevant house SOP once; do not assign shelf life |
| Pickup and plating | Exact grams/count per component, serving vessel/dimensions, assembly order, position, garnish size, service temperature and maximum pickup window? | Use photo for a proposed layout; ask for missing quantities |
| Allergens and substitutions | Compound ingredient label or approved component version? Cross-contact controls? Are substitutions tested, at what ratio, with what method/allergen changes? | Mark unknown labels; default "no approved substitutions" |
| Release | Actual trial yield and defects? Who reproduced it, when, at what scale? Chef approval for this exact version? | R&D status on the built card, never PRODUCTION; editorial review is not release |

Ask safety-critical ambiguity immediately, even if a later gate normally covers it. Do not repeat an unanswered question unchanged: offer "measure next test" or ask for the one source/SOP that resolves several fields. A complete supplied recipe can receive zero follow-up questions and still goes through REVIEW.

## Small relevant rounds

Ask in rounds that apply to this dish, not as one questionnaire. A dry garnish needs no cooling or reheating question; a cooked component needs its endpoint. Group by what the cook can answer in one sitting, and keep each round short.

Do not send an N/A boilerplate questionnaire to fill a schema. A field that does not apply to this recipe is marked as not applicable with a one-line reason on the card, not asked as a question.

## Component cards and assembly

Only once the cook confirms the relationship between blocks do you build more than one card:

- One complete card per component, each pinned to an exact version.
- One dish assembly card that links those exact component versions and carries the per-portion quantities.
- Each component keeps its own reference basis, yield, method, and release status.
- An assembly cannot be released while a critical component is unresolved.

Unrelated blocks stay separate cards. Do not combine them into a single batch total to make the arithmetic close.

## Rewrite vague instructions into testable endpoints

- "Reduce a little" → ask starting mass, final mass or validated volume, vessel and heat conditions; do not invent the target.
- "Season to taste" → ask weighed starting seasoning, permitted adjustment range, reference taste/texture, and final measured addition.
- "Cook until done" → ask process-specific measured endpoint plus visual/texture cue; the cue does not replace required safety controls.
- "One scoop" → ask weighed net portion and tool size; nominal scoop number alone is insufficient.
- "Chill" → ask approved cooling procedure, monitoring points, corrective action and storage rule.
- "Double it" → calculate ingredient multiplier, then ask only about unvalidated capacity, depth, mixing, cooling, or process changes.

## Review gate

This section describes the shape of the record Miseform shows. The rule that governs the gate — when to send it, how to end it, and what the reply does not authorize — is stated once, in the execution contract in [SKILL.md](../SKILL.md).

Once the critical identity, quantities, and method are resolved, send the compact chef-facing record:

- ingredients, grouped by component or source block, with quantities as confirmed,
- method, as confirmed — the cook's own steps, not a reconstruction,
- yield, as confirmed, or explicitly unknown,
- every remaining value listed as explicitly unknown, with no placeholder dressed as an instruction.

Then ask, verbatim: "Is this correct, and should I generate the cards?" And stop.

## No-answer path

When the cook has not answered, Miseform preserves a compact interview ledger and waits. The ledger holds: known facts, the source of each, the uncertainties, and the next at most 3 questions.

On this path Miseform produces no PDF, no Excel workbook, no card, and no draft. The ledger is not a nine-page draft, not a blank-filled schema, not an invented "first-test procedure", and not a card-shaped artifact with confirmation labels standing in for instructions. Preserve the answers already obtained for the next turn.

## Housekeeping conversions

A gram-to-spoon or gram-to-cup conversion is a research task, not a question. Search for an ingredient-specific reference — the exact product and preparation state first, then an authoritative culinary chart, then government food composition data — before the volume is left blank or the cook is asked to convert it. Record the source title, URL, access date, the source's own ratio, the units convention and how the ingredient and state match. Publish the derived measure as approximate, label a generic proxy as a proxy, and ask one targeted question only when the sources conflict or nothing matches.

Research runs after ingredient identity and weight are settled. Start with at most 2 relevant sources per ingredient, reuse a valid already-cited ratio where one exists, and report what stays unresolved rather than searching indefinitely. A source or a proxy authorizes a conversion only; it never authorizes substituting an ingredient that is still unresolved. See the volume research section in [SKILL.md](../SKILL.md) and the arithmetic rules in [schema.md](schema.md).

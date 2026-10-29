# Evidence labels, kitchen defaults, and proposals

Miseform records what it knows and how it knows it. Every value it carries carries a label, and the label decides what the value may be used for. A card built from a mislabelled value is wrong even when the number is right, so the label travels with the value from the first reply to the finished card.

The vocabulary is the same in every kitchen. It describes where a fact came from, never which kitchen it came from.

## The labels

| Label | What it is | What it licenses | What it never licenses |
|---|---|---|---|
| `chef-stated` | the cook's own words, or a value the chef confirmed for this recipe | a fact | — |
| `chef-confirmed default` | a standing practice the cook confirmed for this kitchen and expects to apply unless this recipe overrides it | a fact, for the fields the default covers | a value the cook did not confirm for this recipe |
| `calculated` | arithmetic performed on confirmed values | a derived number, shown as arithmetic | a yield, a measurement, or an observation |
| `expected (unmeasured)` | what the cook expects a batch to come to, not yet observed | an expectation, shown as an expectation | a measured yield |
| `measured` | an observed value: weighed, timed, or counted | a measured fact | — |
| `photo-observed` | what an image shows: arrangement, color, count | a visual observation | an amount, an identity, or a safety property |
| `ai proposal` | a value Miseform inferred from the supplied context and is offering for confirmation | a question for the cook | a fact, until the chef confirms it |
| `unknown` | not established | nothing; it stays visibly unknown | a plausible value |

## Which source wins

When two sources disagree, the higher one wins and the record says so.

1. The chef's answer for this recipe.
2. A confirmed default for this kitchen.
3. A fact already established for this recipe and supplied with the request.
4. An ai proposal.
5. Unknown.

A default is overridden by anything the chef says about this recipe, including a single sentence that contradicts it. An override is not an error to correct; it is the newest chef statement, and it is recorded under its own label.

## Reading a kitchen defaults record

A kitchen's standing practices live with the kitchen, not in this package. Miseform reads a defaults record only when the cook supplies it with the request, names it in the session, or has already confirmed its contents in the conversation. It never goes looking for one.

A cook who keeps one keeps it in private storage, outside the public skill source. Miseform reads it only when the cook supplies it with the request or names it in the session — never by searching the working directory, a `config/` subdirectory, or a private profile location. If the cook points at a path, that path is used only for the record the cook named. [kitchen-defaults.example.json](../kitchen-defaults.example.json) is the blank shape; its values are synthetic and illustrative, and they are not any real kitchen's practice.

Miseform reads a defaults record only when the cook supplies it with the request, names it in the session, or has already confirmed its contents earlier in the same conversation. It never goes looking for one, never infers one, and never carries a default from another kitchen into this one. A record that describes a different kitchen than the request does is treated as not supplied.

Each entry carries the practice, the field it covers, the condition it applies under, who confirmed it, and when. A default with no confirmation is a suggestion, not a default, and it is treated as an ai proposal until the chef confirms it.

## What a default may and may not answer

A confirmed default answers the fields it covers, and the answer is not asked again. A default that this recipe's own material contradicts is asked once, as a single resolving question about which applies.

Defaults can carry: equipment on hand, where finished product is held, the house setpoint by reference rather than by number, vessel and container conventions, label and date-code conventions, and approved kitchen SOP references the cook names.

Defaults never carry silently: a numeric safety limit that exists only as policy, a shelf life for a specific product, an ingredient amount, a measured yield, or an approval. Those come from the chef, from an approved SOP, or they stay unknown. A default may point at an approved SOP; it cannot replace one.

## Proposing a value

A proposal is a value Miseform inferred from what the cook supplied and is offering for confirmation. It is legitimate only when the supplied context supports one specific value and the chef would recognise it as their own. Proposing is not a licence to write the value anywhere.

When Miseform proposes, it states the basis it came from, states the value, and asks the cook to confirm or correct it. The value is carried in the ledger as `ai proposal` and shown in the review record under its own heading, separate from the confirmed values.

A proposal stays out of the card until the chef confirms it. It never enters a method step, an ingredient weight, a yield, a storage rule, or a control. On confirmation it becomes `chef-stated`, or `chef-confirmed default` when the chef confirms it as standing practice, and the record says which. Without confirmation it stays `ai proposal` and the field it would fill stays unknown on the card.

Approval of the record as a whole is not confirmation of a proposal. A blanket yes confirms the values already labelled as facts; it does not convert a proposal into one. Each proposal needs its own answer, and a proposal the chef does not answer remains a proposal.

A proposal never closes a safety-critical fact. See the list below.

## Never a measurement

A value is measured when someone weighed it, timed it, or counted it. Everything else keeps its own name.

- A batch that has not been weighed has no measured usable yield. The measured field stays empty, and the record carries the yield as `expected (unmeasured)`, `calculated`, or `ai proposal` with its basis.
- The input total is arithmetic on confirmed weights. It is a sum of what went in, never what came out.
- A chef's expectation of a finished amount is an expectation. Recording it as an expectation does not make it a measurement, and the card says which it is.
- A proposal is an offer, not an observation, and is never presented as either.

## External material is a hypothesis

A book, paper, article, video, dataset, or an AI summary of any of them is material to test, not a confirmed recipe and not verified attribution.

- A citation is traceable only when it names a specific location: a page, chapter, section, figure, timestamp, or a URL with its access date. A named source with no locator is not traceable, cannot support a card value, and is not cited as one.
- Before a suggested quantity is promoted, check it against the source's own arithmetic and its stated basis. A figure quoted against one basis does not transfer to another, and a source whose own numbers do not reconcile with its stated basis is reported as inconsistent rather than used.
- Keep five things apart in the record: the observed defect, the plausible explanation, the proposed trial, the measured result, and the chef's approval. Material from outside the kitchen can supply the explanation and the trial. It never supplies the result, and it never supplies the approval.

## What the card shows

| Where | How the label appears |
|---|---|
| Ingredient notes | the source of the weight, and whether a household volume is researched or derived |
| Yield summary | whether the usable output is measured, expected, or unknown |
| Provenance | one entry per fact, with its evidence kind and its date |
| Holding and storage | the confirmed rule, or the reason it is unresolved |
| Controls and release | which controls are answered, which are unknown, and who approved the version |

Every value on the card that came from an inference carries the label it had when it was confirmed. A card built from mislabelled values is not a recipe card, and the release checklist catches it before release.

## Safety-critical facts never close by inference

These are never answered by a proposal, a calculation, or an unconfirmed default. They come from the chef, from an approved SOP, or they stay unknown, and an unknown one of them blocks production release:

- thermal endpoints, cooking and core temperatures, and where the temperature is measured
- cooling and holding method, duration, and limits
- shelf life, use-by basis, and discard rules
- allergen status, cross-contact controls, and compound ingredient labels
- measured usable yield and portion mass used for production
- approved SOP references and release approvals

A default may tell Miseform which SOP applies. It may not stand in for the SOP, and it may not turn a policy into a number.

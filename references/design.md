# Editorial recipe-card specification

Default: an original editorial layout inspired by the clarity of contemporary culinary reference books. Reproduce the information architecture shown in the user's references, not their text, photographs, branding, or proprietary illustrations.

## Modern layout (default)

1. Small recipe-type eyebrow, prominent uppercase dish name, and quiet recipe ID/version/status line. Unreleased status must remain visible.
2. A short, useful introduction, typically 40–90 words: target flavor and texture, role in service, and why consequential techniques matter. Do not invent culinary history or scientific claims. Avoid filler when notes do not support an introduction.
3. A compact four-part facts strip: **TIME** (active, inactive, elapsed), **DIFFICULTY** (level plus demanding skill), **YIELD / PORTION** (measured mass/count and portion size), **STORAGE** (confirmed rule/SOP or conspicuous pending status). Unknown facts remain explicit. Equipment follows in a concise line.
4. Ingredient table with **INGREDIENT | WEIGHT | VOLUME | SCALING %**. Group rows under component headings such as “For the sauce.” Put ingredient preparation/brand details below names when needed. Align numerical columns and use consistent units. Label each group's percentage reference nearby. Display measured finished yield separately from input total. A researched volume shows its approximate marker and its units convention in the cell (for example `≈ 11.3 tbsp (US)`), and the row keeps its source pointer so the number is never read as a measured spoonful. An unresolved volume is an em dash, never a guessed conversion.
5. Separate **GENERAL DIRECTIONS** grouped by meaningful stages: PREPARE, MIX, COOK, COOL, FINISH, PLATE, or recipe-specific equivalents. Use continuous numbered steps across stages. Every ingredient must map to steps. Each step states action, consequential equipment/settings, time start condition, endpoint, and relevant control.
6. Short accent-colored tips beside their related stage, clearly distinguished from mandatory steps. Do not hide safety controls in decorative notes.
7. Compact operational notes for service, holding, storage, allergens, substitutions, controls, test/release, and provenance. Long logs may be companion pages linked by exact recipe/version. Critical execution details stay on the card.

## Visual language

Use warm white paper, near-black body text, restrained clay accents (#A8492D) and generous whitespace. Organize by typographic hierarchy and fine rules rather than boxed panels. Serif titles/body provide an editorial feel; compact sans-serif labels and metadata aid scanning. Prefer common local font stacks; no network-loaded fonts required. Aim for readable 16 px screen body text and roughly 10.5–11 pt or larger in print. Do not shrink text to force a one-page recipe.

On wide screens, balance introduction and facts; directions may use up to three reading columns when step order remains obvious. On phones, collapse to one column with the same DOM/reading order. Keep table headings visible, avoid clipped quantities, and allow horizontal table scrolling where necessary. Print on Letter and A4, preserving stage headings with their first step and avoiding split rows. Long cards may span pages. Use real headings, text labels, table header cells, and ordered lists; color is not the sole status cue.

Photo is optional. Use a restrained plating image with caption and target/trial status. Never let photography displace measured plating instructions. Do not imply a placeholder or generated image depicts a tested dish.

## Classic layout (optional)

When requested, use a five-column grid: **INGREDIENT | WEIGHT | VOLUME | SCALING % | PROCEDURE**. Group ingredient rows alongside associated numbered procedures using fine horizontal separators. Preserve complete method text and row-group associations; on narrow screens stack ingredient group then its procedure. Keep the same facts, percentage basis, control points, and release semantics. Modern editorial layout remains the default.

## Reading quality gate

A cook should locate yield, scale basis, starting setup, current stage, ingredient amount, endpoint, allergen warning, and storage rule quickly. Check narrow screens and print preview. No clipped values, orphaned stage headings, microscopic footnotes, decorative icons without labels, or visually buried blockers. Preserve natural kitchen language in generated cards regardless of the assistant's chat style.


## Miseform editorial direction — release 3

The page should feel like a modern cookbook, not an admin dashboard or compliance report. Use an expressive serif title, concise deck, quiet sans-serif labels, and broad whitespace. On wide screens, an ingredient sidebar can sit alongside the method; keep reading order intact on narrow screens and print. Show the four facts without a heavy enclosing box. Number steps visibly without giant decorative counters. Use one warm clay accent sparingly.

Keep operational essentials close to cooking: quantity, temperature location, timing, endpoint, allergens and storage. R&D status and missing storage are plainly visible near the top, but a concise line is preferable to repeating large colored warnings. Put source/version/filing logs after the recipe in quieter supporting sections; never hide critical information inside a collapsed control or low-contrast footnote. Preserve facts when shortening text. Optional tips should earn their space.

Excel follows the same hierarchy, adapted to cells: restrained fills, readable typography, grouped numeric tables and obvious editable inputs. PDF is the preferred printed edition. All variants must agree on content and status. No decorative food photography or invented narrative is needed for elegance.

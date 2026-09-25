# Marketing OS Design Language

Date: 2026-06-21

This document captures the UI language emerging across Marketing OS after the Dashboard, Gallery, Products, navigation, review panels, and icon work. Treat it as the working product design baseline for future polish.

## Product Feel

Marketing OS should feel like a quiet local operator console: practical, warm, direct, and built for repeated use. It is not a marketing landing page and should not feel decorative for its own sake.

The app serves MattMadeMe planning, review, and creative operations. The UI should help an operator scan what matters, make a decision, and keep moving without losing human review control.

## Reference Screens

- Dashboard: `docs/design/screenshots/dashboard-2026-06-21.png`
- Gallery: `docs/design/screenshots/gallery-2026-06-21.png`
- Products: `docs/design/screenshots/products-2026-06-21.png`
- Current Planning wizard to improve: `docs/design/screenshots/planning-wizard-2026-06-21.png`

## Layout Principles

- Use the left navigation as the persistent product anchor. The main content should carry the workflow.
- Start pages with a consistent `.topline`: eyebrow, H2, short supporting sentence, and right-aligned actions when needed.
- For sibling inventory pages, use the same sequence:
  - page title block
  - inventory summary band
  - pagination/filter or sort strip
  - content grid/list
- Prefer full-width working surfaces and restrained sections over nested cards.
- Use cards for individual objects: assets, products, planned posts, reviewable items, stat tiles.
- Avoid cards inside cards.
- Keep radii at 8px or less, matching the current CSS.
- Use borders and spacing before shadows. Shadows should be subtle and reserved for actionable cards, hero task surfaces, drawers, and modals.

## Color

The current palette is warm, local, and utility-focused:

- Canvas: warm cream (`#fff8e8`, `#fff7df`)
- Panels and fields: white or warm off-white (`#ffffff`, `#fffdf7`, `#fff8e6`)
- Ink: near-black (`#1f2328`)
- Muted text: gray green (`#687076`)
- Navigation: deep teal gradient (`#133f46`, `#0f6570`)
- Primary action/accent: teal (`#0c7784`, `#084f58`)
- Supporting accent: gold (`#f0a61f`)
- Status colors:
  - blue for ready/info pills
  - green/teal for complete/good
  - rose/coral for blocked/warn

Avoid one-note palette drift. New screens should not become all teal, all cream, or all gradient.

## Typography

- System UI stack only for now: `-apple-system`, BlinkMacSystemFont, `"Segoe UI"`, sans-serif.
- H2 page titles are large and confident, but only for page headers and hero surfaces.
- Interior headings stay compact: 16-18px for `h3` inside panels/cards.
- Body copy sits around 15px with comfortable line-height.
- Eyebrows are uppercase, bold, and small; use them to orient, not decorate.
- Avoid negative letter spacing.

## Navigation

- The sidebar is compact and persistent.
- Brand lockup stays at the top with the MattMadeMe logo and the current product name.
- The former sidebar promo card was removed to reclaim vertical space.
- Active navigation uses a quiet translucent background and gold dot.
- More tools stay collapsed unless the active page is inside that group.

## Page Headers

Use this page shape for operational surfaces:

```text
EYEBROW
Page Title
One short line explaining what this page is for.

[optional right-side actions]
```

Inventory pages should add a second summary area below the title:

```text
INVENTORY EYEBROW
1-36 of 439 assets
Optional filtering/exclusion explanation.
```

Then use a thin bordered control strip for pagination and filters/sort.

## Controls

- Use real controls, not text pretending to be controls.
- Select filters/sorts apply on change via `data-auto-submit` when the choice is low-risk and reversible.
- Only include reset controls when there is a meaningful cleared state.
  - Gallery tag filter has a reset because it can return to All tags.
  - Products sort has no reset because Name is just another selectable sort.
- Icon-only buttons should be square, 38px by default, and carry accessible labels/titles.
- Buttons use teal for primary actions, white for secondary, and soft orange/red for destructive or hiding actions.

## Icons

Use Lucide as the single icon layer.

- Local bundle: `marketing_os/static/vendor/lucide.min.js`
- Markup: `<i data-lucide="icon-name" aria-hidden="true"></i>`
- Initialization lives in `base.html`.
- Avoid inline SVGs and one-off handcrafted glyphs.
- Use familiar symbols instead of text when the action is common: close, delete, hide/show, add, edit, rewrite, zoom, filter reset.

## Pills And Status

- Pills are small scan aids, not buttons unless explicitly interactive.
- Use consistent tone classes:
  - `.ready` for review counts, selected/ready states, info emphasis.
  - `.blocked` for hidden, missing, or blocked states.
  - `.complete` for complete/local/good states.
  - `.gold` for warm emphasis when needed.
- Keep pill text short.

## Images And Visual Assets

- Product and asset pages should show real product imagery as primary content.
- Gallery cards use full-width image previews with object-fit cover.
- Product image cards are denser, small, and optimized for comparison.
- Missing or remote states should be explicit but quiet.
- Do not use fake artwork, CSS art, or decorative blobs in operational screens.

## Review Surfaces

- Review panels should prioritize readable rows and avoid overlapping line boxes.
- Long review lists should scroll within the review section instead of taking over the whole product page.
- Keep customer language visible and useful, but not at the expense of product/image scanning.

## Current Wizard Gap

The current Planning wizard is functional but less refined than the newer surfaces:

- The wizard progress is just numbered dots, so the steps do not communicate workflow value.
- Step 1 is a tall form inside a large panel, with weak hierarchy between schedule, destination, and goal.
- Destination cards use letter/glyph badges instead of the newer Lucide icon language.
- The form does not show a persistent summary of choices as the operator moves through the 3-step process.
- The wizard does not echo the newer inventory/control strip language, review queue density, or object-card polish.
- It feels more like a scaffolded form than a guided command workflow.

## Planning Wizard Direction

Future wizard concepts should keep the same 3-step workflow:

1. Destination, date, time, and goal.
2. Product, reference images, audience, and occasion.
3. Offer/timing, notes, and queue action.

But the presentation should borrow from the refined system:

- A clear page header and short summary band.
- A stepper with labels, not just numbers.
- A working area plus a persistent “post brief” summary.
- Dense, polished selector cards using Lucide icons and existing pill/status language.
- Reference images shown as useful product objects, not raw checkbox tiles.
- Actions aligned consistently at the bottom/right of the working surface.

The wizard should feel like “build a post brief” rather than “fill out a form.”

## Planning Wizard Concepts

Three generated directions were rendered from this language:

1. Summary Rail: `docs/design/concepts/planning-wizard-summary-rail-2026-06-21.png`
   - Strongest for a guided operator workflow with a persistent brief summary.
   - Best fit if the wizard should feel focused and decision-oriented.

2. Command Strip: `docs/design/concepts/planning-wizard-command-strip-2026-06-21.png`
   - Strongest for density and speed.
   - Best fit if the wizard should behave more like an operational console and less like a form.

3. Post Brief Canvas: `docs/design/concepts/planning-wizard-post-brief-canvas-2026-06-21.png`
   - Strongest for progressive disclosure and workflow storytelling.
   - Best fit if the wizard should make “what will be queued” very explicit before submission.

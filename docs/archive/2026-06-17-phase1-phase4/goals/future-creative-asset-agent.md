# Future Creative Asset Agent

Status: future / not part of Phase 2

## Objective

Build a creative asset skill or agent that turns MattMadeMe product photos into platform-ready marketing graphics for the marketing planner.

## Context

MattMadeMe already has product photos used on Etsy, often on plain backgrounds. These are useful source assets, but social platforms often need native-looking visual formats such as Reels covers, square product cards, carousel slides, story graphics, and launch announcement visuals.

The marketing planner should be able to request a graphic asset, but the generation, editing, QA, and export workflow should be handled by a separate creative asset capability.

## Required Future Capabilities

- Ingest product photos from a local asset inventory.
- Preserve product accuracy, including shape, color, printed details, and proportions.
- Generate platform-ready graphics for:
  - Instagram feed
  - Instagram Reels cover
  - Instagram carousel
  - Facebook image post
  - Facebook cover or announcement graphic
  - Etsy promo/supporting image
  - website/blog hero image
- Support reusable graphic templates.
- Produce predictable output filenames.
- Record source image, prompt/template, output path, and review notes.
- Flag outputs that need human review.

## Guardrails

- Do not materially alter the duck design.
- Do not create misleading product details.
- Do not imply licensed characters or protected brands.
- Do not obscure the product.
- Do not use generated text inside images unless it can be verified.
- Prefer clean, inspectable product presentation over overly stylized scenes.

## Possible Directory Structure

```text
assets/
├── products/
│   └── product-slug/
│       ├── source/
│       ├── edited/
│       └── generated/
├── brand/
└── templates/

docs/templates/graphics/
outputs/graphics/
```

## Definition Of Done For Future Implementation

- A product photo can be selected from the asset inventory.
- The agent can generate at least three platform-ready graphic formats.
- Outputs are saved with predictable filenames.
- A review record is created for each generated asset.
- The marketing planner can reference generated asset paths in a weekly plan.
- Product accuracy checks are documented and manually verifiable.


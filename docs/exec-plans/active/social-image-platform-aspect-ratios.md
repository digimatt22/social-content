# Social-image per-platform aspect ratios

## Status
- Status: ready for review
- Owner: Matthew Wood / Codex
- Branch: `codex/social-image-platform-aspect-ratios`
- PR: TBD
- Last updated: 2026-09-25

## Summary
- Map Platforms → Magnific aspect ratios for Art Studio / Products social-image generation.
- Enqueue + worker pass stored `aspect_ratio` (default `ig_feed` / `1:1`).
- UI: platform chips on Products and Art Studio queue forms.
- Out of scope: Sheldon deploy, Pinterest live publish, secrets.

## Decisions
- Canonical map in `marketing_os/services/art_studio.py`.
- Pinterest `2:3` is generator frame only; Brand Lab owns pin posting.
- Multi-select platforms; one creative job per platform × option.

## Validation
- `python -m unittest tests.test_magnific_api_social_image -v` — pass
- `python -m unittest tests.test_phase3.Phase3LocalWebConsoleTests.test_products_queue_social_images_from_default_references -v` — pass

## Closeout
- No deploy in this PR.

# Social Images On Products And Video Studio

## Status
- Status: completed
- Owner: Codex
- Branch: main
- PR: none (landed on `main` without a dedicated PR; docs closeout 2026-09-25)
- Last updated: 2026-09-25

## Summary
- Move the Social Images generation entry point into Products so product references and generation live together.
- Rename the remaining Art Studio surface to Video Studio.
- Out of scope: changing the Magnific generation/export contract or approving generated assets automatically.

## Work State
- Planned: Product page controls, video studio naming, docs, focused validation.
- In progress: None.
- Blocked: None.
- Needs human validation: None for closeout; product/Video Studio UX can still be re-checked in a live browser anytime.
- Ready for review: None (implementation already on `main`).
- Completed: Product-first Social Images controls, Video Studio naming, focused route/template tests, py_compile, local smoke checks, and operator-guide updates present on `main` as of 2026-09-25.

## Decisions
- Default product references are the source of truth for Social Images generation.
- Queue one social image job per default reference for the selected product.
- Preserve existing `/art-studio` route names internally to keep existing automation contracts stable while changing user-facing labels to Video Studio.

## Implementation
- Update Products to show a simple Social Images control per product.
- Keep generated social image jobs review-gated.
- Remove the Social Images tab from the user-facing Art Studio page and make it Video Studio.

## Validation
- `python -m unittest tests.test_phase3.Phase3LocalWebConsoleTests.test_products_queue_social_images_from_default_references tests.test_phase3.Phase3LocalWebConsoleTests.test_video_studio_page_renders_video_workflow tests.test_phase3.Phase3LocalWebConsoleTests.test_art_studio_generation_jobs_queue_and_attach_results tests.test_phase3.Phase3LocalWebConsoleTests.test_art_studio_video_product_picker_includes_products_beyond_display_queue tests.test_phase3.Phase3LocalWebConsoleTests.test_art_studio_video_product_picker_sorts_products_by_name` passed on 2026-07-02.
- `python -m unittest tests.test_phase3.Phase3LocalWebConsoleTests.test_social_image_prompt_uses_product_theme_scene_context tests.test_phase3.Phase3LocalWebConsoleTests.test_products_queue_social_images_from_default_references tests.test_phase3.Phase3LocalWebConsoleTests.test_art_studio_generation_jobs_queue_and_attach_results` passed on 2026-07-02 after adding product-theme scene directions.
- `python -m py_compile marketing_os/web_app.py` passed on 2026-07-02.
- `python -m py_compile marketing_os/services/art_studio.py marketing_os/web_app.py` passed on 2026-07-02.
- `curl http://127.0.0.1:3001/products` showed `Generate social images` and product Social Images controls on 2026-07-02.
- `python -m unittest tests.test_phase3.Phase3LocalWebConsoleTests.test_web_app_renders_operator_workflow_and_persists_forms tests.test_phase3.Phase3LocalWebConsoleTests.test_products_queue_social_images_from_default_references` passed on 2026-07-02 after wiring async reference saves to the Social Images button state.
- `curl http://127.0.0.1:3001/products` showed `data-social-reference-count`, `data-social-generate-button`, and `syncSocialGenerationState` after server restart on 2026-07-02.
- `curl http://127.0.0.1:3001/art-studio` showed `Video Studio` and `Create product video` on 2026-07-02.
- `curl -I 'http://127.0.0.1:3001/art-studio?tab=social-images'` returned `302` to `/products` on 2026-07-02.
- SQLite verification on 2026-07-02 found 46 queued `art_studio_social_image` jobs. All queued jobs now include `Scene direction:` and the generic-office guardrail. Scene directions were spot-checked by product group, including biker/motorcycle, bowling alley, woodland chipmunk costume, patriotic July 4th, package delivery, lodge hall, firehouse, tropical/beach, Georgia Southern/peach, New York city, Pennsylvania/Keystone, cruise-cabin room steward, tattoo studio, and Texas western scenes.
- `python -m unittest discover -s tests` still fails 2 pre-existing video/content automation expectations: missing `video_plan` text in `video_handoff`, and missing `$video-content-planner` in the weekly Codex prompt.
- `scripts/check-doc-links.sh` still fails on the pre-existing `AGENTS.md` link to `docs/HARNESS_IMPROVEMENT_BACKLOG.md`.
- `scripts/check-current-state.sh` previously failed when no `origin` remote was configured; `origin` is now `https://github.com/digimatt22/social-content.git` (noted at closeout 2026-09-25).

## Human Validation
- Owner: Matthew
- Exact steps: Open Products, choose a product with default references, click Generate social images, then open Video Studio.
- Expected evidence: Product card shows queued Social Worthy jobs; Video Studio no longer presents a Social Images tab.
- Evidence location: This plan or PR notes.
- Blocks merge: No, if automated checks and local smoke pass.

## Documentation
- Local web console guide documents Products Social Images and Video Studio.
- This plan moved to `docs/exec-plans/completed/` on 2026-09-25.

## Closeout
- Final status: completed.
- Merge or abandonment notes: Implementation and operator docs are already on `main` (Products Social Images controls, Video Studio labeling, related tests/services). Plan stayed `ready for review` with stale no-`origin` blockers; closed as completed during the 2026-09-25 docs scrub once remote `https://github.com/digimatt22/social-content.git` and default PR base `main` were recorded.
- Follow-up work items: None required inside this plan. Optional live browser re-check of the product Social Images flow remains available but does not block closeout.

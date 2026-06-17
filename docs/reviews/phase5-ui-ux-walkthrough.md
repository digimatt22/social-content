# Phase 5 UI/UX Walkthrough

Date: 2026-06-17

## Scope

This walkthrough checked the Phase 5 operator surfaces after the first integration, planning, creative-import, content-production, and learning-loop slices.

Screens checked:

- Today dashboard
- Task detail
- Assets
- Creative Assets
- Planning
- Metrics Due
- Metric History
- Insights
- Data Health
- Settings
- JSON endpoints for Insights, Data Health, and Planned Content

Live route smoke was run against the local Flask server at `http://127.0.0.1:8000`.

The local runtime database did not contain planned candidates during the live smoke, so candidate review controls were verified through the automated web-flow test that creates planned content and renders the Planning review state.

## Result

The current Python/Flask UI is usable enough to continue Phase 5 without a frontend rewrite.

The web app now supports the intended division of labor:

- Marketing OS captures planning intent, review decisions, posting state, metrics, and learning summaries.
- Codex/content-production jobs enrich planned items asynchronously.
- Generated copy and generated assets remain behind human review.
- Metrics and outcome notes can feed the next planning/copywriting pass.

## Friction Found And Fixed

### Generated Candidate Review Was Too Thin

Problem:

Planning generated candidates, but the page only showed raw candidate payloads and a copy button. There was no friendly review action, no revision note capture, and no in-app way to attach generated copy to a task.

Why it would cause non-use:

The operator would need to manually copy JSON-ish text, remember which task it belonged to, and rely on external notes for approval state.

Fix:

- Added readable candidate display text for Facebook post candidates.
- Added candidate review controls: `needs_review`, `approved`, `rejected`, and `rewrite_requested`.
- Added revision note capture from the Planning page.
- Added an API review endpoint for future frontend/Codex use.
- Added a Planning-page task selector that attaches a Facebook candidate to a task.

### Learning Loop Was Invisible From Daily Operation

Problem:

Metrics existed, but there was no operator-facing place to see what worked, what failed, or whether the system needed more data.

Why it would cause non-use:

If every new post starts from static planning assumptions, the system feels like a content generator instead of an improving operating system.

Fix:

- Added an Insights page.
- Added `/api/insights`.
- Added a Data Health row for the learning loop.
- Added outcome tags to metric entry and metric history.
- Added learning-summary export data.
- Added performance context to generated content briefs.

## Route Smoke Evidence

All checked routes returned HTTP 200:

- `/`
- `/tasks/1`
- `/assets`
- `/creative-assets`
- `/data-health`
- `/settings`
- `/planning`
- `/metrics-due`
- `/insights`
- `/api/insights`
- `/api/data-health`
- `/api/planned-content`

## Remaining UX Risks

### Planning Still Does Not Create Posting Tasks Automatically

Planned content can generate copy candidates, and candidates can be attached to existing tasks, but the app does not yet create a posting task directly from a planned item.

Recommendation:

Add a "Create posting task" action from Planning that carries destination, product focus, generated copy, source assets, and metric follow-up into a task.

### Candidate Review Is Functional But Not Yet Comfortable

The review flow now works, but it is still compact. Longer copy, multiple candidates, and image-prompt candidates would benefit from a dedicated review page.

Recommendation:

Add a candidate detail/review view once copy and image generation volume increases.

### Metrics Are Still Manual

Manual metric entry is acceptable for Phase 5, but it depends on discipline.

Recommendation:

Keep manual entry, but add future imports for Facebook/Instagram metrics, Etsy listing outcomes, website analytics, and email/campaign signals.

### Creative Asset Import Depends On External File Hygiene

Magnific/MCP output import works, but it depends on the operator saving files into predictable local/external paths.

Recommendation:

Once the Magnific MCP server is configured in Codex Desktop, add a direct generated-output registration path that writes the provider run note and output metadata without manual retyping.

### Mobile Layout Needs Browser-Level QA

The HTML uses responsive grids and route smoke passed, but this pass did not include browser screenshots because browser control was not available in the session.

Recommendation:

Run a visual mobile/desktop screenshot pass before marking Phase 5 complete.

## Doneness Impact

This walkthrough moved Phase 5 closer to done by addressing the most immediate review-flow and learning-loop friction.

Still not complete:

- automatic task creation from planned intent
- browser screenshot-based mobile/desktop QA
- final Phase 5 completion audit
- stronger generated image quality proof from the Freepik/Magnific path
- at least one fully reviewed, approved, and task-attached real Facebook post in the live workflow

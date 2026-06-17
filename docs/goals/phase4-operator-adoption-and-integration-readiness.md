# Phase 4 Operator Adoption And Integration Readiness

Build Phase 4 of the MattMadeMe Marketing Operating System.

## Source Inputs

Phase 4 should be guided by:

- `docs/goals/phase3-local-web-operator-console.md`
- `docs/reviews/phase3-web-ui-ux-review.md`
- `docs/reviews/phase3-system-premortem.md`
- `docs/goals/future-creative-asset-agent.md`
- `docs/architecture/phase3-architecture.md`
- `docs/architecture/etsy-read-only-integration-plan.md`
- `docs/architecture/mattmademe-website-integration-plan.md`
- current implementation in `marketing_os/`

Current execution status is tracked in `docs/reviews/phase4-execution-audit.md`.

Use the Phase 3 UI/UX review as the source of truth for operator workflow problems. Use the Phase 3 system premortem as the source of truth for non-use risks, stack decisions, and integration readiness.

## Problem Statement

Phase 3 successfully moved the Marketing OS from Terminal and Markdown into a local web console with SQLite persistence. It can generate plans, store tasks, show platform playbooks, track assets, and record metrics.

The remaining risk is not that the system cannot generate enough work. The risk is that it generates and stores work in a way that still feels like another system to maintain.

For the day-to-day social operator, the app still exposes too much planner/admin context before it answers the simple question: "What should I do next?" For Matt, the app still depends on manual upkeep for product truth, asset readiness, published URLs, and metrics. If those friction points remain, the app may technically work but stop being used.

Phase 4 should make the system feel easier than working from memory, platform apps, folders, and ad hoc notes.

## Objective

Turn the Phase 3 web console into an operator-first daily workflow while preparing the codebase for future integrations and richer UI without requiring a major rewrite.

Phase 4 should:

- make Today and Task pages feel guided rather than database-driven
- reduce the amount of manual interpretation required from the social operator
- make assets visual, real, and usable from tasks
- make metrics a follow-up workflow instead of an intimidating form
- add the data fields and service boundaries needed for future API/import connections
- execute the first creative asset/image-generation workflow behind a human-review boundary
- keep the current Python/Flask/SQLAlchemy/SQLite stack for now
- avoid coupling business logic to Flask routes or Jinja templates in ways that would block a future Next.js or richer frontend layer

## Product Vision

Phase 4 should feel like a calm daily assistant:

- The operator opens Today and sees one recommended next action.
- A task opens into a short guided flow: prepare, post, finish, metrics later.
- Captions, CTAs, hashtags, and URLs can be copied with buttons.
- Admin/planner pages are still available but do not distract from daily posting.
- Assets show thumbnails and readiness, not just source paths.
- Metrics due work appears when it is time to check results.
- Matt can see what data is stale, missing, imported, or waiting for review.
- Generated graphics are treated as reviewed assets, not automatic planner assumptions.

## Technical Direction

### Keep The Current Stack

Phase 4 should continue using:

- Python
- Flask
- SQLAlchemy
- SQLite
- Jinja templates
- small, purposeful client-side JavaScript where it removes friction

Do not rewrite the app in Next.js during Phase 4.

### Avoid A Future Rewrite Trap

Although Phase 4 should keep Flask, it should prepare for the possibility of a richer frontend later.

Implementation should:

- move workflow decisions out of Flask route functions into service modules
- keep planner, asset, metric, and integration logic independent of Jinja templates
- define small view models or DTO-style dictionaries for pages that could later become JSON responses
- add internal service/repository boundaries before adding integrations
- avoid putting business rules directly in templates
- keep frontend JavaScript small and local to interaction behavior
- prefer progressive enhancement over a frontend framework
- add external IDs, sync state, review state, and staleness fields in the database before real API connections depend on them
- use a lightweight migration pattern if schema changes cannot be handled safely by fresh initialization

If a future Next.js frontend is needed, it should be able to consume stable Python service/API boundaries rather than force a rewrite of the planning engine.

## Required Capabilities

### 1. Operator-First Today Page

The Today page should center on one safe next action.

It should:

- default to the social operator view unless another role is selected
- show the most important open task first
- use an action-oriented title
- provide a clear `Start task` action
- show a small count of remaining attention items
- avoid showing full plan status counts above the daily workflow
- avoid repeating today's tasks in the weekly section
- show a compact preview of upcoming work below the primary task
- provide helpful empty, blocked, and all-done states

The operator should not need to understand plan modes, audience/persona labels, internal status counts, or admin concepts to begin.

### 2. Guided Task Workflow

Task detail should become a step-by-step posting flow.

Required task sections:

1. `Prepare`
   - product name
   - asset thumbnail or readiness warning
   - caption/body with copy button
   - CTA with copy button
   - hashtags with copy button when relevant
2. `Post`
   - platform explanation
   - beginner posting steps
   - preview checklist
   - common mistake to avoid
3. `Finish`
   - primary status actions such as `Mark posted`, `Scheduled`, `Needs help`, and `Skip`
   - notes field
   - advanced status dropdown only if needed
4. `Metrics later`
   - collapsed by default unless the task is posted, metrics needed, or overdue
   - platform-specific fields
   - explanation of when and where to check results

Task pages should replace internal labels with plain action language wherever the operator sees them first.

### 3. Role-Aware Navigation

The app should separate daily operator work from admin/planner work.

Operator-facing navigation should emphasize:

- Today
- This Week
- Metrics Due
- Completed or History
- Posting Guides

Admin/planner navigation may include:

- Plans
- Assets
- Templates
- Settings
- Data Health

It is acceptable to keep these in one app shell, but their visual priority should make it clear which surfaces are daily work and which are setup/admin areas.

### 4. Weekly Agenda And Responsive Calendar

Replace the current table-heavy weekly/calendar experience for normal use.

Phase 4 should:

- provide a `This Week` agenda grouped by day
- filter by role, platform, and status
- show mobile-friendly day cards
- keep dense tables only for admin/debug contexts
- prevent mobile horizontal overflow

### 5. Visual Asset Inventory

Assets should become real operator-usable records.

Phase 4 should:

- support importing or scanning local product asset folders
- generate or register preview thumbnails where possible
- detect missing or broken asset paths
- show asset thumbnails on asset lists and task pages
- track file existence and last checked date
- distinguish source photo, edited photo, generated graphic, template output, and external listing image
- show readiness states in plain language
- connect assets to tasks that use them

Placeholder asset records should no longer be treated as ready without an explicit file check or review state.

### 6. Metrics Due Workflow

Metrics should be a follow-up workflow, not a form shown too early.

Phase 4 should:

- add metric due dates or metric collection states
- create a `Metrics Due` view
- show only platform-relevant fields
- track missing post URLs separately from missing metric numbers
- make it clear when metrics are not due yet
- move completed metric records into history

### 7. Integration-Ready Data Model

Before adding real external APIs, Phase 4 should prepare records for imported data.

Add or plan fields for:

- external source system
- external product/listing/post/campaign IDs
- canonical external URL
- last synced timestamp
- staleness state
- sync error state or note
- manual override state
- published URL
- platform post ID
- metric due date
- metric collection status
- asset file existence
- asset checksum or modified time if practical
- generated asset review state
- human approval fields

The implementation does not need every future integration, but it should stop assuming all records are purely local and manually maintained.

### 8. First Import Or Read-Only Connection

Phase 4 should implement at least one low-risk data connection or import path.

Preferred first choices:

1. Local photo folder import/scanning.
2. MattMadeMe.com product/blog import if API access is practical.
3. Etsy listing/product import if API access is practical.
4. CSV/manual export import for Etsy listings if API access is not practical yet.

The first connection should:

- be read-only or import-only
- store external IDs/URLs where available
- expose sync status in the app
- fail gracefully with plain-language error states
- not block daily operator use if unavailable

Automated publishing remains out of scope.

### 9. Creative Asset Generation With Review Boundary

Phase 4 should execute the plan in `docs/goals/future-creative-asset-agent.md` as a bounded first pass.

The creative asset workflow should:

- select a real product photo from the asset inventory
- generate at least three platform-ready formats:
  - Instagram feed square product card
  - Instagram Reel cover
  - Instagram carousel slide
- save outputs with predictable filenames
- record source image, prompt/template, output path, and review notes
- mark all generated outputs as needing human review by default
- preserve product accuracy as a documented review requirement
- avoid using generated assets in normal tasks until approved
- allow approved generated outputs to become asset records

This should be treated as an asset service or skill boundary, not hidden inside normal plan generation.

### 10. Data Health And Backup

Phase 4 should make local-first operation safer.

The app should:

- show data health status for products, assets, templates, metrics, and imports
- identify stale, missing, broken, or never-reviewed records
- provide a documented backup/export path for SQLite
- make it clear where local data lives
- avoid making the operator responsible for invisible data maintenance

## Out Of Scope

Do not implement in Phase 4:

- a full Next.js rewrite
- internet-facing hosting
- public authentication
- automated publishing to Instagram, Facebook, Etsy, or the website
- paid ads management
- full analytics automation across all platforms
- replacing the Phase 2 planner
- relying on generated images without human review

Phase 4 may add import/sync foundations, but normal posting should remain manual.

## Architecture Constraints

Phase 4 should leave the codebase easier to evolve.

Required architecture constraints:

- Route functions should orchestrate request/response work, not contain core workflow decisions.
- Services should own task prioritization, status transitions, metric due logic, asset scanning, and import behavior.
- Templates should render view models and avoid business logic beyond simple conditionals.
- Database access should be centralized enough that future API endpoints can reuse it.
- Any new JavaScript should be progressive and should not become the only source of truth.
- Generated asset metadata should be persisted and inspectable.
- External connections should be adapters, not direct calls scattered through routes.
- Tests should cover service behavior separately from rendered HTML where practical.

## Definition Of Done

Phase 4 is complete when:

1. Today opens to a role-aware operator view with one recommended next task.
2. Today no longer repeats the same due-today tasks in multiple sections.
3. The operator can start a task without seeing admin/planner concepts first.
4. Task detail is organized into `Prepare`, `Post`, `Finish`, and `Metrics later`.
5. Caption/body, CTA, hashtags, and relevant URLs have copy-to-clipboard controls.
6. Metrics are collapsed or separated until they are due.
7. A `Metrics Due` workflow exists and persists metric follow-up state.
8. This Week is a mobile-friendly agenda grouped by day.
9. Calendar or weekly views no longer overflow on mobile.
10. Admin/planner pages are visually or navigationally separated from daily operator work.
11. Assets show thumbnails or clear missing-preview states.
12. Asset records track file existence and readiness in a way the operator can understand.
13. At least one import/sync path exists, preferably local photo folder import or Etsy listing import.
14. Imported/synced records show source, last sync, and error/staleness state.
15. Products, tasks, assets, or metrics can store external IDs/URLs where relevant.
16. A data health view or panel identifies stale, missing, broken, or unreviewed records.
17. A backup/export path for the SQLite database is documented and tested manually.
18. The first creative asset generation workflow can produce three reviewed-output candidates from a real product photo.
19. Generated assets are saved predictably and marked `needs review` by default.
20. Approved generated assets can be referenced by future tasks.
21. Core workflow decisions are moved into services or adapters rather than being embedded in route/template logic.
22. Existing Phase 1, Phase 2, and Phase 3 tests still pass or have documented replacements.
23. New tests cover task prioritization, guided status actions, metric due logic, asset scanning/import, and generated asset review metadata.
24. Documentation explains the new operator workflow, admin/data health workflow, import/sync behavior, backup path, and creative asset review loop.

## Success Criteria

Phase 4 should be considered successful when:

1. A novice social operator can open the app and identify the next action within 10 seconds.
2. A novice social operator can complete one Instagram or Facebook task without opening Calendar, Plans, Templates, docs, or source files.
3. The operator can copy caption, CTA, hashtags, and post URL fields without manually selecting text.
4. The operator can mark a task posted using a clear primary action without understanding every status option.
5. The operator understands that metrics are a later follow-up, not part of initial posting.
6. The operator does not see source file paths, JSON/template language, or internal persona labels during normal posting.
7. Matt can tell which products, assets, metrics, and imports need attention from one data health surface.
8. At least one manual upkeep burden is reduced through import or sync.
9. Real product assets are visible in the app, and missing/broken asset records are obvious.
10. Generated creative assets are reviewable, traceable to their source image/prompt/template, and not silently treated as approved.
11. The app remains runnable with the existing local Python setup.
12. The codebase has clearer service/adapters boundaries than Phase 3, making a future Next.js frontend possible without replacing the planner core.

## Acceptance Criteria

### AC1 - Operator Today Flow

- The default Today screen shows one recommended open task for the selected role.
- The first viewport includes a clear `Start task` action.
- Completed, skipped, and future tasks do not crowd the primary action.
- Today's tasks are not duplicated elsewhere on the page.

### AC2 - Guided Task Flow

- A task page presents `Prepare`, `Post`, `Finish`, and `Metrics later`.
- Posting steps and checklist are visible before long admin/status forms.
- Caption, CTA, hashtags, and URLs have working copy controls.
- Primary finish actions update task status and persist notes.

### AC3 - Metrics Due

- Metrics have due state or due dates.
- A Metrics Due page shows only tasks needing follow-up.
- Metrics forms are platform-aware.
- A task that is not posted does not present metrics as immediate required work.

### AC4 - Assets

- Asset records can be backed by real local files.
- Asset lists and task pages show thumbnails or missing-preview states.
- Broken asset paths are detected and surfaced.
- Asset readiness is readable by a non-technical operator.

### AC5 - Import/Sync Foundation

- At least one read-only/import-only connection exists.
- Imported records store source and sync metadata.
- Sync errors are visible but do not break daily task use.
- External IDs or URLs can be persisted where available.

### AC6 - Creative Asset Review

- A real source product photo can be selected.
- Three platform-ready generated candidates can be produced and saved.
- Each generated asset records source image, template/prompt, output path, and review state.
- Generated assets default to needing human review.
- Approved outputs can become usable asset records.

### AC7 - Architecture Readiness

- Route functions are thinner than Phase 3 for new workflow behavior.
- New task, metric, asset, import, and generation logic is exposed through services/adapters.
- New view data can reasonably be reused by future JSON endpoints.
- Tests cover core service behavior without relying only on HTML assertions.

### AC8 - Documentation And Operation

- The local startup flow remains documented.
- The operator workflow is documented without requiring code knowledge.
- Data health, import/sync, asset review, and backup/export workflows are documented.
- The documentation clearly states that automated publishing and public hosting are still out of scope.

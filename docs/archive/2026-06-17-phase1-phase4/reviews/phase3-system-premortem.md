# Phase 3 System Premortem

Review date: 2026-06-17

Reviewed system:

- `docs/goals/phase3-local-web-operator-console.md`
- `docs/architecture/phase3-architecture.md`
- `docs/reviews/phase3-web-ui-ux-review.md`
- `docs/goals/future-creative-asset-agent.md`
- current Flask/SQLite implementation in `marketing_os/`

## Premortem Scenario

Six months from now, the Phase 3 Marketing OS technically works but is no longer used every week.

The app can still start. Plans can still be generated. Tasks, templates, assets, and metrics still exist in SQLite. But the day-to-day operator stops trusting it as the easiest place to begin. Matt still keeps pieces of the business in his head, on Etsy, inside social apps, in photos folders, and in ad hoc notes. The Marketing OS becomes another place that needs upkeep instead of the system that reduces upkeep.

This failure is more likely to come from operational friction than from a missing planner feature.

## Executive Read

The Phase 3 technical direction was reasonable for the current milestone. A Python Flask app with SQLAlchemy, SQLite, and server-rendered templates is a good local-first choice for a small household/shop workflow. It is easy to run, test, understand, and keep private.

The stack should not be replaced with Next.js merely because the UI can become richer. A rewrite would add dependency weight, build tooling, frontend state decisions, and deployment choices before the product workflow has proven itself.

That said, the current Python app will start to strain if the next phase adds real-time integrations, background sync jobs, media upload/preview/cropping, richer client-side task flows, notifications, authenticated multi-device use, or heavy API dashboards. If those become central rather than optional, a Next.js app may be worth considering as the frontend layer, but not necessarily as a replacement for the Python planning core.

The next pass should focus on reducing non-use risk:

- make the operator workflow more guided
- remove duplicated and premature information
- reduce manual data entry
- turn assets into visual, usable records
- introduce a first set of API/import connections
- execute the future creative asset/image-generation plan as a separate capability that feeds reviewed outputs back into the planner

## Tech Stack Review

### Current Stack

The current implementation uses:

- Python 3.11+
- Flask 3
- SQLAlchemy 2
- SQLite
- Jinja templates
- local Markdown/JSON business inputs
- local ignored database under `data/`
- no JavaScript framework
- no external publishing or analytics APIs

This matches the Phase 3 goal: a trusted local web console, not a cloud SaaS product.

### What The Current Stack Is Good At

- Local-first privacy and simple operation.
- Fast iteration on planner logic and business rules.
- Straightforward test coverage.
- Low dependency count.
- Durable local database storage.
- Easy access to Python libraries for parsing, image processing, file organization, and future AI/asset workflows.
- Keeping Phase 1/2 planning logic intact while adding a browser UI.

### Where The Current Stack Is Weak

- Rich guided workflows require more custom HTML state handling as the UI grows.
- Copy buttons, progressive disclosure, asset upload, image preview, cropping, and task stepper interactions will need more client-side behavior.
- Background sync, scheduling, and notifications need an explicit job model.
- SQLite is fine locally, but multi-device concurrent edits and backup/restore flows need care.
- Server-rendered tables and forms can accidentally keep the app feeling like an admin console.
- No built-in authentication means local-network use must stay trusted and intentionally bounded.

### Would Next.js Be Better?

Not yet as a full replacement.

Next.js would be better if the product direction becomes:

- a polished mobile-first app with complex client-side state
- authenticated multi-user household/team use
- hosted access outside the local network
- dashboard-style API integrations
- background jobs with visible sync states
- file upload, asset review, image comparison, and media workflows as a core daily surface
- reusable React components for task flows, asset galleries, calendars, and metrics

But a full Next.js rewrite would introduce costs:

- Node/package/build complexity
- more frontend architecture decisions
- duplicated or bridged planner logic if Python remains useful
- more moving parts for a local non-technical operator
- likely slower progress on the actual workflow problems

Recommended direction:

1. Keep Python, Flask, SQLAlchemy, and SQLite through the next operator-first pass.
2. Add light client-side JavaScript only where it directly reduces friction: copy buttons, collapsible metrics, guided task steps, previews, filters.
3. Extract service boundaries for integrations and creative assets before choosing a new app shell.
4. Re-evaluate Next.js after the system has at least one real external data connection and one real asset-generation/review workflow.

Possible later hybrid:

- Python remains the planning, integration, asset, and database service.
- Next.js becomes the frontend if the UI needs a richer app experience.
- The boundary is a small HTTP or local API layer rather than a rewrite of the planning engine.

## Primary Non-Use Risks

### 1. Manual Data Upkeep Becomes The Hidden Tax

Current state:

- Business facts live in Markdown.
- Product metadata lives in JSON.
- Templates live in JSON.
- Assets start as placeholder paths.
- Metrics are manually entered.
- Posting happens manually.
- External platform truth lives outside the system.

Failure mode:

The app is only useful when its data is current, but keeping it current is extra work. If Matt has to update Etsy facts, product photos, social performance, published URLs, launch dates, and product status manually, he may eventually work directly inside Etsy, Instagram, Facebook, folders, and memory instead.

Mitigation:

- Add an "upkeep needed" dashboard separate from today's posting work.
- Track stale product, asset, and metric records explicitly.
- Show last synced/last reviewed dates in plain language.
- Prefer imports and API sync over manual copying where practical.
- Let the system degrade gracefully when data is stale by naming the uncertainty.

### 2. The Operator Still Has To Interpret The System

Current state:

- The UI has the right ingredients but still exposes many records, labels, and forms.
- Task detail reads more like a complete database record than a guided posting flow.

Failure mode:

The social operator opens the app and feels unsure what matters first. If Instagram or Facebook already feel intimidating, the app must lower the emotional cost, not add another layer of interpretation.

Mitigation:

- Make Today choose one recommended next action.
- Convert task detail into `Prepare`, `Post`, `Finish`, `Metrics later`.
- Add copy buttons for caption, CTA, hashtags, and URLs.
- Hide metrics until the task is posted or metrics are due.
- Rename planner-language titles into plain action titles.

### 3. Asset Records Are Not Yet Real Enough

Current state:

- Asset records are seeded as placeholder Etsy photo paths.
- There are no thumbnails or actual product-photo review workflows in the UI.
- Readiness state exists, but it is not yet tied to real files or previews.

Failure mode:

Tasks say to use an asset, but the operator still has to hunt through photos, Etsy listings, downloads, text messages, or folders. The planner looks confident while the real blocker is "which image do I use?"

Mitigation:

- Add real asset import from local folders.
- Generate thumbnails/previews.
- Show "use this asset" from the task page.
- Track missing files and broken paths.
- Track which tasks used which asset.
- Add readiness filters: ready, needs crop, needs new photo, needs generated composite.

### 4. Metrics Entry Feels Like Homework

Current state:

- Metrics are manual and broad.
- The task page shows all metric fields even before posting.

Failure mode:

Metrics are skipped because they require remembering when to check, where to look, and which numbers matter. Without metrics, future plans cannot learn from what worked.

Mitigation:

- Create a dedicated `Metrics Due` workflow.
- Use platform-specific metric fields.
- Add "check on" dates and reminders.
- Track missing post URLs separately from missing numeric metrics.
- Import metrics from APIs where possible.

### 5. Local App Startup Is Still A Ritual

Current state:

- The app is started with `python run_local.py`.
- Normal browser use works after startup, but the server still depends on Terminal or a script.

Failure mode:

If the app is not already running when the operator has a few spare minutes, the workflow loses to whatever app is already open.

Mitigation:

- Add a double-clickable launcher or OS login item.
- Add a health/status page that tells the operator whether data is current.
- Document a stable local URL or bookmark.
- Consider packaging later only after workflow fit improves.

### 6. Plan Generation Can Create More Work Than Clarity

Current state:

- Generating a new plan creates many ready-to-post tasks.
- The Today view includes status counts and repeated week tasks.

Failure mode:

The plan feels like an obligation pile. A high count of ready tasks can discourage use instead of creating momentum.

Mitigation:

- Add plan approval before tasks become active.
- Show only the next one or two tasks to the operator.
- Separate backlog from today.
- Add task throttling by capacity.
- Make skipped tasks normal and non-punitive.

### 7. Integrations Arrive Too Late

Current state:

- `marketing_os/integrations.py` defines future protocols but no real providers.
- README explicitly says Etsy, Instagram, Facebook, Google Analytics, Search Console, and publishing integrations are out of scope.

Failure mode:

The app remains useful for planning but not for operating because all truth still lives elsewhere.

Mitigation:

- Pick one low-risk read-only integration first.
- Favor imports/sync over automated publishing.
- Store external IDs and URLs on products, assets, tasks, and metrics.
- Make integration failure visible but not blocking.

## Useful Connections To Consider

### Highest-Value Early Connections

1. Etsy shop/listing import
   - Pull product titles, listing URLs, prices, status, tags, images, favorites/views if available.
   - Reduces product and asset upkeep.
   - Gives tasks real links and real product images.

2. Local photo folder import
   - Watch or scan `assets/products`.
   - Generate thumbnails and detect missing files.
   - Reduces the "where is the photo?" failure mode.

3. Instagram/Facebook post URL capture
   - Even before full analytics, make it easy to paste or store published URLs.
   - Later metrics can attach to the right object.

4. Website analytics import
   - Google Analytics or another site analytics provider.
   - Useful for blog/product-story tasks and Etsy referral learning.

5. Search Console import
   - Helps website/blog topics become grounded in search reality.
   - Probably owner-facing, not operator-facing.

### Medium-Value Connections

6. Facebook/Instagram insights
   - Pull reach, likes, comments, saves, shares where API access permits.
   - Reduces manual metrics.
   - May have platform permission friction.

7. Email platform metrics
   - Mailchimp, Shopify Email, ConvertKit, or whichever platform is actually used.
   - Pull signups, sends, opens, clicks.

8. Calendar export
   - Apple/Google calendar export or `.ics`.
   - Helps tasks appear where people already look.

9. Reminder/notification bridge
   - Local notifications, email, or calendar reminders.
   - Useful for metrics due and scheduled posting follow-up.

10. Backup/export connection
   - Scheduled SQLite backup to iCloud Drive, Dropbox, Google Drive, or a local backup folder.
   - Prevents local-only data from becoming fragile.

### Lower-Priority Or Riskier Connections

11. Automated publishing
   - High potential value, but high account/API/platform-policy complexity.
   - Should wait until manual workflow and asset QA are reliable.

12. Paid ads integrations
   - Too early unless paid acquisition becomes a real channel.

13. Inventory/order sync
   - Useful later if marketing tasks need to avoid out-of-stock products.
   - Depends on where inventory truth lives.

## Data Model Gaps To Address Before Integrations

- External IDs for products, listings, posts, assets, and campaigns.
- Source system and sync timestamp per record.
- Staleness state: fresh, stale, missing, error, manually overridden.
- Published URL and platform post ID on tasks/content drafts.
- Metric collection due date and collection status.
- Asset file existence and checksum or modified time.
- Review state for generated images and generated copy.
- Human approval fields before publishing or using generated graphics.

## Creative Asset / Image Generation Next Pass

Phase 3 intentionally did not implement automatic image generation. The next pass should reference and execute the plan in `docs/goals/future-creative-asset-agent.md`.

The next pass should treat image generation as a separate creative asset capability, not as hidden behavior inside plan generation.

Required next-pass shape:

1. Select a real product photo from the asset inventory.
2. Generate at least three platform-ready formats:
   - Instagram feed square product card
   - Instagram Reel cover
   - Instagram carousel slide
3. Preserve product accuracy:
   - duck shape
   - color
   - printed details
   - proportions
4. Save outputs under predictable paths such as `outputs/graphics/` or `assets/products/<product-slug>/generated/`.
5. Record source image, prompt/template, output path, and review notes.
6. Mark generated outputs as needing human review by default.
7. Allow reviewed outputs to become asset records that future tasks can reference.
8. Do not rely on generated graphics for normal planning until this review loop exists.

Suggested integration point:

- Add an asset-generation service that consumes `AssetRecord` plus a graphic template from `docs/templates/graphics/`.
- Store each result as a new asset record or child review record.
- Keep prompts/template metadata inspectable.
- Surface generated assets in the task page only after approval.

This is the bridge between the current placeholder graphic templates and a usable creative workflow.

## Recommended Next Phase Priorities

1. Operator-first Today and Task redesign.
2. Real asset import with thumbnails and missing-file detection.
3. Copy buttons and progressive task steps.
4. Metrics Due workflow with platform-specific fields.
5. Product/listing URL fields and external ID fields.
6. First read-only integration or import path, preferably Etsy listing/photo import.
7. Execute the future creative asset/image-generation plan with human review.
8. Add backup/export for the local SQLite database.
9. Add staleness/sync status to data that comes from files or APIs.
10. Reassess Next.js only after richer UI and integration needs are proven.

## Decision

Do not rewrite Phase 3 as Next.js now.

Keep the local Python app and spend the next pass on removing the reasons a real operator would avoid the system. If the product then clearly wants a richer app shell, introduce Next.js as a frontend over stable Python services rather than replacing the planning and asset logic wholesale.

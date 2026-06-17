# Phase 5 Integrations And Creative Quality

Build Phase 5 of the MattMadeMe Marketing Operating System.

## Source Inputs

Active inputs:

- `docs/reviews/phase4-current-state-premortem.md`
- `docs/architecture/etsy-read-only-integration-plan.md`
- `docs/architecture/mattmademe-website-integration-plan.md`
- `docs/architecture/local-asset-library-agent-access-plan.md`
- `docs/architecture/freepik-magnific-creative-integration-plan.md`
- `docs/architecture/copywriter-skill-and-learning-loop-plan.md`
- `docs/operating-guides/local-web-console.md`
- current implementation in `marketing_os/`

Archived historical inputs:

- `docs/archive/2026-06-17-phase1-phase4/goals/`
- `docs/archive/2026-06-17-phase1-phase4/reviews/`
- `docs/archive/2026-06-17-phase1-phase4/architecture/`

## Problem Statement

Phase 4 made the local web app easier to operate, but the system can still fail from non-use.

The biggest risks are:

- the user still has to manually keep product/listing/blog facts current
- the creative generation pass produced low-quality images
- generated copy can still sound generic unless it has a dedicated voice, channel, and quality-review layer
- assets can become scattered across repo-local folders, generated-output folders, and external files
- Data Health can identify problems without making them easy enough to fix
- integrations could become one-off code paths that force a rewrite later
- the system will stop improving if it does not monitor which posts, products, formats, and messages actually work

## Objective

Make Marketing OS more trustworthy and lower-maintenance by adding the first real integration layer, a governed asset library path, and a higher-quality creative workflow while keeping the current Python stack.

Phase 5 should:

- keep Python, Flask, SQLAlchemy, SQLite, and Jinja for now
- deepen service/API boundaries so a future Next.js frontend can attach without replacing the planning core
- reduce manual product and asset upkeep
- make imported facts visible before the planner depends on them
- improve creative quality through Freepik/Magnific or a manual/MCP bridge
- generate at least one high-quality Facebook post in MattMadeMe's tone and voice
- establish a copywriter service boundary for posts and future blog drafts
- create a learning loop that tracks what worked, what did not, and what should change next time
- keep all generated assets behind human review
- validate the operator UI through an actual walkthrough

## Required Capabilities

### 1. Integration Boundary

Add a reusable integration shape for external sources.

It should support:

- source configuration loaded from `.env`
- adapter classes for provider-specific API calls
- services that normalize provider data into local records
- sync status, sync error, last synced timestamp, external source, external ID, external URL, review state, and manual override state
- tests for read/write boundaries
- Data Health summaries for missing credentials, failed syncs, stale data, and mapping conflicts

### 2. Etsy Read-Only Sync

Implement the first safe Etsy path from `docs/architecture/etsy-read-only-integration-plan.md`.

Required:

- API-key configuration with no secrets in git or logs
- read-only adapter methods using `GET` requests only
- active listing import
- listing image import as external asset records
- local product matching suggestions without automatic overwrite
- Data Health cards for missing credentials, sync failure, unmapped listings, stale listings, and missing images

Out of scope:

- writing to Etsy
- renewing listings
- editing inventory
- publishing or deleting listings

### 3. MattMadeMe Website Sync

Implement the read side of `docs/architecture/mattmademe-website-integration-plan.md`.

Required:

- bearer-token configuration with no token logging
- product import
- published blog metadata import
- website product image import as external asset records
- product matching suggestions without automatic overwrite
- Data Health cards for missing credentials, sync failure, unmapped products, stale products, and missing images

Optional if the review UI is ready:

- create CMS-reviewable draft blog posts through the documented draft endpoint

Out of scope:

- publishing blog posts
- editing existing published content
- deleting website data

### 4. Local Asset Library

Implement the first version of `docs/architecture/local-asset-library-agent-access-plan.md`.

Required:

- support `MARKETING_OS_ASSET_ROOT`
- scan an external-drive asset root
- create/update a local asset index
- generate lightweight thumbnails for images
- store hash, file size, dimensions where available, modified time, path, product slug, role, status, and rights/review fields
- show missing asset root and stale index in Data Health
- keep original files and generated outputs out of git

### 5. Freepik/Magnific Creative Workflow

Replace the weak Phase 4 local renderer as the default quality path.

Required:

- create a Freepik/Magnific integration doc-backed adapter or manual/MCP import path
- require approved source assets
- create platform-specific generation requests for square product card, reel cover, and carousel slide
- store source asset, prompt, provider, model/tool, job ID or MCP run note, output path, and review notes
- default generated outputs to `needs_review`
- allow approval, rejection, and assignment only after local file existence checks
- surface failed generations and unreviewed outputs in Data Health

Out of scope:

- auto-approving generated images
- publishing generated assets automatically

### 6. Copywriter Skill And Facebook Post Generation

Create a dedicated copywriter capability for high-quality social posts and future blog drafts.

The copywriter should be a service boundary, not a pile of ad hoc prompt text in routes or templates.

Required:

- read MattMadeMe tone, voice, audience, product, channel, and business-goal context from the existing docs and imported product data
- generate one Facebook post for a selected product or campaign using a real product fact source
- support a review flow where Matt can approve, edit, reject, or request a rewrite
- store the draft body, hook, CTA, product references, source facts, channel, intended audience, and revision notes
- include a quality checklist for accuracy, tone, useful specificity, non-generic wording, and platform fit
- make the post easy to copy into Facebook from the task detail workflow
- keep the generated post out of any automatic publishing path

The first version should focus on Facebook because it is lower-friction, conversational, and useful for community/product storytelling. The same boundary should later support Instagram captions, Etsy listing refresh ideas, emails, and blog drafts.

Suggested implementation shape:

```text
marketing_os/services/copywriter.py
marketing_os/templates/copy_review.html
```

The copywriter service should expose functions such as:

- `generate_facebook_post(request)`
- `generate_blog_draft_outline(request)`
- `score_copy_against_voice(copy, context)`
- `record_copy_review(copy_id, decision, notes)`

Out of scope:

- automatic posting to Facebook
- replacing human review
- long-form blog publication without the website draft review path

### 7. Performance Monitoring And Learning Loop

Marketing OS should always improve by observing what is working and what is not.

Required:

- connect generated posts, tasks, assets, products, and channels to later metric records
- capture outcome notes such as "sold item", "got comments", "no engagement", "good story angle", or "bad image"
- show simple learning summaries in Data Health or a dedicated Insights view
- identify top-performing post patterns by channel, product, audience, CTA, image/source asset, and content angle
- identify low-performing or stale patterns that should be avoided or rewritten
- feed lessons learned back into future copywriter and planner requests
- keep manual metric entry usable while API analytics are not implemented

Useful future metric sources:

- manual Facebook post metrics
- manual Instagram post metrics
- Etsy visits, favorites, cart adds, and orders
- MattMadeMe website product/blog traffic
- email signups or campaign clicks
- qualitative comments from Facebook groups or customer messages

The first Phase 5 implementation can be manual, but the data model and UI should make future API metric ingestion natural.

### 8. UI/UX Validation Pass

Run a practical UI/UX review after integrations are visible.

Required:

- test Today, task detail, Assets, Creative Assets, Data Health, Settings, and integration sync screens
- test the Facebook post copy review flow
- test how performance notes and metrics are entered after the post is live
- check desktop and mobile layouts
- record friction points from a real or simulated operator walkthrough
- fix high-friction issues that block normal use
- document any deferred UI work in the Phase 5 completion audit

## Architecture Constraints

Keep the current stack in place.

Implementation should:

- keep provider-specific API calls out of Flask route functions
- keep planner decisions out of templates
- expose JSON endpoints for new integration summaries where useful
- prefer service functions that can be reused by a future frontend
- avoid direct dependencies from core planning logic to Etsy, website, or Magnific clients
- keep copywriting prompts and quality rules in a reusable service/config layer rather than scattered across templates
- keep performance-learning logic source-agnostic so manual metrics and future API metrics use the same concepts
- add tests before relying on new integration behavior
- fail gracefully when credentials are missing

## Doneness Criteria

Phase 5 is done when:

- the test suite passes
- Etsy read-only sync can import real or fixture-backed active listings and listing images
- MattMadeMe website sync can import real or fixture-backed products and published blog metadata
- imported products/listings/images appear in Data Health and relevant asset/product views
- local asset library scanning works against a configured asset root and produces searchable/indexed records
- Freepik/Magnific or manual/MCP creative output import produces generated candidates from approved source assets
- generated candidates cannot be assigned to tasks until reviewed and approved
- one Facebook post can be generated from real product/source context, reviewed, revised or approved, and copied from the operator workflow
- generated copy stores source facts, channel, audience, CTA, review decision, and revision notes
- at least one posted-task metric or outcome note can be linked back to the generated copy, product, channel, and asset
- a simple learning summary shows what worked, what did not, or what needs more data
- missing credentials and failed syncs are visible without breaking daily workflow
- the Phase 5 UI/UX walkthrough has been documented
- executed/superseded docs are archived and current docs point to the active goal
- no real credentials, SQLite files, generated image batches, or local asset originals are committed

## Success Criteria

Phase 5 succeeds if:

- Matt can see which product/listing/blog facts came from Etsy or MattMadeMe.com and when they were last synced.
- The operator can start the day without caring whether a product came from local docs, Etsy, or the website.
- At least one product has source images discoverable through the local asset library path.
- At least one generated creative candidate from the improved workflow is good enough to approve after review.
- At least one Facebook post reads like MattMadeMe, uses accurate product context, and is ready for human posting without heavy rewrite.
- At least one future recommendation is influenced by recorded performance or outcome notes instead of only static planning assumptions.
- Data Health produces actionable next steps rather than vague maintenance anxiety.
- The codebase has clearer integration boundaries than before Phase 5.
- A future Next.js frontend remains optional, not forced by tangled Flask/Jinja business logic.

## Out Of Scope

- Full Next.js rewrite.
- Public hosting.
- Public authentication.
- Automated posting to Instagram, Facebook, Etsy, or MattMadeMe.com.
- Etsy write operations.
- Website publication without human CMS review.
- Fully automated analytics ingestion.
- Paid ads management.
- Replacing the local-first SQLite deployment model.

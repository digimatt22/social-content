# Phase 5 Integrations And Creative Quality

Build Phase 5 of the MattMadeMe Marketing Operating System.

## Source Inputs

Active inputs:

- `docs/reviews/phase4-current-state-premortem.md`
- `docs/architecture/etsy-read-only-integration-plan.md`
- `docs/architecture/mattmademe-website-integration-plan.md`
- `docs/architecture/local-asset-library-agent-access-plan.md`
- `docs/architecture/freepik-magnific-creative-integration-plan.md`
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
- assets can become scattered across repo-local folders, generated-output folders, and external files
- Data Health can identify problems without making them easy enough to fix
- integrations could become one-off code paths that force a rewrite later

## Objective

Make Marketing OS more trustworthy and lower-maintenance by adding the first real integration layer, a governed asset library path, and a higher-quality creative workflow while keeping the current Python stack.

Phase 5 should:

- keep Python, Flask, SQLAlchemy, SQLite, and Jinja for now
- deepen service/API boundaries so a future Next.js frontend can attach without replacing the planning core
- reduce manual product and asset upkeep
- make imported facts visible before the planner depends on them
- improve creative quality through Freepik/Magnific or a manual/MCP bridge
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

### 6. UI/UX Validation Pass

Run a practical UI/UX review after integrations are visible.

Required:

- test Today, task detail, Assets, Creative Assets, Data Health, Settings, and integration sync screens
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


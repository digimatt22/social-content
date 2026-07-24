# Pinterest Growth Phase 1: Website Hub MVP

## Status

- Status: completed
- Owner: Codex
- Marketing OS branch: `codex/pinterest-growth-phase-1`
- Website branch: `codex/pinterest-growth-phase-1`
- Base commits: Marketing OS `b3d6427`; website `fb92e37`
- Website completion commit: `3166790`
- Last updated: 2026-07-24

## Goal

Create a credible, tracked Pinterest landing hub for one evidence-backed cohort without granting automatic publication authority.

## Selected cohort

`Everyday Heroes`, bounded to six currently public products with verified website/Etsy identity:

- Mailman Duck;
- Mailwoman Duck;
- EMT Duck;
- Firefighter Duck;
- 911 Dispatcher Duck;
- Police Duck.

Selection evidence: a read-only query on 2026-07-24 against the Etsy sales
snapshot last imported 2026-06-20 shows 1,120 Mailman, 266 EMT, 260
Firefighter, 168 911 Dispatcher, 129 Police, and 61 Mailwoman units. The
unmapped Delivery Duck is excluded.

These counts support product demand only. `Everyday Heroes`, `mail carrier
gifts`, and `first responder gifts` are bounded positioning/search-intent
hypotheses. They are not established Pinterest or Google demand, and an absence
of early performance must not be interpreted as negative product demand.

## Deliverables

- Canonical human-readable product slugs with permanent legacy-ID redirects.
- One `Everyday Heroes` collection landing page.
- Two evergreen guides: mail-carrier gifts and first-responder gifts.
- Verified product facts, internal collection/guide/product links, tracked Etsy exits, and Pinterest-ready `2:3` image slots.
- Sitemap/canonical/metadata/Product and editorial structured data.
- Versioned, separately scoped agent read/draft contracts with idempotent blog,
  collection, and guide draft creation plus preview/publish separation.
- Marketing OS contract fixtures for the versioned website API.
- Website build and route/contract validation.

## Guardrails

- No direct database access from Marketing OS.
- No automatic page publication.
- No invented product price, availability, dimensions, materials, or demand claims.
- Unmapped products remain excluded.
- Draft API writes only `status=draft`; a human publishes the initial page types.

## Acceptance

- Legacy product routes permanently redirect to canonical slug routes.
- Canonical product/collection/guide pages build and link correctly.
- Every Etsy exit is tracked with product and source context.
- Pinterest attribution identifiers are retained into the Etsy-exit event and
  delivered to one approved measurement receiver.
- Sitemap contains canonical hub and product paths.
- Agent v1 endpoints remain compatible; v2 contracts are versioned and tested.
- Repeated draft requests with one idempotency key return one draft.
- Concurrent identical draft requests return one stored draft and two successful
  responses; conflicting payloads or slugs return HTTP 409.
- Full website build and focused Marketing OS tests pass.
- Human publication review remains a named deployment gate.

## Approved attribution contract

The first-party receiver, exact non-PII payload, and 400-day retention window
were explicitly approved on 2026-07-24. Etsy exits now retain bounded
campaign/content/publication/Pin identifiers in session storage and send them
only to same-origin `POST /api/growth-events`. The record also includes landing
and click pathnames, product ID, placement, Etsy hostname, and timestamp. It
excludes full query strings, cookies, personal information, and full Etsy URLs.

Events live in a dedicated TTL-enabled DynamoDB table and are exposed to
Marketing OS through a separate `measurement:read` credential at
`GET /api/agent/v2/growth-events`. GA continues receiving pathname-only
pageviews; attribution identifiers are not forwarded to GA or Vercel.

## Commit contract

- Commit website and Marketing OS changes separately at Phase 1 completion.
- Preserve unrelated worktree changes.

## Completion evidence

- Website build passed with 137 generated application pages.
- Twenty-seven website contract, privacy, and security tests passed.
- Nine Marketing OS website-adapter contract tests passed.
- PostgreSQL/durable-job and focused Phase 0–1 tests passed (28 tests).
- Terraform formatting and configuration validation passed.
- Final independent review passed with no Phase 1 implementation blockers.
- Production Terraform apply, production credential rotation, branch review,
  initial page-type publication, and proxy-header enforcement remain release
  gates rather than implementation work.

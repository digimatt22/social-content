# Pinterest Shadow Production v1

## Purpose

Phase 3 turns ranked Phase 2 coverage opportunities into complete local
Pinterest campaign packages. It proves production, review, exception, and
learning workflows without Pinterest, website, or generation-provider writes.

The frozen policy is `config/pinterest-shadow-policy-v1.json`. Runtime adapters
are deterministic Python adapters informed by recorded social-media skill
hashes. Stored provenance says `deterministic_local_adapter`; it never claims a
Markdown skill, agent, Magnific, or Pinterest invocation occurred.

## Input and selection

`shadow.generate` reads ranked, unsuppressed Pinterest page opportunities in
score order, capped at 20 campaigns/60 variants:

- a ready, fresh, published destination plus eligible publication opportunity
  produces `search_exact`, `gift_context`, and `audience_context`;
- a missing, stale, or unready destination produces a local `draft_page`
  artifact and no fabricated Pin;
- a ready destination records exact website ID, path, revision, and check time
  as `reuse_page`.

Campaign, content, and publication IDs are UUIDv5 values derived from immutable
inputs. Changed source, policy, or repository revisions create new immutable
packages. Exact replay returns the existing package. Replays do not consume the
20-campaign write budget, so daily catch-up continues scanning ranked rows until
it drains later unseen candidates.

## Package contract

Every complete variant stores:

- Pinterest title and description, one CTA, no hashtags;
- exact allowlisted shadow-board recommendation with no fallback;
- canonical `https://mattmademe.com` destination and full funnel attribution;
- semantic payload hash excluding run-specific UTM IDs;
- up to four approved, visible, file-backed, checksummed product references;
- a 2:3, 1000×1500 product-preserving image handoff;
- one already-registered, checksummed 1000×1500 review image;
- policy, adapter, prompt, skill-source, repository, and input provenance;
- append-only gate decisions.

Fixture-backed images are `fixture_non_provider` and
`product_accuracy_unverified`. Real imported outputs remain
`real_output_needs_human_review`. Neither label grants product approval.
Generation jobs read and hash registered files only.

## QA and lifecycle

All variant gates persist evidence for identity, claims, placeholders,
destination, tracking, board, copy quality, season, asset lineage, review
fixture, crop, product preservation, authority, and active-payload uniqueness.
Failures remain queryable as blocked candidates.

Only variants passing every required gate acquire a unique payload lease and
reach `ready_for_review`. Supersession explicitly releases the old lease and
never deletes QA evidence. PostgreSQL advisory locks serialize same-input
replay, while the unique payload lease resolves distinct-input races.

Every generation pass first reconciles active packages against current identity,
suppression, freshness, destination, and publication eligibility. Lost
eligibility blocks the old variants, releases their leases, and appends
invalidation QA. A new valid input with changed semantic payload automatically
supersedes its prior active variant in the same transaction.

## Review and learning

Authenticated APIs and pages expose campaigns, exceptions, and the latest
digest. Operator/admin or service `write` authority is required to start a
timed review, append an exact item decision, and complete the session.

Decision kinds and results are allowlisted; reason codes are normalized
snake_case. Counts are derived from append-only decisions. Elapsed time exists
only for completed sessions. Shadow acceptance never grants website, asset,
board, provider, or Pinterest authority.

Publication decisions link the exact variant, manifest, and review image.
Page-only campaigns store campaign-level `destination` or `package` decisions,
so editorial drafts use the same measured feedback loop without fabricating a
Pin record.

`shadow.digest` groups states and QA failures plus human results, reason codes,
result-and-reason pairs, decision kinds, variants, boards, review assets,
evidence maturity, and measured review effort. Learning remains explicitly
observational. Every query is bounded to the requested UTC week; empty sessions
cannot complete or enter measured-effort statistics.

## Routes

Canonical authenticated reads:

- `GET /api/shadow-campaigns`
- `GET /api/shadow-campaigns/<campaign_id>`
- `GET /api/shadow/exceptions`
- `GET /api/shadow-digests/latest`
- `GET /shadow-campaigns`
- `GET /shadow-campaigns/<campaign_id>`
- `GET /shadow-digests`

Canonical authenticated mutations:

- `POST /api/shadow-review-sessions`
- `POST /api/shadow-review-sessions/<token>/decisions`
- `POST /api/shadow-review-sessions/<token>/complete`

Compatibility aliases under `/api/shadow` and `/shadow` have identical
authorization and behavior.

## Authority boundary

Phase 3 contains no Pinterest connector, board-create, media-upload, Pin-create,
website-draft, website-publish, Magnific, or other provider call. Reviewed board
names are recommendations only. Phase 4 is the first phase that may request
scoped external authority.

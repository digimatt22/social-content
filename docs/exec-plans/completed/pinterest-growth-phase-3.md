# Pinterest Growth Phase 3: Shadow Campaign Production

## Status

- Status: completed
- Owner: Codex
- Branch: `codex/pinterest-growth-phase-3`
- Base commits: Marketing OS `022330c`; website `5018810`
- PR: unavailable until the Marketing OS repository has an `origin` remote
- Last updated: 2026-07-24
- External authority: none
- Independent plan review: `PASS` — strategy 9.6/10, automation 9.5/10,
  feedback 9.6/10; no P0/P1 blockers
- Independent implementation review: `PASS` after three challenge rounds —
  strategy 9.7/10, automation 9.6/10, feedback 9.6/10; no P0/P1 blockers

## Summary

Turn eligible Phase 2 publication opportunities into complete, reviewable
Pinterest campaign packages without writing to Pinterest, the public website, or
a paid generation provider.

Each package will contain a local page action/draft, up to three
Pinterest-native copy variants, a reviewed-board recommendation, tracked
destination URL, product-preserving image-generation manifests, a checksummed
shadow review image, provenance, deterministic QA decisions, and item-level
review/effort instrumentation. Phase 3 proves the production system and
exception loop; Phase 4 remains the first phase that may request external
publishing authority.

## Strategy and skill contract

The source skill sequence informing the adapter design is fixed:

1. `social-media-strategist` selects Pinterest search-discovery intent, audience,
   gift/occasion context, one story move, one CTA, evidence labels, and unknowns.
2. `social-media-copywriter` creates Pinterest title/description variants rather
   than a generic social caption.
3. `social-media-copy-chief` scores source discipline, search fit, body, CTA, and
   MattMadeMe voice. A score below 3/5 blocks the variant.
4. `social-media-art-director` creates a 2:3, 1000×1500 product-preserving
   Magnific handoff with actual approved reference paths and identity-lock roles.
5. `video-content-planner` and `video-editor` metadata are supported for future
   video variants, but Phase 3 defaults to static Pins and makes no video/provider
   call.

Database-only jobs do not claim that Markdown skills or an agent executed. Phase
3 implements versioned deterministic local adapters named
`pinterest-shadow-strategy-v1`, `pinterest-shadow-copy-v1`,
`pinterest-shadow-copy-review-v1`, and `pinterest-shadow-creative-v1`. Each
adapter records `execution_mode=deterministic_local_adapter`, its own version and
hash, and `informed_by` skill names/file hashes. A later explicitly authorized
agent/provider path must record a distinct execution mode and actual invocation
evidence.

The runtime stores adapter versions/hashes, source skill references/hashes,
prompt template version, policy version, provider/model preference, and
repository revision. Plugin packaging remains Phase 6.

## Scope and non-goals

In scope:

- deterministic shadow package generation from eligible Phase 2 cells;
- local page reuse/draft artifacts;
- Pinterest-native titles, descriptions, tracked links, and board
  recommendations;
- product-safe static-image manifests;
- provenance and asset lineage;
- append-only QA decisions and exception reasons;
- shadow review/read APIs and operator pages;
- representative batch execution and weekly digest;
- review-effort measurement.

Out of scope:

- Pinterest access-token use, board creation, Pin creation, media upload, save,
  update, delete, or reconciliation;
- website draft/publish API calls;
- live Magnific/Freepik/image/video generation or provider cost;
- automatic approval;
- claiming that a fixture-backed shadow image passed real product-accuracy
  review;
- changing the Phase 2 taxonomy or opportunity weights;
- causal performance claims.

## Versioned shadow policy

Create `config/pinterest-shadow-policy-v1.json` and schema-validate it at load.
It freezes:

- policy version `pinterest-shadow-v1`;
- package variants: `search_exact`, `gift_context`, and `audience_context`;
- static Pin format: 2:3, 1000×1500, no text overlay by default;
- title safety target: nonempty and at most 90 characters;
- description safety target: nonempty and at most 400 characters;
- one CTA and no hashtags;
- allowed destination origin `https://mattmademe.com`;
- required UTM source `pinterest` and medium `organic_social`;
- required campaign/content/publication IDs;
- reviewed shadow-only board allowlist:
  - `Everyday Heroes Gift Ideas`
  - `Mail Carrier Gift Ideas`
  - `First Responder Gift Ideas`
- exact intent-to-board mappings with no fallback;
- banned unsupported-claim patterns, including popularity, scarcity, discounts,
  guarantees, and exact sales claims;
- banned product terms, including `rubber duck`;
- asset requirements: mapped product, approved/visible source asset, file exists,
  product match, usable rights, brand-safe state, and at least one reference;
- maximum 20 packages per durable job and 60 artifacts per job;
- three transient attempts under the Phase 0 durable-job policy;
- zero provider calls and zero public writes.

The board allowlist is approved for shadow recommendation testing only. It is not
authority to create or publish to those boards.

## Domain and migration contract

Add Alembic revision `0004_pinterest_shadow_production` and these records:

- `ShadowCampaign`
  - stable `campaign_id`;
  - coverage cell, product, landing page, Phase 2 decision run;
  - source revision and repository revision;
  - policy/skill/prompt versions;
  - lifecycle: `generating`, `blocked`, `ready_for_review`, `reviewed`;
  - deterministic input hash and timestamps.
- `ShadowPublication`
  - stable `content_id` and `publication_id`;
  - one of the three variant roles;
  - title, description, board recommendation, page action/draft JSON;
  - canonical destination and tracked UTM URL;
  - payload hash and lifecycle;
  - no external Pin or board ID.
- `ShadowCreativeManifest`
  - publication, source asset IDs/checksums, output role;
  - provider path/model preference;
  - prompt, negative prompt, crop/dimensions;
  - expected local output path;
  - generation state fixed to `handoff_ready` in Phase 3;
  - optional imported fixture/review asset linkage.
- `ShadowQADecision`
  - publication/manifest, gate name/version, result, reason codes;
  - evidence JSON and timestamp;
  - append-only.
- `ShadowReviewSession`
  - campaign, reviewer/session token;
  - started/completed timestamps, elapsed seconds;
  - counts derived from linked item decisions, never directly entered;
  - no inferred time when a session is incomplete.
- `ShadowReviewDecision`
  - session and campaign; publication is required for Pin decisions and absent
    only for page-only `destination`/`package` decisions;
  - optional creative manifest/review asset, validated against the publication;
  - decision kind: `copy`, `board`, `destination`, `creative`, `package`;
  - result: `accepted_for_shadow`, `revise`, `rejected`, `exception`;
  - normalized reason codes and optional reviewer note;
  - append-only reviewer/time evidence;
  - never grants website, asset, board, or Pinterest approval.
- `ShadowPayloadLease`
  - unique canonical payload hash;
  - owning ready/reviewed publication;
  - acquired/released/superseded timestamps;
  - database boundary preventing concurrent active duplicates while blocked
    duplicate candidates and their QA records remain persistable.
- `ShadowDigest`
  - UTC week, deterministic input hash;
  - ready/blocked counts, gate failure distribution, evidence maturity summary,
    review-effort statistics, and observational learning notes.

Uniqueness:

- one campaign per coverage-cell/input-policy-repository tuple;
- one publication per campaign/variant role;
- one payload lease per active semantic payload;
- one manifest per publication/option number;
- one digest per UTC week/input hash.

One transaction writes campaign, publications, manifests, links to already
registered review-image inputs, QA decisions, payload leases, supersession
state, and outbox state. Any failure rolls back the package. The durable job
performs no filesystem write.

## Deterministic production

### Candidate selection

- Select ranked, unsuppressed Phase 2 page opportunities even when their
  publication opportunity is blocked. Generate a local page draft/action and
  preserve the Pin as `blocked_destination` until a later fresh editorial read.
- Select Pinterest `PublicationOpportunity` rows for complete Pin variants only
  when eligible, ranked, unsuppressed, fresh, and within any seasonal publish
  window.
- Sort by opportunity score descending, publish date null-last, product ID,
  intent key, then cell ID.
- Never silently broaden beyond the Phase 2 cohort.
- A changed source revision/policy/repository revision creates a new immutable
  package input; replay of the same tuple is a no-op. Page-only packages do not
  fabricate a destination URL, board recommendation, or ready Pin.

### IDs and destination

- `campaign_id`: UUIDv5 from coverage cell + source/policy/repository revisions.
- `content_id`: UUIDv5 from campaign + variant role.
- `publication_id`: UUIDv5 from content + `pinterest-shadow`.
- Destination: the cell’s exact canonical `https://mattmademe.com` landing-page
  URL.
- Append the three identifiers through the existing `tracked_destination_url`
  contract. Reject pre-existing conflicting attribution parameters.

### Copy variants

All variants remain Pinterest `pinterest_search_pin` structures:

- `search_exact`: lead with the normalized intent and product type;
- `gift_context`: lead with recipient/occasion;
- `audience_context`: lead with the approved audience and appreciation context.

Copy uses only:

- product name and canonical identity;
- normalized search intent, audience, occasion, season, and evidence state;
- verified landing-page path/revision;
- reviewed brand phrases and CTA;
- explicit `[MATT_TO_CONFIRM: ...]` placeholders where a required fact is absent.

No variant may expose internal sales counts, rankings, private review data, or
unsupported materials/features. The runtime performs a deterministic source
claim inventory before copy-chief scoring. Adapters first choose
fact-independent Pinterest copy from the approved product name, intent,
audience, occasion, and page facts. If a safe complete variant cannot be written
without `[MATT_TO_CONFIRM: ...]`, it is stored as `blocked_missing_required_fact`
and excluded from representative passing counts; Matthew is not assigned routine
fact completion.

### Page artifact

- Ready/published destination: store a `reuse_page` artifact with exact website
  ID/path/revision; never call the website.
- Missing/unready destination: store a local `draft_page` artifact and block Pin
  readiness until a fresh Phase 2 editorial read verifies it. Page drafts derive
  from the ranked page opportunity path, so this branch is exercised by normal
  production rather than unreachable defensive code.

### Board recommendation

Map an exact reviewed intent key to exactly one allowlisted shadow board.
Unknown/ambiguous mappings block with `board_unreviewed`; there is no fallback,
fuzzy match, or board API call.

### Creative manifest

- Select up to four approved, visible, file-backed product assets in stable
  order; the first is `@img1`, remaining images are identity locks.
- Require checksums and source/product lineage.
- Produce one 2:3 manifest per publication with Google Nano Banana 2 as the
  preference and a reference-capable-model fallback note.
- Prompt the exact 2.5-inch inanimate 3D-printed duck in a full-scale,
  story-aligned environment.
- Preserve silhouette, color, accessories, print texture, facial details,
  proportions, material, scale, and grounding.
- Negative prompt rejects living motion, changed product details, duplicates,
  text, logos, watermarks, weapons, unsafe content, and a generic listing-photo
  scene.
- Phase 3 never performs live generation. It stores the handoff and expected
  output path, then links either a deterministic fixture review image for
  workflow proof or a separately imported real output for human review. Fixture
  assets remain labeled `fixture`, never provider-generated or human-approved.

### Shadow review image

- Every passing representative variant links one actual local 1000×1500 PNG or
  JPEG whose bytes, checksum, dimensions, MIME type, source IDs, and fixture/real
  origin are verified.
- Fixture images are immutable inputs prebuilt by the test harness before the
  job/transaction begins, then registered with checksum, dimensions, MIME type,
  and origin. They may be deterministic composites derived from a checksummed
  product source image. They prove packaging, crop, lineage, and review UI
  behavior only.
- Fixture images are labeled `fixture_non_provider`,
  `product_accuracy_unverified`, and cannot satisfy a human product-accuracy
  gate or be promoted to a reusable approved asset.
- A real provider/imported image uses `real_output_needs_human_review` and still
  cannot be marked product-accurate by automation.
- A manifest without a verified local review image is
  `handoff_ready`, not a complete reviewable package and not counted in the
  representative 20.
- Shadow jobs only read and hash registered files. They never generate, copy,
  rename, delete, or overwrite fixture/real images, so database rollback cannot
  orphan a job-created file. Missing or changed bytes block with
  `review_image_missing_or_changed`.

## QA gates

Every publication runs all gates; failures are stored, not short-circuited:

1. `identity`: mapped canonical product and source IDs.
2. `source`: all public copy claims trace to approved source fields.
3. `missing_required_fact`: no unresolved placeholder or required empty fact.
4. `copy_chief`: every category scores at least 3/5.
5. `destination`: HTTPS, exact allowed origin/path, ready page revision, no
   conflicting attribution.
6. `tracking`: all three stable IDs round-trip through the UTM URL.
7. `board`: one exact allowlisted shadow board.
8. `season`: not expired and not before publish start.
9. `duplicate`: unique canonical payload hash among active candidates.
10. `asset_lineage`: approved, visible, file-backed, checksummed product refs.
11. `crop`: exact 2:3/1000×1500 manifest request and linked review-image
    dimensions.
12. `product_preservation`: manifest includes identity locks; real generated
    output remains `needs_human_product_review`.
13. `authority`: no external ID, connector call, or public-write state.

`ready_for_review` requires gates 1–11 and 13 plus a verified local review
image. Gate 12 can only become `human_verified` after real output review; Phase
3 fixture runs report `fixture_workflow_verified_product_accuracy_unverified`.
Manifest-only work remains `handoff_ready`.

### Duplicate and supersession order

Campaigns and provisional publications are inserted first under the existing
PostgreSQL source lock, so every candidate can retain QA evidence.

- Query the unique `ShadowPayloadLease` by canonical payload hash.
- If another ready/reviewed publication owns it, store this candidate as
  `blocked_duplicate`, append the duplicate QA decision, and do not acquire a
  lease.
- If the payload is new and all other gates pass, acquire its unique lease and
  mark the publication `ready_for_review`.
- A newer input supersedes an older publication only after it passes all gates
  and acquires a different semantic payload lease. In the same transaction,
  release the old lease, mark the old publication `superseded`, and activate the
  new one.
- Lifecycle states considered active are `ready_for_review` and
  `reviewed`; `generating`, `blocked_*`, and `superseded` never own leases.
- Concurrent attempts race on the unique lease; the loser reloads the owner and
  persists a blocked duplicate decision on bounded retry.

## Durable jobs and schedules

- `shadow.generate`
  - event-driven from eligible Phase 2 materialization;
  - daily catch-up at 03:10 UTC;
  - maximum 20 campaigns/60 variants per job;
  - database-only and restart-safe.
- `shadow.digest`
  - once per UTC week, first scheduler pass Monday at or after 09:10;
  - summarizes prior-week packages, failures, maturity, and completed review
    sessions;
  - no email/slack send in Phase 3; the digest is an authenticated read surface.

Validation/auth/policy failures are nonretryable. Transient database failures use
the Phase 0 retry policy. Unknown or authority-violating work quarantines.

## Read surfaces

Authenticated read-only routes:

- `GET /api/shadow-campaigns`
- `GET /api/shadow-campaigns/<campaign_id>`
- `GET /api/shadow-digests/latest`
- `GET /shadow-campaigns`
- `GET /shadow-campaigns/<campaign_id>`
- `GET /shadow-digests`

Review-effort mutations require operator/admin authority and CSRF/service-write
scope:

- start review session;
- append a decision for an exact publication/manifest/review image;
- finish review session only after server-derived counts and elapsed time are
  persisted.

No route approves assets, publishes pages, or publishes Pins.

## Representative shadow proof

The deterministic fixture batch uses the reviewed Phase 2 cohort and three
Pinterest-native variant roles. It must complete at least 20 variant-level
production opportunities across at least 10 distinct coverage cells and all
three board mappings. At least two normal page-opportunity fixtures must also
produce local drafts with their Pin side correctly blocked.

Evidence must prove:

- every counted package has page revision/action, copy, board, tracked URL,
  manifest, a real checksummed 1000×1500 fixture review image, provenance, and QA
  decisions;
- replay creates no duplicates;
- at least 20 reach `ready_for_review`, while remaining explicitly
  `product_accuracy_unverified`;
- blocked fixtures cover identity, claims, destination, duplicate, season,
  board, asset lineage, crop, and authority failures;
- no network/provider/Pinterest/website mutation was attempted;
- item-level review decisions link exact publications/images to normalized
  reasons, and a completed session derives real elapsed time and counts without
  fabricating a human-effort result;
- the latest digest groups item-level revisions/rejections by adapter version,
  variant, board, asset, and QA reason so the next reviewed policy/prompt version
  has actionable evidence.

Actual human-time reduction remains a human-validation gate: the system records
it from linked item decisions, but Phase 3 cannot claim a material reduction
until Matthew completes a representative real-output review session. Fixture
review timing may validate workflow ergonomics but is never reported as product
approval or the business outcome. This does not block implementation or the
scoped commit; it blocks claiming the Phase 3 business outcome and any Phase 4
autonomy graduation.

## Validation

- policy schema/hash tests;
- reversible SQLite migration and current-schema checks;
- mandatory PostgreSQL transaction, uniqueness, and concurrent replay tests;
- stable ID/UTM round-trip tests;
- 20+ representative shadow variants and 10+ distinct cells;
- full QA fail/pass matrix, including normal page-only draft production;
- immutable prebuilt fixture-file, missing/changed checksum, rollback, and replay
  tests proving shadow jobs perform no filesystem mutation;
- provenance completeness and asset-lineage tests;
- durable handler/scheduler idempotency and budget tests;
- authenticated/anonymous read tests and authorized review-session mutations;
- zero-network/provider-call assertion;
- item-level review decision integrity, server-derived session counts, digest
  idempotency, actionable reason grouping, and evidence-maturity labeling;
- full Marketing OS suite;
- documentation links and `git diff --check`.

## Independent review gate

Before implementation, a sub-agent must challenge:

1. Does the plan fit the Pinterest-first search/coverage strategy?
2. Does it minimize routine human involvement without inferring publish
   authority?
3. Is the feedback/review loop sufficient to understand impact and adjust?

Repeat after revisions until no P0/P1 plan blockers remain. After implementation,
repeat the same challenge against code and validation evidence.

## Human validation

- Owner: Matthew
- Required action: review one representative shadow batch using the timed review
  session.
- Evidence: completed `ShadowReviewSession` plus sampled product-accuracy and
  source-claim decisions.
- Blocks Phase 3 scoped commit: no.
- Blocks claim of material human-time reduction: yes.
- Blocks Phase 4 autonomy graduation: yes.

## Risks and release gates

- The repository contains unrelated unstaged Art Studio/video/harness work.
  Phase 3 must use new files or isolate hunks and must not stage that work.
- Actual source-image availability may block some real cohort packages; surface
  `asset_lineage` exceptions rather than downloading or generating implicitly.
- Board names are shadow-only recommendations until real board IDs/access are
  discovered and approved.
- Pinterest’s current API uses board, link, title, description, and media-source
  fields for Pin creation, but Phase 3 stores a provider-neutral candidate and
  does not call that API.
- No Marketing OS remote exists; the local scoped commit is the review boundary.

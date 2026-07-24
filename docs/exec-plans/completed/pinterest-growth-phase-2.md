# Pinterest Growth Phase 2: Coverage Intelligence and Catalog Monitor

## Status

- Status: completed
- Owner: Codex
- Branch: `codex/pinterest-growth-phase-2`
- Base commit: Marketing OS `db32352`
- PR: unavailable until an `origin` remote is configured
- Last updated: 2026-07-24
- Planning framework: Digi-CTO plugin `0.3.0`

## Summary

Replace calendar-first planning for the approved Everyday Heroes cohort with a
sparse, evidence-labeled coverage model that can detect catalog changes, explain
what is missing, and enqueue the next safe action without publishing externally.

This phase adds the decision substrate used by later Pinterest production. It
does not generate creative, publish pages or Pins, call a public Pinterest write
API, or graduate any autonomy policy.

## Work State

- Planned: schema, services, durable handlers/schedule, read-only UI/API, docs.
- In progress: none.
- Blocked: none.
- Needs human validation: none for merge; production credentials and deployment
  remain release gates.
- Ready for review: Phase 2 scoped commits; no remote is configured for a PR.
- Completed: schema/migration, versioned policy/taxonomy, complete catalog and
  editorial contracts, catalog/identity reconciliation, sparse coverage,
  separate page/publication scoring, durable schedules/handlers, maturity-window
  feedback, authenticated read surfaces, documentation, and independent review.

## Decisions

- Keep the existing Flask/PostgreSQL/durable-job foundation.
- Model only observed or planned sparse combinations; do not materialize a
  product × intent × season × format Cartesian product.
- Store normalized scores as integers from 0–10,000 with versioned weights,
  explicit missing-data defaults, confidence adjustment, penalties, tie-breakers,
  and component-level explanations.
- Freeze those values in reviewed `config/coverage-policy-v1.json`; freeze exact
  intent keys, website product IDs, evidence references, locale, season/event
  dates, and page mappings in `config/coverage-taxonomy-v1.json`. Both files are
  schema-validated and hashed into each `DecisionRun`. The final independent
  Phase 2 review is the named configuration review gate.
- Keep page opportunity and publication opportunity separate. A missing page may
  rank highly for creation; publication is ineligible until its destination page
  is ready.
- Treat strategy/use-case topics as `hypothesis`, never measured search volume.
  Sales, reviews, catalog facts, and website state retain their source labels.
- Use source revision and per-product hashes for catalog-change idempotency.
  Unchanged revisions enqueue no work; new, updated, and retired products enqueue
  one affected-cell materialization job each.
- Accept retirement-by-absence only from a strict website response containing
  `complete=true`, an exact `productCount`, one full-catalog revision, and all
  contract-valid products. Failed, malformed, truncated, over-budget, or
  explicitly incomplete reads preserve the prior checkpoint and cannot retire
  products.
- Target seasonal readiness 90 days before the event and publication eligibility
  60 days before it. These dates are planning bounds, not claims of demand.
- Coverage and Exceptions are authenticated read surfaces. Phase 2 introduces no
  new mutation authority.
- Ingest the approved Phase 1 Etsy-exit measurement stream with a durable cursor.
  Its evidence is observational at product/page level until later publication
  IDs provide a causal join; it may adjust a bounded performance prior but cannot
  suppress evergreen coverage in Phase 2.
- UX strategy is bounded to information hierarchy and empty/error/explanation
  states. A separate visual-design track is deferred because this is an internal
  console using the existing component language.

## Domain and migration contract

Add Alembic revision `0003_coverage_intelligence` and SQLAlchemy records for:

- `SearchIntent`: normalized query/topic, audience, occasion, locale, season,
  evidence state, confidence, evidence references, revision, lifecycle.
- `LandingPage`: website ID/type/path/revision, product and intent scope,
  draft/published/retired state, readiness, last verification.
- `CatalogChange`: source/revision/product/change type, before/after hashes,
  payload reference, detected time, unique deduplication key.
- `CatalogSnapshot`: last accepted complete source revision, payload hash/count,
  compact per-product hash map, completeness state, and checkpoint time.
- `CoverageCell`: sparse product/intent/season/format/page/channel tuple, state,
  freshness, suppression, source revision, explanation, dimensional key.
- `PageOpportunity`: one current scored page action per coverage cell, score
  version/components/explanation, target-ready date, lifecycle.
- `PublicationOpportunity`: one current scored channel action per coverage cell,
  score version/components/explanation, eligibility and block reason,
  publish-start date, lifecycle.
- `DecisionRun`: append-only input revision, score version, considered/selected/
  suppressed counts, explanation and timestamp.
- `MeasurementCursor`: source cursor, last source event key/time, checkpoint
  time, and ingestion counts.
- `CoverageOutcome`: product/page/cell, metric, maturity window, observed value,
  attribution quality, source period/revision, and observational/causal label.

Database constraints and service validation own enumerations. Foreign keys use
restrictive behavior by default; retirement changes lifecycle state instead of
deleting evidence or decisions. One database transaction writes an accepted
`CatalogSnapshot`, all corresponding `CatalogChange` rows, and their unique
`AutomationJob` outbox rows. A failure rolls back all three; retries can neither
lose nor duplicate work.

## Frozen v1 decision policy

`config/coverage-policy-v1.json` is authoritative:

- Page weights: business relevance 2,000; demand evidence 2,500; seasonal
  urgency 1,500; performance prior 1,000; coverage gap 2,000; internal-link
  value 1,000 basis points.
- Publication weights: business relevance 2,500; demand evidence 2,500;
  seasonal urgency 1,500; performance prior 1,500; coverage gap 2,000 basis
  points.
- Missing defaults: business relevance 5,000; demand hypothesis 2,500;
  evergreen seasonal urgency 5,000; performance prior 5,000; missing coverage
  gap 10,000; missing-page internal-link value 10,000.
- Confidence multiplies only demand evidence. Hypotheses default to 2,500
  confidence basis points. Verified evidence uses its persisted confidence.
- Duplicate/already-covered penalty: 4,000. Stale-evidence penalty: 1,000.
  Insufficient-evidence penalty: 1,500. Scores clamp to 0–10,000.
- Website destination-page coverage values: missing 10,000; planned 6,500;
  published 0. These values never indicate that a Pinterest Pin exists;
  publication is scored independently and an eligible destination selects
  `create_pin`.
- A mapped cohort product has business relevance 8,000; other active products
  default to 5,000 until reviewed evidence changes the policy.
- With no outcome evidence, performance prior is neutral at 5,000. Observational
  Etsy exits can increase it by 250 per qualified click in a rolling 30-day
  window, capped at 10,000, but cannot cause suppression or be labeled causal.
  A qualified click is one unique accepted `etsy_outbound_click` event with a
  valid event UUID/timestamp, `destinationHost` ending in `etsy.com`, mapped
  product ID, exact recognized landing pathname, and all three campaign/content/
  publication IDs (`utm_complete`). Events more than five minutes in the future,
  duplicates, incomplete attribution, unmapped products, unknown paths, and
  events outside the rolling window remain stored diagnostics but contribute
  zero ranking points. Daily outcome buckets expire from scoring after 30 days.
- Seasonal urgency is 2,000 before the 90-day ready date, 8,000 from day -90 to
  day -61, 10,000 from day -60 through the event, and 0 after expiry. Seasonal
  work targets ready at event minus 90 days and publish start at event minus 60.
- Suppress when product identity is unresolved/retired, intent is inactive,
  destination identity is ambiguous, seasonal work is expired, or the exact
  dimensional key duplicates an existing active cell.
- Rank by score descending, then target date ascending with null last, then
  product ID, then intent key. Every read model includes the component values,
  penalties, current outcome signal, and the smallest named component change
  that would alter eligibility or move the score across the next 1,000-point
  threshold.
- Observed evidence is fresh for 30 days unless its record declares a shorter
  expiry; landing-page readiness is fresh for 48 hours. Stale state never becomes
  a negative demand result.

## Implementation

1. Add the records, relationships, uniqueness constraints, lookup/score indexes,
   and reversible Alembic migration.
2. Add `coverage_intelligence.py` with:
   - deterministic canonical JSON/hash helpers;
   - reviewed Everyday Heroes taxonomy seeding from existing `DemandEvidence`,
     product audiences/use cases, verified sales/review signals, published hub
     pages, and explicitly labeled hypotheses;
   - catalog diff for new/updated/retired inputs;
   - idempotent affected-cell job emission;
   - landing-page reconciliation from the website v2 contract;
   - sparse coverage materialization;
   - versioned page/publication scoring and explanations;
   - freshness and suppression rules;
   - product coverage and exception read models.
3. Extend website v2 reads:
   - product snapshots declare `complete` and exact `productCount`;
   - a typed editorial listing returns collection/guide lifecycle, revision,
     canonical path/URL, product scope, intent scope, and readiness inputs.
   Marketing OS accepts neither as authoritative when incomplete or malformed.
4. Register durable `catalog.reconcile`, `coverage.materialize`,
   `editorial.reconcile`, and `measurement.ingest` handlers.
   - Catalog/editorial reconciliation is due once per UTC day after 02:10; the
     first scheduler pass after 02:10 catches up the current UTC date only.
   - Measurement ingestion is due every 15-minute UTC slot and resumes from its
     committed opaque cursor.
   - One catalog run accepts at most 500 products/5 MiB, one measurement run at
     most four 500-event pages/2,000 events, and one materialization job at most
     250 cells. A valid processed measurement page commits its cursor even when
     the run budget is reached; `hasMore=true` records backlog and the next
     15-minute slot resumes from that cursor. Only the malformed/invalid page
     leaves its cursor unchanged. Catalog/materialization over-budget inputs
     record an exception without advancing their checkpoint.
   - Existing Phase 0 retry policy applies: at most three transient attempts;
     validation/auth/policy failures do not retry. No run may emit public writes
     or incur generation/provider cost.
   Worker execution remains restart-safe through the Phase 0 lease contract.
5. Add read-only JSON endpoints:
   - `GET /api/coverage`
   - `GET /api/coverage/<product_id>`
   - `GET /api/coverage/exceptions`
6. Add authenticated operator pages:
   - `GET /coverage`
   - `GET /coverage/exceptions`
   showing current coverage, missing/suppressed items, score explanations, source
   labels, freshness, next action, and explicit empty/error states.
7. Add outcome ingestion and rescoring:
   - validate and upsert Phase 1 events idempotently;
   - commit each event page, daily outcome aggregates, next cursor, and unique
     affected-cell rescore outbox jobs in the same transaction;
   - aggregate 24-hour delivery-health and 7-day diagnostic windows;
   - map only by approved product ID and exact landing pathname;
   - label product/page joins `observational`;
   - enqueue affected-cell rescoring after a changed aggregate;
   - explain current impact and the bounded evidence change that would alter the
     decision. Phase 2 never auto-suppresses from low/absent traffic.
8. Update architecture, automation, validation, and project-context docs.

## Acceptance criteria

- New, updated, and retired catalog fixtures record one correct change and enqueue
  one idempotent affected-cell job; unchanged input records/enqueues nothing.
- A website-only product remains visible as an identity exception, and a later
  successful mapping reprojects stored editorial website IDs and emits one
  deterministic repair materialization even when catalog/editorial revisions
  are otherwise unchanged. A changed catalog snapshot still emits only one job.
- A transition out of a mapped identity also rematerializes existing cells and
  suppresses stale publication opportunities. A monotonic mapping revision keeps
  repeated transition cycles idempotent without collapsing later repair work.
- Incomplete/failed/truncated snapshots cannot create retirement changes or
  advance the accepted checkpoint. Change rows, checkpoint, and jobs are proven
  atomic under rollback and concurrent replay.
- Re-running the same revision creates no duplicate changes, cells, opportunities,
  or jobs, including under the database uniqueness boundary.
- The initial taxonomy contains only evidence-linked records or records visibly
  labeled `hypothesis`.
- A product view shows what exists, what is missing, why it matters, evidence
  quality/freshness, suppression state, and the next action.
- Covered/duplicate combinations receive a documented penalty or suppression.
- A missing-page creation opportunity can rank; its publication opportunity is
  ineligible until a fresh typed editorial/product read verifies the landing
  page is published, canonical, internally identified, and ready.
- Seasonal fixtures produce a target-ready date 90 days and publish-start date
  60 days before the configured event, and publication remains ineligible before
  that publish-start date.
- Retired or ambiguously mapped products suppress external-production actions and
  appear in Exceptions.
- Viewer/operator/service-read identities can read the API according to the
  Phase 0 auth contract; anonymous users cannot.
- The migration upgrades from revision `0002`, downgrades cleanly, and current
  schema validation recognizes revision `0003`.
- Measurement replay does not duplicate events/outcomes, cursor advancement is
  atomic with outcome/rescore-job writes, and changed product/page observations
  enqueue bounded rescoring. A run that stops at 2,000 events resumes from its
  committed cursor rather than rereading the same backlog.
- Each qualified event updates 24-hour and 7-day diagnostic buckets and one
  30-day performance bucket; only the 30-day bucket affects scoring.
- Every opportunity explanation shows current score inputs, evidence labels,
  penalties, readiness blocker, outcome signal, and the smallest policy input
  change that would materially change the result.

## Validation

- Focused unit tests for hashing, taxonomy labels, catalog diff, sparse
  materialization, scoring, readiness, seasonal dates, freshness, suppression,
  UI/API serialization, and unchanged-input idempotency.
- SQLite migration upgrade/downgrade and empty/current schema tests.
- Mandatory PostgreSQL transaction rollback, uniqueness, concurrent snapshot/
  outbox idempotency, and cursor-checkpoint tests against the Phase 0 local
  PostgreSQL test service.
- Durable worker handler and scheduler idempotency tests.
- Authenticated/anonymous API and page smoke tests.
- Full Marketing OS unit suite.
- `scripts/check-doc-links.sh`
- `git diff --check`

Completed evidence:

- focused Phase 0–2 validation: 38/38 passed;
- PostgreSQL 17 integration: 5/5 passed;
- website contract suite: 28/28 passed;
- website production build: 138 application pages;
- full Marketing OS discovery: 167 tests, 161 passed, five PostgreSQL tests
  skipped in that environment and passed separately, plus one unrelated
  pre-existing Art Studio assertion failure;
- final independent implementation review: `PASS`, with strategy,
  automation/idempotency, and feedback each scored 9.5/10 and no P0/P1 blockers.

## Human Validation

- Owner: Matthew
- Exact steps: none required to merge Phase 2; later review the deployed Coverage
  explanations before using them to authorize public production.
- Expected evidence: sampled product rows show correct source labels, missing
  coverage, and next action.
- Evidence location: `docs/reviews/phase2-coverage-validation.md`
- Blocks merge: no. Blocks Phase 4 public publishing: yes.

## Risks and open questions

- Website v2 currently lacks completeness markers and a typed editorial read
  listing. Phase 2 adds both contracts before any page can become authoritative;
  the versioned manifest is seed input only and never sufficient for readiness.
- Search-volume APIs remain unavailable. Scores must not label sales, use cases,
  or strategy hypotheses as Pinterest query volume.
- The existing Marketing OS worktree contains unrelated Art Studio/video/harness
  edits, including `web_app.py`; stage Phase 2 hunks and new files only.
- No `origin` remote exists, so local scoped commits remain the review boundary.

## Documentation

- Update `docs/ARCHITECTURE.md`, `docs/AUTOMATIONS.md`,
  `docs/PROJECT_CONTEXT.md`, and the master autonomous-growth plan.
- Record validation in `docs/reviews/phase2-coverage-validation.md`.
- Move this plan to `docs/exec-plans/completed/` after the Phase 2 commit.

## Closeout

- Independent challenge: `PASS` after three rounds; strategy fit 9.7/10,
  low-human-involvement automation 9.2/10, feedback/explanation loop 9.1/10,
  with no remaining P0/P1 plan blockers.
- Final status: pending implementation and validation.
- Commit only Phase 2-owned files/hunks.
- Phase 3 may start only after acceptance tests and independent strategy/
  automation/feedback-loop review pass.

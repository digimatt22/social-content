# Coverage Intelligence v1 Contract

## Purpose

Phase 2 converts complete website catalog/editorial snapshots and approved
measurement events into sparse, explainable product × intent coverage and
next-action records. It ranks preparation work but has no public write authority.

## Versioned inputs

- `config/coverage-policy-v1.json` freezes weights, defaults, penalties,
  qualification, freshness, schedules, budgets, tie-breakers, and suppression.
- `config/coverage-taxonomy-v1.json` freezes the approved Everyday Heroes
  products, exact website IDs, intent keys, hypothesis labels, and seed pages.
- Website `GET /api/agent/v2/products` is accepted only with `complete=true`,
  exact `productCount`, a 64-character revision, and strict product records.
- Website `GET /api/agent/v2/editorial` is accepted only with `complete=true`,
  exact `pageCount`, revisioned typed pages, canonical URLs, lifecycle, scope,
  and readiness.
- Website `GET /api/agent/v2/growth-events` remains measurement-credential-only
  and is consumed in opaque-cursor order.

## Atomicity and recovery

PostgreSQL transaction advisory locks serialize each source checkpoint.

- Catalog snapshot, changes, and unique materialization outbox jobs commit
  together. Only a complete accepted snapshot can infer retirement by absence.
- A website product that arrives before its Marketing OS identity remains visible
  in Exceptions. When reconciliation later establishes that identity, a
  stored website-product/page relationship is reprojected to the internal ID and
  a deterministic repair materialization job is emitted even if both accepted
  source revisions are unchanged. A changed catalog row and identity repair
  converge on one materialization job. The same transition out of `mapped`
  rematerializes existing cells immediately so stale publication eligibility is
  replaced by `product_identity_unresolved` suppression. A monotonic
  `mapping_revision` participates in repair-job identity, so repeated
  mapped/unresolved cycles under one unchanged catalog revision each enqueue
  exactly once.
- Each valid measurement page commits deduplicated events, qualified 24-hour,
  7-day, and 30-day outcome buckets, its next cursor, and affected-cell rescore
  outbox jobs together.
- A malformed page rolls back without cursor advancement. A valid page at the
  four-page run budget keeps its cursor and resumes the backlog next slot.
- Deterministic job keys and database uniqueness make unchanged replay a no-op.

## Sparse coverage

Only reviewed product/intent combinations are materialized. The dimensional key
uses product, intent, season, `static_pin`, and Pinterest channel. It does not
create a Cartesian product across all known products, topics, seasons, formats,
pages, and channels.

A page opportunity may rank while its destination is missing or unready. A
publication opportunity is ineligible unless one fresh, typed, published,
canonical destination is ready and the product/intent is not suppressed.
Multiple published destinations for the same cell are an identity exception.
`coverageState` describes destination-page coverage only; it does not mean a Pin
has already been published. Pinterest publication remains a separate
`PublicationOpportunity`, and a ready destination selects `create_pin` as the
next action only when its configured publish-start date has arrived.

## Scoring and feedback

Scores are integers clamped to 0–10,000. Read models expose every component,
penalty, evidence label, readiness blocker, observed outcome signal, and next
1,000-point counterfactual.

Only a unique, timestamp-valid `etsy_outbound_click` with an Etsy destination,
mapped product, exact recognized landing pathname, and complete campaign,
content, and publication IDs qualifies for the bounded performance prior.
Qualified clicks are observational, add 250 points each above the neutral 5,000
prior, cap at 10,000, and expire from scoring after 30 days. The 24-hour and
7-day buckets remain diagnostic; only `30d_performance` contributes to scoring,
preventing the same event from being counted three times. Phase 2 never
suppresses coverage because traffic is absent or low.

## Schedules and budgets

- Catalog/editorial: once per UTC date on the first scheduler pass at or after
  02:10.
- Measurement: every 15-minute UTC slot.
- Catalog: at most 500 products and 5 MiB per accepted snapshot.
- Measurement: four pages of 500 events, at most 2,000 events per run.
- Materialization: at most 250 cells per job.
- Retry: Phase 0 durable-job policy, at most three transient attempts;
  validation/auth/policy failures do not retry.

No Phase 2 job calls Pinterest write APIs, generates paid/provider creative, or
publishes website content.

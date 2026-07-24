# Pinterest Controlled Publishing v1

## Purpose

This contract turns an approved Phase 3 shadow publication into an auditable
Pinterest write candidate while keeping all live authority disabled. Version 1
contains no HTTP client, OAuth exchange, secret value, or live provider
adapter.

## Authority layers

A write can execute only when all layers agree:

1. The source shadow publication is immutable and reviewed.
2. The destination board is in the connection's explicit allowlist.
3. The connection has `boards:read`, `pins:read`, and `pins:write`.
4. A matching, unrevoked, unexpired authority grant exists for the exact
   account, scopes, board allowlist, provider contract, and policy class.
5. A live adapter must also see the literal
   `MARKETING_OS_PINTEREST_PUBLISH_ENABLED=EXPLICITLY_ENABLED`, a verified
   Standard-access connection, an injected credential, alert delivery, and a
   positive numeric daily cost ceiling.

Fixture authority is separately named, audited, expiring, and valid only for a
`fixture_only` connection. It cannot activate a live adapter.

## External idempotency

The semantic key is:

```text
pinterest:<shadow publication id>:<immutable payload hash>:<approved board id>
```

One `pinterest_publications` row owns that key. Preparation serializes on the
immutable shadow publication, and execution requires the latest completed
package review to be `accepted_for_shadow`. The review snapshot hashes title,
description, tracked destination, board recommendation, payload, manifest
evidence, and the exact review-asset ID/checksum/location. Preparation adds the
allowlisted board ID and a persisted media-delivery record to an immutable
provider request. That record binds the connection, approved asset, checksum,
content revision, verified URL/evidence/time, and revocation state. Claim
revalidates the review, delivery, and complete request; a caller cannot supply
an arbitrary live URL. A changed destination, source, delivery, or later review
decision cannot reuse it. Live providers require checksum-verified HTTPS media;
fixture media is rejected outside fixture mode.

## State machine

```text
prepared
  ├─ created ───────────────→ published
  ├─ timeout/partial ───────→ publish_unknown ── reconcile ──→ published
  │                                                └─────────→ confirmed_absent
  ├─ auth/validation ───────→ failed
  └─ throttle/server error ─→ prepared (durable bounded retry)
```

Before any provider call, a PostgreSQL row lock transitions `prepared` to
`submitted` and commits an append-only five-minute attempt lease. A second
worker that sees a fresh attempt reports in-progress without changing state.
Only an expired submission transitions to `publish_unknown`; it never calls
Create Pin. Transport exceptions after submission are also ambiguous.

`publish_unknown` is a quarantine state and transactionally enqueues one
reconciliation job. Reconciliation is read-only and append-only attempts
preserve provider evidence. Provider errors and unknown results use bounded
durable retries. Two absence observations are required before
`confirmed_absent`. Even then, version 1 cannot create again; a future
separately audited recovery transition is required.

A delayed provider response uses compare-and-set state rules. It may resolve an
unresolved publication, or confirm the same already-published identity. It
cannot overwrite a reconciled identity or confirmed absence; conflicting late
evidence remains append-only and quarantines the durable job.

## Durable jobs

- `pinterest.publish` classifies ambiguous responses for durable-job
  quarantine after first committing `publish_unknown`.
- Authentication and validation failures are nonretryable.
- Throttling and server failures use the existing bounded retry/backoff
  contract.
- `pinterest.reconcile` reads the semantic key and never creates content.
- Production refuses the fixture provider, and no live provider is installed
  in this increment.

## Metrics

Pinterest snapshots require a reconciled external Pin identity and are
append-only and unique by publication, source revision, and exact UTC source
window. The canonical source-payload hash must also match on replay; conflicting
reuse is rejected. Impressions, saves, Pin clicks, and outbound clicks are
nonnegative source facts. Missing windows are unknown, not zero, and no causal
claim is derived by this layer.

## Remaining activation evidence

- redacted Pinterest authorization and access-tier evidence;
- approved board IDs and provider request/response fixtures;
- token refresh and revocation proof;
- real alert delivery and acknowledgement evidence;
- backup/restore target and recovery objectives;
- deployed five-service topology and rollback evidence;
- explicit sampled-write grant from Matthew for one named policy class.

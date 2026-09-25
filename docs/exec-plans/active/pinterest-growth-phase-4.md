# Phase 4 — Hosted, Controlled Pinterest Vertical Slice

## Status

- Status: in progress; disabled connector complete and hosted deployment contract under exact-release validation
- Branch: `codex/marketing-os-sheldon-deployment`
- Started: 2026-07-24
- Production activation: blocked by external capability and authority gates

## Goal

Build and validate the bounded Pinterest publishing control plane without
granting it live authority. The implementation must fail closed until every
provider, alerting, backup, deployment, and explicit publish-authority gate is
present.

## Safe implementation scope

- Versioned Pinterest connector protocol plus deterministic fixture adapter.
- Persisted publish attempt, external idempotency, ambiguous-response
  quarantine, and read-after-write reconciliation.
- Bounded retry and rate-limit classification through durable jobs.
- Append-only Pinterest delivery/click snapshots with explicit source windows.
- Capability preflight that validates values and independent authority gates,
  rather than treating environment-variable presence as proof.
- Production-like PostgreSQL, migration, web, worker, and scheduler smoke and
  recovery tests.
- Deployment, rollback, alert, backup, and operator runbooks.

## Hard non-goals

- No network call to Pinterest.
- No OAuth exchange or token storage.
- No public, trial, or sampled Pin write.
- No production cutover or public route.
- No claim that Phase 4 acceptance or autonomy graduation has passed.

## External blockers

1. Pinterest app/access tier, client authorization, scopes, refresh behavior,
   approved board IDs, token custody, and provider response evidence.
2. Explicit sampled/public write authority for a named policy class.
3. Alert destination, named owner, acknowledgement policy, and cost ceiling.
4. Off-host encrypted backup destination, key custodian, retention, RPO/RTO.
5. Production hostname locked for now as `mmm.digicolony.net` (Matthew, 2026-09-25); Cloudflare route configuration, administrator handoff, and cutover approval remain open.
6. Live Sheldon mutations remain separately gated, but the upgraded deployer
   now supports and validates the required multi-service topology.

## Work sequence

1. Freeze the connector, state-machine, and authority contracts.
2. Add schema and disabled publishing/reconciliation services.
3. Register durable handlers and fixture-only tests.
4. Add metrics snapshots and operational preflight.
5. Run SQLite and PostgreSQL migration/recovery validation.
6. Have the plan challenger assess strategy fit, automation, and feedback loop.
7. Commit the disabled readiness increment while leaving this plan active.
8. Resume hosted/sample operation only when the external blockers are supplied.

## Hosted deployment increment

- Work Items and Relay Hub SMS were redeployed and read-only verified healthy
  on 2026-07-24.
- `sheldon.json` now declares web, worker, scheduler, one-shot migration,
  dedicated database hooks, and application-owned PostgreSQL 17.10.
- Migration, runtime, backup, and cluster-bootstrap identities are separated.
- Worker/scheduler health now fails on expired leases or queue lag beyond the
  declared Sheldon attention contract.
- Backup and isolated restore hooks produce/verify schema revision plus
  protected row counts.
- Garage, AWS S3, off-host encrypted retention, alert recipient/fallback, first
  administrator handoff, and public Pinterest authority remain explicit gates.

## Disabled increment result

Implementation and five independent challenge rounds completed on 2026-07-24.
Final scores were 9.8 strategy, 9.7 automation/recovery, and 9.6 feedback, with
no P0/P1 defects. Validation evidence is recorded in
`docs/reviews/phase4-disabled-readiness-validation.md`.

## Acceptance for the disabled readiness increment

- The default environment cannot enqueue or execute a Pinterest write.
- A fully populated test environment still requires an explicit, expiring,
  policy-class authority record.
- Repeated requests reuse one semantic external idempotency key.
- Timeout/partial-response fixtures become `publish_unknown` and quarantined;
  they never retry blindly.
- Reconciliation can resolve an ambiguous result to published or confirmed
  absent without creating a second Pin.
- Authentication/permission/validation errors are nonretryable; provider
  throttling and server failures retry with bounded durable-job policy.
- Metrics snapshots are append-only and idempotent by source/window/revision.
- All external behavior is exercised through fakes; test logs prove zero live
  provider calls.

## Validation

- `python -m unittest tests.test_phase4_pinterest_connector`
- `python -m unittest tests.test_phase4_pinterest_connector_postgres`
- `alembic upgrade head`
- `alembic downgrade 0004_pinterest_shadow_production`
- `alembic upgrade head`
- `git diff --check`

## Independent challenge

The first readiness audit concluded that implementation may proceed behind a
hard-disabled gate, but hosted activation and Phase 4 completion cannot be
claimed from general approval. The challenger must repeat the strategy,
automation, and feedback-loop review after implementation.

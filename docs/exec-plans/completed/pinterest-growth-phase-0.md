# Pinterest Growth Phase 0: Permanent Service Foundation

## Status

- Status: completed
- Owner: Codex
- Branch: `codex/pinterest-growth-phase-0`
- Base commit: `e9d17a2`
- PR: Not applicable until an `origin` remote exists
- Last updated: 2026-07-24

## Goal

Make Marketing OS safe to run continuously before adding Pinterest behavior:

- PostgreSQL production persistence and controlled SQLite cutover;
- reviewed schema migrations;
- durable scheduler/worker jobs;
- authenticated and authorized hosted Flask access;
- auditable human/service identities;
- production packaging, backup/restore, and validation contracts;
- accurate project system-of-record documentation.

## Scope

### Database

- Add PostgreSQL driver/configuration and connection health checks.
- Add Alembic migration infrastructure.
- Preserve SQLite for local fixtures and migration source.
- Add dry-run/migrate/verify commands with deterministic IDs and reports.
- Add backup/restore runbook and test fixture.

### Durable jobs

- Add persisted automation job/run models.
- Implement atomic claims, leases, heartbeats, expiry recovery, bounded retry, quarantine, dead letters, replay, cancel, and idempotency.
- Add worker and scheduler entrypoints with graceful shutdown.
- Add handler registry and test handlers without invoking external providers.

### Authentication and authorization

- Add PostgreSQL-backed users, roles, opaque login sessions, service credentials, and audit events.
- Add Argon2id password hashing, session rotation/revocation, CSRF protection, throttling, and security headers.
- Add TTY-safe admin/service bootstrap CLIs.
- Protect hosted entrypoints while preserving an explicit local-development mode.

### Operations

- Add production WSGI and container entrypoints.
- Add Sheldon deployment manifest only after local tests and container health pass.
- Add liveness/readiness endpoints with minimal unauthenticated output.
- Add queue/database/auth observability.

### Baseline contracts

- Replace generic harness placeholders with current Marketing OS facts.
- Record product identity exceptions and initial measurement availability.
- Add capability preflight consumed by automation.
- Repair the pre-existing broken harness-backlog documentation link if the correct project-owned target can be added without changing upstream harness behavior.

## Non-Goals

- Public Pinterest writes
- New Pinterest, Google, or Etsy OAuth credentials
- Automatic website publication
- Production content generation
- Plugin extraction
- Public self-registration
- Migrating the public Next.js website to PostgreSQL

## Work State

- Completed: PostgreSQL/Alembic/cutover, durable jobs, authenticated service, production packaging, identity and measurement contracts, website tracking/schema repair, production-like validation, and current-state docs.
- In progress: None.
- Planned: Phase 1 website hub MVP.
- Blocked: Remote PR/push because Marketing OS has no `origin`; live external providers remain gated.
- Human-only: First production administrator secret transfer, Cloudflare route/access configuration, and any live provider authorization.

## Acceptance Criteria

### PostgreSQL

- Empty PostgreSQL and representative current SQLite upgrade paths pass.
- SQLite migration dry run reports counts/conflicts without writes.
- Cutover preserves primary/external IDs and required relationships.
- PostgreSQL becomes authoritative only after verification.
- Backup restore is proven against a disposable database.
- Application startup refuses an incompatible production schema.

### Durable jobs

- Concurrent workers cannot claim the same job.
- Worker termination releases work through lease expiry.
- Heartbeats extend only the owning lease.
- Retryable errors back off within the configured attempt ceiling.
- Validation/auth/policy failures do not retry.
- Ambiguous writes quarantine.
- Dead-letter replay/cancel requires permission and records an audit event.
- Repeated schedule evaluation emits one idempotent job.

### Authentication

- Anonymous requests cannot access hosted operator data or mutations.
- Login, logout, expiry, revocation, and password verification pass.
- `viewer`, `operator`, `admin`, and `service` permissions are enforced server-side.
- State-changing browser requests require valid CSRF evidence.
- Login throttling and secure cookie/header configuration pass.
- Service tokens are shown once, stored hashed, scoped, revocable, and audited.
- No route relies on client-side role checks for authorization.

### Operations and documentation

- Web, worker, scheduler, and PostgreSQL containers/processes start independently.
- Readiness fails when database/schema requirements fail.
- Secrets are excluded from source/release archives.
- Project context, architecture, automations, validation, repo map, setup, and operating guide match reality.
- Full unit suite, PostgreSQL integration tests, security tests, container smoke, and doc checks pass or have a named pre-existing exception.

## Validation Log

- Phase -1 PostgreSQL `SKIP LOCKED` proof passed.
- 19 Phase 0/durable focused tests passed.
- 3 PostgreSQL integration tests passed against PostgreSQL 17.
- Frozen empty-schema upgrades passed on SQLite and PostgreSQL.
- Concurrent claim/idempotent-enqueue tests passed on PostgreSQL.
- Logical dump/restore and sampled row verification passed.
- Production web/worker/scheduler container smoke passed; disposable containers removed.
- Representative current SQLite cutover copied 72 products, 832 assets, 858 reviews, 3,182 sales rows, and related records; relationship orphans were zero, revision was current, readiness passed, and the next product ID advanced to 73.
- Full suite: 141 tests run; 137 passed, 3 PostgreSQL-profile tests skipped without their disposable URL, and 1 named pre-existing Art Studio worktree test failed.
- Website `npm run build` passed and generated 65 static pages.
- Markdown links, shell syntax, Python compilation, and diff checks passed.
- Independent challenge findings were incorporated into reproducible migrations, hosted auth, queue processes, growth contracts/baseline, operations, and current-state docs.
- Final blocker pass bound CSRF to server sessions, prevented bearer-role inheritance, advanced PostgreSQL sequences after explicit-ID cutover, enforced PostgreSQL for every production process, removed the remaining hard-coded website size claim, and strengthened restore attestation/checksum/authority checks.

## Commit Contract

- Stage only Phase 0 files and selected hunks.
- Do not stage pre-existing user modifications.
- Create one scoped Phase 0 completion commit after all required checks pass.
- Move this plan to `docs/exec-plans/completed/` in that commit.

## Closeout

- Status: completed.
- Next phase: Phase 1 website hub MVP after Phase 0 passes.

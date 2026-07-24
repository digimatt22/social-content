# Architecture

## System boundaries

| Component | Responsibility | Authority |
| --- | --- | --- |
| Flask web | Private operator UI/API, auth, review and control | Marketing OS |
| PostgreSQL 17 | Production domain state, jobs, sessions, audit, measurement | Marketing OS |
| Durable scheduler | Idempotent schedule emission under advisory lock | Marketing OS |
| Durable workers | Leased/restart-safe execution and exception handling | Marketing OS |
| Next.js website | Public product/editorial destination and Etsy-click emission | Website repo |
| Etsy | Listings, sales, reviews, order facts | Etsy |
| Pinterest | Pins, boards, trends, organic metrics | Pinterest |

The public website and private control plane are intentionally separate. Marketing OS remains Flask/Python; there is no Node rewrite plan.

## Persistence and schema

SQLite supports local development, fixtures, and cutover source data. Hosted production requires PostgreSQL and a current Alembic revision. Application startup never silently migrates PostgreSQL.

SQLite cutover is dry-run first, requires an empty migrated destination, preserves IDs, copies in dependency order, verifies row counts inside the transaction, and leaves SQLite authoritative until explicit post-copy verification.

## Durable execution

`automation_jobs` stores payload schema version, priority, state, schedule, attempts, idempotency key, lease owner/expiry, heartbeat, results/errors, and correlation IDs. Workers claim using `FOR UPDATE SKIP LOCKED`. Expired leases requeue or dead-letter; ambiguous writes quarantine; unknown handlers/schema versions quarantine.

The scheduler uses a PostgreSQL transaction advisory lock and deterministic idempotency keys. Web, worker, and scheduler processes start independently.

## Security

Production startup requires PostgreSQL, a strong application secret, trusted hosts, and an explicit proxy-hop count. Only liveness, readiness, login, and static assets are public.

Human passwords use Argon2id. Browser sessions are opaque, hashed in PostgreSQL, idle/absolute bounded, revocable, secure/HTTP-only/same-site, and CSRF-protected. Roles are `viewer`, `operator`, and `admin`. Service tokens are shown once, stored hashed, scoped, and revocable. Sensitive job controls require an active administrator and audited reason.

## Growth feedback

`product_identities`, `demand_evidence`, and `growth_events` implement the cross-system identity and feedback contract. Campaign/content/publication IDs and UTM fields remain stable through landing and Etsy-exit events. Source time and ingestion time are distinct. Late/stale/missing evidence is never treated as negative performance.

See `docs/architecture/growth-measurement-contract.md`.

The public hub route and v2 draft/read contracts are defined in `docs/architecture/website-hub-v2-contract.md`.

## Coverage intelligence

Phase 2 stores complete catalog checkpoints, typed landing-page readiness,
sparse coverage cells, separate page/publication opportunities, append-only
decision runs, measurement cursors, and observational coverage outcomes.
Snapshot/change/job and cursor/outcome/rescore writes use one PostgreSQL
transaction and source advisory lock. Incomplete snapshots cannot retire
products or advance authority. Coverage state describes website destination
readiness, not Pinterest publication; eligible Pin work remains a distinct
ranked publication opportunity.

See `docs/architecture/coverage-intelligence-v1.md`.

## Pinterest shadow production

Phase 3 converts ranked Phase 2 opportunities into immutable, deterministic
campaign packages with Pinterest-native copy, exact shadow-board
recommendations, tracked destinations, product-preserving creative handoffs,
checksummed review fixtures, append-only QA, payload leases, timed item-level
review, and observational weekly digests. It performs no Pinterest, website, or
provider writes. Fixture workflow proof never becomes automated product
approval.

See `docs/architecture/pinterest-shadow-production-v1.md`.

## Hosting

Sheldon is the initial internal always-on target using rootless Docker. The web origin binds loopback only; PostgreSQL uses an internal network and persistent named volume. Caddy/Cloudflare routing and deployment are separate approval gates.

See `docs/architecture/adr-001-permanent-marketing-service-foundation.md` and `deploy/sheldon/compose.yml`.

## Principal risks

- No configured Pinterest/Google reporting authorization.
- No real alert destination, acknowledgement owner, or cost ceiling.
- Off-host encrypted backup policy is not yet selected.
- Identity mapping is 80.6%; exceptions must remain excluded.
- Provider response ambiguity can create duplicate external writes; such jobs quarantine.
- Local development credentials must not be copied to hosted production.
- Phase 3 review fixtures prove packaging and ergonomics only; a human must
  verify real-output product accuracy before Phase 4 autonomy graduation.

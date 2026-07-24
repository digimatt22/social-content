# ADR-001: Permanent Marketing Service Foundation

## Status

Accepted for Phase 0 implementation on 2026-07-24. External publishing remains separately gated.

## Context

Marketing OS is a Python 3.11+ Flask and SQLAlchemy application using local SQLite and operator-run jobs. The Pinterest-first strategy requires an always-on private control plane with durable schedules, restart recovery, authentication, auditability, and safe external writes.

MattMadeMe.com is already a separate Next.js application backed by AWS DynamoDB and S3. Rewriting Marketing OS in Node would merge unrelated security boundaries and discard working Python services without improving the growth loop.

The available Sheldon Debian server has:

- Linux;
- Docker 29.6.2 with a rootless context;
- PostgreSQL 17 client tools;
- active Caddy;
- a `0700` Sheldon configuration directory and `0600` application secret files.

No PostgreSQL server is currently active on Sheldon. A disposable local PostgreSQL 17 test proved the row-locking behavior required for durable job claims.

## Decision

### Application boundary

- Retain Python, Flask, SQLAlchemy, and server-rendered operator UI.
- Keep MattMadeMe.com as the separate public Next.js brand/content site.
- Integrate the two systems through versioned authenticated HTTP contracts.

### Initial hosting target

- Deploy the private Marketing OS to Sheldon using the installed `sheldon-deploy` workflow.
- Run the application in rootless Docker.
- Publish the application container only to a loopback host port.
- Route traffic through Caddy and, when configured, a narrowly scoped Cloudflare Tunnel route.
- Do not expose the Flask development server or bind an unauthenticated origin to the LAN or public internet.

Sheldon is the initial always-on internal service target, not a claim of multi-region or high-availability production infrastructure.

### PostgreSQL

- Use an application-owned PostgreSQL 17 container on a private rootless Docker network.
- Store PostgreSQL data in a named persistent volume excluded from immutable release archives.
- Use PostgreSQL as the hosted production authority after a controlled SQLite cutover.
- Retain SQLite for lightweight local development, fixtures, and the cutover source only.
- Add Alembic migrations; application startup must not silently apply production schema changes.
- Require a dry-run SQLite export/import, deterministic ID preservation, row and relationship verification, a write-stop cutover, and a tested rollback window.
- Add encrypted daily logical backups and a tested off-host restore target before unattended publishing. The exact off-host destination remains a Phase 0 deployment decision.

### Durable jobs

- Implement the first durable queue in PostgreSQL rather than introducing Redis or RabbitMQ.
- Claim jobs atomically with `SELECT ... FOR UPDATE SKIP LOCKED`.
- Use PostgreSQL advisory locking for single-leader schedule emission.
- Persist job type and schema version, payload reference, priority, state, schedule, attempts, idempotency key, lease owner/expiry, heartbeat, result/error, correlation ID, and timestamps.
- Separate `web`, `worker`, and `scheduler` processes.
- Recover expired leases, retry transient failures with bounded backoff, quarantine ambiguous external writes, and require permissioned/audited dead-letter replay.
- Add another broker only if measured concurrency or latency demonstrates a need.

### Human authentication

- Implement application-level authentication so origin security does not depend solely on an external proxy.
- Use Flask-Login with server-side PostgreSQL user/session records.
- Hash human passwords with Argon2id.
- Provide no public registration.
- Bootstrap the first administrator through a TTY-safe CLI that does not place a password in shell history.
- Define `viewer`, `operator`, and `admin` roles.
- Protect state-changing browser requests with CSRF tokens.
- Use secure, HTTP-only, same-site cookies, idle and absolute session expiry, logout/revocation, reauthentication for high-risk operations, login throttling, and security headers.
- Cloudflare Access may be added as defense in depth but is not the only authentication layer.

This intentionally selects local password storage for the single-operator first release because no OIDC provider is configured and the application must remain deployable without a new identity dependency. A later OIDC migration must preserve role and audit contracts.

### Service authentication

- Replace shared browser/service credentials with separately revocable service identities.
- Generate high-entropy service tokens once, display them only at creation, and store only a token prefix and cryptographic hash in PostgreSQL.
- Scope service identities by operation and environment.
- Keep the existing MattMadeMe website bearer token during a compatibility window, then rotate to a scoped service identity.

### Secrets

- Store Sheldon runtime secrets only in `~/.config/sheldon/secrets/<app>.env` with mode `0600`.
- Never package or upload local `.env` files.
- Replace local long-lived AWS user credentials with a deployment-scoped credential or workload identity before hosted operation.
- Rotate credentials during the hosted cutover rather than copying existing development secrets.

### Alerts and external writes

- Persist all failures and exception states in PostgreSQL and show them in the authenticated operator console.
- Do not enable unattended Pinterest writes until a real alert destination, acknowledgement owner, cost ceiling, and automatic pause policy are configured and tested.
- Until then, shadow/export and sampled manual publishing are the safe fallback.

## Alternatives Considered

### Rewrite Marketing OS in Node

Rejected. It adds a large rewrite, weakens the public/private boundary, and does not improve durable automation.

### Keep SQLite in hosted production

Rejected. SQLite cannot provide the intended multi-process locking, durable job claims, operational concurrency, and production migration contract.

### Add Redis and Celery immediately

Deferred. PostgreSQL already owns durable state and supports the required first-slice concurrency. Another stateful service is not justified yet.

### Depend only on Cloudflare Access

Rejected as the sole control. Origin/application authorization and service identities still need independent enforcement and audit.

### Require OIDC before development

Deferred. No provider is configured. Application-level authentication has a safe, testable path and avoids blocking Phase 0.

## Consequences

- Phase 0 must add PostgreSQL drivers, Alembic, authentication/security dependencies, job models, worker/scheduler entrypoints, and production container configuration.
- SQLite-specific lightweight schema mutation becomes legacy cutover support, not the production migration system.
- Deployment includes database backup and restore operations, not only application archives.
- Authentication and durable job behavior become release-blocking test areas.
- Pinterest automation can be developed in shadow mode while external account permissions remain unresolved.

## Validation Evidence

- Sheldon read-only preflight: Linux, rootless Docker, PostgreSQL 17 client, active Caddy, protected secret directory.
- Local PostgreSQL 17 disposable-container proof:
  - first worker locked job `1`;
  - concurrent `FOR UPDATE SKIP LOCKED LIMIT 1` selected job `2`;
  - container removed after the test.
- Current source review: Flask/SQLAlchemy engine supports an explicit database URL but production migrations, auth, and durable workers do not yet exist.

## Review Triggers

Revisit this ADR if:

- Sheldon cannot meet backup, storage, security, or uptime needs;
- PostgreSQL job throughput or latency becomes insufficient;
- team-wide OIDC becomes available;
- Marketing OS becomes a multi-tenant product;
- the public website and private control plane ownership boundaries materially change.

# Phase 0 Validation Evidence

## Automated

| Check | Result |
| --- | --- |
| Durable job focused suite | Passed |
| Phase 0 migration/auth/identity/feedback suite | Passed |
| Frozen Alembic empty-schema upgrade | Passed on SQLite and PostgreSQL 17 |
| PostgreSQL concurrent claim | Passed; one job claimed by one of two workers |
| PostgreSQL concurrent idempotent enqueue | Passed; one job, one creator |
| PostgreSQL sequence advancement | Passed; next ID exceeded explicit migrated maximum |
| Representative current SQLite cutover | Passed; 72 products, 832 assets, 858 reviews, 3,182 sales rows plus related records |
| Representative relationship/readiness check | Revision current, zero sampled orphans, readiness passed, next product ID 73 |
| Logical PostgreSQL dump/restore | Passed against disposable restore database |
| Restored Alembic revision | `0002_growth_contracts` |
| Source/restored sampled row counts | Matched (`automation_jobs:principals:product_identities` = `1:0:0`) |
| Production image build | Passed |
| Production web container | Liveness 200, readiness 200, anonymous API 401 |
| Scheduler container one-shot | Passed |
| Worker container one-shot | Passed |
| Website production build | Passed; 65 static pages generated |
| Full Python suite | 141 run; 137 passed, 1 named failure, 3 PostgreSQL-profile skips |

The disposable PostgreSQL/web containers and their test-only data were stopped and removed after validation.

The single full-suite failure is in the pre-existing uncommitted Art Studio/video work: its newly added test expects `$social-media-art-director` in an image handoff, while that uncommitted implementation currently emits the direct prompt without the skill invocation marker. Phase 0 did not modify or stage that test/behavior. Phase 0-focused tests pass, and the exception remains owned by the separate Art Studio work.

## Live read-only baseline

- Website agent API returned 61 public products.
- Identity reconciliation mapped 58 of 72 Marketing OS products by Etsy listing ID and reported 14 explicit exclusions.
- Local verified Etsy import contains 3,182 sales rows and 4,738 units from 2025-03-14 through 2026-06-20.

## Security boundaries

- Production startup refuses SQLite, weak/default secrets, missing trusted hosts, and an unspecified proxy chain.
- Hosted routes deny anonymous access except liveness, readiness, login, and static assets.
- Browser mutations require a matching CSRF token.
- Service tokens are hashed/scoped/revocable.
- Bearer credentials always use their scopes and cannot inherit linked human roles.
- CSRF evidence is hashed and bound to the authenticated server-side session.
- Login forms use a short-lived signed CSRF token and reject forged/direct cross-site submissions.
- Job replay/cancel checks the active administrator role in the transaction and records success/denial audit events.
- Docker context excludes environment files, local databases/backups, exports, outputs, and customer data.

## Remaining deployment gates

- A production hostname and Cloudflare/Caddy policy are not selected.
- Off-host encrypted backup destination, age-key custody, retention, RPO, and RTO are not selected.
- Alert webhook/delivery owner, acknowledgement policy, and cost ceiling are not configured.
- Pinterest API authorization is not available.
- GA4 reporting and Google Search Console authorization are not available.

These are safe degraded-mode gates. The `pinterest_publish` preflight remains non-ready, so no unattended publishing is enabled.

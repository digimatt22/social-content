# Automations

## Runtime entrypoints

| Entrypoint | Trigger | State/effects | Recovery |
| --- | --- | --- | --- |
| `marketing-os-web` / `run_local.py` | Manual local | Local Flask and SQLite | Restart; local only |
| `gunicorn marketing_os.wsgi:app` | Hosted service | Authenticated UI/API | Container restart; readiness gates DB/schema |
| `marketing-os-scheduler` | Continuous | Emits deterministic jobs under advisory lock | Re-evaluation is idempotent |
| `marketing-os-worker` | Continuous | Claims/executes leased jobs | Lease expiry, bounded retry, dead letter/quarantine |
| `marketing-os-status` | Monitor/cron | Read-only JSON queue/evidence status | Nonzero with `--fail-on-attention` |
| `marketing-os-preflight` | Startup/policy gate | Read-only capability report | Select reported safe degraded mode |
| `marketing-os-admin` | Manual TTY | Human/service identities and audit | Tokens revocable; passwords never CLI args |
| `migrate_sqlite_to_postgres` | Controlled cutover | Dry-run or verified copy | SQLite remains authority until acceptance |

## Existing business jobs

| Module | Purpose | External-write posture |
| --- | --- | --- |
| `marketing_os.jobs.weekly_social_planner` | Build review-gated social plan | Local state/export |
| `marketing_os.jobs.content_automation` | Prepare content/creative handoffs | Local state/files; provider handoff |
| `marketing_os.jobs.content_production` | Produce planned content records | Review gated |
| `marketing_os.jobs.import_etsy_sales_csv` | Import Etsy sales evidence | Local database |
| `marketing_os.jobs.phase5_readiness` | Readiness assessment | Read-only/report |
| Art Studio registration jobs | Register generated image/video results | Local files/database; separate in-progress work |

No public Pinterest publish handler exists in Phase 0.

`MattMadeMeAgentApiAdapter.list_products_v2` provides strict,
content-revision-aware public catalog reads and preserves the last valid revision
when a malformed response is rejected. `create_blog_draft_v2` and
`create_editorial_draft_v2` use the separately scoped draft credential and a
16–128 character stable idempotency key. They create only admin-preview drafts;
neither can publish.

`list_growth_events_v2` uses a measurement-only credential and reads ordered
cursor pages from the website’s approved first-party receiver. Marketing OS
never reads the website DynamoDB table directly.

## Schedules

The durable scheduler process evaluates on a configurable polling interval.
`system.noop` remains an hourly lease proof. Phase 2 adds:

- `catalog.reconcile` and `editorial.reconcile` once per UTC date, first pass at
  or after 02:10;
- `measurement.ingest` every 15-minute UTC slot;
- `coverage.materialize` as a change/outcome-triggered outbox job.

Identity reconciliation also emits a deterministic repair materialization when
a previously unresolved website product becomes mapped, including when the
catalog and editorial content revisions are unchanged. Stored website product
IDs allow authoritative page mappings to be reprojected without replaying the
editorial source. A changed catalog job and repair job are deduplicated before
enqueue. Identity loss uses the same repair path so existing publication
opportunities cannot remain eligible after their mapping becomes unresolved.
Repair keys include the product identity’s monotonic mapping revision, preventing
later state transitions under an unchanged catalog revision from colliding with
completed repair jobs.
Measurement ingestion records 24-hour and 7-day diagnostic buckets plus the
single 30-day scoring bucket.

Catalog/editorial reads use the catalog credential; measurement reads use its
separate credential. All four handlers are internal read/decision jobs and have
no public Pinterest or website publish authority. Exact budgets, cursor
semantics, qualification, and catch-up rules are in
`docs/architecture/coverage-intelligence-v1.md`.

## Failure semantics

- retryable/transient: bounded exponential backoff with deterministic jitter;
- validation/auth/policy: nonretryable dead letter;
- ambiguous external write: quarantine for reconciliation;
- unknown handler/schema: quarantine;
- lost worker: lease-expiry recovery;
- replay/cancel: active administrator plus audited reason.

## Operations

`deploy/sheldon/compose.yml` defines PostgreSQL, one-shot migration, web, worker, and scheduler services. It is packaging, not proof of a production deployment.

Encrypted backup/restore commands:

- `scripts/postgres-backup.sh`
- `scripts/postgres-restore.sh`

See `docs/operating-guides/permanent-service-operations.md`.

## Harness utilities

Repository workflow utilities remain under `scripts/`, including current-state, documentation-link, inbox, installer/update, and issue-session checks. They do not run the marketing service.

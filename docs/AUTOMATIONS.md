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

## Schedules

The durable scheduler process evaluates on a configurable polling interval. The Phase 0 built-in `system.noop` schedule proves leadership/idempotency only. Business cadences remain defined by later phase policy and must not be guessed.

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

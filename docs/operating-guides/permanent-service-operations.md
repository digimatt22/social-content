# Permanent Marketing Service Operations

## Runtime

Hosted operation uses separate `web`, `worker`, `scheduler`, and PostgreSQL 17 processes. The public MattMadeMe Next.js site remains a separate service.

Local setup:

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m unittest discover -s tests -q
```

SQLite remains supported for local development. Authenticated production refuses SQLite and requires:

- `MARKETING_OS_ENV=production`;
- a PostgreSQL `MARKETING_OS_DB_URL`;
- a strong `MARKETING_OS_SECRET`;
- explicit `MARKETING_OS_TRUSTED_HOSTS`;
- explicit `MARKETING_OS_PROXY_HOPS`.

## Schema and cutover

Apply migrations separately before application processes:

```sh
MARKETING_OS_DB_URL='postgresql+psycopg://…' .venv/bin/alembic upgrade head
```

Startup refuses unversioned, behind, or ahead PostgreSQL schemas.

Dry-run a current SQLite copy:

```sh
.venv/bin/python -m marketing_os.jobs.migrate_sqlite_to_postgres \
  --source 'sqlite:////absolute/path/marketing_os.sqlite' \
  --destination 'postgresql+psycopg://…'
```

Add `--apply` only after the destination is migrated and empty. The command preserves explicit primary/external IDs, copies in foreign-key order, verifies row counts in the transaction, and refuses a nonempty/missing destination table.

Cutover order:

1. Stop SQLite writes.
2. Take and verify a SQLite backup.
3. Run the dry-run report.
4. Apply the copy to the migrated PostgreSQL database.
5. Verify row counts, identity exceptions, foreign-key relationships, and application readiness.
6. Start PostgreSQL-backed processes.
7. Keep the SQLite backup read-only through the rollback window.
8. Declare PostgreSQL authoritative only after operator validation.

If verification fails, do not switch authority. Discard the incomplete destination, correct the migration, and repeat from the read-only SQLite backup.

## Identities

Create the first administrator from an interactive terminal:

```sh
MARKETING_OS_DB_URL='postgresql+psycopg://…' marketing-os-admin create-admin owner
```

The password is prompted twice and is never accepted as a CLI argument. Create scoped service credentials with `marketing-os-admin create-service-token`; the raw token is displayed once and only its hash is stored.

Roles are `viewer`, `operator`, and `admin`. Job replay/cancel requires an active administrator and an audited reason. Browser mutations require CSRF evidence. Password changes revoke existing operator sessions.

## Jobs and observability

```sh
marketing-os-scheduler
marketing-os-worker
marketing-os-status --fail-on-attention
marketing-os-preflight --profile pinterest_publish
```

Unknown job/schema handlers and ambiguous provider writes quarantine. Retryable failures use bounded backoff; validation/auth/policy failures dead-letter. Lease expiry recovers abandoned work. Repeated schedule evaluation is idempotent.

`marketing-os-status` reports queue lag, job states, and stale/undated evidence. A non-ready Pinterest publish preflight means publishing remains disabled or shadow/export-only according to the reported degraded mode.

## Backups

Production logical backups must be encrypted:

```sh
MARKETING_OS_DB_URL='postgresql+psycopg://…' \
MARKETING_OS_BACKUP_AGE_RECIPIENT='age1…' \
scripts/postgres-backup.sh /protected/off-host/path
```

Restore into a non-authoritative database first:

```sh
MARKETING_OS_RESTORE_TARGET_CLASS=disposable \
  scripts/postgres-restore.sh backup.dump.age 'postgresql+psycopg://…/restore_test'
```

The restore verifies the adjacent SHA-256 file and compares resolved database/server identity with `MARKETING_OS_DB_URL`. An authority restore requires `MARKETING_OS_RESTORE_TARGET_CLASS=authority` plus the explicit high-risk acknowledgement documented by the script. Run Alembic revision, row-count, relationship, identity, and application-readiness checks before any authority change. The off-host destination, age identity custody, retention, recovery time objective, and recovery point objective remain deployment approvals and must be recorded before unattended production publishing.

## Sheldon packaging

`deploy/sheldon/compose.yml` binds the web origin only to loopback and keeps PostgreSQL on an internal network. Runtime secrets belong in `~/.config/sheldon/secrets/<app>.env` with mode `0600`; use `deploy/sheldon/secrets.env.example` only as a field list.

Deployment, Caddy/Cloudflare routing, first administrator transfer, and production authority cutover require explicit operator confirmation. Do not copy local development `.env` files or long-lived AWS credentials to Sheldon.

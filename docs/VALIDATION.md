# Validation

## Canonical checks

```sh
.venv/bin/python -m unittest discover -s tests -q
bash -n scripts/*.sh
scripts/check-doc-links.sh
```

The repo-local `.venv` is canonical because system Python may be externally managed and may not contain Pillow/Alembic/PostgreSQL dependencies.

## Production foundation checks

Set `MARKETING_OS_TEST_POSTGRES_URL` to a disposable PostgreSQL 17 database:

```sh
MARKETING_OS_TEST_POSTGRES_URL='postgresql+psycopg://…' \
  .venv/bin/python -m unittest \
    tests.test_phase0_postgres \
    tests.test_phase2_postgres \
    tests.test_phase3_shadow_postgres -q
```

Required evidence:

- empty Alembic upgrade to head;
- schema mismatch startup refusal;
- concurrent `SKIP LOCKED` claim;
- concurrent idempotent enqueue;
- atomic/concurrent complete catalog snapshot, change, and outbox creation;
- atomic/concurrent measurement event, outcome, cursor, and rescore creation;
- same-input shadow replay serialization and one active semantic-payload lease
  under concurrent changed inputs;
- lease expiry/retry/dead-letter/quarantine/replay tests;
- logical dump/restore and revision/row comparison;
- production image build;
- web liveness/readiness and anonymous denial;
- one-shot worker and scheduler containers;
- secret/data exclusion from build context.

## Security checks

- Route inventory anonymously denies everything except health/readiness/login/static.
- Viewer/operator/admin/service permissions are server-side.
- Browser mutations reject missing/mismatched CSRF.
- Login lockout, idle/absolute expiry, logout, password-change revocation, and service-token revocation pass.
- No raw credentials or IP addresses appear in audit detail.

## Website checks

In the separate website repo:

```sh
npm run build
```

Inspect Product JSON-LD for verified facts only and verify Etsy exits emit `etsy_outbound_click` with the product ID/destination.

## Documentation and exceptions

Record results and pre-existing exceptions in the phase review. A separate dirty-work failure must have evidence and owner; it must not be silently fixed or staged in an unrelated phase.

Phase 0 evidence is in `docs/reviews/phase0-validation.md`.
Phase 2 evidence is in `docs/reviews/phase2-coverage-validation.md`.
Phase 3 evidence is in `docs/reviews/phase3-shadow-validation.md`.

## Phase 4 disabled Pinterest controls

```sh
.venv/bin/python -m unittest tests.test_phase4_pinterest_connector
```

This suite proves hard-off configuration, fixture-only expiring authority,
semantic idempotency, committed ambiguous-write quarantine, read-only
reconciliation, and append-only metric snapshots. It makes zero network or
provider calls. Migration validation applies revision
`0005_pinterest_control_plane`, downgrades to
`0004_pinterest_shadow_production`, and reapplies head on SQLite and
PostgreSQL.

## Sheldon exact-release checks

Use the installed reviewed Sheldon Deploy release:

```sh
python3 <plugin>/scripts/deploy.py doctor --project-dir .
python3 <plugin>/scripts/deploy.py sync-metadata --project-dir .
python3 <plugin>/scripts/deploy.py verify-release --project-dir . \
  --output /tmp/marketing-os-release-verification.json
python3 <plugin>/scripts/deploy.py plan --project-dir .
python3 <plugin>/scripts/deploy.py package-audit --project-dir . \
  --output /tmp/marketing-os-package-audit.json
python3 <plugin>/scripts/deploy.py preflight --project-dir .
```

`verify-release` must build the runtime and database-tools targets, confirm
non-root execution, verify `pg_dump`, `pg_restore`, `psql`, `initdb`, and
`pg_ctl`, and syntax-check the committed hook scripts. Live provisioning,
migration, deployment, backup, restore check, and rollback are distinct
human-authorized validations.

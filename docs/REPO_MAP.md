# Repo Map

## Project summary

- Purpose: private MattMadeMe marketing/content/growth control plane
- Runtime: Python 3.11+, Flask, SQLAlchemy, PostgreSQL/SQLite
- Package: `pyproject.toml`
- Tests: `tests/` with `unittest`
- Public website: separate repo at `../websites/mattmade_me`

## Remote

- Git remote: `https://github.com/digimatt22/social-content.git`
- Default PR base: `main`

## High-value paths

| Path | Role |
| --- | --- |
| `marketing_os/web_app.py` | Existing local Flask operator application |
| `marketing_os/secure_app.py` | Auth/authz/security wrapper and readiness |
| `marketing_os/db.py` | Engine, schema gate, legacy SQLite initialization |
| `marketing_os/db_models.py` | Domain, auth, job, identity, evidence, event records |
| `marketing_os/services/durable_jobs.py` | Queue state machine, leasing, retry, replay/cancel |
| `marketing_os/jobs/durable_worker.py` | Durable worker process |
| `marketing_os/jobs/durable_scheduler.py` | Idempotent scheduler process |
| `marketing_os/services/auth.py` | Password/session/service-token contracts |
| `marketing_os/services/growth_contracts.py` | Funnel identifiers, tracked URLs, event/evidence rules |
| `marketing_os/services/product_identity.py` | Existing identity matching plus cross-system map |
| `migrations/` | Frozen Alembic revisions |
| `deploy/sheldon/` | Rootless Docker Compose packaging and safe env example |
| `docs/architecture/` | Durable architecture and measurement decisions |
| `docs/exec-plans/` | Phase execution state |
| `.agents/skills/` | Repo-owned social/video workflow skills |

## Commands

| Command | Purpose |
| --- | --- |
| `.venv/bin/python -m unittest discover -s tests -q` | Full Python suite |
| `.venv/bin/alembic upgrade head` | Apply reviewed schema revisions |
| `marketing-os-admin create-admin <name>` | TTY-safe administrator bootstrap |
| `marketing-os-worker` | Run durable jobs |
| `marketing-os-scheduler` | Emit idempotent scheduled jobs |
| `marketing-os-status --fail-on-attention` | Machine-readable operational health |
| `marketing-os-preflight --profile pinterest_publish` | Enforce capability/safe-mode gate |
| `scripts/check-current-state.sh` | Local branch/worktree gate |
| `scripts/check-doc-links.sh` | Markdown link validation |

## Risky areas

| Area | Caution |
| --- | --- |
| `marketing_os/jobs/*` provider work | External writes need explicit authority, idempotency, reconciliation |
| Database migrations | Dry-run/copy/verify; never silently migrate production startup |
| `data/` and `outputs/` | May contain operational/customer data; never package |
| Local environment files | May contain long-lived credentials; never log, stage, or deploy |
| Website repo | Separate source of truth and deployment; use HTTP contracts |
| Pre-existing dirty files | Preserve and stage only phase-owned files/hunks |

## Current gaps

- Pinterest/GA4/GSC authorization is unavailable.
- Off-host backup target and real alert delivery are unconfigured.
- Magnific is not callable in the current session.
- Separate uncommitted Art Studio/video work has one known failing test.

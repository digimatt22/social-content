# Marketing OS Sheldon Configuration Report

Configuration date: 2026-07-24

## Target

- Host: Sheldon (SSH address retained in private operator configuration)
- Application: `marketing-os`
- Public hostname: `mmm.digicolony.net`
- Ingress: Caddy to a rootless-Docker loopback origin
- Deployment manifest: schema 2 in `sheldon.json`
- Deployer: Sheldon Deploy 0.4.1 release contract

## Services

- `web`: Gunicorn/Flask on container port 8080, with separate liveness and
  dependency-readiness paths.
- `worker`: durable job worker with queue/lease attention health.
- `scheduler`: durable scheduler with advisory-lock and attention health.
- `migration`: separately authorized Alembic upgrade to
  `0005_pinterest_control_plane`.
- `hooks`: dedicated non-root PostgreSQL readiness, backup, and isolated
  restore-check image.
- PostgreSQL: application-owned 17.10 instance with a labeled persistent
  volume and no published port.

## Identity and secret boundaries

The canonical Sheldon secret file is
`~/.config/sheldon/secrets/marketing-os.env`, mode `0600`. It contains
separate cluster-bootstrap, migration, runtime, and backup credentials plus
the Flask application configuration. Secret values are not recorded here,
committed to Git, or retained in release directories.

## Live-operation state

Dependency-network provisioning, PostgreSQL provisioning, migration,
deployment, backup, restore check, initial administrator creation, and the
Cloudflare route are separately authorized operations. This report records the
reviewed intended state; it is not evidence that any of those mutations have
run.

Pinterest publishing remains hard-disabled independently of infrastructure
readiness.

# Project Context

## Product

MattMadeMe Marketing OS is a Python/Flask private operator application for product/catalog context, content planning, creative review, tasks, provider imports, and growth automation. It is not the public website.

The public MattMadeMe site is a separate Next.js application at `../websites/mattmade_me`, backed by DynamoDB/S3 and deployed independently. Marketing OS uses authenticated HTTP contracts rather than direct access to that website database.

## Current runtime

- Python 3.11+ package: `marketing_os`
- Local web entrypoint: `python run_local.py` or `marketing-os-web`
- Hosted web entrypoint: `gunicorn marketing_os.wsgi:app`
- Local persistence: SQLite
- Hosted persistence: PostgreSQL 17 after controlled cutover
- Durable processes: `marketing-os-worker`, `marketing-os-scheduler`
- Schema management: Alembic
- Hosted authentication: Argon2id human accounts, opaque database sessions, scoped hashed service tokens
- Initial host target: Sheldon rootless Docker behind loopback Caddy/Cloudflare routing

## Current data and capabilities

- Local catalog: 72 Marketing OS products.
- Read-only website API: configured; 61 public products observed on 2026-07-24.
- Read-only Etsy API/import: configured; 74 active listings observed in Phase -1 and 3,182 imported sales rows locally.
- Product identity baseline: 58 mapped by Etsy listing ID; 14 named exceptions.
- Pinterest API: unavailable/unconfigured.
- Pinterest organic analytics: unavailable/unconfigured.
- GA4 reporting API: unavailable/unconfigured.
- Google Search Console API: unavailable/unconfigured.
- Alert delivery: unavailable/unconfigured.
- Magnific provider: unavailable in the current tool session.

Missing capabilities degrade to shadow/export, persisted exceptions, labeled hypotheses, or disabled publishing. They do not authorize guessed data or public writes.

## Repository and collaboration

- This repository currently has no `origin` remote.
- Pull requests and pushes are unavailable until a remote is configured.
- Implementation branches use the `codex/` prefix and are committed phase by phase.
- The worktree contains separate pre-existing Art Studio/video/harness changes. Phase commits stage only their owned files/hunks.
- The public website does have an `origin` remote; Phase 0 website changes are on `codex/pinterest-growth-phase-0`.
- Phase 1 website hub work is on `codex/pinterest-growth-phase-1` in both
  repositories and adds canonical product routes, typed editorial drafts,
  dedicated portrait metadata images, and separately scoped agent v2 contracts
  without direct database coupling.
- Phase 2 coverage intelligence work is on `codex/pinterest-growth-phase-2`.
  It keeps Flask/PostgreSQL, adds the `0003_coverage_intelligence` schema,
  complete catalog/editorial reads, durable measurement cursors, sparse
  explainable opportunities, and authenticated Coverage/Exceptions surfaces.
  It does not publish externally.
- Phase 3 shadow campaign production is on
  `codex/pinterest-growth-phase-3`. It adds Alembic revision
  `0004_pinterest_shadow_production`, deterministic Pinterest package adapters,
  checksummed review fixtures, append-only QA/review evidence, duplicate payload
  leases, durable generation/digest jobs, and authenticated shadow surfaces.
  It has no external publishing or generation authority.

## Strategy source

The active strategy and phased implementation plan is:

- `docs/exec-plans/active/pinterest-first-autonomous-brand-growth.md`

Phase -1 evidence and decisions:

- `docs/architecture/adr-001-permanent-marketing-service-foundation.md`
- `docs/architecture/pinterest-growth-capability-matrix.md`
- `docs/reviews/phase-minus-1-capability-test-log.md`

## Known human/deployment gates

- Configure the Marketing OS remote/PR workflow.
- Select production hostname and Caddy/Cloudflare policy.
- Transfer the first administrator credential securely.
- Select encrypted off-host backup destination, retention, RPO/RTO, and key custodian.
- Configure alert delivery/owner, acknowledgement, and cost ceiling.
- Authorize provider accounts before any public Pinterest write.
- Rotate existing long-lived local AWS credentials before hosted operation.
- Apply the website growth-event Terraform table and configure/rotate distinct
  catalog-read, draft-write, and measurement-read production credentials before
  enabling the deployed Phase 1 receiver.
- Deploy the Phase 2 website completeness/editorial-read contract and apply
  Alembic revision `0003_coverage_intelligence` before enabling hosted Phase 2
  schedules.
- Apply Alembic revision `0004_pinterest_shadow_production` and inject
  `MARKETING_OS_REPOSITORY_REVISION` when deployed without Git metadata before
  enabling Phase 3 schedules.
- Complete one timed representative real-output shadow review before claiming a
  review-time improvement or graduating Phase 4 autonomy.

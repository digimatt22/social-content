# Sheldon Platform Hardening and Deployment Migration

## Status

- Status: Phases 0–5 complete; Phase 6 dependency applications redeployed and Phase 7 Marketing OS deployment preparation in progress
- Owner: Matthew / Codex
- Branch: `codex/sheldon-platform-hardening` in `sheldon-deploy`
- PR: https://github.com/DigiColonyLLC/sheldon-deploy/pull/1 (merged)
- Last updated: 2026-07-24
- Planning framework: Digi-CTO plugin `0.3.0`
- Deployment baseline: Sheldon plugin `0.4.0`; compatibility patch `0.4.1` under review

## Summary

Upgrade the reusable Sheldon deployment plugin from a safe single-application
deployer into a versioned small-service platform contract that can deploy and
operate:

- single-container Next.js, Flask, and generic applications;
- multi-process applications with independent web, worker, scheduler, and
  one-shot migration services;
- application-owned or approved shared PostgreSQL dependencies;
- private Garage object storage and external AWS S3 storage;
- restart-safe health checks, rollback, backup verification, operational
  inventory, and actionable alerts.

After the plugin is proven, migrate every current Sheldon deployment to the new
contract, then use it to deploy MattMadeMe Marketing OS at
`mmm.digicolony.net`.

This plan does not authorize a deployment, database migration, backup deletion,
secret change, Cloudflare route change, AWS resource change, or public
Pinterest write. Each live mutation retains its own explicit approval gate.

## Source Inputs

- Read-only Sheldon inventory performed 2026-07-24.
- Work Items deployment records at
  `/Users/mwood/Documents/Digicolony/Codex/work-items`.
- Relay Hub deployment records at
  `/Users/mwood/Documents/Lab714/SMS Gateway`.
- Marketing OS topology in `deploy/sheldon/compose.yml`.
- Sheldon deployment plugin
  `0.1.0+codex.20260717125641`.
- `docs/architecture/adr-001-permanent-marketing-service-foundation.md`.
- `docs/exec-plans/active/pinterest-growth-phase-4.md`.

## Current Deployment Inventory

| Component | Current state | Database/storage | Finding |
| --- | --- | --- | --- |
| DigiColony Client Operations / Work Items | Release `20260724T140218Z`; `portal.digicolony.net`; origin `127.0.0.1:39732`; rootless network `172.30.0.0/16` | PostgreSQL at `172.18.0.2:5432`, database `appdb`, role `appuser`; Garage bucket configured | Public health returned `200`. Application is isolated at the container-network layer. |
| Relay Hub SMS | Release `20260724T135803Z`; `sns.digicolony.net`; origin `127.0.0.1:35607`; rootless network `10.246.135.0/24` | Same PostgreSQL server at `172.18.0.2:5432`, database `relayhub_sms`, dedicated role `relayhub_sms_runtime` | Public readiness returned `200`. Logical database/role isolation exists, but PostgreSQL failure is shared with Work Items. |
| Garage | `dxflrs/garage:v2.2.0`; one healthy node; private address `172.30.0.3`; no published ports | Volumes `sheldon-garage-meta` and `sheldon-garage-data`; private Work Items bucket; isolated restore drill passed | Single-host storage is suitable for private working data but is not an off-host durability boundary. Garage is coupled to the Work Items network instead of declared as a platform dependency. |
| Rootful PostgreSQL | Listening on Sheldon loopback and reachable from the approved rootless routes | Hosts Work Items and Relay Hub databases | Separate database names and roles prevent normal cross-application access, but maintenance, process failure, corruption, and host failure remain shared failure modes. |
| Marketing OS | Not deployed | Planned PostgreSQL 17, web, worker, scheduler, migration job, asset/output storage | Existing Sheldon plugin can generate only one `app` service and cannot safely deploy this topology. |

### Capacity snapshot

- Sheldon memory: 7.6 GiB total, approximately 5.9 GiB available at review.
- Sheldon disk: 221 GiB total, approximately 189 GiB available.
- Rootless Docker build cache: 16.72 GB, of which 15.91 GB was reclaimable.
- Garage reported one healthy node and approximately 202.5 GB available.

Capacity is adequate for the next deployment wave, but resource budgets and
build-cache retention must become explicit policy rather than informal state.

## Urgent Finding

Relay Hub has an untracked database dump at `backups/relayhub-pre-019.dump`.
The current deployment packager does not exclude `backups/` or database dump
files, so the dump was copied into five immutable release source directories
with mode `0644`. The local `.gitignore` correctly ignores the directory, but
the deployer packages the full working tree rather than an exact reviewed Git
source set.

The final Relay Hub image copies only selected standalone runtime files, so the
dump is not known to be present in the final runtime filesystem. It did enter
the Docker builder context/cache and deployed release archives. No public HTTP
exposure was identified during this review.

Containment requires a separate authorized operation:

1. inventory every release archive, source tree, image layer, and build-cache
   reference containing the dump;
2. verify the intended protected backup exists separately with mode `0600`;
3. remove release/cache copies after Matthew approves the exact targets;
4. determine whether the dump contains reusable session, token, or credential
   material and rotate only affected credentials;
5. record cleanup evidence without copying sensitive dump contents into logs.

## Decisions

### 1. Database isolation policy

Sharing a PostgreSQL server is not automatically unsafe. Sharing the same
database, schema ownership, or runtime role is prohibited.

Use these tiers:

| Tier | Workloads | Required isolation |
| --- | --- | --- |
| Platform-critical | Alerting, identity, deployment control, secrets, or monitoring dependencies | Dedicated PostgreSQL instance and volume. It may initially share the Sheldon host, but not the application database process. |
| Stateful automation | Durable queues, workers, scheduled jobs, or materially different PostgreSQL version/extension needs | Dedicated PostgreSQL instance unless a reviewed capacity and failure-domain exception is recorded. |
| Ordinary internal applications | Low-volume apps with compatible version, maintenance, recovery, and security needs | A shared cluster is permitted only with a separate database, owner, migrator, runtime role, connection limit, logical backup, and restore test per app. |

Required controls for every database:

- no use of another application's runtime role;
- no application runtime ownership of its database or schema;
- separate owner/migrator and least-privilege runtime roles;
- revoke unintended `PUBLIC` privileges;
- explicit maximum connections and statement/lock timeouts;
- reviewed migrations run separately from application deployment;
- application-specific logical backups and isolated restore verification;
- version, extension, collation, and recovery compatibility recorded;
- readiness checks prove database usability without exposing credentials.

Application of the policy:

- Relay Hub moves to a dedicated PostgreSQL instance because it is the alert
  path for other services. This removes the current Work Items database process
  as a Relay Hub failure dependency.
- Marketing OS uses an application-owned PostgreSQL 17 instance because it
  requires PostgreSQL-backed leases, advisory locking, durable scheduling, and
  PostgreSQL 17 validation.
- Work Items can remain on its current PostgreSQL instance during this plan.
  Its generic `appdb`/`appuser` production names are preserved until a separate
  reviewed credential/schema migration justifies changing them.
- Separate instances on Sheldon still share the host, power, disk, and network
  failure domain. This plan improves service isolation but does not claim high
  availability.

### 2. Pinterest object-storage policy

Use a two-tier storage flow:

1. **Garage for private working storage**
   - generated drafts, review fixtures, intermediate assets, manifests, and
     reproducible provider outputs;
   - private bucket and unique credentials for Marketing OS;
   - no public bucket access;
   - lifecycle cleanup for superseded intermediates after their audit-retention
     window.
2. **AWS S3 for approved delivery media**
   - immutable final Pin images and other public delivery assets;
   - an exact DigiColony/MattMadeMe AWS account must be confirmed before any
     inspection or provisioning because multiple AWS accounts are configured;
   - separate bucket/prefix and least-privilege publishing identity;
   - versioning, encryption, public-delivery policy, lifecycle, CORS, and
     access logging explicitly configured;
   - serve through an approved stable HTTPS origin, preferably the existing
     MattMadeMe delivery path or a dedicated CloudFront-backed media hostname.

Garage alone is not recommended for final Pinterest delivery while it is a
single node on the same Sheldon disk and no off-host backup is planned. AWS S3
adds a separate durability and availability boundary at negligible expected
storage/request cost for the initial content volume.

### 3. Live-media checksum contract

For every approved Pinterest asset:

1. hash the exact generated bytes with SHA-256;
2. store immutable object key, byte length, MIME type, dimensions, source
   revision, and SHA-256 in the Marketing OS asset manifest;
3. upload with provider checksum/metadata support;
4. verify the storage provider's `HEAD` result;
5. fetch the exact public delivery URL before publishing and independently
   verify byte length, MIME type, dimensions, and SHA-256;
6. persist that verification time and result with the publication attempt;
7. create the Pin only from the verified immutable URL;
8. perform Pinterest read-after-write reconciliation for Pin ID, board,
   destination URL, title/description, and media presence.

Pinterest may transcode or resize media, so the Pinterest-hosted bytes are not
required to preserve the source SHA-256. The checksum proves what Marketing OS
delivered; reconciliation proves what Pinterest created.

### 4. Alert dependency policy

- Application and Marketing OS alerts use Relay Hub SMS with deduplication,
  severity, acknowledgement, quiet hours, and automatic policy-pause rules.
- Sheldon host, PostgreSQL platform, Garage, and Relay Hub health must be
  evaluated by a watchdog outside the application containers.
- Relay Hub cannot be the only notification path for its own outage. A
  separately operated fallback channel remains a human decision before the
  monitoring phase can close.
- Alerts contain identifiers and recovery actions, never secret values,
  database URLs, raw customer data, or message bodies.

### 5. Plugin ownership and distribution

- Do not edit the installed plugin cache as the source of truth.
- The canonical source repository is
  `git@github.com:DigiColonyLLC/sheldon-deploy.git`, with the local checkout at
  `/Users/mwood/Documents/Digicolony/Codex/sheldon-deploy`.
- Release the enhancements as a semantically versioned plugin update in the
  DigiColony private marketplace so devices and team members receive the same
  tested behavior.
- Keep schema-1 manifests readable during a bounded migration window.
- Require clean-machine installation and smoke evidence before migrating live
  deployments.

## Target Sheldon Manifest Contract

Introduce a backward-compatible schema 2 with explicit sections for:

- release source: exact commit, clean-worktree requirement, permitted generated
  artifacts, exclusions, digest, and provenance;
- services: image/build target, command, process type, resource limits,
  restart/shutdown policy, dependencies, liveness, and readiness;
- ingress: one loopback-only public service and Caddy hostname;
- networks: collision-checked application subnets and approved dependency
  attachments;
- secrets: required names by runtime/build scope without values;
- storage: named volumes and declared Garage/S3 dependencies;
- database: isolation tier, engine/version, database/role names without
  passwords, migration command, backup hook, and restore-check hook;
- rollout: preflight, deploy lock, health deadline, rollback behavior, release
  retention, and cleanup;
- observability: machine-readable status, dependency checks, alert policy, and
  audit destination.

The generated Compose file remains derived output. Application repositories
commit the manifest and operational runbook, not server secrets or mutable
state.

## Work State

- Planned: separately authorized Phases 6 and 7 application migrations.
- In progress: Phase 7 Marketing OS exact-release contract and validation.
- Completed externally, then read-only verified: Phase 6 Work Items and Relay
  Hub application redeployments are healthy. Plugin-version-only update drift
  remains and does not invalidate their current health evidence.
- Completed: Phases 0–5, including host monitoring and Relay Hub alert
  contracts.
- Completed: Sheldon Deploy 0.2.0 source and private-marketplace release gate.
- Blocked: live cleanup, database migration, AWS provisioning, fallback alert
  channel, and deployments require later explicit authorization.
- Needs human validation: AWS account selection, Relay Hub maintenance window,
  fallback notification path, and all public-service smoke tests.
- Ready for review: this planning artifact after documentation validation.
- Completed: read-only deployment, database-topology, backup, storage, health,
  and capacity inventory; canonical source repository and initial
  `sheldon-deploy` 0.1.0 team-marketplace release.

## Implementation Phases

### Phase 0 — Contain unsafe release inputs

Goal: prevent any new deployment from packaging backups or other sensitive
local artifacts before broader plugin work.

Work:

- add deny-by-default deployment exclusions for `backup/`, `backups/`, local
  databases, database dumps, private keys, credential exports, and common
  archive formats;
- scan the proposed release archive and Docker build context for prohibited
  paths and secret-like material;
- fail with exact path names but never print contents;
- add a `package-audit` command that emits a JSON file inventory and SHA-256;
- make reviewed Git source the default package input; allow generated inputs
  only through an explicit manifest allowlist;
- add regression fixtures for ignored-but-present database dumps;
- prepare, but do not execute, the Relay Hub release/cache cleanup runbook.

Acceptance:

- the Relay Hub dump fixture cannot enter a release archive or Docker context;
- a dirty or untracked sensitive file causes a preflight failure;
- normal migrations and application source still package correctly;
- schema-1 apps receive the new safety behavior without manifest changes.

### Phase 1 — Freeze the platform policy and inventory contract

Goal: make every Sheldon service and stateful dependency discoverable and
reviewable.

Work:

- add an `inventory` command covering releases, loopback ports, hostnames,
  container/image digests, networks, volumes, resource limits, health,
  database metadata, storage dependencies, backup age, and drift;
- produce redacted JSON and human-readable output;
- record database isolation tiers, network policy, resource budgets, release
  retention, backup ownership, and unsupported topology failures;
- update the server configuration report template;
- record the current Work Items, Relay Hub, Garage, PostgreSQL, and Marketing OS
  intended state.

Acceptance:

- inventory reveals shared failure domains without exposing environment values;
- declared state can be compared with live state;
- unexpected public port binding, shared role/database, missing resource
  limit, stale backup, or unmanaged volume is reported as actionable drift.

### Phase 2 — Implement schema 2 and exact-source releases

Goal: provide a safe, reproducible foundation before multi-service support.

Work:

- implement and validate manifest schema 2 while preserving schema-1 reads;
- package an exact commit by default and record commit SHA, source digest,
  plugin version, and build timestamp;
- refuse ambiguous dirty worktrees unless an explicit reviewed artifact
  allowlist covers the change;
- add a per-application deployment lock;
- make CPU/memory/PID limits, non-root user checks, stop grace period, and
  release retention configurable with safe bounds;
- persist release manifest and checksums alongside the release;
- validate Caddy before switching traffic and preserve the previous working
  release.

Acceptance:

- two deployments of the same commit and manifest have identical source
  inventories;
- concurrent deploys of one app serialize or fail safely;
- schema-1 Work Items and Relay Hub plans remain readable;
- rollback selects a known healthy release and reports configuration drift.

### Phase 3 — Add multi-service and migration-safe deployment

Goal: support Marketing OS without embedding database mutation in ordinary
application startup.

Work:

- support independently declared `web`, `worker`, `scheduler`, and one-shot
  `migration` services;
- support service-specific commands, health checks, secrets, resource limits,
  dependencies, and graceful shutdown;
- require migration preflight, backup reference, explicit migration authority,
  and recorded result before a release depending on a new schema becomes live;
- keep application rollback separate from database downgrade;
- add worker/scheduler liveness, lease-age, and queue-attention checks;
- ensure failed web health or required-process health restores the prior app
  release without re-running a migration.

Acceptance:

- fixture deployments prove web/worker/scheduler restart recovery;
- failed migrations never switch the current release;
- failed application health restores the previous application release;
- rollback never silently downgrades or resets a database;
- Marketing OS's five-service topology passes plan and preflight.

### Phase 4 — Add database and object-storage dependency profiles

Goal: make stateful dependencies explicit, isolated, backed up, and testable.

Work:

- support application-owned PostgreSQL containers and approved external
  PostgreSQL profiles;
- validate database version, database name, runtime role, migration role,
  connectivity, connection ceiling, and isolation tier without printing
  credentials;
- support named-volume ownership and collision checks;
- add backup and restore-check hooks whose execution is always separately
  authorized;
- move Garage from an implicit Work Items sidecar assumption to a declared
  Sheldon platform dependency;
- create per-application Garage bucket/key policy and safe network attachment;
- add external S3 profile validation for account, region, bucket, identity,
  encryption, versioning, lifecycle, and delivery URL;
- implement the asset checksum verification contract.

Acceptance:

- Relay Hub and Work Items cannot accidentally share a database or runtime role;
- application-owned PostgreSQL survives application release replacement;
- isolated restore checks compare schema/revision and protected row counts;
- Garage credentials cannot access another application's bucket;
- an S3 asset cannot become publish-eligible until the public URL checksum
  verification passes.

### Phase 5 — Add host monitoring and Relay Hub alerts

Goal: detect actionable failures without creating a circular monitoring
dependency.

Work:

- install an external host watchdog through a reviewed systemd user service or
  equivalent host-level scheduler;
- monitor Caddy routes, origins, required containers, database readiness,
  Garage health, disk, memory, build-cache growth, backup age, certificate
  expiry where observable, and release drift;
- deliver application alerts through Relay Hub;
- persist deduplication keys, first/last seen, delivery result,
  acknowledgement, and recovery;
- automatically pause only the affected Marketing OS policy class on critical
  publishing/storage/tracking failures;
- configure an independent fallback for Relay Hub/host failure after Matthew
  selects it.

Acceptance:

- a simulated application failure generates one deduplicated SMS with an exact
  recovery action;
- recovery closes the incident and permits an audited resume;
- Relay Hub outage is detected independently and does not disappear silently;
- routine success is summarized rather than texted per event.

### Phase 6 — Migrate current deployments

Goal: move each live service onto the enhanced contract one at a time.

Order:

1. **Relay Hub**
   - remove prohibited backup artifacts from future release inputs;
   - create its dedicated PostgreSQL instance and volume;
   - dry-run backup/restore and migration;
   - cut over during an approved maintenance window;
   - prove recipient authorization, queued delivery, readiness, rollback, and
     alert-path behavior.
2. **Work Items**
   - adopt schema 2 and exact-source releases;
   - preserve the existing database contract initially;
   - declare Garage and its bucket as a platform dependency;
   - add database/storage readiness and verified backup hooks;
   - prove Auth.js callback URLs, file upload/download, permissions, and
     rollback.
3. **Garage**
   - move lifecycle, bucket policy, credentials, network attachments, capacity,
     backup, and restore evidence into the platform inventory;
   - preserve existing Work Items objects and key identities.

Acceptance:

- each migration has preflight, backup, smoke, rollback, and closeout evidence;
- only one live workload changes at a time;
- public health and one successful/one expected-failure business path pass;
- no current user, consent, work-item, permission, or stored-object record is
  lost or silently changed.

### Phase 7 — Deploy Marketing OS and activate storage safely

Goal: deploy the permanent private control plane without enabling live
Pinterest authority.

Work:

- deploy Marketing OS web, worker, scheduler, migration, and PostgreSQL 17
  services at `mmm.digicolony.net`;
- create the private Marketing OS Garage bucket and least-privilege credentials;
- after the exact AWS account is confirmed, create or select the approved S3
  delivery location and least-privilege publishing identity;
- migrate SQLite to PostgreSQL using the existing dry-run/copy/verify contract;
- create the first administrator through the TTY-safe flow;
- configure Relay Hub alerts and host monitoring;
- run asset upload, checksum, public-fetch, worker restart, scheduler lock,
  database restore, and application rollback drills;
- keep Pinterest publishing hard-disabled until Pinterest grants access and
  Matthew separately approves the sampled-write policy.

Acceptance:

- anonymous requests are limited to approved health/login/static surfaces;
- web, worker, and scheduler recover independently;
- PostgreSQL 17 is authoritative after signed cutover evidence;
- private drafts remain private in Garage;
- approved test media is delivered from the immutable S3 URL with verified
  SHA-256 evidence;
- no live Pinterest API write occurs in this phase.

## Validation

Plugin-level:

```sh
python -m unittest discover -s skills/deploy-to-sheldon/tests -q
python skills/deploy-to-sheldon/scripts/deploy.py plan --project-dir <fixture>
python skills/deploy-to-sheldon/scripts/deploy.py package-audit --project-dir <fixture>
python skills/deploy-to-sheldon/scripts/deploy.py inventory --project-dir <fixture>
```

Project-level:

```sh
scripts/check-current-state.sh
scripts/check-doc-links.sh
.venv/bin/python -m unittest discover -s tests -q
```

Live validation must use the plugin's non-mutating `plan`, `preflight`,
`inventory`, and `status` commands before any approved mutation.

## Human Validation and Approval Gates

| Gate | Owner | Required evidence | Blocks |
| --- | --- | --- | --- |
| Approve exact Relay Hub release/cache cleanup targets | Matthew | Redacted inventory of dump copies and protected backup | Phase 0 live cleanup |
| Select Relay Hub/host fallback notification channel | Matthew | Tested independent notification receipt | Phase 5 completion |
| Approve Relay Hub database maintenance window | Matthew | Dry-run migration/restore report and rollback steps | Phase 6 Relay migration |
| Confirm MattMadeMe AWS account/profile and target bucket/region | Matthew | Account ID displayed without credentials; reviewed plan | AWS inspection/provisioning |
| Approve Cloudflare route for `mmm.digicolony.net` | Matthew | Route plan to `http://localhost:80` | Public Marketing OS verification |
| Transfer initial Marketing OS administrator credential | Matthew | Successful login and forced-change evidence | Hosted operator access |
| Approve sampled Pinterest write policy | Matthew | Pinterest access, board, scope, shadow QA, alert, recovery evidence | Any public Pin |

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Sensitive local files enter release archives | Exact Git source, prohibited-path scan, explicit generated-artifact allowlist |
| Shared PostgreSQL outage disables apps and alerting | Dedicated Relay Hub and Marketing OS instances; tiered sharing policy |
| More PostgreSQL instances increase maintenance | Standardized version/backup/status hooks and resource limits |
| Garage failure loses final publishing media | Garage only for private working assets; final approved media promoted to S3 |
| Sheldon host failure affects all local services | State limitation explicitly retained; S3 and independent alert fallback provide partial external boundaries |
| Multi-service rollback corrupts schema | Separate migration authority; application rollback never implies database downgrade |
| Monitoring depends on the failed service | Host-level watchdog and independent Relay Hub fallback |
| AWS commands use the wrong account | Require explicit profile/account-ID confirmation before inspection or changes |
| Plugin changes drift across devices | Versioned private-marketplace release and clean-machine smoke tests |

## Documentation Updates During Implementation

- Plugin `SKILL.md`, manifest reference, security reference, templates, and
  server report.
- Work Items and Relay Hub `sheldon.json`, `SHELDON_DEPLOY.md`, architecture,
  backup, and migration runbooks.
- Marketing OS `docs/PROJECT_CONTEXT.md`, `docs/ARCHITECTURE.md`,
  `docs/AUTOMATIONS.md`, Phase 4 plan, deployment runbook, and this plan.
- A new ADR for Sheldon database isolation, platform dependencies, storage, and
  alert failure domains.

## Closeout Conditions

- Plugin update is reviewed, versioned, published to the DigiColony private
  marketplace, and installed successfully on a clean device.
- Sensitive release-input containment and authorized cleanup are complete.
- Relay Hub, Work Items, and Garage conform to the enhanced inventory and
  deployment contract.
- Marketing OS is deployed and verified at `mmm.digicolony.net`.
- PostgreSQL, storage, backup, restore, alert, rollback, and checksum evidence
  is recorded.
- Public Pinterest publishing remains independently gated by provider approval
  and Matthew's sampled-write authority.

## Validation Log

- Canonical source commit `d024883` created and pushed to
  `DigiColonyLLC/sheldon-deploy`; 2026-07-24.
- Source packaging safety tests: 3 passed; deployment runtime tests: 4 passed;
  2026-07-24.
- Codex plugin validator and public-skill validator passed against source and
  final packaged output; 2026-07-24.
- Final 17-file release inventory passed SHA-256 verification and contained no
  symlinks or detected private-key/AWS-key/machine-path patterns; 2026-07-24.
- DigiColony marketplace commit `5834212` published
  `sheldon-deploy@digicolony-team` version `0.1.0`; 2026-07-24.
- The existing `sheldon-deploy@personal` installation remains enabled until a
  deliberate installation migration is performed from a fresh Codex task.
- Phase 0 source implementation completed on
  `codex/sheldon-platform-hardening`; 2026-07-24. It packages committed Git
  blobs with reviewed modes, rejects dirty or prohibited inputs, pins the
  preflight inventory, and emits `package-audit` SHA-256 evidence.
- Phase 0 independent review found five material packaging issues: executable
  mode loss, prohibited-input bypasses, generated-allowlist exclusion bypass,
  preflight/package TOCTOU, and missing-inventory Dockerfiles. All five were
  corrected with regression coverage before the 0.1.1 release gate.
- Remaining Phase 0 human gate: historical Relay Hub release and build-cache
  cleanup remains unexecuted pending approval of exact targets. This does not
  block publishing the containment fix.
- Phase 0 source commit `9f3dd76` created and pushed on
  `codex/sheldon-platform-hardening`; 2026-07-24.
- Phase 0 validation: 6 source packaging tests and 18 deployment runtime tests
  passed; source/package, Codex plugin, and public-skill validators passed;
  a clean 17-file marketplace snapshot passed packaged runtime tests and
  SHA-256 manifest verification; 2026-07-24.
- DigiColony marketplace commit `776e72b` published and validated
  `sheldon-deploy@digicolony-team` version `0.1.1`; 2026-07-24.
- Phase 1 implemented read-only JSON/text inventory for releases, origins,
  Caddy routes, container/image identity, loopback exposure, networks, volumes,
  resource budgets, backup evidence, database isolation, storage dependencies,
  host capacity, and actionable drift; 2026-07-24.
- Phase 1 independent review identified missing normal-run database/storage
  evidence, name-only storage checks, inconsistently labeled dated baselines,
  and unsafe arbitrary-file backup freshness. All were corrected with
  allowlisted host metadata, explicit baseline-age findings, profile/owner/
  health drift, and contract-only backup evidence.
- Phase 1 validation: 6 source packaging tests and 31 deployment/inventory
  tests passed in source and packaged output; source/package, Codex plugin,
  public-skill, clean 20-file snapshot, and SHA-256 validators passed;
  2026-07-24.
- Phase 1 source commit `3fbcc38` created and pushed on
  `codex/sheldon-platform-hardening`; 2026-07-24.
- Phase 2 implemented backward-compatible schema 2, deterministic exact-source
  provenance, per-application and shared-Caddy locking, bounded resource and
  effective-UID enforcement, collision-checked candidate isolation, unrouted
  candidate health gates, immutable image promotion/recovery/rollback,
  current-value runtime/build secret scoping, stored health contracts, and
  inventory-visible recovery/image drift; 2026-07-24.
- Phase 2 independent review challenged UID aliases/effective identity,
  pre-health traffic exposure, mutable rebuild recovery, stale credential
  resurrection, target health drift, candidate network collision, Bash error
  propagation, empty-secret rollback, and observability. All material findings
  were corrected and the final review granted approval.
- Phase 2 validation: 6 source tests and 50 deployment/inventory/rollback tests
  passed in source and packaged output; source/package, Codex plugin,
  public-skill, shell syntax, and diff validators passed; clean staging snapshot
  `/tmp/sheldon-phase2-gate.4ZA6Kc` contained 20 plugin files and its complete
  `release-manifest.sha256` verified; 2026-07-24.
- Phase 2 source commit `d815a54` created and pushed on
  `codex/sheldon-platform-hardening`; 2026-07-24.
- Remaining human gates are unchanged: no live Sheldon service, database,
  secret, backup, Cloudflare, cleanup, deployment, or rollback operation was
  performed during Phases 0–2.
- Phase 3 implemented independently built and bounded web/worker/scheduler
  services, per-service current-value secret scopes, health and queue-attention
  contracts, dependency-cycle rejection, per-service image provenance/drift,
  and multi-process candidate/promotion/recovery checks; 2026-07-24.
- Phase 3 added one-shot migration staging that never runs during ordinary
  deploy or rollback. Migration requires a health-ready exact-source staging
  attestation, protected-backup reference, explicit mutation authority,
  effective non-root UID, recorded image/source/manifest/revision evidence,
  and separately explicit retry authority after a failed attempt.
- Phase 3 independent review challenged unhealthy staging, mutable migration
  evidence, migration UID 0, partial-failure retry, per-service image drift,
  unenforced attention thresholds, source-bound observability, dependency
  cycles, dirty-worktree diagnostics, and recovery fixtures. All material
  findings were corrected and final approval was granted.
- Phase 3 validation: 6 source tests and 61 deployment/inventory/migration/
  rollback tests passed in source and packaged output; source/package, Codex
  plugin, public-skill, Bash/Python syntax, and diff validators passed; clean
  staging snapshot `/tmp/sheldon-phase3-gate.9cZbJ5` contained 22 plugin files
  and its complete `release-manifest.sha256` verified; 2026-07-24.
- Phase 3 source commit `980d8b8` created and pushed on
  `codex/sheldon-platform-hardening`; 2026-07-24.
- Remaining human gates are unchanged: no live Sheldon service, database,
  secret, backup/restore, Cloudflare, cleanup, deployment, migration, or
  rollback operation was performed during Phase 3.
- Phase 4 implemented application-owned and external PostgreSQL profiles,
  stable collision-checked dependency networks, labeled persistent volumes,
  release-independent digest-pinned bounded PostgreSQL lifecycle, separate
  bootstrap/migration/runtime identities, Garage own/foreign-bucket isolation,
  AWS S3 delivery contracts, streamed non-root backup/restore hooks, exact
  schema/revision/row-count restore evidence, and non-redirected public asset
  verification with required provider SHA-256 and object identity; 2026-07-24.
- Phase 4 independent review challenged rootless bind-mount permissions,
  application-owned PostgreSQL lifecycle, volume/network collision and
  point-of-use ownership, dependency evidence, atomic recovery evidence,
  redirects/checksum metadata, database upgrade authority, bootstrap
  superuser separation, and identity secret scopes. All material findings were
  corrected and final approval was granted.
- Phase 4 validation: 6 source tests and 68 deployment/database/storage/
  backup/restore/inventory/security tests passed in source and packaged output;
  source/package, Codex plugin, public-skill, Bash/Python syntax, and diff
  validators passed; clean staging snapshot
  `/tmp/sheldon-phase4-gate.qVav28` contained 24 plugin files and its complete
  `release-manifest.sha256` verified; 2026-07-24.
- Phase 4 source commit `853d466` created and pushed on
  `codex/sheldon-platform-hardening`; 2026-07-24.
- Remaining human gates are unchanged: no live Sheldon service, dependency
  network, database, secret, backup/restore, S3/Garage, Cloudflare, cleanup,
  deployment, migration, or rollback operation was performed during Phase 4.
- Phase 5 implemented the independently installed host watchdog, Caddy/origin/
  container/dependency/backup/certificate/release/host-capacity findings,
  deduplicated incidents and recovery, Relay Hub failover, independent
  dead-man heartbeat, scoped policy-control adapters, per-cycle read-only
  dependency refresh, durable idempotent delivery outbox, explicit
  acknowledgement/resume, and content-addressed systemd installation with
  full activation rollback; 2026-07-24.
- Phase 5 independent review challenged policy enforcement, unattended
  dependency evidence, crash/recovery delivery durability, installed-service
  execution, Relay Hub identity, systemd rollback, systemd filesystem
  isolation, and delayed resume reconciliation. All material findings were
  corrected and final approval was granted.
- Phase 5 validation: 6 source tests and 81 deployment/monitoring/security/
  backward-compatibility tests passed; source/package, Codex plugin,
  public-skill, Python syntax, and diff validators passed; clean staging
  snapshot `/tmp/sheldon-phase5-final.r4mpZo` contained 30 plugin files and its
  complete `release-manifest.sha256` verified; 2026-07-24.
- Phase 5 source commit `cd62209` created and pushed on
  `codex/sheldon-platform-hardening`; 2026-07-24.
- Remaining human gates are unchanged: provider/API/recipient selection and a
  real fallback/Relay receipt are required before live monitor installation.
  No live Sheldon service, monitor, database, secret, backup/restore,
  S3/Garage, Cloudflare, cleanup, deployment, migration, or rollback operation
  was performed during Phase 5.
- Sheldon Deploy 0.2.0 release commit `3213a09` created and pushed on
  `codex/sheldon-platform-hardening`; the exact generated package from clean
  staging `/tmp/sheldon-0.2.0-release.9CGvyS` passed source/package, Codex
  plugin, public-skill, checksum, semantic-version, and complete marketplace
  validation; 2026-07-24.
- DigiColony private marketplace commit `d924fab` published and pushed only
  the generated `plugins/sheldon-deploy` folder plus the marketplace README;
  unrelated `digi-cto` and `digi-portal` packages and catalog order were
  preserved. All three marketplace plugins and the complete catalog validated.
- Source PR `DigiColonyLLC/sheldon-deploy#1` merged release commit `3213a09`
  into `main` at merge commit `e81db34`. Before merge, 87 tests passed along
  with source/package validation, release checksums, the Codex plugin
  validator, the public-skill validator, and the Git whitespace check;
  2026-07-24.
- No enabled personal installation was replaced and no live application,
  monitor, migration, database, storage, backup/restore, secret, Cloudflare,
  cleanup, deployment, or rollback operation was performed. Those remain
  separate human gates for Phases 6–7 and production adoption.
- 2026-07-24 resume: Work Items current release
  `20260724T221955Z-2fe481bb6c` returned origin HTTP 200 and known-healthy
  evidence. Relay Hub SMS current release
  `20260724T220328Z-6296685c6a` returned origin HTTP 200 and known-healthy
  evidence. Both releases were created with plugin 0.2.1 and remain healthy;
  no repeat update was performed merely to refresh plugin provenance.
- Sheldon Deploy 0.4.1 compatibility patch added reviewed-source support for
  placeholder `*.env.example` and Alembic `migrations/env.py` files while
  preserving content-based secret scanning; 97 deployer tests and package
  validation passed.

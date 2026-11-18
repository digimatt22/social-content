# Deploying Marketing OS to Sheldon

## Social Studio replacement

The `studio-runtime` image serves Next.js at `/studio/` through the existing private Marketing OS login. The classic dashboard stays at `/legacy`. Product management stays at `/products`. Sheldon still uses the `marketing-os` application and `mmm.digicolony.net` route.

The `studio_0001` migration creates a `social_studio` schema and grants the existing runtime role access to its tables. It leaves the earlier Alembic revision and existing tables intact. Readiness can report the pending schema while the deployment tool stages the image. Production promotion must first record the matching approved migration. Check the protected backup's freshness before running it. Rollback uses the previous known-healthy release; the new schema remains available for a future release.

Before promotion, verify an anonymous denial and a signed-in session through the staged app. Check that the catalog uses the existing product IDs and labels Etsy references separately from uploaded originals. Verify that an assignment created on a disposable database and its selected image survive a web process restart. Check `/ready` and the actual `/studio/api/studio/state` response through the authenticated path after promotion.

The Sheldon worker service runs the existing Marketing OS worker and, when enabled, the Studio caption worker. The service forwards `OPENAI_API_KEY` only to the Studio worker. Both web and worker read `STUDIO_OPENAI_DAILY_JOBS`. Set it to `0` for manual captions, or to an approved daily limit from `1` to `20` to accept background caption jobs. Each job uses the Terra default and a 1,500-output-token cap. The scheduler keeps its existing scope.

Marketing OS uses the schema-2 Sheldon contract in `sheldon.json`.

The release contains separate web, worker, scheduler, migration, and database
hook images plus an application-owned PostgreSQL 17.10 service. Runtime,
migration, backup, and cluster-bootstrap credentials are separate server-side
secrets. No secret value belongs in Git or a release archive.

## Read-only release gate

From the repository root, use the installed Sheldon Deploy skill:

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

The exact release commit must be pushed to its upstream before a live
operation. The canonical Sheldon secret file is
`~/.config/sheldon/secrets/marketing-os.env`, mode `0600`.

## Separately authorized live sequence

Each command below is a separate live authority:

1. Provision the stable dependency network.
2. Provision the application-owned PostgreSQL service and roles.
3. Stage the exact application release.
4. Take or identify a protected backup and run the migration.
5. Promote the already-built release.
6. Run the logical backup and isolated restore check.
7. Create the first administrator interactively.
8. Configure the Cloudflare route for `mmm.digicolony.net` to
   `http://localhost:80` with no Host-header override.

Ordinary deploy/update and rollback never run a migration or downgrade the
database. Pinterest publishing remains hard-disabled until its independent
provider and sampled-write authority gates pass.

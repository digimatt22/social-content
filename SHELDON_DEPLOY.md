# Deploying Marketing OS to Sheldon

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

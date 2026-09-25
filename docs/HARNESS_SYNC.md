# Harness Sync

Use this workflow to keep project implementations aligned with the upstream harness while preserving project-owned facts.

## Source Of Truth
- Upstream harness repo: `git@github.com:MATT-Agent/DigiColony-Harness.git`
- Hosted bootstrap installer: `https://harness.digicolony.com/install`
- Version marker: `.harness/version.json`
- Sync allowlist: `.harness/core-files.txt`
- Boundary policy: `docs/HARNESS_BOUNDARIES.md`

## Protected Core
Protected core files are owned by the upstream harness and listed in `.harness/core-files.txt`. They may be overwritten during sync.

Do not customize protected core files inside projects unless the change should be promoted upstream. Put local differences in `docs/PROJECT_OVERRIDES.md`.

## Project-Owned Files
These files contain repo-specific truth and should not be overwritten by sync unless the project owner explicitly asks:
- `README.md`
- `docs/PROJECT_CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/AUTOMATIONS.md`
- `docs/VALIDATION.md`
- `docs/REPO_MAP.md`
- `docs/REFERENCES.md`
- `docs/PROJECT_OVERRIDES.md`
- active and completed execution plans
- issue sessions
- inbox material
- `Inbox/README.md`
- `.harness/version.json`
- `docs/REPOSITORY_HEALTH.md`

If `docs/PROJECT_OVERRIDES.md` is missing in a project, create it from `docs/templates/PROJECT_OVERRIDES_TEMPLATE.md`.
If `docs/REPOSITORY_HEALTH.md` is missing in a project, create it from `docs/templates/REPOSITORY_HEALTH_TEMPLATE.md`.

## Sync Workflow
1. Run the current-state gate.
2. Create a short-lived branch.
3. Review upstream harness changes when practical.
4. Run a dry-run update:
   ```sh
   curl -fsSL https://harness.digicolony.com/install | bash -s -- --dry-run
   ```
5. Run the update:
   ```sh
   curl -fsSL https://harness.digicolony.com/install | bash
   ```
6. Review the diff carefully, especially `AGENTS.md`, scripts, templates, and docs.
7. If sync stops because a protected file has local edits, move project-specific content into `docs/PROJECT_OVERRIDES.md` or upstream the change.
8. Confirm `.harness/version.json` records the new upstream version, source commit, import date, and previous version.
9. Run validation:
   ```sh
   scripts/check-current-state.sh
   scripts/check-doc-links.sh
   scripts/check-inbox.sh
   ```
10. Open a PR with accepted changes, skipped changes, and project-specific follow-up.

## When To Promote Project Changes Upstream
If a project develops a reusable workflow, script, or template:
- Keep the project implementation working first.
- Add a note to the project inbox or execution plan.
- Port the generic version back to the upstream harness.
- Avoid upstreaming project-specific product facts.

For routine updates after the harness is installed, the local wrapper is equivalent:

```sh
scripts/update-harness.sh
```

Use the hosted curl command as the recovery path when a project has an older or broken local update script.

For brand-new projects from a local harness checkout, `scripts/new-project.sh` remains available. For existing projects, prefer the hosted installer because it preserves project-owned files and creates only missing starter docs.

## Older Harness Installs
If a target has `.harness/version.json` but no `.harness/core-files.txt`, treat it as an older harness install. Run a dry run first:

```sh
curl -fsSL https://harness.digicolony.com/install | bash -s -- --dry-run
```

After reviewing the planned changes, rerun with `--yes` to allow migration:

```sh
curl -fsSL https://harness.digicolony.com/install | bash -s -- --yes
```

## Conflict Policy
When upstream and project-local guidance conflict:
- Preserve project-specific operational truth.
- Prefer upstream for generic workflow, templates, and scripts.
- Record intentional deviations in `docs/PROJECT_OVERRIDES.md` and summarize them in `.harness/version.json`.

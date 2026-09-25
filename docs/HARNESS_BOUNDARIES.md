# Harness Boundaries

Use this document to decide which files are protected harness core and which files belong to the project.

## Protected Harness Core
Protected core files are owned by the upstream harness. Project copies should not edit these files for local policy unless the change should be promoted upstream.

Examples:
- `AGENTS.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.harness/core-files.txt`
- `.harness/version.template.json`
- `docs/WORKFLOW.md`
- `docs/CURRENT_STATE_GATE.md`
- `docs/GITHUB_ISSUE_WORKFLOW.md`
- `docs/HARNESS_SYNC.md`
- `docs/INBOX.md`
- `docs/PULL_REQUESTS.md`
- `docs/SETUP.md`
- `docs/TOOL_ADAPTERS.md`
- `docs/WORK_STATE.md`
- `docs/templates/`
- `scripts/`
  - including `scripts/install-harness.sh`, `scripts/bootstrap-install.sh`, `scripts/update-harness.sh`, and validation helpers

Protected files are listed in `.harness/core-files.txt`.

## Project-Owned Truth
Project-owned files contain facts about the actual product, architecture, commands, environments, risks, and validation expectations. Harness sync should not overwrite them by default.

Examples:
- `README.md`
- `.gitignore`
- `docs/PROJECT_CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/AUTOMATIONS.md`
- `docs/VALIDATION.md`
- `docs/REPO_MAP.md`
- `docs/REFERENCES.md`
- `docs/PROJECT_OVERRIDES.md`
- `docs/exec-plans/`
- `docs/issue-sessions/`
- `Inbox/`
- `Inbox/README.md`
- `.harness/version.json`
- `docs/REPOSITORY_HEALTH.md`

## Project Overrides
When a project needs behavior that differs from the upstream harness, record it in `docs/PROJECT_OVERRIDES.md` instead of editing protected core files.

Use overrides for:
- Project-specific read order additions
- Local package-manager or shell quirks
- Project-specific validation policy
- Release, review, or branch-policy deviations
- Temporary exceptions during migration

Do not use overrides to hide reusable improvements. If a local override would help multiple projects, upstream it into the harness.

Start new override files from `docs/templates/PROJECT_OVERRIDES_TEMPLATE.md`.

## Sync Rule
Harness sync may overwrite protected core files. It must preserve project-owned truth.

If a protected core file has local edits, `scripts/update-harness.sh` should stop and report the file. The project can then:
- Move the local change to `docs/PROJECT_OVERRIDES.md`
- Promote the change upstream
- Rerun sync with `--force` after intentionally accepting overwrite risk

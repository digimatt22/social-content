# Project Bootstrap Checklist

Use this checklist when installing the harness into a new or existing project. The goal is to replace generic starter assumptions with project-specific facts before routine development begins.

Preferred hosted install/update command:

```sh
curl -fsSL https://harness.digicolony.com/install | bash
```

To install into a specific project folder:

```sh
curl -fsSL https://harness.digicolony.com/install | bash -s -- --target /path/to/project
```

Local harness-development bootstrap command:

```sh
scripts/new-project.sh --init-git /path/to/new-project
```

## Required Before Shared Development
- [ ] Project name and purpose are written in `README.md`.
- [ ] The project was installed or updated with the hosted installer, `scripts/install-harness.sh`, `scripts/new-project.sh`, or an equivalent reviewed process.
- [ ] For existing projects, pre-existing project-owned files were preserved.
- [ ] For older harness installs, `.harness/version.json` records the previous and new harness version after update.
- [ ] `AGENTS.md` read order still matches the repo.
- [ ] `docs/PROJECT_CONTEXT.md` describes the project runtime, package manager, local setup, known constraints, owners, and unknowns.
- [ ] `docs/ARCHITECTURE.md` describes system boundaries, data flow, contracts, and operational risks.
- [ ] `docs/AUTOMATIONS.md` lists local commands, CI checks, jobs, scheduled tasks, deployments, and manual operations.
- [ ] `docs/VALIDATION.md` lists the checks required for documentation, behavior, UI, data, and production-facing changes.
- [ ] `docs/PROJECT_INTAKE_WORKFLOW.md` has been run or explicitly deferred.
- [ ] lifeOS registration state is recorded in `docs/PROJECT_CONTEXT.md` as `Known`, `Proposed`, `Skipped`, or `Unknown`.
- [ ] If lifeOS MCP was available and the project was not known, a `lifeos.propose_project_registration` proposal was submitted for review and the returned `CTX-*` key was recorded.
- [ ] Any planning-relevant `STATUS-*` key from `lifeos.remember` or `lifeos.submit_status_update` is recorded only when follow-up depends on it.
- [ ] `docs/PROJECT_OVERRIDES.md` exists and records local harness deviations or explicitly says none.
- [ ] `docs/REPO_MAP.md` identifies high-value files, source layout, commands, risky areas, and known gaps.
- [ ] `docs/INBOX.md` and `Inbox/README.md` exist if supplemental repo-tracked context will be used.
- [ ] `.harness/version.json` records the upstream harness version or commit.
- [ ] Git is initialized with a remote and default branch.
- [ ] The default branch has an owner-approved protection policy.
- [ ] A first execution plan exists for any non-trivial project setup work.

## Runtime And Tooling
- [ ] Language and framework are identified.
- [ ] Package manager is identified.
- [ ] Local setup command is documented.
- [ ] Build command is documented or marked `TBD`.
- [ ] Format command is documented or marked `TBD`.
- [ ] Lint command is documented or marked `TBD`.
- [ ] Typecheck command is documented or marked `TBD`.
- [ ] Test command is documented or marked `TBD`.
- [ ] Required local services are documented.
- [ ] Required environment variables are listed without secret values.

## Environments
- [ ] Local environment expectations are documented.
- [ ] Preview or review environment expectations are documented, if applicable.
- [ ] Staging environment expectations are documented, if applicable.
- [ ] Production environment expectations are documented, if applicable.
- [ ] Deployment owner is identified.
- [ ] Rollback path is documented or marked `TBD`.

## Access And Secrets
- [ ] Repository owner and maintainers are identified.
- [ ] Agent account access is limited to required repos.
- [ ] Required GitHub teams or collaborators are documented.
- [ ] Secrets manager or storage location is documented.
- [ ] Secret rotation owner is documented or marked `TBD`.
- [ ] External systems and permissions are listed.

## Work Tracking
- [ ] Source of truth for backlog items is selected.
- [ ] Source of truth for active execution plans is `docs/exec-plans/active/`.
- [ ] Source of truth for completed plans is `docs/exec-plans/completed/`.
- [ ] Issue tracker labels or conventions are documented, if applicable.
- [ ] PR review and merge rules are documented.

## First-Project Readiness
The harness is ready to bring into a real project when every required item is checked or explicitly marked `TBD` with owner, risk, and follow-up location.

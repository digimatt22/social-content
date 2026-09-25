# Repository Health Checklist

Use this checklist to decide whether a copied harness is ready for regular shared development.

## Source Control
- [ ] Project was installed or updated with the hosted installer, `scripts/install-harness.sh`, `scripts/new-project.sh`, or an equivalent reviewed process.
- [ ] Git repository initialized.
- [ ] Remote configured.
- [ ] Default branch pushed.
- [ ] Default branch protected or exception documented.
- [ ] Agent account has only required repository access.
- [ ] Commit author identity is intentional for this machine.
- [ ] Current-state gate exists and is documented.

## Documentation
- [ ] `README.md` describes the actual project.
- [ ] `AGENTS.md` is short and links to durable docs.
- [ ] `docs/PROJECT_CONTEXT.md` reflects current repo reality.
- [ ] `docs/PROJECT_INTAKE_WORKFLOW.md` has been run or explicitly deferred.
- [ ] `docs/PROJECT_OVERRIDES.md` exists and records local deviations from harness core.
- [ ] `docs/REPO_MAP.md` helps future agents target file reads.
- [ ] `docs/INBOX.md` exists if supplemental repo-tracked context is used.
- [ ] `.harness/version.json` records harness source version.
- [ ] GitHub issue-session workflow exists if issues are used as work intake.
- [ ] `docs/ARCHITECTURE.md` documents boundaries and contracts.
- [ ] `docs/AUTOMATIONS.md` documents commands and operational entrypoints.
- [ ] `docs/VALIDATION.md` documents required checks.
- [ ] Internal Markdown links pass.

## Workflow
- [ ] Active work uses feature branches.
- [ ] Non-trivial work has an execution plan.
- [ ] PR template exists.
- [ ] PRs include validation evidence.
- [ ] Agents verify PR branch state before resuming work.
- [ ] GitHub issue work posts status/questions back to the source issue.
- [ ] Human validation has owner, steps, and evidence location.
- [ ] Completed plans move to `docs/exec-plans/completed/`.

## Automation And Testing
- [ ] Format command exists or is marked `TBD`.
- [ ] Lint command exists or is marked `TBD`.
- [ ] Typecheck command exists or is marked `TBD`.
- [ ] Test command exists or is marked `TBD`.
- [ ] CI exists or is marked `TBD` with owner and timeline.
- [ ] Link checker or equivalent documentation validation exists.
- [ ] Inbox checker exists when inbox material is used.

## Operations
- [ ] Deployment path is documented or marked `TBD`.
- [ ] Rollback path is documented or marked `TBD`.
- [ ] Secrets and environment variables are documented without values.
- [ ] External system owners are documented.
- [ ] Runbooks exist for risky manual operations.

## Readiness Rating
- `Ready`: all required items are checked or have accepted owners and risks.
- `Usable with gaps`: development can proceed, but gaps are tracked with owners.
- `Not ready`: missing remote, review path, validation path, or project context.

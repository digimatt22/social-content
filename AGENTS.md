# AGENTS.md

This repository is a lightweight development harness for AI-assisted project work. It is designed to help agents orient quickly, plan safely, validate their changes, and preserve durable project knowledge inside the repo.

## Read Order
1. [README.md](README.md)
2. [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md)
3. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
4. [docs/AUTOMATIONS.md](docs/AUTOMATIONS.md)
5. [docs/WORKFLOW.md](docs/WORKFLOW.md)
6. [docs/CURRENT_STATE_GATE.md](docs/CURRENT_STATE_GATE.md)
7. [docs/GITHUB_ISSUE_WORKFLOW.md](docs/GITHUB_ISSUE_WORKFLOW.md)
8. [docs/HARNESS_BOUNDARIES.md](docs/HARNESS_BOUNDARIES.md)
9. [docs/SETUP.md](docs/SETUP.md)
10. [docs/PULL_REQUESTS.md](docs/PULL_REQUESTS.md)
11. [docs/WORK_STATE.md](docs/WORK_STATE.md)
12. [docs/VALIDATION.md](docs/VALIDATION.md)
13. [docs/BOOTSTRAP_CHECKLIST.md](docs/BOOTSTRAP_CHECKLIST.md)
14. [docs/LIFEOS_INTEGRATION.md](docs/LIFEOS_INTEGRATION.md)
15. [docs/PROJECT_INTAKE_WORKFLOW.md](docs/PROJECT_INTAKE_WORKFLOW.md)
16. [docs/PROJECT_OVERRIDES.md](docs/PROJECT_OVERRIDES.md)
17. [docs/INBOX.md](docs/INBOX.md)
18. [docs/REPO_MAP.md](docs/REPO_MAP.md)
19. [docs/HARNESS_SYNC.md](docs/HARNESS_SYNC.md)

## Repo Purpose
- Provide a reusable starter layout for AI agent development projects.
- Keep project facts, decisions, work state, and validation notes in durable files.
- Make safe collaboration through branches, remotes, pull requests, and review the default.
- Give future agents clear rules without duplicating long instructions in every tool-specific file.

## Working Rules
- Treat `docs/` as the system of record for project knowledge.
- Keep this file short. Add details to `docs/`, then link here.
- Keep protected harness core generic. Put project-specific deviations in `docs/PROJECT_OVERRIDES.md`.
- Do not guess missing schedules, field semantics, production contracts, or business rules. Record them as `Unknown` or `TBD`.
- Prefer small, explicit changes over broad rewrites.
- Preserve production-facing names unless a change request explicitly includes renaming and rollout notes.
- When changing behavior, update affected operational docs in the same change.
- Keep work synchronized with the configured remote unless the repo intentionally has no remote yet.
- Before starting or resuming work, run `scripts/check-current-state.sh` when available.
- When lifeOS MCP is available, load `project_harness` context, check whether the project is known, and propose registration for missing projects instead of asking Matthew to manually set them up. Treat lifeOS as private context, review queue, and outcome-level status, not as the project implementation log.
- If lifeOS context informed business strategy and Matthew later corrects durable positioning, goals, ICP, preferences, or decision criteria, propose a reviewed update with `lifeos.propose_context_update` before closeout.

## Definition Of Done
A change is not complete until all of the following are true:
- Requested code or docs are updated.
- Impacted files in `docs/` still match repo reality.
- New operational assumptions are written down.
- Work state is current in the active execution plan or relevant tracking doc.
- Validation has been performed to the extent the repo allows.
- Human-only validation steps are clearly assigned with expected evidence.
- If lifeOS context informed the work, check whether the turn produced new durable context and either propose a lifeOS update or explicitly state none was found.
- Changes are ready for review through a pull request, or the reason PR review is not applicable is documented.
- Open questions or risks are called out explicitly.

## Standard Workflow
Follow the process in [docs/WORKFLOW.md](docs/WORKFLOW.md):
- Orient
- Sync
- Plan
- Implement
- Validate
- Document
- Review
- Close

## Durable Knowledge Locations
- Repo inventory and current-state facts: [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md)
- System behavior and data flow: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Jobs, automations, commands, and operational entrypoints: [docs/AUTOMATIONS.md](docs/AUTOMATIONS.md)
- Current-state gate: [docs/CURRENT_STATE_GATE.md](docs/CURRENT_STATE_GATE.md)
- GitHub issue workflow: [docs/GITHUB_ISSUE_WORKFLOW.md](docs/GITHUB_ISSUE_WORKFLOW.md)
- Harness boundaries: [docs/HARNESS_BOUNDARIES.md](docs/HARNESS_BOUNDARIES.md)
- Setup and remote sync: [docs/SETUP.md](docs/SETUP.md)
- Pull request workflow: [docs/PULL_REQUESTS.md](docs/PULL_REQUESTS.md)
- Work-state protocol: [docs/WORK_STATE.md](docs/WORK_STATE.md)
- Validation protocol: [docs/VALIDATION.md](docs/VALIDATION.md)
- Bootstrap checklist: [docs/BOOTSTRAP_CHECKLIST.md](docs/BOOTSTRAP_CHECKLIST.md)
- lifeOS global context integration: [docs/LIFEOS_INTEGRATION.md](docs/LIFEOS_INTEGRATION.md)
- Project intake workflow: [docs/PROJECT_INTAKE_WORKFLOW.md](docs/PROJECT_INTAKE_WORKFLOW.md)
- Project overrides: [docs/PROJECT_OVERRIDES.md](docs/PROJECT_OVERRIDES.md)
- Supplemental context inbox: [docs/INBOX.md](docs/INBOX.md)
- Repo map: [docs/REPO_MAP.md](docs/REPO_MAP.md)
- Harness sync workflow: [docs/HARNESS_SYNC.md](docs/HARNESS_SYNC.md)
- Issue and backlog conventions: [docs/ISSUES_AND_BACKLOG.md](docs/ISSUES_AND_BACKLOG.md)
- Repository health checklist: [docs/REPOSITORY_HEALTH.md](docs/REPOSITORY_HEALTH.md)
- Tool adapter guidance: [docs/TOOL_ADAPTERS.md](docs/TOOL_ADAPTERS.md)
- External references and compatibility notes: [docs/REFERENCES.md](docs/REFERENCES.md)
- Harness improvement backlog: [docs/HARNESS_IMPROVEMENT_BACKLOG.md](docs/HARNESS_IMPROVEMENT_BACKLOG.md)

## Execution Plans
- Put active plans in `docs/exec-plans/active/`.
- Move completed plans to `docs/exec-plans/completed/`.
- Start from [docs/templates/EXEC_PLAN_TEMPLATE.md](docs/templates/EXEC_PLAN_TEMPLATE.md).
- Keep plan status current: planned, in progress, blocked, needs human validation, ready for review, or completed.

## What This Starter Contains
- `AGENTS.md` as the compact agent entrypoint.
- `docs/` as durable project memory.
- `docs/exec-plans/active/` and `docs/exec-plans/completed/` for work state.
- `docs/templates/` for specs, execution plans, and runbooks.
- A workflow that expects Git remotes, branches, pull requests, and validation evidence once the project is initialized.

## When To Stop And Ask
- A requested change would alter a production contract that is not documented here.
- A required trigger schedule, deployment path, or orchestration dependency is missing.
- A rename would affect production bindings or external users.
- A secret, external permission, or environment detail is missing.
- The repo has no remote or branch protection but the task requires shared review or deployment.

## Future Extensions
This starter pack intentionally omits tool-specific adapters by default:
- `CLAUDE.md`
- `.github/copilot-instructions.md`
- MCP-specific setup files
- CI provider-specific workflow files

If cross-tool compatibility becomes necessary, document the reason and add thin adapters that point back to `docs/` and this file.

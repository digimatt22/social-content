# Project Intake Workflow

Use this workflow immediately after copying the harness into a real project, or when a repo has grown enough that agents need better durable context.

## Kickoff Prompt
Ask an agent:

```text
Run the project intake workflow. Review this repo, interview me for missing context, build or update the repo map, and fill in the harness docs with facts, unknowns, validation commands, and follow-up work.
```

## Goals
- Replace starter placeholders with repo-specific facts.
- Build a concise repo map so future agents can target file reads and use fewer tokens.
- Identify build, test, validation, deployment, and review workflows.
- Capture unknowns, risks, and human-only validation needs.
- Produce follow-up work items rather than guessing missing business or production details.

## Agent Workflow
1. Orient:
   - Read `AGENTS.md`, `README.md`, and existing docs.
   - Read `docs/LIFEOS_INTEGRATION.md`.
   - Check Git status, branch, and remote.
   - Inspect top-level files with `rg --files`.
   - Identify languages, frameworks, package managers, config files, scripts, tests, and CI.
   - Check `docs/INBOX.md` and `Inbox/README.md` for supplemental context.
   - If the lifeOS MCP server is available, call `lifeos.use(project_harness)`, then `lifeos.find_project` with the workspace name, aliases, and repo path.
   - Use `lifeos.list_context`, `lifeos.read_context`, or `lifeos.search_context` only when intake needs context beyond the `project_harness` bundle.
   - If lifeOS does not know this project, infer a project registration from local repo context, ask Matthew only for missing high-impact details, and call `lifeos.propose_project_registration`.
2. Build a first-pass repo map:
   - Fill in `docs/REPO_MAP.md`.
   - Prefer concise summaries over exhaustive file listings.
   - Identify high-value entrypoints, modules, commands, and tests.
3. Interview the user:
   - Ask only for information that cannot be discovered safely from the repo.
   - Batch questions by topic so the user can answer efficiently.
   - Mark unanswered items as `Unknown` or `TBD` with owner and follow-up.
4. Update harness docs:
   - `README.md`: project purpose and quick start.
   - `docs/PROJECT_CONTEXT.md`: current facts, owners, constraints, unknowns.
   - `docs/PROJECT_CONTEXT.md`: record lifeOS registration state as `Known`, `Proposed`, `Skipped`, or `Unknown`, including any returned `CTX-*` proposal key or pending-review status.
   - `docs/ARCHITECTURE.md`: system boundaries, data flow, contracts, risks.
   - `docs/AUTOMATIONS.md`: commands, jobs, CI, deployment, manual operations.
   - `docs/VALIDATION.md`: validation contract and human checks.
   - `docs/REPOSITORY_HEALTH.md`: readiness state.
   - `docs/INBOX.md` and `Inbox/README.md`: supplemental context rules and index, if context was provided.
5. Validate:
   - Run the documented structural checks.
   - Run available build, lint, typecheck, and test commands when safe.
   - Record anything that cannot be validated locally.
6. Close:
   - Create or update an execution plan for remaining setup work.
   - Send only standup-worthy lifeOS status with `lifeos.remember` if the intake changed Matthew's planning context.
   - Use `lifeos.propose_context_update` only if intake discovers stable personal or cross-project context that belongs in lifeOS after review; preserve uncertainty and keep implementation facts in the project repo.
   - Do not send raw repo inventory, command output, or tiny setup details to lifeOS.
   - Open a PR unless the initial bootstrap is explicitly direct-to-main.

## lifeOS Project Registration

Project registration is a review proposal, not an automatic profile edit.

If `lifeos.find_project` returns unknown, use `lifeos.propose_project_registration` with:

- project name
- purpose
- status
- Matthew's role
- key people or client, if known
- why it matters now
- what done looks like
- priority
- next action
- repo path
- uncertainty notes

The proposal should be reviewed in Matthew's nightly recap with a stable key such as `CTX-12`. Matthew can approve or deny each proposed change individually by replying with phrases like `Approve CTX-12` or `Deny CTX-12`.

Record the returned key and status in `docs/PROJECT_CONTEXT.md`. If the MCP server also returns a status update key such as `STATUS-7`, record it only when it matters for follow-up.

Do not edit `context-profile/current-projects.md` from a project workspace. After Matthew approves a proposal, a local lifeOS agent can apply the exact approved change in the lifeOS repo and mark the proposal `applied`.

## lifeOS Review Queue

Use `lifeos.list_pending_reviews` or `lifeos.review_digest` only when Matthew asks to inspect pending lifeOS review items or prepare the nightly recap. Mark review items only after explicit instruction:

- `lifeos.mark_context_update_proposal` for `CTX-*` items.
- `lifeos.mark_status_update` for `STATUS-*` items.

Do not approve, deny, include, dismiss, or apply review items based only on inferred intent.

## User Intake Questions
Ask these only when the answer is not discoverable from the repo.

### Product And Ownership
- What is the project’s purpose in one or two sentences?
- Who owns the project?
- Who reviews code changes?
- Who approves production releases?

### Runtime And Setup
- What operating systems should local development support?
- What package manager and runtime versions are expected?
- Are there required local services, databases, queues, or emulators?
- Which environment variables are required, and where should secret values live?

### Architecture And Contracts
- What are the main system boundaries?
- Which APIs, schemas, files, or UI behaviors are considered stable contracts?
- Which external systems does this repo read from or write to?
- Are there destructive or production-impacting operations?

### Validation
- What commands should agents run before opening a PR?
- Which checks require a human, credentials, or a live environment?
- Are screenshots, recordings, logs, or other evidence expected?

### Delivery
- How is the project deployed?
- What is the rollback path?
- Are there release windows, approvals, or notifications?
- Which branch protection or PR rules should apply?

### Work Tracking
- Should future work live in GitHub issues, a backlog doc, an external tracker, or execution plans?
- Are there labels, milestones, or naming conventions to preserve?

## Outputs
The intake is complete when:
- `docs/REPO_MAP.md` exists and points future agents to the right files.
- `docs/PROJECT_CONTEXT.md` records whether lifeOS already knows the project, a registration proposal was submitted, the returned `CTX-*` key, or lifeOS was unavailable.
- `Inbox/README.md` indexes supplemental context when provided.
- Starter placeholders are replaced or marked `TBD`.
- Validation commands and human checks are documented.
- Unknowns have owners or follow-up items.
- A PR or documented bootstrap exception captures the change.

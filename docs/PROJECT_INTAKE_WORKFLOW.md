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
   - Check Git status, branch, and remote.
   - Inspect top-level files with `rg --files`.
   - Identify languages, frameworks, package managers, config files, scripts, tests, and CI.
   - Check `docs/INBOX.md` and `Inbox/README.md` for supplemental context.
   - Note: lifeOS / LifeOS integration is removed from this project; durable knowledge stays in `docs/`.
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
   - Open a PR unless the initial bootstrap is explicitly direct-to-main.

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
- `docs/PROJECT_CONTEXT.md` captures current project facts, owners, constraints, and unknowns.
- `Inbox/README.md` indexes supplemental context when provided.
- Starter placeholders are replaced or marked `TBD`.
- Validation commands and human checks are documented.
- Unknowns have owners or follow-up items.
- A PR or documented bootstrap exception captures the change.

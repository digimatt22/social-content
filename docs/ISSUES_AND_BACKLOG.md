# Issues And Backlog Conventions

Use one clear source of truth for each kind of work. Do not leave durable project state only in chat.

## What Goes Where
- Execution plans: approved or active non-trivial implementation work.
- Project backlog doc: near-term work that is known but not yet active.
- GitHub issues or external tracker: team-visible work that needs prioritization, assignment, labels, or cross-repo coordination.
- PRs: review discussion for a concrete branch.
- Runbooks: repeatable operational procedures.

## Execution Plan Criteria
Create an execution plan when work:
- Touches runtime behavior, deployment, data, or production contracts
- Requires multiple steps or files
- Has meaningful validation or human-review requirements
- Needs assumptions, risks, or decisions recorded before implementation

Do not create an execution plan for a tiny typo or a single obvious documentation correction unless the project owner asks for one.

## Backlog Item Criteria
Use a backlog item when work is not ready to implement but should not be forgotten. Each backlog item should include:
- Status
- Short outcome
- Why it matters
- Acceptance criteria
- Owner or `TBD`
- Links to issues, plans, or PRs when they exist

## Issue Tracker Criteria
Use GitHub issues or an external tracker when work needs:
- Assignment across people
- Labels, milestones, or prioritization
- Cross-repo visibility
- Discussion before a plan exists
- Non-agent stakeholders

When an issue becomes active implementation work, link it from the execution plan.

## GitHub Issue Sessions
When multiple GitHub issues are pulled into agent work, use `docs/GITHUB_ISSUE_WORKFLOW.md`.

Issue sessions should:
- Import issues as claims to verify, not guaranteed facts.
- Comment on GitHub when imported, triaged, blocked, started, merged into a session branch, or completed.
- Use one `session/<slug>` branch as the integrated test branch.
- Use individual `issue/<number>-<description>` branches for confirmed issue work.
- Open one final session PR when the issue set is ready for integrated review.

## Status Values
Use the same status values as `docs/WORK_STATE.md` where practical:
- planned
- in progress
- blocked
- needs human validation
- ready for review
- completed
- abandoned

## Closeout
When work closes, record:
- Final status
- PR or commit link
- Validation evidence
- Follow-up items
- Reason if abandoned or superseded

# Pull Request Workflow

Pull requests are the default review path for shared changes.

## Branch Naming
Use short-lived branches with clear prefixes:
- `codex/<description>` for agent-authored changes
- `feature/<description>` for human-authored features
- `fix/<description>` for targeted fixes
- `docs/<description>` for documentation-only work

## Before Opening A PR
- Fetch and update from the target branch.
- Confirm the active execution plan is current.
- Run the validation commands required by the project.
- Record manual validation steps if human testing is needed.
- Push the branch to the remote.

## PR Requirements
Every PR should include:
- Summary of what changed
- Reason for the change
- Validation performed, with commands and results
- Docs updated
- Risks, unknowns, or rollback notes
- Screenshots or recordings for user-facing UI changes
- Human validation owner and evidence location when applicable

## Review Expectations
- Use at least one reviewer for shared work.
- Require CI checks when the project has CI.
- Keep discussions and requested changes attached to the PR when possible.
- Update the execution plan when review changes scope or validation status.

## Merge Policy
- Prefer squash merge unless the project documents a different policy.
- Merge only after required automated checks pass.
- Merge only after required human validation is complete or explicitly deferred with owner and risk.
- After merge, move the execution plan from `docs/exec-plans/active/` to `docs/exec-plans/completed/`.

## Direct-To-Main Exception
If PR review is skipped, document:
- Why a PR was not practical
- Who approved the exception
- What validation was performed
- What follow-up review or cleanup remains

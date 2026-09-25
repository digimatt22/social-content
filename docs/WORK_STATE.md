# Work-State Tracking

Durable work state belongs in the repo, not only in chat. Use execution plans for non-trivial work and keep them current as the work changes.

## Status Values
- `planned`: accepted or likely work that has not started.
- `in progress`: active implementation, investigation, or documentation work.
- `blocked`: work cannot continue without a missing decision, access, dependency, or external state change.
- `needs human validation`: implementation is ready for checks that only a person or live environment can perform.
- `ready for review`: implementation and required validation are complete enough for PR review.
- `completed`: work is merged, closed, or otherwise finished with no required follow-up inside the plan.
- `abandoned`: work intentionally stopped, superseded, or rejected.

## Where State Lives
- Active non-trivial work: `docs/exec-plans/active/`
- Completed or abandoned work: `docs/exec-plans/completed/`
- Future improvement ideas: project backlog, issue tracker, or a clearly named backlog doc
- External tasks: link the issue, ticket, or PR from the execution plan

## When To Update State
Update the execution plan when:
- Starting implementation
- Changing scope or acceptance criteria
- Discovering a blocker
- Completing automated validation
- Assigning human validation
- Opening a PR
- Merging, abandoning, or superseding the work

## Minimum Active Plan Fields
An active plan should include:
- Status
- Owner
- Branch
- PR link when available
- Summary and scope
- Work-state checklist
- Key decisions and assumptions
- Implementation areas
- Validation log
- Human validation requirements
- Closeout notes

## Closing A Plan
Move a plan to `docs/exec-plans/completed/` only when:
- The work has merged, or
- The work was intentionally abandoned or superseded, and
- The closeout section explains final status, validation, and follow-up work.

Do not delete active plans just because work paused. Mark them `blocked`, `needs human validation`, or `abandoned` with the reason.

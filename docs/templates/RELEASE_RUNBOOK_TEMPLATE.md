# Release And Rollback Runbook Template

## Purpose
Describe what release or deployment this runbook covers.

## Scope
- Included changes
- Excluded changes
- Systems affected

## Preconditions
- Required access
- Required approvals
- Required branch, commit, tag, or artifact
- Required secrets or environment state
- Required backup or migration state

## Release Steps
1. Confirm the target commit or artifact.
2. Confirm required checks passed.
3. Announce or coordinate release window, if needed.
4. Run deployment steps.
5. Capture deployment output or release URL.

## Verification
- Automated checks:
- Smoke checks:
- Human checks:
- Evidence location:

## Rollback Criteria
- Signal that requires rollback
- Owner who can decide rollback
- Time window for deciding

## Rollback Steps
1. Stop or pause rollout if supported.
2. Restore previous artifact, config, or data state.
3. Verify rollback success.
4. Notify stakeholders.

## Failure Handling
- Common failure signal
- Immediate safe response
- Escalation path

## Closeout
- Release result
- Validation evidence
- Follow-up items
- Incident or post-release notes, if applicable

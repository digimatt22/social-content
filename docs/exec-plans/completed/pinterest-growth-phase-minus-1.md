# Pinterest Growth Phase -1: Capability and Authority Gate

## Status

- Status: completed
- Owner: Codex
- Branch: `codex/pinterest-growth-phase-minus-1`
- PR: Not applicable; Marketing OS has no `origin` remote
- Last updated: 2026-07-24

## Summary

- Verified local, website, provider, and Sheldon capabilities without making production writes.
- Selected the permanent Marketing OS service foundation.
- Defined explicit safe fallbacks for every unavailable external capability.
- Authorized Phase 0 internal foundation work while keeping public Pinterest writes and unavailable analytics/attribution paths gated.

Out of scope:

- Persistent infrastructure creation
- Database migration
- Authentication implementation
- Public Pin creation
- Production website writes
- External account or Cloudflare configuration

## Work State

- Planned: None.
- In progress: None.
- Blocked: Public Pinterest publishing, private Etsy transaction ingestion, Google reporting, live alert delivery, and Magnific execution remain gated as recorded in the capability matrix.
- Needs human validation: External provider connection/authority decisions are required only before their first live use.
- Ready for review: ADR, capability matrix, and redacted test evidence.
- Completed: Local/provider read tests, Sheldon preflight, PostgreSQL locking proof, architecture decision, safe fallbacks.

## Decisions

- Retain Flask/Python and keep it separate from the public Next.js website.
- Use Sheldon as the initial always-on private service host.
- Use an app-owned PostgreSQL 17 container as hosted production persistence.
- Implement the first durable queue in PostgreSQL with leases, heartbeats, `SKIP LOCKED`, advisory scheduler locking, retry, quarantine, and dead letters.
- Implement application-level human authentication and scoped service identities.
- Allow Phase 0 to proceed without Pinterest/Google/private Etsy credentials.
- Do not allow unattended external writes until provider, alert, cost, and pause-policy gates pass.

## Implementation

- Added `docs/architecture/adr-001-permanent-marketing-service-foundation.md`.
- Added `docs/architecture/pinterest-growth-capability-matrix.md`.
- Added `docs/reviews/phase-minus-1-capability-test-log.md`.
- Updated the parent plan’s work state and validation evidence.

## Validation

- `scripts/check-current-state.sh` — reported missing `origin`, expected.
- Live read-only Etsy catalog check — passed, 74 active listings.
- Live authenticated MattMadeMe product read — passed, 61 products.
- Live authenticated MattMadeMe blog read — passed, 6 posts.
- Sheldon read-only runtime and secret-permission preflight — passed.
- Disposable PostgreSQL 17 connection test — passed.
- Concurrent `FOR UPDATE SKIP LOCKED` durable-job claim — passed.
- Disposable PostgreSQL container cleanup — passed.
- Documentation whitespace/structure checks — passed.
- `python -m unittest tests.test_skills` — 2 tests passed.
- `scripts/check-doc-links.sh` — new Phase -1 links passed; the repository check still reports the pre-existing missing `docs/HARNESS_IMPROVEMENT_BACKLOG.md` target from `AGENTS.md`.

## Human Validation

- Owner: Matthew
- Exact steps: Before the first live use of each gated provider, approve/connect that provider and review the corresponding capability-matrix row.
- Expected evidence: Redacted successful API/preflight result, confirmed account/access tier and scopes, alert/pause policy, and a linked phase plan.
- Evidence location: `docs/reviews/` and the implementing phase plan.
- Blocks merge: No for this documentation/evidence phase.
- Blocks live use: Yes for the corresponding gated external capability.

## Documentation

- Phase -1 artifacts are project-owned durable records.
- This plan is closed under `docs/exec-plans/completed/` in the scoped Phase -1 commit.

## Closeout

- Final status: completed.
- Remote review is unavailable because the repo has no `origin`.
- Phase 0 may begin.

# Phase 3 Shadow Production Validation

## Scope

Validation covers policy/schema, deterministic campaign production, page-only
drafts, Pinterest variants, provenance, QA, duplicate leases, review evidence,
digests, durable scheduling, authentication, and zero-external-write authority.

## Commands

```sh
.venv/bin/python -m unittest -v \
  tests.test_phase3_shadow \
  tests.test_phase3_shadow_postgres
```

```sh
MARKETING_OS_DB_URL=sqlite:///… .venv/bin/alembic upgrade head
MARKETING_OS_DB_URL=sqlite:///… .venv/bin/alembic downgrade 0003_coverage_intelligence
MARKETING_OS_DB_URL=sqlite:///… .venv/bin/alembic upgrade head
```

## Representative evidence

- 30 ready variants across 10 distinct coverage cells;
- all three reviewed shadow-board mappings;
- two ranked page opportunities producing local page-only drafts;
- actual prebuilt checksummed 1000×1500 PNG inputs;
- product accuracy remains `unverified_requires_human`;
- zero Pinterest, website, or provider calls.

Failures cover unresolved identity, unsupported claims, unresolved placeholders,
conflicting attribution, unknown boards, missing/non-fixture/changed assets,
duplicate payloads, and attempted authority expansion.

Review-loop evidence includes append-only item decisions, server-derived counts,
a measured 73-second completed fixture session, immutable completion, digest
replay, and actionable reason grouping.

## Results

- Local Phase 3 tests: 23/23 passing.
- SQLite migration upgrade/downgrade/upgrade: passing.
- PostgreSQL 17 migration and foundation/coverage/shadow concurrency: 7/7
  passing.
- Impacted foundation, Phase 1, coverage, and shadow suite: 58/58 passing.
- Full Marketing OS suite: 193 run, 185 passing, 7 environment-gated skips, and
  one pre-existing unrelated Art Studio failure in the user-owned dirty
  `tests/test_phase3.py` work. The failing expectation requires a literal
  `$social-media-art-director` marker that its companion dirty implementation
  currently omits; Phase 3 shadow tests do not import or modify that path.
- Shell syntax, documentation links, and `git diff --check`: passing.
- Independent implementation review: PASS after three challenge rounds —
  strategy 9.7/10, automation 9.6/10, feedback 9.6/10, no P0/P1 blockers.

## Human validation

Matthew still needs to time one representative real-output review and record
product-accuracy/source-claim decisions. This does not block the Phase 3
implementation commit. It blocks the claim that review effort materially
decreased and blocks Phase 4 autonomy graduation.

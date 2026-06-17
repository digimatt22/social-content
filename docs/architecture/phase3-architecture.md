# Phase 3 Architecture

Phase 3 moves the Marketing OS from generated Markdown into a local web console backed by SQLite.

## Runtime Shape

- `marketing_os.web_app` runs a Flask server.
- `marketing_os.db` owns engine creation, schema initialization, and sessions.
- `marketing_os.db_models` defines SQLAlchemy ORM models.
- `marketing_os.phase3` syncs business context, seeds templates/assets, persists Phase 2 plans, and updates task status/metrics.
- `docs/business` remains the editable business source input.
- `docs/templates` contains editable platform, copy, and graphic template source files.
- `data/marketing_os.sqlite` is the default local working database and is ignored by git.

## Local Database

SQLite is the default database. SQLAlchemy is used as the ORM so a later database migration does not require rewriting application logic.

Persisted records include:

- products synced from `docs/business/product-catalog.json`
- platform, copy, and graphic templates synced from `docs/templates`
- asset inventory records
- generated plans
- calendar items
- operator tasks
- task status and notes
- manual metrics
- sync metadata

## Phase 2 Compatibility

The existing CLI and Phase 2 planner remain intact. Phase 3 calls the Phase 2 planner, then persists its output into the database.

## Extension Points

- Template files can be edited or expanded without changing planner code.
- Asset records prepare for a future creative asset agent.
- Manual metrics can later be replaced or augmented by analytics adapters.
- Publishing is intentionally manual in Phase 3.

## Operating Boundary

The app is intended for a trusted local machine or trusted local network. It does not implement internet-facing authentication and should not be exposed publicly.

# MattMadeMe Marketing OS

Local-first Marketing Operating System for MattMadeMe.

The app helps a solo business owner generate and execute marketing plans from a browser-based local web console. Business knowledge is stored in `docs/business`; day-to-day plans, tasks, templates, assets, notes, and metrics are stored in local SQLite.

## What It Does

- Loads business context from Markdown files in `docs/business`.
- Loads structured product metadata from `docs/business/product-catalog.json`.
- Runs a local browser-based operator console.
- Binds to the local network by default for trusted household/shop devices.
- SQLite persistence through SQLAlchemy
- database-backed plans, tasks, assets, templates, and metrics
- operator-first Today page with one recommended next task
- guided task pages for Instagram, Facebook, Etsy, and website work
- copy controls for captions, CTAs, and hashtags
- metrics due workflow for follow-up after posting
- completed-task review and operator-facing posting guides
- local asset scanning with file checks and review states
- local/external asset-library scan with thumbnails and manifest metadata
- source-photo upload into the local product asset inventory
- manual source-photo registration from a local file path
- creative asset planning, generation manifests, and generated-output review registration
- Magnific/MCP generated-output import with provider/job metadata and review state
- high-level Planning page for destination, goal, and multi-product calendar intent
- scriptable content-production job for Codex-assisted copy and image-brief candidates
- read-only Etsy CSV listing import foundation
- read-only Etsy API sync boundary for active listings and listing images
- MattMadeMe website adapter boundary for blog draft publishing and published blog metadata
- manual override fields that protect local edits from future imports
- data health view for stale, missing, or unreviewed records
- local JSON read/write endpoints for future frontend/API reuse
- editable platform, copy, and graphic templates under `docs/templates`
- manual metric entry after posting

The Phase 2 planner remains active behind the web app. Old Phase 1/2 executable entry points are archived under `archive/phase1-phase2-executables`, and executed planning docs are archived under `docs/archive`.

Repo-specific Codex skills live under `.agents/skills/`; see [SKILLS.md](SKILLS.md) and [AGENTS.md](AGENTS.md).

## Installation

Requirements:

- Python 3.11 or newer

Clone the repository and enter it:

```bash
git clone <repo-url>
cd marketing-os
```

Editable install:

```bash
python -m pip install -e .
```

Phase 3 uses Flask and SQLAlchemy.

## Configuration

Business knowledge lives in:

- `docs/business/company-profile.md`
- `docs/business/business-goals.md`
- `docs/business/products.md`
- `docs/business/audiences.md`
- `docs/business/brand-voice.md`
- `docs/business/marketing-channels.md`

Edit those files to update business facts, products, audiences, voice, goals, and channels. The application reads them at runtime, so business updates do not require code changes.

## Usage

For a step-by-step local test flow, see [docs/getting-started.md](docs/getting-started.md). For the current operator guide, see [docs/operating-guides/local-web-console.md](docs/operating-guides/local-web-console.md).

Run the local web console:

```bash
python run_local.py
```

The default development port is `3001` so Marketing OS can run alongside other local dev servers. Override it with `--port` or `MARKETING_OS_PORT` only when needed.

Startup does not seed sample products, plans, or tasks by default. To explicitly bootstrap business docs into a fresh local database for demo or fixture work, run:

```bash
python run_local.py --bootstrap-data
```

On the same machine, open:

```text
http://127.0.0.1:3001
```

On another trusted device on the same network, open `http://<this-computer-ip>:3001`.

To bind to localhost only, override the host:

```bash
python run_local.py --host 127.0.0.1
```

To use a different local product-photo inventory:

```bash
MARKETING_OS_ASSETS_ROOT=/path/to/assets/products python run_local.py
```

Phase 5 planning uses `MARKETING_OS_ASSET_ROOT` for the repo-local asset library. The app still accepts `MARKETING_OS_ASSETS_ROOT` for the product-photo inventory, which defaults to `assets/products`.

To write JSON exports somewhere else:

```bash
MARKETING_OS_EXPORT_DIR=/path/to/exports python run_local.py
```

To store uploaded generated outputs somewhere else:

```bash
MARKETING_OS_GENERATED_OUTPUT_ROOT=/path/to/generated python run_local.py
```

To prepare review candidates for planned marketing items:

```bash
python -m marketing_os.jobs.content_production --limit 10
./scripts/run-content-production.sh
```

The wrapper defaults to planned items due within the next 14 days and is intended for manual or Codex-managed runs.

See [docs/operating-guides/codex-content-automation.md](docs/operating-guides/codex-content-automation.md) for the weekly Codex App automation prompt.

Do not expose this local app to the public internet.

Archived Phase 1/2 executable references live in `archive/phase1-phase2-executables`.

## Testing

Run the test suite with Python's built-in unittest runner:

```bash
python -m unittest discover -s tests
```

## Current Scope

**Active product goal:** Marketing OS is the **asset workshop** — find product truth + reference photos, make social-ready assets for review (catalog ↔ files ↔ generate ↔ review). Strategy lock: [docs/exec-plans/active/asset-workshop.md](docs/exec-plans/active/asset-workshop.md).

Hosted runtime targets `mmm.digicolony.net` (Sheldon). Magnific social-image drain uses the worker REST path when `MAGNIFIC_API_KEY` is set; Magnific MCP remains the interactive assistant path. Brand Lab / grok desks own posting; this app does not auto-publish to social networks.

Current implementation keeps the Python/Flask/SQLAlchemy stack (SQLite locally; PostgreSQL when hosted) with service boundaries for assets, Art Studio jobs, and review.

Operator guides:

- [Local web console operating guide](docs/operating-guides/local-web-console.md)
- [Magnific MCP creative asset guide](docs/operating-guides/magnific-mcp-creative-assets.md) (MCP + hosted REST drain notes)

Superseded Phase 5 implementation plans and proof artifacts are archived under `docs/archive/2026-06-17-phase5-implementation/`. Phase 5 is historical. The Pinterest-first growth plan is parked for primary focus (see asset-workshop park list).

Out of scope for this app's primary loop:

- Instagram / Facebook / X API publishing (Brand Lab desks)
- Live Pinterest publish as the day-to-day build driver
- Google Analytics / Search Console as primary nav
- Public mattmademe.com site desk work

The code includes local-first extension points so future integrations can be added without rewriting the core planning logic.

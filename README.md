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
- MattMadeMe website sync boundary for products, product images, and published blog metadata
- manual override fields that protect local edits from future imports
- data health view for stale, missing, or unreviewed records
- local SQLite backup from Settings
- local JSON read/write endpoints for future frontend/API reuse
- editable platform, copy, and graphic templates under `docs/templates`
- manual metric entry after posting

The Phase 2 planner remains active behind the web app. Old Phase 1/2 executable entry points are archived under `archive/phase1-phase2-executables`, and executed planning docs are archived under `docs/archive`.

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

On the same machine, open:

```text
http://127.0.0.1:8000
```

On another trusted device on the same network, open `http://<this-computer-ip>:8000`.

To bind to localhost only, override the host:

```bash
python run_local.py --host 127.0.0.1
```

To use a different local product-photo inventory:

```bash
MARKETING_OS_ASSETS_ROOT=/path/to/assets/products python run_local.py
```

Phase 5 planning uses `MARKETING_OS_ASSET_ROOT` for the future external-drive asset library. The current Phase 4 app still accepts `MARKETING_OS_ASSETS_ROOT` for the repo-local product-photo inventory.

To write JSON exports somewhere else:

```bash
MARKETING_OS_EXPORT_DIR=/path/to/exports python run_local.py
```

To prepare review candidates for planned marketing items:

```bash
python -m marketing_os.jobs.content_production --limit 10
```

To check Phase 5 final proof readiness or export a review packet:

```bash
python -m marketing_os.jobs.phase5_readiness
python -m marketing_os.jobs.phase5_readiness --export-markdown
```

For strict completion gates, add `--fail-on-incomplete` so the command exits with code 2 while human proof is still missing.

Do not expose this local app to the public internet.

Archived Phase 1/2 executable references live in `archive/phase1-phase2-executables`.

## Testing

Run the test suite with Python's built-in unittest runner:

```bash
python -m unittest discover -s tests
```

## Current Scope

The Marketing OS is a local planning and operator assistant. It does not publish content or connect to external analytics.

Current implementation keeps the Python/Flask/SQLAlchemy/SQLite stack while adding service boundaries and integration-ready fields so a future richer frontend can attach without replacing the planning core.

Current active planning docs:

- [Phase 5 goal](docs/goals/phase5-integrations-and-creative-quality.md)
- [Phase 4 current-state premortem](docs/reviews/phase4-current-state-premortem.md)
- [Etsy read-only integration plan](docs/architecture/etsy-read-only-integration-plan.md)
- [MattMadeMe website integration plan](docs/architecture/mattmademe-website-integration-plan.md)
- [Local asset library agent access plan](docs/architecture/local-asset-library-agent-access-plan.md)
- [Freepik/Magnific creative integration plan](docs/architecture/freepik-magnific-creative-integration-plan.md)
- [Copywriter skill and learning loop plan](docs/architecture/copywriter-skill-and-learning-loop-plan.md)
- [Codex nightly content production plan](docs/architecture/codex-nightly-content-production-plan.md)
- [Phase 5 UI/UX walkthrough](docs/reviews/phase5-ui-ux-walkthrough.md)
- [Phase 5 Facebook post proof](docs/reviews/phase5-facebook-post-proof.md)
- [Phase 5 operator workflow proof](docs/reviews/phase5-operator-workflow-proof.md)
- [Phase 5 completion audit](docs/reviews/phase5-completion-audit.md)

Phase 5 final proof readiness is visible in the local app at `/phase5-readiness` and as JSON at `/api/phase5-readiness`. The readiness page can export a Markdown approval packet, and the same packet is available as JSON at `/api/phase5-approval-packet`.

Out of scope:

- Instagram API integration
- Facebook API integration
- Google Analytics integration
- Search Console integration
- Automated content publishing

The code includes local-first extension points so future integrations can be added without rewriting the core planning logic.

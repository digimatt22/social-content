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
- beginner-friendly task pages for Instagram, Facebook, Etsy, and website work
- editable platform, copy, and graphic templates under `docs/templates`
- manual metric entry after posting

The Phase 2 planner remains active behind the web app. Old Phase 1/2 executable entry points are archived under `archive/phase1-phase2-executables`.

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

For a step-by-step local test flow, see [docs/getting-started.md](docs/getting-started.md).

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

Do not expose this local app to the public internet.

Archived Phase 1/2 executable references live in `archive/phase1-phase2-executables`.

## Testing

Run the test suite with Python's built-in unittest runner:

```bash
python -m unittest discover -s tests
```

## Current Scope

The Marketing OS is a local planning and operator assistant. It does not publish content or connect to external analytics.

Out of scope:

- Etsy API integration
- Instagram API integration
- Facebook API integration
- Google Analytics integration
- Search Console integration
- Automated content publishing

The code includes local-first extension points so future integrations can be added without rewriting the core planning logic.

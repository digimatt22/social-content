# MattMadeMe Marketing OS

Local-first Phase 1 Marketing Operating System for MattMadeMe.

The app helps a solo business owner generate marketing plans, content ideas, weekly reports, and prioritized recommendations from the business knowledge stored in `docs/business`.

## What It Does

- Loads business context from Markdown files in `docs/business`.
- Loads structured product metadata from `docs/business/product-catalog.json`.
- Generates a 30-day marketing calendar.
- Generates:
  - 30 Instagram post ideas
  - 30 Facebook post ideas
  - 10 Instagram Reel ideas
  - 10 Etsy promotion ideas
  - 10 blog topic ideas
  - 10 email newsletter ideas
- Generates a weekly marketing report.
- Generates prioritized marketing recommendations with aligned business goals, impact, effort, rationale, and next steps.
- Runs fully locally with Python stdlib only.

Phase 2 adds:

- planning modes: `light`, `standard`, `launch`, `holiday`, and `event`
- validated calendar items
- ready-to-edit content drafts
- asset briefs and production notes
- weekly action list
- manual weekly review template

## Installation

Requirements:

- Python 3.11 or newer

Clone the repository and enter it:

```bash
git clone <repo-url>
cd marketing-os
```

Optional editable install:

```bash
python -m pip install -e .
```

No third-party Python packages are required for Phase 1.

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

Check that business context loads:

```bash
python -m marketing_os.cli --check-context
```

Generate a marketing plan to stdout:

```bash
python -m marketing_os.cli --start-date 2026-06-17
```

Generate a Markdown plan file:

```bash
python -m marketing_os.cli --start-date 2026-06-17 --output outputs/marketing-plan.md
```

Generate a Phase 2 standard-week plan:

```bash
python -m marketing_os.cli --phase 2 --mode standard --start-date 2026-06-17 --output outputs/phase2-standard.md
```

Generate a Phase 2 launch-week plan:

```bash
python -m marketing_os.cli --phase 2 --mode launch --start-date 2026-06-17 --output outputs/phase2-launch.md
```

Run the end-to-end demo:

```bash
python demo.py
```

Run the Phase 2 demos:

```bash
python demo_phase2.py
```

The demo writes:

```text
outputs/demo-marketing-plan.md
```

## Testing

Run the test suite with Python's built-in unittest runner:

```bash
python -m unittest discover -s tests
```

## Current Scope

Phase 1 is a local planning assistant. It does not publish content or connect to external analytics.

Out of scope:

- Etsy API integration
- Instagram API integration
- Facebook API integration
- Google Analytics integration
- Search Console integration
- Automated content publishing

The code includes adapter interfaces and mock implementations so future integrations can be added without rewriting the core planning logic.

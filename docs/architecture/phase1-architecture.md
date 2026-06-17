# Phase 1 Architecture

Last updated: 2026-06-17

## Design Goals

- Local-first and runnable after cloning the repository.
- Business context is read from `docs/business` at runtime.
- No business facts are hardcoded into generators.
- Python stdlib only for Phase 1.
- Modular services with interfaces for future integrations.

## System Structure

```text
marketing_os/
├── context.py          # Markdown knowledge-base loader
├── models.py           # Dataclasses for context, ideas, calendar, reports, recommendations
├── content.py          # Content idea generator
├── calendar.py         # 30-day content calendar planner
├── recommendations.py  # Business-goal-aligned recommendation engine
├── reporting.py        # Weekly marketing report builder
├── integrations.py     # Future adapter interfaces and local mocks
├── workflow.py         # End-to-end orchestration
├── render.py           # Markdown rendering
└── cli.py              # Command-line interface
```

## Data Flow

1. `context.load_business_context()` reads the authoritative Markdown files from `docs/business`.
2. `ContentGenerator` creates content ideas using products, audiences, brand voice, goals, channels, and CTAs from the loaded context.
3. `CalendarPlanner` turns generated ideas into a 30-day calendar.
4. `RecommendationEngine` evaluates actions against business goals and returns prioritized recommendations.
5. `ReportBuilder` summarizes the next week of planned content, opportunities, recommended actions, seasonal opportunities, and priorities.
6. `render.render_plan_markdown()` exports a readable Markdown plan.

## Business Context Boundary

The following files are the source of truth:

- `docs/business/company-profile.md`
- `docs/business/business-goals.md`
- `docs/business/products.md`
- `docs/business/audiences.md`
- `docs/business/brand-voice.md`
- `docs/business/marketing-channels.md`

To change products, audiences, goals, brand voice, or channel context, edit these Markdown files. The app will pick up changes on the next run.

## Extension Points

`marketing_os/integrations.py` defines interfaces for future external systems:

- `Publisher`
- `AnalyticsProvider`
- `CalendarExporter`

Phase 1 includes:

- `MockPublisher`
- `MockAnalyticsProvider`
- `MarkdownCalendarExporter`

Future integrations can implement those protocols for Etsy, Instagram, Facebook, Google Analytics, Search Console, email platforms, or calendar tools while keeping the core planning services local and testable.

## Out-Of-Scope Integrations

Phase 1 intentionally does not implement:

- Etsy API integration
- Instagram API integration
- Facebook API integration
- Google Analytics integration
- Search Console integration
- Automated content publishing

## Verification

Acceptance coverage lives in `tests/test_phase1.py`.

Run:

```bash
python -m unittest discover -s tests
python demo.py
```


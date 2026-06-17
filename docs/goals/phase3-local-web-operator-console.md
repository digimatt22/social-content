# Phase 3 Local Web Operator Console

Build Phase 3 of the MattMadeMe Marketing Operating System.

## Source Inputs

Phase 3 should be guided by:

- `docs/goals/phase1-marketing-agent.md`
- `docs/goals/phase2-marketing-planner.md`
- `docs/reviews/marketing-plan-premortem.md`
- `docs/reviews/phase2-output-operator-premortem.md`
- `docs/goals/future-creative-asset-agent.md`
- `docs/business/company-profile.md`
- `docs/business/business-goals.md`
- `docs/business/products.md`
- `docs/business/product-catalog.json`
- `docs/business/audiences.md`
- `docs/business/brand-voice.md`
- `docs/business/marketing-channels.md`

Use the Phase 2 operator premortem as the source of truth for the Phase 3 problem statement.

## Problem Statement

Phase 2 produces strategically better plans, but it is still a Markdown-and-terminal workflow. That is not friendly enough for the likely day-to-day operator: Matt's wife, who may be managing social channels without being a social media power user.

The system needs to become a usable local web app, not just a text generator. It should guide a non-technical operator through what to do today, what to post, what asset to use, what buttons or platform flow to follow, and what metric to record afterward.

## Objective

Transform the Marketing OS from generated Markdown files into a local-network web application with persistent state, beginner-friendly workflows, platform templates, and a database-backed planning and execution system.

The app should run locally, be accessible from devices on the local network, and support a practical weekly social workflow without requiring normal users to open Terminal, edit Markdown, or understand the codebase.

## Product Vision

Phase 3 should feel like a small local marketing command center:

- Matt can review business context, generate plans, and approve work.
- The social operator can open a browser, see today's tasks, follow posting instructions, copy captions, select assets, and mark work complete.
- The system remembers status, notes, assets, and manual performance metrics.
- Templates make platform-specific posting less mysterious.
- The planner becomes an app experience, not a file dump.

## Technical Direction

### Local Web App

- Build a web app that runs locally and is accessible on the local network.
- Provide a browser-based UI for planning, review, and daily execution.
- Avoid requiring Terminal for normal day-to-day use after the server is running.
- Include a simple startup command for development/testing.

Suggested stack:

- Python backend.
- FastAPI or Flask for the local web server.
- Server-rendered HTML or a small frontend app; choose the simpler path unless the UI truly needs more.
- SQLite for Phase 3 persistence.
- SQLAlchemy or SQLModel as the ORM so the app can migrate to another database later.
- Alembic or a lightweight migration pattern if schema changes are expected.

### Local Database

Use SQLite as the default local database.

Persist at minimum:

- business/product sync metadata
- product entities
- platform templates
- copy templates
- asset records
- generated plans
- calendar items
- content drafts
- operator tasks
- posting workflow status
- manual metrics
- review notes

The source Markdown/JSON business files may remain as seed/source-of-truth inputs, but Phase 3 should not rely on generated Markdown outputs as the working state.

## Required Capabilities

### 1. Local Web Console

- Start a local web server.
- Show a home dashboard.
- Show today's operator tasks first.
- Show weekly plan overview.
- Show plan status at a glance.
- Provide navigation for:
  - Today
  - This Week
  - Calendar
  - Content Drafts
  - Assets
  - Templates
  - Metrics
  - Settings

### 2. Beginner Operator View

Create a simplified daily execution view for a non-social-media user.

Each task should show:

- what to do today
- who owns it
- platform
- plain-English platform explanation
- product
- asset to use
- exact draft caption/body
- CTA
- hashtags, if applicable
- posting steps
- preview checklist
- status
- what metric to record later

The operator should not need to read the full 30-day plan to complete today's work.

### 3. Role-Aware Workflow

Support at least these roles:

- Matt
- social operator
- either
- blocked until owner input

Tasks should be assignable by role.

Social operator views should hide or de-emphasize Etsy/admin/website tasks unless assigned.

### 4. Platform Playbooks

Add beginner-friendly platform playbooks for:

- Instagram feed post
- Instagram Reel
- Instagram carousel
- Facebook Page post
- Facebook group-style discussion prompt
- Etsy listing/promotion task
- Website/blog task

Each playbook should include:

- what this format means
- when to use it
- recommended device: phone, desktop, or either
- recommended media type
- posting steps
- where to put caption, CTA, hashtags, and links
- preview checklist
- beginner mistakes to avoid
- metric to check later

### 5. Platform And Copy Template System

Add editable templates for platform-native output.

Template types:

- platform templates
- copy templates
- graphic/asset templates as placeholders for future creative work

Each platform template should include:

- platform
- format
- recommended dimensions
- media count
- text overlay rules
- caption structure
- CTA placement
- asset requirements
- example layout
- difficulty level
- reuse notes

Each copy template should include:

- hook pattern
- body pattern
- CTA pattern
- hashtag rules
- first comment, if relevant
- alt text guidance
- short version
- long version

### 6. Asset Inventory

Create a local asset inventory.

Track:

- product
- asset type
- source path
- preview path, if available
- platform suitability
- readiness state
- notes
- date added

Readiness states:

- existing Etsy photo ready
- needs crop
- needs background or scene
- needs graphic template
- needs new photo
- needs generated composite

Phase 3 does not need to generate graphics automatically, but it should prepare the ground for a future creative asset agent.

### 7. Plan Generation Into The Database

Phase 3 should continue to use the Phase 2 planner logic, but generated plans should be stored in the database.

Persist:

- plan
- planning mode
- generated date
- weekly theme
- campaign narrative
- validation report
- calendar items
- content drafts
- weekly actions
- manual review fields

The UI should allow viewing prior generated plans.

### 8. Task Status Workflow

Support practical task statuses:

- needs asset
- needs copy review
- ready to post
- scheduled
- posted
- metrics needed
- complete
- skipped
- blocked

Status changes should persist.

Each task should support notes.

### 9. Manual Metrics Workflow

Make metrics easy for a beginner.

For each posted item, show:

- when to check metrics
- where to find the metric
- which numbers to copy
- fields to enter values

Track:

- post URL
- views or reach
- likes
- comments
- shares
- saves
- Etsy visits or sales note
- email signup note
- lesson learned

### 10. Non-Terminal Friendly Operation

Normal use should not require:

- editing Markdown
- editing JSON
- running multiple CLI commands
- interpreting tracebacks
- opening generated Markdown output files

Acceptable for Phase 3:

- one documented command to start the server
- optional helper script such as `./run-local.sh`
- browser-based use after server starts

## Directory Structure Direction

Phase 3 should introduce structure for app, templates, skills, and assets without overbuilding every future feature.

Target direction:

```text
app/
├── backend/
├── frontend/ or templates/
└── static/

marketing_os/
├── core/
├── planners/
├── validators/
├── repositories/
├── services/
└── adapters/

docs/
├── operating-guides/
├── templates/
│   ├── platform/
│   ├── copy/
│   └── graphics/
└── skills/

assets/
├── products/
├── brand/
└── templates/

data/
├── marketing_os.sqlite
└── backups/

outputs/
├── plans/
├── graphics/
├── captions/
└── reviews/
```

The exact structure may differ if implementation pressure suggests a simpler approach, but the system should stop treating raw Markdown outputs as the primary user interface.

## Out Of Scope

Do not implement in Phase 3:

- automated publishing to Instagram, Facebook, Etsy, or the website
- external analytics integrations
- automatic image generation
- paid ads management
- multi-user cloud hosting
- authentication for internet-exposed deployment

The app is intended for local network use only in this phase.

## Creative Asset Agent Boundary

Phase 3 should prepare for a future creative asset agent but not implement the full agent.

Phase 3 should:

- create asset inventory support
- allow plans/tasks to reference asset records
- define graphic template metadata placeholders
- link to `docs/goals/future-creative-asset-agent.md`

Phase 3 should not:

- automatically generate product graphics
- alter product photos
- rely on AI image generation for normal planning

## Definition Of Done

Phase 3 is complete when:

1. A local web app can be started with a documented command.
2. The web app is accessible from a browser on the local machine.
3. The app can be configured to bind to the local network for access from another device.
4. SQLite is used as the default local database.
5. An ORM is used for database access.
6. The app can initialize or migrate its database.
7. Business/product context can be loaded or seeded into the database.
8. A Phase 2-style plan can be generated and persisted to the database.
9. The dashboard shows today's tasks before long planning details.
10. A non-technical operator can open a task and see:
    - plain-English instructions
    - platform steps
    - product
    - asset
    - caption/body
    - CTA
    - hashtags where relevant
    - preview checklist
    - metric instructions
11. Task status can be updated and persists after refresh.
12. Manual metrics can be entered and persist after refresh.
13. Platform templates exist for Instagram, Facebook, Etsy, and Website/blog workflows.
14. Copy templates exist for at least:
    - launch post
    - collector prompt
    - cruise duck post
    - gift buyer post
15. Asset inventory exists and can track at least product, path, readiness state, and notes.
16. Existing Phase 1 and Phase 2 CLI tests still pass or have documented replacements.
17. New tests cover database setup, plan persistence, task status persistence, metrics persistence, and template loading.
18. Documentation explains:
    - how to start the local web app
    - how to access it from another local device
    - how to generate a plan
    - how the operator should use Today's Tasks
    - how to update task statuses
    - how to enter metrics
    - how templates and assets are stored

## Acceptance Criteria

### AC1 - Local Web App

- A documented command starts the app locally.
- The app serves a browser UI.
- The app has a health check endpoint or equivalent status indicator.
- The app can be configured for local-network access.

### AC2 - Database And Persistence

- SQLite is the default database.
- ORM models exist for products, templates, assets, plans, calendar items, tasks, and metrics.
- Database initialization is documented.
- Generated plans persist.
- Task status updates persist.
- Metrics entries persist.

### AC3 - Operator Dashboard

- The first screen prioritizes today's tasks.
- The operator can see what to do next without reading a 30-day Markdown plan.
- Must-do tasks are visually separated from should-do and optional tasks.
- Blocked tasks clearly explain what input is needed.

### AC4 - Task Detail View

Each task detail view includes:

- role owner
- platform
- format
- product
- asset record or asset requirement
- exact copy
- CTA
- hashtags, if relevant
- beginner posting steps
- preview checklist
- metric instructions
- status controls
- notes field

### AC5 - Platform Templates

- Platform templates are loaded from editable files or database records.
- Templates include dimensions, media count, caption structure, CTA placement, and beginner steps.
- At least one Instagram Reel template exists.
- At least one Instagram post or carousel template exists.
- At least one Facebook post template exists.
- At least one Etsy task template exists.
- At least one Website/blog template exists.

### AC6 - Copy Templates

- Copy templates are loaded from editable files or database records.
- Templates produce hook/body/CTA/hashtag sections.
- Persona labels are translated into human-friendly language.
- The system avoids internal labels such as `Hobby, Profession, Or Identity Buyer` in public-facing copy unless intentionally transformed.

### AC7 - Asset Inventory

- Product assets can be represented in the system.
- Each asset can be associated with a product.
- Each asset has a readiness state.
- Tasks can reference assets or asset requirements.
- Missing assets are shown as actionable blockers.

### AC8 - Manual Metrics

- The operator can enter metrics for a posted task.
- The UI explains where or when to collect metrics.
- Metrics remain available after refresh.
- A weekly review view summarizes completed, skipped, blocked, and metrics-needed tasks.

### AC9 - Non-Technical Usability

- Normal operator use does not require Terminal.
- Normal operator use does not require editing Markdown or JSON.
- Errors are shown in friendly language.
- The app provides enough guidance for a person unfamiliar with Instagram/Facebook terminology.

### AC10 - Backward Compatibility

- Phase 1 and Phase 2 command-line workflows remain usable, or replacements are documented and tested.
- Existing tests continue to pass unless intentionally replaced by stronger tests.

## Success Metric

A non-social-media-savvy operator can open the local web app, complete today's top social task, and record the result without asking Matt how to interpret the plan, where to find the copy, what asset to use, or what metric to capture.


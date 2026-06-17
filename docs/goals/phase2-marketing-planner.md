# Phase 2 Marketing Planner

Build Phase 2 of the MattMadeMe Marketing Operating System.

## Source Inputs

Phase 2 should be guided by:

- `docs/goals/phase1-marketing-agent.md`
- `docs/reviews/marketing-plan-premortem.md`
- `docs/business/company-profile.md`
- `docs/business/business-goals.md`
- `docs/business/products.md`
- `docs/business/audiences.md`
- `docs/business/brand-voice.md`
- `docs/business/marketing-channels.md`

Use the business files as the source of truth for business context. Use the premortem as the source of truth for the Phase 2 problem statement.

## Problem Statement

Phase 1 successfully generates a complete marketing plan, but the output is not yet reliable or operational enough for weekly use. The premortem identified several failure modes:

- product parsing can confuse analytical text with product names
- generated content is mostly prompt-like rather than ready-to-edit
- goals, platforms, and CTAs can be misaligned
- calendar cadence is mechanical
- audience/product pairings can be arbitrary
- seasonal intelligence is too thin
- recommendations are not specific enough to execute
- brand voice rendering can be awkward
- asset and production planning are missing
- calendar items are not prioritized by importance, effort, or impact

## Objective

Transform the Phase 1 generator from a count-complete planning demo into a usable weekly marketing planner that produces strategically coherent, ready-to-edit content plans for MattMadeMe.

The system should help a solo business owner decide what to create first, why it matters, what asset is needed, what copy to start from, and how success should be judged.

## Required Capabilities

### 1. Structured Product Knowledge

- Separate product entities from commentary and analysis.
- Prevent analytical sentences from being treated as products.
- Support product metadata that can be edited without code changes.
- Track, at minimum:
  - product name
  - product status, such as active, upcoming, seasonal, cooling, or momentum
  - primary audience
  - secondary audiences
  - best channels
  - use cases
  - seasonality
  - sales momentum note
  - launch priority

### 2. Plan Validation

- Validate every generated calendar item before rendering.
- Flag invalid or unknown products.
- Flag unsupported platforms.
- Flag mismatched business goal, objective, channel, and CTA.
- Flag awkward brand-voice rendering patterns.
- Produce a validation report with errors and warnings.
- Do not silently render a plan with P0 validation errors.

### 3. Campaign-Aware Calendar

- Support planning modes:
  - light week
  - standard week
  - launch week
  - holiday push
  - event/custom-order push
- Allow weekly owner capacity to influence the plan.
- Generate a weekly theme or campaign narrative.
- Generate a 30-day calendar that is less mechanical than Phase 1.
- Avoid unsupported channels unless they are explicitly enabled in business/channel config.

### 4. Ready-To-Edit Content Drafts

Generate real draft content, not only content angles.

Each content item should include:

- title
- platform
- content type
- business goal
- objective
- target audience
- featured product
- draft caption or body copy
- CTA
- hashtags when relevant
- asset brief
- production notes
- priority
- effort estimate
- expected impact
- success metric

### 5. Asset And Production Planning

Each social or content item should include a clear asset brief.

Reusable asset brief types should include:

- finished product closeup
- printer plate reveal
- packing order
- desk scene
- cruise hiding setup
- bundle lineup
- customer photo prompt
- maker/process shot
- seasonal gift setup
- custom/event order concept

### 6. Recommendation Quality Upgrade

Recommendations should be specific enough to act on in under 30 minutes.

Each recommendation should include:

- title
- aligned business goal
- impact estimate
- effort estimate
- estimated owner time in minutes
- rationale
- why now
- linked calendar item or content item when applicable
- next action
- success metric

### 7. Weekly Action Workflow

Generate a weekly action list that separates:

- must do
- should do
- optional
- blocked or needs input

Each action should include:

- owner task
- related content item or recommendation
- estimated time
- needed asset or input
- completion status

### 8. Measurement Prep Without External APIs

Do not implement external analytics integrations in Phase 2.

Instead, support manual tracking fields:

- planned
- approved
- posted
- skipped
- post URL
- notes
- views or reach
- likes
- comments
- shares
- saves
- Etsy visits or sales note
- email signups note
- lesson learned

Generate a weekly review template that can be filled in manually.

## Technical Constraints

- Python preferred.
- Local-first architecture.
- Open-source components preferred.
- Business and product knowledge should remain editable without code changes.
- Modular architecture.
- Future integrations should remain easy to add.
- Use interfaces/adapters where future external integrations would exist.
- Keep Phase 1 CLI workflows working unless there is an intentional documented replacement.

## Out Of Scope

Do not implement:

- Etsy API integration
- Instagram API integration
- Facebook API integration
- Google Analytics integration
- Search Console integration
- automated content publishing
- automated image or video generation
- paid ads management

Create extension points and mock implementations where future integrations would exist.

## Definition Of Done

Phase 2 is complete when:

1. Structured product knowledge exists and can be edited without code changes.
2. Generated plans no longer treat analytical sentences as products.
3. The system can generate a validated 30-day calendar.
4. The system can generate a weekly plan for at least:
   - light week
   - standard week
   - launch week
5. Every generated calendar item includes:
   - date
   - platform
   - content type
   - business goal
   - objective
   - target audience
   - featured product
   - CTA
   - draft copy or content body
   - asset brief
   - production notes
   - priority
   - effort estimate
   - expected impact
   - success metric
6. Every generated recommendation includes:
   - aligned business goal
   - impact estimate
   - effort estimate
   - estimated owner time in minutes
   - rationale
   - why now
   - next action
   - success metric
7. The system generates a weekly action list with must-do, should-do, optional, and blocked/needs-input sections.
8. The system generates a manual weekly review template.
9. Validation catches:
   - non-product featured products
   - unsupported channels
   - mismatched goal/channel/CTA combinations
   - missing asset briefs
   - missing success metrics
   - known awkward brand-voice rendering patterns
10. Documentation explains:
   - structured product knowledge
   - planning modes
   - validation
   - weekly workflow
   - manual metrics tracking
11. End-to-end demo workflows execute successfully for standard week and launch week planning.
12. Tests cover the new validation rules and Phase 2 output requirements.

## Acceptance Criteria

### AC1 - Product Knowledge

- Product entities are loaded from structured product knowledge, not inferred from arbitrary Markdown bullets.
- Product metadata can be changed without code changes.
- At least 10 products from current business docs are represented as structured product entities.
- Analytical sentences from `docs/business/products.md` are not loaded as products.

### AC2 - Plan Validation

- A validation report is produced for generated plans.
- P0 validation errors block rendering by default.
- Validation fails if a featured product is not a known product entity.
- Validation fails if a calendar item has no asset brief.
- Validation fails if a calendar item has no success metric.
- Validation flags goal/channel/CTA mismatches.
- Validation flags the awkward phrase pattern `as a Add a duck to your flock`.

### AC3 - Campaign-Aware Calendar

- The planner supports `light`, `standard`, and `launch` modes.
- Calendar cadence changes based on planning mode.
- Owner capacity affects the number and priority of generated tasks.
- Unsupported channels are excluded unless explicitly enabled.
- The weekly plan includes a theme or campaign narrative.

### AC4 - Ready-To-Edit Content

- Generated content includes draft copy, not only an angle.
- Instagram posts include caption, CTA, hashtags, and asset brief.
- Instagram Reels include hook, shot list, CTA, and production notes.
- Facebook posts include post body, CTA, and engagement prompt.
- Etsy promotions include listing/promotion action and success metric.
- Blog ideas include title, outline, CTA, and target audience.
- Email ideas are generated only when email is enabled or are clearly marked as setup/placeholder actions.

### AC5 - Strategic Coherence

- Every calendar item has a coherent combination of business goal, platform, CTA, product, and audience.
- Product/audience pairings use structured product metadata.
- Recommendations can reference specific calendar items or explain why they stand alone.
- Seasonal opportunities explain why the current week matters.

### AC6 - Recommendations

- Every recommendation includes aligned business goal, impact, effort, estimated minutes, rationale, why now, next action, and success metric.
- Recommendations are prioritized.
- At least one recommendation targets repeat customers or collectors.
- At least one recommendation targets Etsy sales.
- At least one recommendation targets owned email list growth or email-list setup.
- At least one recommendation targets new duck releases when launch mode is used.

### AC7 - Weekly Action Workflow

- The weekly output includes must-do, should-do, optional, and blocked/needs-input sections.
- Each action includes estimated time and needed input or asset.
- The plan clearly identifies what the owner should do first.
- Optional work can be skipped without breaking the week.

### AC8 - Manual Measurement

- The system outputs a weekly review template.
- The template includes fields for posted/skipped status, URL, notes, engagement, Etsy impact, email signup impact, and lessons learned.
- No external analytics API is required.

### AC9 - Documentation

- README or linked docs explain how to run Phase 2 planning modes.
- Architecture docs explain structured product knowledge and validation.
- Getting started docs include a Phase 2 test flow.
- Documentation lists known out-of-scope integrations.

### AC10 - Demonstration

- A standard-week demo runs successfully.
- A launch-week demo runs successfully.
- Demo output includes:
  - validated calendar
  - ready-to-edit content drafts
  - asset briefs
  - recommendations
  - weekly action list
  - manual review template
- Demo output contains no invalid products and no P0 validation errors.

## Success Metric

A MattMadeMe owner can generate a weekly plan in under 30 minutes and immediately know:

- what to create first
- what product and audience each item supports
- what copy to start from
- what asset to capture
- what CTA to use
- what success metric to check
- what can be skipped if time is tight


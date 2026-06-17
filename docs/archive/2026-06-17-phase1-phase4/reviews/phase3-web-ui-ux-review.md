# Phase 3 Web UI/UX Review

Reviewed interface: `http://127.0.0.1:8000`

Review date: 2026-06-17

Primary operator lens: Matt's wife may be the day-to-day social operator. She should be able to open the app, know what to do next, complete one posting task, and record follow-up metrics without understanding the planner, database, Markdown files, or social-media jargon.

Supporting screenshots captured in:

- `docs/reviews/ui-audit-screenshots-2026-06-17/`

## Executive Read

The current web console is a strong Phase 3 foundation: it has persistent tasks, platform playbooks, statuses, metrics, assets, templates, plans, and a clear local-app structure. It successfully moved the system out of Terminal and Markdown.

The main UX issue is that it still feels like a database-backed planner, not yet a calm operator assistant. The screens expose many records and labels at once, use strategy/planning terms as primary text, and ask the operator to scan grids, tables, statuses, copy blocks, and metric forms before they have a confident sense of "do this one thing now."

For a novice, the first impression is likely still overload. The next phase should focus less on adding more information and more on sequencing the information into a guided daily workflow.

## Evidence Summary

- The Today page shows `Today's Tasks`, an `Active Plan` panel, open task cards, and then repeats the same due-today tasks under `This Week`.
- The desktop Today page rendered 11 card-like objects and 10 task links in the main content area.
- The mobile Today page stacked into a 2,288 px tall main area, with duplicated due-today tasks starting again under `This Week`.
- The task detail page rendered 10 section headings and 12 form fields.
- On mobile task detail, the actual `Posting Steps` section began around 1,203 px down the page, after task title, metadata, "What To Do," asset information, caption, CTA, and hashtags.
- The metric-entry section alone was about 1,092 px tall on mobile because all metric fields are shown at once.
- The Calendar page is a full 30-day table with 31 task links and 32 rows. On mobile it overflowed wider than the viewport.
- Assets and Calendar are table-first pages. Templates is card-first but still displays implementation-oriented source paths and template records rather than an operator-facing chooser.

## What Is Working

- The left navigation is simple and predictable.
- The visual style is restrained, readable, and not gimmicky.
- Task cards expose useful metadata: due date, owner, platform, status, and product.
- The task detail page contains the right raw ingredients: explanation, device, media, asset, caption, CTA, hashtags, posting steps, checklist, status, and metrics.
- Status and notes persist, which is critical for a real operator workflow.
- The app matches the Phase 3 technical goal of being a local web console backed by SQLite.

## Critical Findings

### P0 - The Home Screen Does Not Yet Prioritize One Safe Next Action

The Phase 3 goal says the operator should not need to read the full plan to complete today's work. The current Today page starts in the right place, but it still behaves like a task inventory. It shows active-plan summary, status counts, all due-today cards, and then a broader week grid that repeats today's work.

Why this matters:

- A novice wants reassurance and a next step, not a dashboard to interpret.
- Seeing the same task twice can create doubt: "Did I already do this? Are these separate?"
- The status count `ready to post: 30` makes the workload feel huge even when only one or two tasks matter today.

Next phase goal:

- Make the first viewport a guided "Today's next task" area.
- Show one recommended task first, with a large action like `Start this task`.
- Move the weekly overview below a clear divider or to a separate `This Week` page.
- Do not repeat today's tasks in the weekly list on the same screen.
- Default the operator view to `social operator` if the intended user is the social operator.

### P0 - Task Detail Contains The Right Content But In The Wrong Order For A Novice

The task detail page has the ingredients needed for success, but it does not yet sequence them like a guided workflow. The operator sees a title with platform jargon, then explanation, asset path, draft copy, CTA, hashtags, posting steps, status, and a large metric form.

Why this matters:

- The most important action, "follow these posting steps," appears after copy and asset details.
- The operator has to infer when to copy text, when to open Instagram/Facebook, when to mark posted, and when metrics are due.
- Metrics are shown immediately even though they usually happen later.

Next phase goal:

- Convert task detail into a step-by-step flow:
  1. `Prepare`: product, asset, caption, CTA, hashtags, copy buttons.
  2. `Post`: beginner checklist and platform steps.
  3. `Finish`: mark status and save notes.
  4. `Later`: metrics, hidden or collapsed until status is `posted` or `metrics needed`.
- Put posting steps above long copy blocks, or provide a sticky/visible "Step 1, Step 2, Step 3" progress path.
- Add `Copy caption`, `Copy CTA`, and `Copy hashtags` buttons.
- Replace local source paths with plain labels and previews where possible.

### P0 - The Interface Still Uses Planner Language Where The Operator Needs Plain Language

Examples visible in the UI include `Collector / Completionist`, `Hobby, Profession, Or Identity Buyer`, `Website blog topic`, `Admin owner input`, `ready to post: 30`, and plan modes like `light`, `standard`, `launch`, `holiday`, `event`.

Why this matters:

- These labels make sense to the planning engine but are not how a novice thinks while posting.
- Persona labels in task titles make tasks feel analytical instead of doable.
- Status counts and plan modes add cognitive load before the user has learned the workflow.

Next phase goal:

- Rewrite operator-facing task titles around the action:
  - `Post a short Bingo Duck Reel on Instagram`
  - `Ask a Facebook question about Biker Duck`
  - `Matt: Check email list setup before newsletter tasks`
- Keep personas, planning mode, and internal classification in secondary metadata or details.
- Add plain-English definitions only where needed, near the action.

### P1 - Navigation Mixes Operator Work With Admin/Planner Work

The nav exposes `Today`, `Calendar`, `Plans`, `Assets`, `Templates`, `Metrics`, and `Settings` equally. For an operator, only Today and a small amount of Metrics matter most. Plans, Templates, Assets, and Settings are more owner/admin surfaces.

Why this matters:

- Equal-weight nav makes every section look equally relevant.
- A novice may wander into Templates or Plans and assume they need to understand them.
- `Plans` includes a Generate button that could create anxiety because it looks powerful and unclear.

Next phase goal:

- Split the app into beginner and admin zones:
  - Operator: `Today`, `This Week`, `Completed`, `Metrics Due`
  - Admin: `Plans`, `Assets`, `Templates`, `Settings`
- Consider a role switcher or simplified operator mode.
- De-emphasize or hide admin pages by default for `social operator`.
- Add a confirmation or explanatory review step before generating a new plan.

### P1 - Calendar And Assets Are Record Tables, Not Decision Helpers

Calendar and Assets are currently full tables. They are useful for debugging and administration, but they are hard to scan on mobile and do not answer the novice question: "what should I do with this?"

Why this matters:

- Tables are dense and require horizontal comparison.
- The Calendar mobile layout overflowed wider than the viewport.
- Asset paths are technical and there are no image previews, readiness explanations, or "use this asset" cues.

Next phase goal:

- Convert Calendar into grouped day cards or a weekly agenda at small widths.
- Add filters for owner, platform, and status.
- Make Assets visual: thumbnail, product, readiness badge, recommended platform, and "used by task" links.
- Hide source paths behind an admin detail affordance.

### P1 - Metrics Are Presented As A Large Generic Form Too Early

The task detail page shows all metric fields at once: post URL, reach/views, likes, comments, shares, saves, Etsy visits, Etsy orders, email signups, and notes.

Why this matters:

- The operator has not posted yet when they first see this.
- Not every platform needs every metric.
- The large form makes the task feel more complicated than it is.

Next phase goal:

- Collapse metrics by default until a task is `posted` or `metrics needed`.
- Show only metrics relevant to the platform and task type.
- Add helper text like `Come back tomorrow and enter these numbers`.
- Consider a dedicated `Metrics Due` page for follow-up work.

### P1 - Status Workflow Is Present But Not Guided

The status dropdown includes practical statuses, but the UI does not explain which status to choose next or when to choose it.

Why this matters:

- A novice may not know the difference between `ready to post`, `scheduled`, `posted`, `metrics needed`, and `complete`.
- Status is a data field, not yet a workflow.

Next phase goal:

- Use status-specific primary actions:
  - `Mark posted`
  - `Save as scheduled`
  - `Needs Matt's help`
  - `Skip this task`
- Keep the full dropdown available as an advanced control.
- Show the next expected status in context.

### P1 - Templates Page Is Useful Internally But Not Yet Useful To The Operator

Templates are displayed as records synced from `docs/templates`, including source paths and condensed rules. This is valuable for development/admin review, but it does not help a beginner choose what to do.

Why this matters:

- The operator does not need to know that templates live in JSON files.
- The page reads like a template registry, not a playbook library.

Next phase goal:

- Rename or split this surface:
  - Admin `Templates`
  - Operator `Posting Guides`
- For operator guides, show platform cards with beginner language:
  - what it means
  - when to use it
  - phone or desktop
  - where caption/hashtags/link go
  - mistakes to avoid
  - example

### P2 - Visual Hierarchy Is Clean But Too Uniform

Most content appears in similar white panels, pills, tables, and headings. This is tidy, but it does not strongly distinguish primary action, secondary reference, admin context, and later follow-up.

Why this matters:

- When everything is equally calm, the operator still has to decide what matters.
- The app needs stronger hierarchy, not more decoration.

Next phase goal:

- Use a clear primary action treatment for the one next step.
- Use collapsible secondary sections for reference content.
- Use quieter styling for metadata.
- Reserve dense tables for admin contexts.

## Recommended Next Phase Goals

1. Build a true beginner `Today` flow centered on one recommended next task.
2. Redesign task detail into a guided posting checklist with progressive disclosure.
3. Add copy-to-clipboard controls for caption, CTA, hashtags, and post URL.
4. Hide or separate admin/planner pages from the default social-operator path.
5. Replace duplicated Today/This Week content with a clean weekly agenda.
6. Make metrics a follow-up workflow, not part of the initial posting form.
7. Make assets visual and operator-readable.
8. Convert Calendar to responsive day/week cards on mobile.
9. Rename internal concepts in operator-facing UI to action language.
10. Add novice-friendly empty, blocked, and success states so the app always explains what to do next.

## Suggested Operator-First Screen Model

### Today

- Greeting or short status: `2 things need attention today`
- Primary card: `Post a short Bingo Duck Reel on Instagram`
- CTA: `Start task`
- Secondary card: `Matt needs to check email list setup`
- Collapsed preview: `Coming up this week`

### Task

- Header: `Post a short Bingo Duck Reel`
- Step tracker: `Prepare -> Post -> Finish -> Metrics later`
- Prepare:
  - product and asset preview
  - caption with copy button
  - hashtags with copy button
- Post:
  - exact beginner steps
  - preview checklist
- Finish:
  - `Mark posted`
  - note field
  - `Needs help` option
- Later:
  - collapsed metrics form

### This Week

- Day cards grouped by date.
- Filters for role/status/platform.
- No duplicate Today task cards above the fold.

### Admin

- Plans, Assets, Templates, Settings.
- Clear warning that these are setup/planning areas, not daily posting steps.

## Phase Acceptance Criteria

The next UI phase should be considered successful when a novice operator can:

- open the app and identify the single next action within 10 seconds;
- complete one Instagram or Facebook task without opening Calendar, Plans, Templates, or docs;
- copy caption/CTA/hashtags without selecting text manually;
- mark the task posted without understanding every possible status;
- understand that metrics are a later follow-up;
- avoid seeing source file paths, JSON/template language, or internal persona names during normal posting.

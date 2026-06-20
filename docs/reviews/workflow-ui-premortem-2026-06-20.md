# Marketing OS Workflow And UI Premortem

Date: 2026-06-20

## Goal

Marketing OS should feel like a practical growth assistant for MattMadeMe, not a CMS admin panel. The app should answer one human question quickly:

What should I do next to keep the flock growing?

The interface should hide internal machinery until it is needed. The human should not have to understand historical phase names, internal roles, template records, plan records, or automation architecture before posting, reviewing, or measuring content.

Brand grounding reviewed from `https://mattmademe.com/`: the public brand emphasizes the flock, found-duck sharing, Facebook participation, giveaway entry, Etsy buying, fan favorites, and upcoming designs. The tool should therefore feel like a friendly retail growth desk with product truth and review gates, not a generic enterprise console.

## Challenged Assumptions

| Existing assumption | Challenge | Decision |
| --- | --- | --- |
| Tasks need visible owners like `social operator` and `Matt`. | This makes the user learn the system's org chart before doing work. The current business workflow is one human deciding what to do next. | Keep old owner values internally for compatibility, but remove role selection and owner labels from the core UI. |
| Plan Archive deserves navigation. | A generated plan is provenance, not a daily destination. Most users will not know why they should open it. | Demote it to advanced history and explain that it is a troubleshooting/provenance page. |
| Posting templates deserve their own primary page. | Templates are implementation scaffolding. A human wants posting help or reusable recipes, not raw template records. | Keep as an advanced "Automation Recipes" reference. Posting help should be task-contextual first. |
| Every page should be reachable from the sidebar. | Too many menu items increases learning cost and makes the app feel unfinished. | Main nav should reflect the weekly loop. Reference and maintenance tools should be secondary. |
| Review Desk should lead with "Phase 5". | Phase numbers are project history, not business language. | Rename it to "Review Gate" and frame it as human approval before automation. |
| Daily Briefing should filter by role. | The human should not need to pick an identity. | Default daily and weekly views to all active work. Filter by status/platform instead. |

## Human Workflow

### Daily Check-In

1. Open **Today**.
2. See the single recommended next action and any items needing attention.
3. Start the task if it is ready.
4. If the task needs a post, use the task page to copy caption, CTA, hashtags, and posting checklist.
5. Mark the result as posted, scheduled, skipped, or needs help.
6. If metrics are due, record the platform numbers before leaving.

The daily screen should not require choosing a role, reading a plan archive, or opening template records.

### Weekly Planning

1. Open **Week** to scan the next seven days.
2. Use **Calendar** to move posts, review time of day, and inspect scheduled details.
3. Use **Studio** to plan or regenerate upcoming posts.
4. Use **Gallery** only when a post needs visual proof, source photos, or generated creative review.
5. Use **Review Gate** when generated copy or creative must be approved before automation or reuse.
6. Use **Signals** after posts have run to learn what should influence the next week.

The weekly loop should make it easy to rebalance the calendar without forcing the user into admin pages.

### Occasional Maintenance

| Maintenance need | Page | Why it exists |
| --- | --- | --- |
| Product truth, tags, Etsy references, default images | Products | The assistant cannot make good content without accurate product facts and source images. |
| File health, stale data, missing imports | Data Health | This is a diagnostic surface, not daily work. |
| Export data, sync Etsy, backup | Settings | These are operational actions that should not compete with posting work. |
| Generated plan provenance | Plan History | Useful for debugging or comparing generated plans, not daily execution. |
| Platform/template source records | Automation Recipes | Useful for maintaining future automation, not for routine posting. |

## Page Value Review

| Page | Primary job | Keep, change, or demote |
| --- | --- | --- |
| Today | Decide the next action quickly. | Keep. Remove role filter and owner-language. |
| Week | Scan all active work for the week. | Keep. Rename from Mission Board to Week. Remove role filter. |
| Calendar | Reschedule and inspect timed posts. | Keep. Continue improving calendar interactions. |
| Studio | Plan, generate, review, and convert posts to tasks. | Keep. This is the content workbench. |
| Gallery | Browse visual inventory and inspect item details in drawers. | Keep. Gallery-first is right. |
| Products | Maintain product truth and source references. | Keep. It is foundational but not daily. |
| Signals | Summarize learning from metrics. | Keep. It closes the weekly loop. |
| Review Desk / Phase 5 | Human approval for generated copy and creative. | Keep, rename to Review Gate, remove phase framing. |
| Metrics Due | Capture performance follow-up. | Keep as secondary; link from Today when due. |
| Completed | History of handled work. | Keep secondary; no role filter. |
| Posting Guides | Reference help for platform formats. | Demote; task pages should show contextual help first. |
| Metric History | Raw performance records. | Demote; Signals is the useful interpretation layer. |
| Data Health | Maintenance diagnostics. | Keep secondary under maintenance. |
| Plans | Generated plan provenance. | Rename Plan History and demote. |
| Templates | Raw recipe records. | Rename Automation Recipes and demote. |
| Settings | Exports, sync, backup. | Keep secondary under maintenance. |

## Premortem

Assume the tool launches and gets low usage. Assume some content is still poor. The likely causes are:

1. The first screen asks the user to understand internal roles instead of showing one clear next action.
2. The sidebar advertises too many pages with names that sound like implementation details.
3. "Phase 5," "Plan Archive," and "Templates" make the system feel like a project dashboard instead of a business assistant.
4. Posting still feels risky because the app may provide copy without enough taste guidance or brand context.
5. Generated images may be attractive but inaccurate, causing distrust in the whole workflow.
6. The user may not know whether to start in Today, Calendar, Week, Studio, or Review Desk.
7. Metrics entry may feel like homework unless it is presented as a small follow-up tied to better future content.
8. Calendar rescheduling helps, but low usage remains likely if the daily screen does not make the next action obvious.

## Premortem Analysis

The highest-risk issue is learning curve, not missing capability. The app already has many useful surfaces, but too many of them expose internal history. The next UI pass should prioritize language and hierarchy:

- Replace roles with human work modes.
- Rename pages around jobs-to-be-done.
- Put daily and weekly pages first.
- Demote plan/template internals.
- Change review language from phase proof to brand safety and human approval.
- Make content quality gates visible in the context of work, not as separate abstract status pages.

## Resolution Pass

This pass should make the following changes:

1. Remove role dropdowns from Today, Week, and Completed.
2. Default Today, Week, and Completed to all work.
3. Remove owner-role pills from task cards and task headers.
4. Rename sidebar pages:
   - Daily Briefing -> Today
   - Mission Board -> Week
   - Review Desk -> Review Gate
   - Metrics Due -> Follow-Ups
   - Plan Archive -> Plan History
   - Playbook Library -> Automation Recipes
5. Keep Plan History and Automation Recipes out of the main workflow group.
6. Rename Phase 5 Proof Check to Review Gate.
7. Update empty states and assistant copy to focus on human work, not internal roles.
8. Preserve old URLs and database values for compatibility.

## Acceptance Check

After the pass, a new user should be able to answer:

- What should I do today?
- What is coming this week?
- What posts are scheduled and when?
- Where do I create or edit a post?
- Where do I check images?
- Where do I approve generated content?
- Where do I see whether the work is helping?

They should not need to understand:

- `social operator`
- why Matt is a role
- what phase the project is in
- what raw template records are
- why generated plans exist

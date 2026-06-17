# Marketing Plan Premortem

Reviewed file: `outputs/marketing-plan.md`

Review date: 2026-06-17

## Executive Read

The Phase 1 generator proves the workflow works, but the generated plan is not yet something a solo owner could confidently execute without heavy editing. It produces the required sections and counts, but the quality is still template-driven, sometimes internally inconsistent, and occasionally wrong because the parser confuses product names with analytical sentences.

The most important Phase 2 job is to move from "generate enough rows" to "generate usable, strategically coherent marketing work."

## Premortem Scenario

Imagine Matt tries to use this plan for a real 30-day marketing cycle. The likely failure is not that the system crashes. The likely failure is that the plan feels too generic, repetitive, and awkward to trust. Matt still has to do the hard thinking: decide what to actually post, rewrite most copy, choose creative assets, pick the right CTA, and judge whether the week is coherent. After one or two uses, the system risks becoming a novelty report generator instead of a weekly marketing operating tool.

## Critical Findings

### P0 - Product Parser Pollutes The Plan With Non-Products

The generated plan includes analytical sentences as featured products, for example:

- `Mailman Duck remains the lifetime leader, but last-90-day units are down 38% versus the prior 90 days.`
- `Firefighter Duck is down 56% versus the prior 90 days, though it still sold 20 units in the last 30 days.`
- `Delivery Duck is down 37% versus the prior 90 days.`

Why this matters:

- It makes the calendar look obviously broken.
- It undermines trust in every recommendation.
- It means the knowledge loader is not distinguishing entities from narrative analysis.

Likely cause:

- The current parser treats any short bullet containing `Duck` as a product, including bullets in the "Cooling products to watch" section.

Phase 2 requirement:

- Introduce structured business entities instead of inferring everything from free-form Markdown.
- At minimum, parse products only from explicit product sections/tables and ignore analytical sections.

### P0 - Output Is Not Ready-To-Use Content

Most content ideas are prompts about what to write, not actual draft posts. Example pattern:

```text
show the tiny detail that makes this design giftable; keep it whimsical, maker-led...
```

Why this matters:

- Matt still has to write the posts from scratch.
- The plan does not save enough time to hit the success metric.
- It does not yet feel like a marketing manager, more like a checklist generator.

Phase 2 requirement:

- Add separate output modes:
  - idea
  - draft caption
  - asset brief
  - CTA
  - hashtags
  - production notes

### P1 - Goal, Platform, And CTA Frequently Do Not Match

Examples:

- Etsy promotion assigned to `Build An Owned Email List`, but CTA is `Add it to your cart`.
- Instagram Reel assigned to `Grow Etsy Sales`, but CTA is `Follow for the next duck drop`.
- Email newsletter assigned to `Promote New Duck Releases`, but there is no email platform configured yet.

Why this matters:

- Measurement becomes impossible if objective and CTA are misaligned.
- The owner cannot judge whether the tactic succeeded.
- The recommendation engine may optimize for labels rather than outcomes.

Phase 2 requirement:

- Add objective-to-CTA rules.
- Add channel-specific CTA rules.
- Add a validation pass that flags mismatched objective, channel, CTA, and business goal.

### P1 - Calendar Cadence Is Mechanical

The 30-day calendar repeats the same sequence:

- Instagram Reel
- Facebook post
- Instagram post
- Etsy promotion
- Email newsletter

Why this matters:

- It ignores realistic owner capacity.
- It treats every week as the same.
- It does not distinguish launch weeks, maintenance weeks, seasonal campaigns, or rest days.
- It includes email before the business has a defined email list/platform.

Phase 2 requirement:

- Add planning modes:
  - light week
  - standard week
  - launch week
  - holiday push
  - event/custom-order push
- Let the owner set weekly capacity.

### P1 - Audience/Product Pairings Are Often Arbitrary

Examples:

- Declaration Duck for Event And Convention Buyer.
- Firefighter Duck positioned as a cruise hiding surprise for an event buyer.
- Room Steward Duck for Gift Buyer without clear cruise context.

Why this matters:

- It can create content that feels tone-deaf or irrelevant.
- Strong product-market fit is the point of the system.

Phase 2 requirement:

- Add product metadata:
  - primary audience
  - secondary audience
  - best channel
  - best use cases
  - seasonality
  - launch status
  - sales momentum

### P1 - Seasonal Intelligence Is Too Thin

The weekly report says:

```text
Plan around new duck launch windows.
```

Why this matters:

- It misses June/July-specific opportunities.
- It does not turn seasonal knowledge into timing recommendations.
- It does not distinguish Christmas, cruise season, summer travel, conventions, or new releases.

Phase 2 requirement:

- Add a real seasonal calendar model.
- Map dates to likely campaigns and lead times.
- Include "why now" in each weekly report.

### P1 - Recommendations Are Directionally Useful But Not Operational

Recommendations are good high-level signals, but several are not specific enough to execute.

Example:

```text
Add a customer-photo CTA to one Website post and one follow-up post this week.
```

Problems:

- Website is not really a social post channel.
- It does not say which post, what copy, what asset, or what success metric.

Phase 2 requirement:

- Recommendations should include:
  - owner task
  - estimated minutes
  - exact output needed
  - linked calendar entries
  - metric to check
  - why this is recommended now

### P2 - The Brand Voice Is Referenced Awkwardly

The repeated phrase:

```text
as a Add a duck to your flock.
```

is grammatically broken.

Why this matters:

- It makes generated copy feel robotic.
- It weakens trust in the system's voice handling.

Phase 2 requirement:

- Treat brand phrases as optional copy ingredients, not sentence fragments.
- Add rendering rules for grammar and casing.
- Add snapshot tests for obvious awkward phrases.

### P2 - No Asset Or Production Planning

The plan says what content type to create but not what asset is needed.

Missing:

- product photo
- reel shot list
- caption draft
- hashtags
- post format
- whether to use finished product, printer plate, packaging, customer photo, or mockup

Why this matters:

- The owner still has to translate every idea into production work.
- Social media work is usually blocked by asset decisions, not just topic ideas.

Phase 2 requirement:

- Add asset briefs to each content item.
- Add reusable shot types:
  - finished product closeup
  - printer plate reveal
  - packing order
  - desk scene
  - cruise hiding setup
  - bundle lineup
  - customer photo prompt

### P2 - No Prioritization Inside The Calendar

Every calendar row looks equally important.

Why this matters:

- A solo owner needs to know what can be skipped.
- The system should protect the highest-impact work when time gets tight.

Phase 2 requirement:

- Add priority to every calendar item:
  - must do
  - should do
  - optional
- Add effort estimate and expected impact to each item.

## What Worked

- The system successfully loads business docs and generates the required sections.
- The high-level business goals are represented throughout the plan.
- The recommendation section points in the right strategic direction: launch discipline, collector/email capture, current momentum products, convention/event buyers, and customer photos.
- The output format is easy to inspect and can become a useful review artifact.
- The local-first architecture is a good foundation for iterative improvements.

## Phase 2 Direction

Phase 2 should be framed around quality, strategy, and usability rather than more integrations.

Recommended Phase 2 objective:

> Transform the Phase 1 generator from a count-complete planning demo into a usable weekly marketing planner that produces strategically coherent, ready-to-edit content plans.

Suggested Phase 2 capabilities:

1. Structured Product Knowledge
   - Add product metadata files or structured frontmatter.
   - Separate product entities from commentary.
   - Track audience fit, channel fit, seasonality, status, and momentum.

2. Plan Validation
   - Validate every calendar item before rendering.
   - Flag non-product featured products.
   - Flag CTA/objective/platform mismatches.
   - Flag unsupported channels like email when no list exists.

3. Campaign-Aware Calendar
   - Support planning modes: standard week, launch week, holiday push, event push.
   - Add owner capacity constraints.
   - Add weekly theme and campaign narrative.

4. Ready-To-Edit Content Drafts
   - Generate real captions, not just angles.
   - Include CTA, hashtags, asset brief, and production notes.
   - Provide variants by channel.

5. Recommendation Quality Upgrade
   - Tie recommendations to specific calendar entries.
   - Include owner task, effort in minutes, expected impact, metric, and rationale.

6. Review And Approval Workflow
   - Add statuses: draft, needs asset, approved, posted, skipped.
   - Output a weekly action list.

7. Measurement Prep Without APIs
   - Add manual metrics fields.
   - Create a weekly review template.
   - Track what was planned, posted, skipped, and learned.

## Phase 2 Success Criteria

- The owner can pick up the weekly output and know exactly what to create first.
- No generated calendar item contains invalid products.
- Every calendar item has a coherent goal, channel, CTA, audience, product, and asset brief.
- Every recommendation is specific enough to act on in under 30 minutes.
- The plan clearly separates must-do work from optional ideas.
- The weekly report explains why this week matters.


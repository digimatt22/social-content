# Phase 2 Output Operator Premortem

Reviewed files:

- `outputs/phase2-standard.md`
- `outputs/phase2-launch.md`

Review date: 2026-06-17

Primary operator lens: Matt's wife may be managing the social channels. She is not a regular social media user, is unfamiliar with platform conventions, and should not need to understand terminal workflows, Markdown files, or social-media jargon to execute the plan.

## Executive Read

Phase 2 is a meaningful upgrade over Phase 1. It fixes the worst parser failure, adds structured products, validates plans, creates draft copy, includes asset briefs, and separates must-do from optional work. But it still fails the "can a non-social-media operator use this confidently?" test.

The current output is better as a planning artifact for Matt than as an operating guide for someone unfamiliar with Instagram, Facebook, Etsy promotion mechanics, or website/blog workflows. It tells the operator what kind of marketing object to make, but not enough about how to make it, where to click, what template to use, what visual format is needed, how to adapt Etsy photos, or what "done" looks like.

## Premortem Scenario

Imagine Matt's wife opens `outputs/phase2-standard.md` and tries to run the week. She sees a 775-line Markdown file with a 30-day calendar, content drafts, asset briefs, recommendations, action lists, and a manual review table.

Likely failure mode: she gets stuck before posting. The plan says "Create Instagram reel for Bingo Duck" and "Capture a bundle lineup," but it does not explain whether to use a Reel template, what canvas size matters, how long the video should be, where to put text, how to pick music, whether to upload from phone or desktop, whether to use an Etsy image, or how to avoid making something that feels off-platform.

The system has become strategically smarter, but it has not yet become an operator-friendly marketing assistant.

## Critical Findings

### P0 - Output Is Still Too Technical And Too Long For A Novice Operator

The standard output is 775 lines. It is complete, but intimidating.

Why this matters:

- A non-social-media user needs a short "today's task" flow, not a full planning document first.
- The important next action is buried inside a large report.
- The weekly action list appears near the end, after hundreds of lines of content.

Phase 3 requirement:

- Generate an operator view in addition to the planner view.
- The operator view should start with:
  - what to do today
  - which product
  - which platform
  - what asset to use
  - exact caption
  - step-by-step posting instructions
  - what to record after posting

### P0 - Platform Actions Are Not Beginner-Friendly

Examples from the output:

- `Instagram reel`
- `Facebook post`
- `Etsy promotion`
- `Website blog topic`

These labels are accurate but not actionable for someone unfamiliar with the platforms.

Missing operator instructions:

- Where to create the post.
- Whether to use desktop or phone.
- Whether Instagram should be Feed, Reel, Story, or Carousel.
- Whether Facebook should be Page post, Group post, Reel, or Story.
- Where hashtags go.
- Where the Etsy link should go.
- Whether the post needs an image, video, or carousel.
- What preview step to check before publishing.

Phase 3 requirement:

- Add platform playbooks with beginner steps.
- Every calendar item should resolve to a platform-specific execution checklist.
- The system should define terms like Reel, caption, hashtag, CTA, carousel, story, post body, and alt text.

### P0 - Local Markdown And Terminal Workflow Is Fragile

Current testing and execution require commands like:

```bash
python -m marketing_os.cli --phase 2 --mode standard --start-date 2026-06-17 --output outputs/phase2-standard.md
```

Why this matters:

- A non-technical operator may not know how to open Terminal, navigate folders, or interpret errors.
- Local Markdown files are easy to lose, overwrite, ignore, or edit incorrectly.
- Generated files in `outputs/` are ignored by git, so important working plans may not be tracked unless intentionally copied elsewhere.
- Manual editing of JSON/Markdown creates formatting risks.

Phase 3 requirement:

- Add a guided non-terminal interface or at least a single-click script.
- Consider a local web UI, desktop-friendly command wrapper, or generated HTML dashboard.
- Add guardrails for local data:
  - validate business files before planning
  - show friendly error messages
  - save timestamped plan outputs
  - optionally copy approved weekly plans into tracked docs

### P1 - The System Does Not Understand Platform Templates

Modern social platforms are template-heavy:

- Instagram Reels often use audio, timing, transitions, text overlays, and remixable formats.
- Instagram posts may be single image, carousel, Reel cover, Story, or pinned post.
- Facebook posts can be image posts, link posts, Reels, Stories, event posts, group posts, or page posts.
- Etsy listing images have their own layout expectations and buyer-scanning behavior.

Current output says things like:

```text
Use vertical framing. Start with the duck already visible in the first second.
```

That is useful, but not enough.

Phase 3 requirement:

- Add platform template definitions.
- A template should include:
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

Example templates:

- Instagram Reel: printer plate reveal
- Instagram Reel: product spin / hand reveal
- Instagram carousel: 3 reasons this duck is a good gift
- Instagram single image: product hero with short caption
- Facebook image post: question prompt
- Facebook group post: cruise duck discussion prompt
- Etsy listing refresh: hero image and first sentence
- Website/blog: product story post

### P1 - Asset Briefs Do Not Match Available Product Photos

MattMadeMe already has product photos used on Etsy, likely on clean/plain backgrounds. The current output asks for assets such as:

- bundle lineup
- printer plate reveal
- cruise hiding setup
- custom/event order concept
- maker/process shot

Why this matters:

- The plan may ask for new photography even when a usable Etsy product image already exists.
- Plain-background Etsy photos may not perform well as native social graphics without design treatment.
- A novice operator needs to know when to use an existing product photo, when to take a new photo, and when to generate a graphic.

Phase 3 requirement:

- Add an asset inventory and asset selection workflow.
- Track available product images separately from product metadata.
- Add asset readiness states:
  - existing Etsy photo ready
  - needs crop
  - needs background/scene
  - needs graphic template
  - needs new photo
  - needs generated composite

### P1 - We Likely Need A Separate Creative Asset Skill Or Agent

The marketing planner can say what visual is needed, but creating graphics is a different capability.

Potential scope:

- Take plain-background product photos.
- Create platform-sized graphics.
- Preserve product accuracy.
- Add branded background treatments.
- Generate simple scene/mockup variations.
- Create Reel cover images.
- Create carousel slides.
- Export files with predictable names.
- Avoid altering product shape, color, or details in misleading ways.

Why this should probably be separate:

- Creative generation has different rules, QA needs, and failure modes.
- It needs asset inputs and output files, not just Markdown.
- It may use image generation, image editing, or template rendering.
- It needs strict product-accuracy safeguards.

Future goal stub created:

- `docs/goals/future-creative-asset-agent.md`

### P1 - Copy Still Needs Platform-Native Templates

Drafts are better than Phase 1, but still generic:

```text
Biker Duck feels made for hobby, profession, or identity buyers...
```

Why this matters:

- Social posts need stronger hooks and fewer internal persona labels.
- The operator should not have to translate "Hobby, Profession, Or Identity Buyer" into human language.
- Different formats need different copy structures.

Phase 3 requirement:

- Add copywriting templates by platform and format.
- Generate copy sections:
  - hook
  - body
  - CTA
  - hashtags
  - first comment if needed
  - alt text
  - short version
  - long version

### P1 - Output Does Not Include Posting Workflow State

Current statuses are mostly `not started`, but there is no practical workflow:

- asset selected
- asset edited
- caption approved
- scheduled
- posted
- metrics recorded

Why this matters:

- A non-social-media operator needs a checklist, not just a plan.
- The process should reduce anxiety: "do this, then this, then this."

Phase 3 requirement:

- Add operator statuses:
  - needs asset
  - needs copy review
  - ready to post
  - scheduled
  - posted
  - metrics needed
  - complete

### P1 - Website And Etsy Tasks Are Mixed With Social Tasks

The weekly action list includes:

- Instagram
- Facebook
- Etsy
- Website

Why this matters:

- These require different access, confidence, and skills.
- A social-channel operator may not be responsible for Etsy listing edits or website blog posts.

Phase 3 requirement:

- Add owner/role assignment:
  - Matt
  - wife/social operator
  - either
  - blocked until owner input
- Separate social tasks from shop/admin/content-site tasks.

### P2 - Metrics Are Too Broad For A Beginner

Examples:

- `Track first 7-day views, favorites, comments, and sales notes.`
- `Track Etsy visits, favorites, orders, or a manual sales note.`

Why this matters:

- A novice may not know where to find these metrics.
- "or" metrics make it unclear what is actually required.
- Manual measurement may get skipped unless it is simple.

Phase 3 requirement:

- Add exact metric instructions by platform:
  - where to find it
  - when to check it
  - what number to copy
  - where to paste it
- Use a minimal default metric set for beginners.

## Directory Structure Premortem

The current structure works for Phase 2 but will strain if we add skills like image generation, copywriting templates, platform templates, and asset inventories.

Current issue:

- `docs/business` contains business facts and product catalog.
- `marketing_os` contains planner code.
- `outputs` contains generated plans.
- There is no clear home for reusable skills, platform templates, graphic templates, or product assets.

Recommended future structure:

```text
docs/
├── business/
├── goals/
├── reviews/
├── operating-guides/
│   ├── instagram-beginner-guide.md
│   ├── facebook-beginner-guide.md
│   └── weekly-social-workflow.md
├── templates/
│   ├── platform/
│   │   ├── instagram-reel-printer-reveal.json
│   │   ├── instagram-carousel-gift-ideas.json
│   │   └── facebook-image-question-post.json
│   ├── copy/
│   │   ├── launch-caption.json
│   │   ├── collector-prompt.json
│   │   └── cruise-duck-post.json
│   └── graphics/
│       ├── square-product-card.json
│       ├── reel-cover.json
│       └── carousel-slide.json
└── skills/
    ├── copywriting.md
    ├── platform-posting.md
    └── creative-assets.md

assets/
├── products/
│   ├── bingo-duck/
│   │   ├── source/
│   │   ├── edited/
│   │   └── generated/
│   └── biker-duck/
├── brand/
└── templates/

outputs/
├── plans/
├── graphics/
├── captions/
└── reviews/
```

The exact structure can wait, but Phase 3 should avoid stuffing every new capability into one planner module.

## Recommended New Future Goals

### Goal 1 - Operator-Friendly Social Workflow

Build a non-technical workflow for someone unfamiliar with social platforms.

Key outcomes:

- daily task view
- beginner posting instructions
- role assignment
- platform glossary
- single-click or UI-based execution path
- no terminal requirement for normal use

### Goal 2 - Platform And Copy Template System

Create reusable templates for platform-native posts.

Key outcomes:

- Instagram Reel templates
- Instagram post/carousel templates
- Facebook post templates
- Etsy promotion templates
- website/blog templates
- copywriting templates with hook/body/CTA/hashtags/alt text

### Goal 3 - Creative Asset Agent

Build a future skill or agent that turns product photos into platform-ready marketing graphics while preserving product accuracy.

Stub goal:

- `docs/goals/future-creative-asset-agent.md`

## What Phase 2 Still Does Well

- Product parsing is much safer than Phase 1.
- Output includes ready-to-edit draft copy.
- Asset briefs exist.
- Weekly actions separate must-do, should-do, optional, and blocked work.
- Manual review fields exist.
- The plan is strategically more coherent.

## Bottom Line

Phase 2 is now useful for a technical owner or marketing-literate reviewer. It is not yet safe to hand to a non-social-media operator and expect confident execution.

The next phase should not be "more content." It should be "make this operable by a beginner."


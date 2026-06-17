# Codex Nightly Content Production Plan

Date: 2026-06-17

## Recommendation

Use Marketing OS as the planning, review, posting, and measurement tool. Use Codex as the scheduled creative production worker.

This keeps the web app calm and operator-friendly while still using agent assistance for the parts that need taste, judgment, and synthesis: copywriting, image prompt direction, creative review, and performance-aware iteration.

## Concept

The user creates high-level calendar intent in the web interface:

- destination: Instagram, Facebook, Pinterest, blog post, Etsy, website, email, or other channel
- goal: sales growth, repeat customers, followers, product awareness, email signup, blog traffic, seasonal launch, or engagement
- product focus: one or more products
- optional audience, occasion, promotion, deadline, notes, and asset preferences

Marketing OS stores this as a planned calendar item. It does not need final copy, image prompts, or generated assets at planning time.

A scheduled Codex automation runs later, finds planned items that need detail, gathers context, creates draft content and creative briefs, saves candidates back to the app, and leaves everything in review.

## Responsibilities

### Marketing OS Web App

Owns:

- planning intent capture
- calendar storage
- product/channel/goal selection
- product and asset source data
- review status
- copy and asset candidate records
- posting workflow
- metrics and outcome notes
- learning summaries

The web app should be usable by Matt or the social operator without needing to know how the generation happened.

### Codex Automation

Owns:

- reading planned items that need detail
- assembling context from products, assets, brand voice, channel rules, and prior outcomes
- writing quality copy drafts
- creating image-generation prompts or provider requests
- reviewing generated image candidates for product accuracy and usefulness
- producing notes about uncertainty or missing inputs
- writing candidates back to Marketing OS

Codex should not publish, approve, or mark work as complete without human review.

## Workflow

1. User creates a planned marketing item in the web app.
2. Marketing OS saves it to the calendar with status `planned`.
3. Nightly Codex automation runs `python -m marketing_os.jobs.content_production`.
4. The job finds planned items that need detail.
5. The job writes a structured brief per item.
6. Codex/model-assisted generation creates copy candidates, image prompts, asset recommendations, and review notes.
7. Marketing OS stores generated candidates with status `needs_review`.
8. User reviews candidates in the web app.
9. User edits, approves, rejects, posts, or skips.
10. Metrics and outcome notes are recorded later.
11. Future Codex runs use the learning summary to improve recommendations.

## Suggested Data Model Concepts

Planned content item:

- `id`
- `calendar_date`
- `destinations`
- `goals`
- `product_ids`
- `audience`
- `occasion`
- `promotion`
- `notes`
- `status`
- `brief_status`
- `last_production_run_at`
- `production_error`

Content brief:

- `planned_item_id`
- `source_products`
- `source_assets`
- `channel_requirements`
- `brand_voice_summary`
- `performance_context`
- `missing_inputs`

Generated candidate:

- `planned_item_id`
- `candidate_type`: copy, blog_outline, image_prompt, generated_asset, posting_notes
- `provider`: codex, magnific, manual, api
- `body`
- `source_fact_ids`
- `source_asset_ids`
- `review_state`
- `revision_notes`
- `created_at`

## Script Contract

Suggested command:

```bash
python -m marketing_os.jobs.content_production --limit 10
```

Useful options:

- `--date YYYY-MM-DD`
- `--channel facebook`
- `--dry-run`
- `--planned-item-id <id>`
- `--limit <n>`
- `--force`
- `--export-briefs-dir <dir>`

Use `--export-briefs-dir` to write one structured JSON brief per planned item before generation. The filename should be stable by planned item ID so a nightly run can refresh the current Codex handoff without creating duplicate files.

The job should be idempotent. If a planned item already has current candidates, rerunning should update run metadata or create a new revision intentionally, not silently duplicate drafts. Items with candidates marked `rewrite_requested` should be included in normal runs and regenerated back into `needs_review` so the review loop does not stall. Exported briefs should include rewrite notes and prior copy for those candidates so Codex can respond to the specific critique.

Final readiness/proof command:

```bash
python -m marketing_os.jobs.phase5_readiness --export-markdown
python -m marketing_os.jobs.phase5_readiness --export-creative-handoff
```

This reports the current Phase 5 human-proof gate as JSON and can export a Markdown approval packet or focused creative handoff. Use `--fail-on-incomplete` only for a strict final completion gate; normal nightly content production should not fail just because Matt still needs to review copy or generated creative.

## Automation Schedule

Start with one nightly run.

Recommended first schedule:

- nightly on weekdays
- local time
- only process planned items due within the next 7 to 14 days
- skip items already in review, approved, posted, or skipped

Current local implementation:

- manual-safe runner: `./scripts/run-content-production.sh`
- macOS LaunchAgent template: `docs/automation/com.mattmademe.marketing-os.content-production.plist`
- default schedule: weekdays at 2:30 AM local time
- brief export path: `data/exports/content-briefs`
- log path: `data/logs/content-production.log`

Manual runs should remain available because scheduled automation is harder to debug than a direct command.

## Human Review Rules

All generated work starts in `needs_review`.

The web app should make it easy to:

- compare planned intent with generated draft
- edit copy
- approve copy
- reject or request rewrite
- attach or replace assets
- copy final text into the destination platform
- mark posted
- schedule metrics follow-up

## Acceptance Criteria

- A user can create a high-level planned marketing item from the web app.
- A planned item can include multiple product focuses.
- The content-production job can find planned items needing detail.
- The job can produce or import at least one generated candidate.
- Generated candidates are linked to the planned item and source products.
- Generated candidates start in `needs_review`.
- The user can review generated content from the web app before posting.
- The job can be run manually and later by Codex automation.
- Rerunning the job does not duplicate existing candidates accidentally.

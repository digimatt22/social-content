# Codex Content Automation Setup

Use this guide to create the scheduled Codex App automation that processes Marketing OS Planning requests.

## What The Automation Does

The scheduled run should:

- pull pending Planning items due in the next 14 days
- export `copy-workflow.json` for each social item so Codex can see the required social skills and review sequence
- write or refresh copy only through the agent-run social media strategy -> writing -> challenge flow
- register agent-written copy as a Planning review candidate
- export social-media-art-director requests for each item still waiting on images
- use the `social-media-art-director` skill and Magnific MCP as the primary image path to create 2-3 real image files
- register generated image files as Planning image options
- leave all copy and images in human review

It must not approve copy, approve images, create posting tasks, or publish anywhere.

## Repo Commands

Import a weekly Etsy sales CSV export before the planner runs:

```bash
./scripts/import-etsy-sales-csv.sh /path/to/etsy-sales.csv
```

You can also upload the Etsy order items CSV in the local web app under `Settings -> Etsy Order Items -> Import order items`.

The import is idempotent. Rows are deduped by transaction/order/receipt ID when present, or by a generated row key when the export does not include an ID. Overlapping weekly exports are safe to import.

Create the next weekly social plan:

```bash
./scripts/run-weekly-social-planner.sh
```

The weekly planner creates normal Planning items for review and writes a strategy export under:

```text
data/exports/weekly-social-plans/<week-start>/weekly-social-strategy.json
```

Prepare pending content and export image requests:

```bash
./scripts/run-codex-content-automation.sh
```

Dry-run the queue without writing candidates:

```bash
python -m marketing_os.jobs.content_automation --dry-run --limit 10 --days-ahead 14
```

Image requests are written under:

```text
data/exports/content-automation/planned-item-<id>/image-requests.json
```

Copy workflow requests are written under:

```text
data/exports/content-automation/planned-item-<id>/copy-workflow.json
```

After Codex generates image files, register them with a manifest:

```bash
python -m marketing_os.jobs.register_generated_images \
  --manifest data/exports/content-automation/planned-item-<id>/register-images.json
```

After Codex writes and challenges social copy, register it with a manifest:

```bash
python -m marketing_os.jobs.register_generated_copy \
  --manifest data/exports/content-automation/planned-item-<id>/register-copy.json
```

The copy registration manifest shape is:

```json
{
  "planned_item_id": 1,
  "provider": "codex_agent",
  "copy_text": "Hook line\n\nBody copy\n\nCTA line",
  "skill_request": {},
  "skill_check": {},
  "social_strategy": {},
  "social_challenge": {},
  "notes": "Agent-written copy; review before posting."
}
```

To register selectable copy tabs, use `copy_options` instead of a single `copy_text`:

```json
{
  "planned_item_id": 1,
  "provider": "codex_agent",
  "copy_options": [
    {
      "copy_text": "Engagement hook\n\nBody copy\n\nComment CTA",
      "social_strategy": { "selected_variant": "Engagement" },
      "social_challenge": { "status": "ready_for_human_review" }
    },
    {
      "copy_text": "Shop hook\n\nBody copy\n\nShop CTA",
      "social_strategy": { "selected_variant": "Shop-click" },
      "social_challenge": { "status": "ready_for_human_review" }
    }
  ],
  "skill_request": {},
  "skill_check": {},
  "notes": "Agent-written options; review before posting."
}
```

The registration manifest shape is:

```json
{
  "planned_item_id": 1,
  "provider": "codex_imagegen",
  "images": [
    {
      "option_number": 1,
      "image_path": "outputs/graphics/planning/uploads/planned-item-1/option-1.png",
      "title": "Product-In-Use Scene",
      "best_for": "A clear product-forward social post.",
      "skill_request": {},
      "skill_check": {},
      "review_checklist": [
        "Subject is obvious at thumbnail size.",
        "Product identity is preserved against the source or uploaded image.",
        "No unwanted text, watermark, logos, or irrelevant objects.",
        "Crop fits the planned destination."
      ]
    }
  ]
}
```

## Codex App Automation

Create a standalone weekly Codex app automation for:

```text
/Users/matt/Documents/marketing-os
```

Recommended schedule:

```cron
0 20 * * 0
```

This is Sunday at 8:00 PM local machine time. If the runner uses UTC, convert this schedule before saving it.

Run it in the local project checkout, not a worktree. Use workspace-write permissions so Codex can update SQLite runtime data, logs, exports, and the repo-local ignored asset/output folders.

Use the shared automation prompt:

```text
docs/operating-guides/codex-weekly-automation-prompt.md
```

The prompt is repeated below for Codex app setup:

```text
Run the weekly Marketing OS social planner and content production for /Users/matt/Documents/marketing-os.

Use the repo skills:
- $copywriter
- $social-media-strategist
- $social-media-copywriter
- $social-media-copy-chief
- $social-media-art-director

Rules:
- Do not edit source code, docs, tests, or configuration.
- Only write runtime outputs under data/, `assets/products/`, `outputs/`, and the local SQLite database.
- Never approve generated copy or images.
- Never create posting tasks.
- Never post to external platforms.
- Keep all generated outputs in human review.

Each run:
1. Read AGENTS.md and SKILLS.md.
2. Run the weekly planner:
   ./scripts/run-weekly-social-planner.sh
3. Inspect data/exports/weekly-social-plans/**/weekly-social-strategy.json.
4. Run:
   ./scripts/run-codex-content-automation.sh
5. Inspect data/exports/content-automation/**/copy-workflow.json and data/exports/content-automation/**/image-requests.json.
6. For each copy workflow, follow the required social flow:
   - Use $social-media-strategist to confirm platform, audience, content pillar, social angle, CTA type, and variant plan.
   - Use $social-media-copywriter to draft from that strategy, not directly from Etsy titles or product descriptions.
   - Use $social-media-copy-chief to challenge the draft. If it fails, revise before reporting it as ready for human review.
   - Build register-copy.json beside copy-workflow.json with 2-3 challenged `copy_options` when useful, plus strategy, challenge result, skill_request, and skill_check.
   - Register generated copy:
     python -m marketing_os.jobs.register_generated_copy --manifest data/exports/content-automation/planned-item-<id>/register-copy.json
   - Do not approve, publish, or mark copy final.
7. For each pending image option, use $social-media-art-director and Magnific MCP with Google Nano Banana 2 to generate a real PNG file under:
   outputs/graphics/planning/uploads/planned-item-<id>/option-<n>.png
   Pass every listed reference image to Magnific. Assign @img1 as the primary visible product and @img2+ as identity locks. Use built-in image editing only if Magnific MCP is unavailable, and still pass the reference images.
8. Download each completed image to the path above. Build register-images.json beside image-requests.json using the registration_manifest_example shape from the request file, with image_path values updated to the downloaded files.
9. Register generated files:
   python -m marketing_os.jobs.register_generated_images --manifest data/exports/content-automation/planned-item-<id>/register-images.json
10. Verify:
   python -m marketing_os.jobs.content_automation --dry-run --limit 10 --days-ahead 14
11. Report:
   - weekly strategy file inspected
   - planned item IDs processed
   - copy workflow files inspected, copy candidates registered, and challenge statuses
   - image files generated and registered
   - failures that need user attention
   - whether queued items remain

If no pending requests exist, report that nothing needed generation.
```

## Manual Codex App Setup

If the automation must be created manually in the Codex App, use the prompt in:

```text
docs/operating-guides/codex-weekly-automation-prompt.md
```

Create it as a standalone project automation for `/Users/matt/Documents/marketing-os`, scheduled for Sunday at 8:00 PM local time, running in the local project checkout with workspace-write permissions.

## Etsy Sales CSV

Sales-aware weekly planning uses imported CSV rows for order-item data. The regular Etsy API sync imports listings, listing images, and shop reviews. The planner does not call Etsy's private sales/transactions API.

Recommended weekly order:

1. Export recent Etsy sales/orders as CSV.
2. Import the file from `Settings -> Etsy Order Items` or with:

```bash
./scripts/import-etsy-sales-csv.sh /path/to/etsy-sales.csv
```

3. Let the Sunday 8 PM Codex App automation run, or run the deterministic prepare commands manually:

```bash
./scripts/run-weekly-social-planner.sh
./scripts/run-codex-content-automation.sh
```

The planner targets a mix of popular products from recent CSV quantities and slow products with low or no imported sales.

## Review Workflow

After the automation runs:

1. Open Planning.
2. Review generated copy.
3. Review the generated image options.
4. Select one image or upload your own.
5. Create the posting task only after the copy is ready and one image is selected.

Generated files are review candidates, not approved assets.

## Troubleshooting

- If image generation is unavailable in the automation run, the item should stay queued and the run should report the missing capability.
- If registration fails, confirm every `image_path` in `register-images.json` exists on disk.
- If copy keeps regenerating, check whether the candidate review state is still `rewrite_requested`.
- Logs for the prepare step are written to:

```text
data/logs/codex-content-automation.log
```

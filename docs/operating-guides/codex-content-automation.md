# Codex Content Automation Setup

Use this guide to create the scheduled Codex app automation that processes Marketing OS Planning requests.

## What The Automation Does

The scheduled run should:

- pull pending Planning items due in the next 14 days
- generate or refresh copy through the copywriter adapter
- export image-creator requests for each item still waiting on images
- use the `image-creator` skill and Magnific MCP as the primary image path to create 2-3 real image files
- register generated image files as Planning image options
- leave all copy and images in human review

It must not approve copy, approve images, create posting tasks, or publish anywhere.

## Repo Commands

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

After Codex generates image files, register them with a manifest:

```bash
python -m marketing_os.jobs.register_generated_images \
  --manifest data/exports/content-automation/planned-item-<id>/register-images.json
```

The registration manifest shape is:

```json
{
  "planned_item_id": 1,
  "provider": "codex_imagegen",
  "images": [
    {
      "option_number": 1,
      "image_path": "outputs/graphics/planning/planned-item-1/option-1.png",
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

Create a standalone Codex app automation for:

```text
/Users/matt/Documents/marketing-os
```

Recommended schedule:

```cron
0 8-20 * * *
```

Run it in the local project checkout, not a worktree. Use workspace-write permissions so Codex can update SQLite runtime data, logs, exports, and `outputs/graphics/`.

Use this automation prompt:

```text
Run scheduled Marketing OS content production for /Users/matt/Documents/marketing-os.

Use the repo skills:
- $copywriter
- $image-creator

Rules:
- Do not edit source code, docs, tests, or configuration.
- Only write runtime outputs under data/, outputs/graphics/, and the local SQLite database.
- Never approve generated copy or images.
- Never create posting tasks.
- Never post to external platforms.
- Keep all generated outputs in human review.

Each run:
1. Read AGENTS.md and SKILLS.md.
2. Run:
   ./scripts/run-codex-content-automation.sh
3. Inspect data/exports/content-automation/**/image-requests.json.
4. For each pending image option, use $image-creator and Magnific MCP with Google Nano Banana 2 to generate a real PNG file under:
   outputs/graphics/planning/planned-item-<id>/option-<n>.png
   Pass every listed reference image to Magnific. Assign @img1 as the primary visible product and @img2+ as identity locks. Use built-in image editing only if Magnific MCP is unavailable, and still pass the reference images.
5. Download each completed image to the path above. Build register-images.json beside image-requests.json using the registration_manifest_example shape from the request file, with image_path values updated to the downloaded files.
6. Register generated files:
   python -m marketing_os.jobs.register_generated_images --manifest data/exports/content-automation/planned-item-<id>/register-images.json
7. Verify:
   python -m marketing_os.jobs.content_automation --dry-run --limit 10 --days-ahead 14
8. Report:
   - planned item IDs processed
   - copy candidates created or refreshed
   - image files generated and registered
   - failures that need user attention
   - whether queued items remain

If no pending requests exist, report that nothing needed generation.
```

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

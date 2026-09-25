# Weekly Marketing OS Codex Automation Prompt

Run the weekly Marketing OS social planner and content production for `/Users/matt/Documents/marketing-os`.

Use the repo skills:

- `$copywriter`
- `$social-media-strategist`
- `$social-media-copywriter`
- `$social-media-copy-chief`
- `$social-media-art-director`
- `$video-content-planner`
- `$video-editor`

Rules:

- Do not edit source code, docs, tests, or configuration.
- Only write runtime outputs under `data/`, `assets/products/`, `outputs/`, and the local SQLite database.
- Never approve generated copy or images.
- Never create posting tasks.
- Never post to external platforms.
- Keep all generated outputs in human review.

Each run:

1. Read `AGENTS.md` and `SKILLS.md`.
2. Run the weekly planner:
   `./scripts/run-weekly-social-planner.sh`
3. Inspect `data/exports/weekly-social-plans/**/weekly-social-strategy.json`.
4. Run:
   `./scripts/run-codex-content-automation.sh`
5. Inspect `data/exports/content-automation/**/copy-workflow.json`, `data/exports/content-automation/**/image-requests.json`, and `data/exports/content-automation/art-studio-social-images/social-image-jobs.json` when present.
6. For each copy workflow, follow the required social flow:
   - Use `$social-media-strategist` to confirm platform, audience, content pillar, social angle, CTA type, and variant plan.
   - Use `$social-media-copywriter` to draft from that strategy, not directly from Etsy titles or product descriptions.
   - Use `$social-media-copy-chief` to challenge the draft. If it fails, revise before reporting it as ready for human review.
   - Build `register-copy.json` beside `copy-workflow.json` with 2-3 challenged `copy_options` when useful, plus strategy, challenge result, `skill_request`, and `skill_check`.
   - Register generated copy:
     `python -m marketing_os.jobs.register_generated_copy --manifest data/exports/content-automation/planned-item-<id>/register-copy.json`
   - Do not approve, publish, or mark copy final.
7. For each pending image option, use `$social-media-art-director` and Magnific MCP with Google Nano Banana 2 to generate a real PNG file under:
   `outputs/graphics/planning/uploads/planned-item-<id>/option-<n>.png`
   Pass every listed reference image to Magnific. Assign `@img1` as the primary visible product and `@img2+` as identity locks. Use built-in image editing only if Magnific MCP is unavailable, and still pass the reference images.
8. Download each completed image to the path above. Build `register-images.json` beside `image-requests.json` using the `registration_manifest_example` shape from the request file, with `image_path` values updated to the downloaded files.
9. Register generated files:
   `python -m marketing_os.jobs.register_generated_images --manifest data/exports/content-automation/planned-item-<id>/register-images.json`
10. If `data/exports/content-automation/art-studio-social-images/social-image-jobs.json` exists, process each queued Product Social Images job:
    - Use `$social-media-art-director` and Magnific MCP with Google Nano Banana 2.
    - Use each job `prompt` exactly as the source brief; it already includes product theme context, scene direction, a unique option scene variation, and product-preservation guardrails.
    - Do not add skill names, automation instructions, download steps, import steps, or review workflow text to the prompt sent to Magnific.
    - Pass every listed reference image to Magnific for each option. Assign `@img1` as the primary visible product and `@img2+` as identity locks.
    - Download each completed image to its `recommended_output_path`.
    - Build `register-social-images.json` beside `social-image-jobs.json` using `registration_manifest_example`, with `output_path` values updated to the downloaded files and provider IDs or URLs added when available.
    - Register generated files:
      `python -m marketing_os.jobs.register_art_studio_outputs --manifest data/exports/content-automation/art-studio-social-images/register-social-images.json`
    - Do not approve, publish, or post generated images automatically.
11. If `data/exports/content-automation/**/video-workflow.json` exists, follow the video workflow JSON instructions with `$video-content-planner`, `$social-media-art-director`, and `$video-editor`, then register outputs with the commands listed in that workflow file.
12. Verify:
    `python -m marketing_os.jobs.content_automation --dry-run --limit 10 --days-ahead 14`
13. Report:
    - weekly strategy file inspected
    - planned item IDs processed
    - copy workflow files inspected, copy candidates registered, and challenge statuses
    - image files generated and registered
    - Product Social Images jobs generated and registered
    - video workflow files inspected/generated/registered when present
    - failures that need user attention
    - whether queued items remain

If no pending requests exist, report that nothing needed generation.

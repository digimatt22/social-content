# Codex Image Generation Setup

Marketing OS now queues image generation from Planning instead of showing prompt text as a finished option.

## Current Behavior

When a post is saved in Planning:

- The post enters `waiting_content_generation`.
- The content-production job can generate copy through the copywriter adapter.
- Image generation remains queued as `waiting_image_generation` until real image files are created.
- Review screens only show image options that have an actual local file or user upload.

## Enable Generated Image Files

Use this path when Codex has Magnific MCP available in the active environment. Built-in image editing is only a fallback when Magnific is unavailable, and product work must still pass actual reference images.

1. Open Planning and create a queued post.
2. Select one or more approved product reference images in Planning. These are exported as `@img1`, `@img2`, and additional identity locks for Magnific.
3. Run:

   ```bash
   python -m marketing_os.jobs.content_production --limit 10
   ```

4. Export or inspect the content brief for the queued item:

   ```bash
   python -m marketing_os.jobs.content_production \
     --planned-item-id ITEM_ID \
     --dry-run \
     --export-briefs-dir data/exports/content-briefs
   ```

5. Use the `image-creator` skill with the exported brief facts to generate 2-3 real image files through Magnific MCP using Google Nano Banana 2. Natural prompts like "create three Facebook image options for this planned post" should trigger it from `.agents/skills/image-creator`.
6. Download generated files under `outputs/graphics/planning/planned-item-<id>/`.
7. Register each downloaded file with `python -m marketing_os.jobs.register_generated_images --manifest ...`, or add it through Planning with `Upload image option`.
8. Review and approve one image option in Planning before creating the posting task.

## Automation Adapter Contract

A future image-generation adapter should:

- Read queued items with status `waiting_image_generation` or `waiting_image_regeneration`.
- Use `build_content_brief()` to collect product, destination, goal, audience, and approved source-asset facts.
- Use `image_creator_contracts(brief, count=3)` from `marketing_os.services.skill_adapters`.
- Generate real image files from those contracts with Magnific MCP, passing every listed reference image.
- Register each output as an `AssetRecord` and a `GeneratedContentCandidateRecord` with `candidate_type="image_asset_option"`.
- Leave every image candidate in `needs_review`.

Do not mark generated images approved automatically. Product accuracy and brand fit need human review first.

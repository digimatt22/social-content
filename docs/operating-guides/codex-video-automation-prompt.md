# Marketing OS Video Automation Prompt

Run scheduled Marketing OS video production for `/Users/matt/Documents/marketing-os`.

Use the repo skills:

- `$video-content-planner`
- `$social-media-art-director`
- `$video-editor`

Rules:

- Read `AGENTS.md` and `SKILLS.md` at the start of each run.
- Follow the repo skill workflows for video planning, scene-card prompting, and video handoff packaging.
- Do not edit source code, docs, tests, or configuration.
- Only write runtime outputs under `data/`, `outputs/graphics/`, and the local SQLite database.
- Never approve generated video plans, images, or videos.
- Never create posting tasks.
- Never post to external platforms.
- Keep all generated outputs in human review.
- Process all queued video workflow requests and all approved queued video generations.
- Continue processing remaining video requests after failures, then report failures at the end.

Each run:

1. Read `AGENTS.md` and `SKILLS.md`.
2. Run:
   `./scripts/run-codex-content-automation.sh`
3. Inspect `data/exports/content-automation/**/video-workflow.json`.
4. For each queued Art Studio video workflow:
   - Use `$video-content-planner` first to choose one grounded scene direction, one effect, the motion prompt, and whether an ending card is actually required.
   - Use `$social-media-art-director` second to write the opening scene-card prompt from that planner result. Only write an ending-card prompt when the planner explicitly requires one.
   - Keep the duck physically unchanged and in review.
   - Build `register-video-workflow.json` beside `video-workflow.json` using the `registration_manifest_example` shape from the request file.
   - Register the planner result and queue the scene-card jobs:
     `python -m marketing_os.jobs.register_art_studio_video_workflow --manifest data/exports/content-automation/video-request-<id>/register-video-workflow.json`
   - Generate the opening scene card through Magnific MCP using the queued prompt, download it to the local output path, and register it with `python -m marketing_os.jobs.register_art_studio_outputs`.
   - Generate the ending card only when the planner explicitly required one, then register it the same way.
   - Leave the request waiting for human video approval after the scene cards are loaded into Art Studio.
5. Inspect `data/exports/content-automation/**/video-generation.json`.
6. For each approved queued Art Studio video generation:
   - Use `$video-editor`.
   - Call Magnific `video_plan` before `video_generate` unless the user explicitly asked for a one-shot generation.
   - Use the generated opening card as the first frame and the ending card only when one was required and attached.
   - Use the sectioned Magnific-style prompt format:
     ```text
     SCENE:
     Realistic product-in-scene social video continuing from the approved opening card.

     SUBJECT:
     The exact 2.5 inch 3D printed duck shown in the start frame, inanimate and unchanged.

     REFERENCE / PRODUCT LOCK:
     Start frame: use the generated opening card as the first frame.
     Preserve silhouette, colors, accessories, layer lines, facial details, proportions, material, scale, and contact shadows.

     MOTION:
     0-2s - Establish the start frame and begin the selected safe effect gently.
     2-5s - Continue camera, light, focus, perspective, time, or environmental motion only.
     5-8s - Ease into a stable final view without inventing product action.

     AUDIO:
     Subtle scene-matched ambient sound. No music and no voices unless requested.

     STYLE:
     Photorealistic high-detail product video, clean social frame, no text, logos, watermarks, or duplicate products.

     NEGATIVE PROMPT:
     Use the standard Art Studio video negative prompt.

     TAIL (Ending Rule):
     End with the duck still physically unchanged while the motion settles into a clean final frame.
     ```
   - Keep the duck physically unchanged and in review.
   - Download the MP4 and optional poster locally and register them with `python -m marketing_os.jobs.register_art_studio_outputs`.
   - Do not approve or publish the generated video automatically.
7. Verify:
   `python -m marketing_os.jobs.content_automation --dry-run --limit 10 --days-ahead 14`
8. Report:
   - video workflow files inspected
   - scene-card jobs generated and registered
   - approved queued video jobs generated and registered
   - failures that need user attention
   - whether queued video items remain

If no queued video requests or approved queued video jobs exist, report that nothing needed generation.

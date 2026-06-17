# Magnific MCP Creative Asset Guide

Date: 2026-06-17

## Recommendation

Use the Magnific MCP server as the preferred interactive path for generating MattMadeMe creative assets from an AI assistant.

Magnific, formerly Freepik, now documents an official remote MCP server at:

```text
https://mcp.magnific.com
```

The MCP path is better than a direct REST API integration for assistant-driven image work because it uses OAuth with the Magnific account, draws from the existing account credits, and exposes generation, upload, history, and asset tools directly inside the assistant. The REST API remains useful for future automation, batch generation, or app-level integration, but it requires an API key and more explicit task polling.

Primary source docs:

- [Magnific MCP](https://docs.magnific.com/modelcontextprotocol)
- [Magnific API introduction](https://docs.magnific.com/introduction)
- [Nano Banana Pro Flash create image](https://docs.magnific.com/api-reference/text-to-image/nano-banana-pro-flash/generate)
- [Imagen 4 overview](https://docs.magnific.com/api-reference/text-to-image/imagen4/overview)

## Setup

Add Magnific as a remote streamable HTTP MCP server in any MCP-compatible client:

```text
Name: Magnific
URL: https://mcp.magnific.com
Authentication: OAuth
```

On first use, the client should open a browser OAuth flow. Sign in with the Magnific account that has the subscription or credits. No API key is needed for MCP.

For clients that accept JSON MCP configuration, use:

```json
{
  "mcpServers": {
    "magnific": {
      "url": "https://mcp.magnific.com"
    }
  }
}
```

For Claude Code, Magnific documents:

```bash
claude mcp add --transport http magnific https://mcp.magnific.com
```

For Codex Desktop, use the app's MCP/server settings if available and add the same URL as a remote streamable HTTP MCP server. If this workspace does not show Magnific tools in the tool list, the server has not been connected for the current session yet.

## Available MCP Tools

Magnific documents these relevant MCP tool groups:

| Area | Useful tools |
| --- | --- |
| Account | `account_balance`, `project_report` |
| Creations | `creations_search`, `creations_get`, `creations_show`, `creations_wait`, `creation_status` |
| Uploads | `creations_request_upload`, `creations_upload`, `creations_finalize_upload` |
| Image generation | `images_generate`, `images_models_list`, `images_models_show` |
| Image editing | `images_upscale`, `images_crop`, `images_resize`, `images_remove_background` |
| Other media | `video_generate`, `audio_tts`, `models3d_generate` |
| Spaces | `folders_list`, `spaces_list`, `spaces_view` |

For MattMadeMe, the highest-value flow is:

1. Upload the product angle photos for a duck.
2. Use `images_models_list` or `images_models_show` to confirm the current Google/Nano Banana model names.
3. Generate scene candidates with `images_generate`.
4. Use `creations_wait` or `creation_status` until the result completes.
5. Use `creations_show` for review.
6. Save approved outputs under `assets/products/<product-slug>/generated` or `outputs/graphics`.
7. Mark generated assets as `needs review` until product accuracy is manually approved.

## Model Notes

Nano Banana Pro Flash is the most relevant documented REST endpoint for the current manual workflow. The API page describes it as a Google Gemini 3.1 Flash model with:

- reference image support,
- Google Search grounding when needed,
- aspect ratios including `1:1`, `2:3`, `3:2`, `4:3`, `3:4`, `5:4`, `4:5`, `16:9`, `9:16`, and `21:9`,
- resolutions up to `4K`,
- up to 14 reference images.

For product preservation, prefer Nano Banana style models over pure text-to-image models because reference images are central to the workflow. Use Imagen 4 only for scenes where no exact product preservation is required.

## Product Preservation Guardrails

The generated image must be treated as a composite-style scene, even if the model performs it as one generation. The environment can change. The duck cannot.

Required review checks:

- Overall silhouette matches the source duck.
- Colors match the source duck.
- Printed layer lines are still visible where they exist in the source.
- Accessories, clothing, props, facial details, and any text elements are unchanged.
- Scale reads as a 2.5 inch object in a full-size environment.
- Grounding, contact shadows, and reflections are believable.
- The duck is not smoothed, repainted, reinterpreted, made glossy, or turned into a different material.
- The output does not introduce misleading product details.

Any failed check keeps the asset in `needs review` or rejects the generation.

## Reference Image Roles

Use all available product photo angles. When there are four images:

| Image | Role |
| --- | --- |
| `@img1` | Primary 3/4 angle and the exact visible duck to place in the scene. |
| `@img2` | Secondary angle for silhouette, profile, color, and accessory verification. |
| `@img3` | Detail or alternate side reference. |
| `@img4` | Back, top, or remaining angle reference. |

Tell the model that only `@img1` should appear in the scene unless a different angle is intentionally requested. The other images are identity locks, not extra objects to render.

## Improved Prompt Template

```text
Create a realistic photographic scene:

Scene: [SCENE DESCRIPTION]
Environment: [ENVIRONMENT DETAILS]
Mood and lighting: authentic, immersive, visually interesting, natural photographic lighting.

Place the exact duck shown in @img1 in the foreground at [PLACEMENT DESCRIPTION]. Use @img2, @img3, and @img4 only as identity references to preserve the duck's exact appearance. Do not render additional copies from @img2, @img3, or @img4.

The duck is a real 2.5 inch long 3D printed object. It must appear miniature inside a full-scale real-world environment. All surrounding objects, furniture, vehicles, buildings, plants, surfaces, and props must remain life-sized to create strong, accurate scale contrast.

The duck itself is locked reference content. Do not alter it. Do not smooth, repaint, recolor, reshape, resize, stylize, reinterpret, enhance, simplify, upscale-detail, or change the material of the duck. Preserve all 3D print layer lines, surface texture, colors, accessories, facial features, clothing details, props, text elements, and proportions exactly as shown in the reference images.

Generate only the surrounding environment, lighting, reflections, shadows, depth of field, and atmospheric effects. Add realistic contact shadows and grounding under the duck, but do not change the duck's geometry or appearance.

Composition: [CAMERA ANGLE, LENS FEEL, CROP, PLATFORM FORMAT]
Output: realistic photograph, no illustration, no cartoon styling, no added text, no watermark.
```

## Example MCP Request Wording

```text
Use Magnific `images_generate` with the current Nano Banana reference-image model.

Upload/use these references:
- @img1: primary visible 3/4 product angle
- @img2: identity lock side angle
- @img3: identity lock detail angle
- @img4: identity lock back/top angle

Generate one square 1:1 image at 2K using this prompt:

[paste the improved prompt]

After generation, wait for completion and show the result for manual product-accuracy review before saving it as an approved Marketing OS asset.
```

## REST API Fallback

If MCP is unavailable, the REST API can be used with an API key:

```bash
curl --request POST \
  --url https://api.magnific.com/v1/ai/text-to-image/nano-banana-pro-flash \
  --header 'Content-Type: application/json' \
  --header 'x-magnific-api-key: <api-key>' \
  --data '{
    "prompt": "...",
    "reference_images": [
      {
        "image": "https://example.com/primary-3-4.jpg",
        "text": "Primary visible 3/4 product angle. Preserve exactly.",
        "mime_type": "image/jpeg"
      },
      {
        "image": "https://example.com/side.jpg",
        "text": "Identity lock reference only. Do not render as a second object.",
        "mime_type": "image/jpeg"
      }
    ],
    "aspect_ratio": "1:1",
    "resolution": "2K",
    "use_google_search_tool": false
  }'
```

REST reference images must be publicly accessible URLs or GCS paths. Local product files would need to be uploaded somewhere accessible first. MCP upload tools may be easier for assistant workflows.

## Suggested Marketing OS Integration Later

Keep the first step manual through MCP. If the workflow proves reliable, add a small integration layer later:

```text
marketing_os/integrations/magnific.py
```

Possible capabilities:

- prepare a generation manifest from approved source photos,
- open or reference uploaded Magnific creation IDs,
- record model name, prompt, source image IDs, task ID, and output path,
- save outputs under predictable local filenames,
- keep outputs in `needs review`,
- store rejection notes when product preservation fails.

Suggested metadata for generated assets:

| Field | Purpose |
| --- | --- |
| `source_system` | `magnific_mcp` or `magnific_api` |
| `model` | Exact model used, such as Nano Banana Pro Flash. |
| `prompt_path` | Local prompt or manifest file. |
| `reference_images` | Local paths or remote creation IDs for all product angles. |
| `primary_reference` | The `@img1` path or ID. |
| `generation_task_id` | Magnific task or creation ID. |
| `scale_claim` | Usually `2.5 inch miniature`. |
| `review_state` | `needs_review`, `approved`, or `rejected`. |
| `review_notes` | Product-accuracy notes. |

## Open Questions

- Confirm exactly how Codex Desktop exposes remote streamable HTTP MCP server configuration in this install.
- Confirm which Magnific image model appears in `images_models_list` for the account.
- Test whether MCP upload tools preserve local filenames and whether uploaded product photos can be reused across sessions.
- Test if the model follows the instruction that `@img2` through `@img4` are identity locks rather than extra objects.
- Decide whether generated outputs should be stored under each product folder or centralized in `outputs/graphics`.

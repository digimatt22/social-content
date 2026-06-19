# Magnific/Freepik MCP Workflow

Use this path when the user asks for Magnific, Freepik, MCP generation, reference-image product preservation, or an external handoff.

## If MCP Tools Are Available

1. Confirm the user is logged in and MCP tools are visible.
2. Use model-list/show tools if available to confirm current model names. Prefer `Google Nano Banana 2`; use the closest current Nano Banana reference-image model only if that exact model is unavailable.
3. Upload reference images or identify existing creation IDs.
4. Assign image roles: `@img1` primary visible product, secondary images as identity locks.
5. Call image generation with the prompt from `references/prompt-format.md`.
6. Wait for completion.
7. Download the completed image to the requested local output path, normally under `outputs/graphics/planning/planned-item-<id>/`.
8. Show the result for review.
9. Keep the output in review until product accuracy is confirmed.

## If MCP Tools Are Unavailable

Do not attempt live generation. Produce a handoff containing:

- Provider path: `magnific-mcp`.
- Model preference if known.
- Reference image paths and roles.
- Prompt.
- Aspect ratio and resolution.
- Upload/generate/wait/download/review instructions.
- Product-preservation checklist.
- Expected local output path or naming convention.

## Suggested MCP Request

```text
Use Magnific `images_generate` with Google Nano Banana 2.

References:
- @img1: primary visible product angle.
- @img2: identity lock side/profile angle.
- @img3: identity lock detail angle.
- @img4: identity lock back/top angle.

Generate one [ASPECT RATIO] image at [RESOLUTION] using this prompt:

[PROMPT]

After generation, wait for completion, download the generated file to the requested local output path, and show the result for manual product-accuracy review before marking it usable.
```

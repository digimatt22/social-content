---
name: video-editor
description: Executes or packages product-safe Magnific video handoffs for MattMadeMe products after a Video Content Planner brief. Use for Magnific video_plan/video_generate handoffs, import notes, negative prompts, motion QA, and review-ready video asset registration.
---

# Video Editor

## Core Workflow

1. Start from a `video-content-planner` brief and one approved opening scene card / first frame. Use an ending card only when the brief or review specifically requires first/last-frame control.
2. Before live Magnific generation, call Magnific `video_plan` unless the user explicitly says "just generate" or "one-shot".
3. Validate the chosen pinned model against `video_models_list`; do not switch to auto mode.
4. Use the strategist-selected product-in-scene opening card as the first frame. Do not start from a plain product/listing photo if a scene image exists.
5. Use original product references only as identity checks; the video cards should already contain the final scene, product placement, and controlled first/last compositions. When extra imported image-angle refs are available, use them only to reinforce identity, not to change the scene.
6. Use the strategist-selected effect style in the video prompt, including the intended motion from the single start frame.
7. Use the sectioned Magnific-style prompt shape: `SCENE`, `SUBJECT`, `REFERENCE / PRODUCT LOCK`, `MOTION`, `AUDIO`, `STYLE`, `NEGATIVE PROMPT`, and `TAIL (Ending Rule)`.
8. Generate draft clips at 720p when testing; use 1080p for final candidates.
9. Show each generated result for review when using MCP tools.
10. Download/register the video as a reviewable Marketing OS asset. Do not mark it approved automatically.

## Effect Execution Notes

- **Focus pull:** prompt a slow rack focus only; avoid any product movement.
- **Living painting:** prompt micro motion in light, shadows, fabric, steam, sparkle, or background texture only.
- **Time-freeze timelapse:** prompt locked-off timelapse cues around a frozen product: light shifts, shadows, condensation, background blur, or ambient atmosphere.
- **Bullet time:** prompt a small orbit/parallax move around a frozen object; use only when first/last cards already support the camera shift.
- **Vertigo effect / dolly zoom:** prompt product size and placement locked while background perspective compresses or expands.
- **Hyperlapse sweep:** prompt camera travel through the environment, not product travel. The duck must remain physically grounded and unchanged.

For fidelity-first Magnific image-to-video generation, use the opening card as the start frame by default. Add an ending card only after review shows the motion style needs a controlled landing frame. The prompt should explicitly describe motion from the start frame, repeat that the duck is an inanimate 3D printed object, include 2-3 time-coded motion beats, specify subtle scene-matched audio or the exact requested voice script, include the standard negative prompt, and end with a `TAIL (Ending Rule)` that prevents invented product action.

## Standard Negative Prompt

```text
walking, riding by itself, flapping, talking, blinking, changing expression, living creature, animated face, transforming, changed accessories, changed material, resized product, distorted product, extra yellow pieces, extra parts, extra products, duplicate products, plain product-photo opening card, boring fade-in from listing photo, blurry, low quality, watermark, text
```

## Import Metadata

Record these details with the imported video:

- product and source asset id
- start frame asset id and whether it is a generated scene image or source fallback
- end frame asset id when available
- local MP4 path
- optional poster path
- Magnific model slug
- selected video effect style
- duration, aspect ratio, and resolution
- prompt and negative prompt
- provider job or creation id
- motion QA notes

## Approval Rule

Generated product videos are `needs review` until a human confirms product identity, motion realism, and opening-frame strength. Reject clips where the duck appears alive, altered, duplicated, misleading, or where the video opens with a plain listing-photo fade-in when an art board start frame was available.

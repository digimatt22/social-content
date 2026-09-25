---
name: social-media-art-director
description: Social media visual art director for product-preserving creative. Use when the user asks for Facebook/Instagram/Pinterest/social post images, product scene concepts, generated image options, visual directions, image prompts, Magnific/Freepik handoffs, reference-image preservation, aspect ratios, crop guidance, creative review, or MattMadeMe product social visuals. Specializes in reviewable social creative, product-in-environment scenes, giftable moments, collector details, and source-image-safe prompts.
---

# Social Media Art Director

## Core Workflow

1. Normalize the request into: `platform`, `format`, `audience`, `goal`, `subject`, `social_angle`, `post_story`, `story_move`, `brand_style`, `details`, `reference_images`, `aspect_ratio`, `provider_path`, `must_include`, and `avoid`.
2. Select the destination playbook from `references/destination-image-playbooks.md`, including the platform-specific social format when the asset is for Facebook, Instagram, Pinterest, Threads, or LinkedIn.
3. Choose the provider path:
   - Use **Magnific/Freepik MCP** as the primary path for MattMadeMe product images, reference-image product preservation, Freepik/Magnific requests, or external handoff packages.
   - Use **built-in image generation/image editing** only as a fallback when Magnific MCP is unavailable, blocked, or explicitly declined by the user. For product work, fallback must still pass actual reference images through an image-editing path, not just describe them in text.
4. Choose a social creative role before prompting: product-in-use, giftable moment, collector detail, maker/process, seasonal/occasion, or community prompt.
5. If social copy exists, translate the copy's story move into the image scene. The visual must feel like the same idea as the caption, not a generic product image.
6. Build a prompt from `references/prompt-format.md`.
7. Run the quality checklist in `references/image-quality-rubric.md`.
8. If generating, keep generated output reviewable. Do not claim product accuracy without human or visual verification.

Normalize a loose image request:

```bash
python .agents/skills/social-media-art-director/scripts/normalize_image_request.py \
  --destination instagram \
  --format "square post" \
  --subject "miniature desk duck in a cozy workspace" \
  --audience "gift buyers" \
  --provider-path built-in
```

Package a handoff manifest:

```bash
python .agents/skills/social-media-art-director/scripts/build_generation_manifest.py \
  --product-slug mailman-duck \
  --destination instagram \
  --target-format square-product-card \
  --provider-path magnific-mcp \
  --source assets/products/mailman-duck/source.jpg \
  --prompt "Place the exact duck in a realistic mailroom scene."
```

## Magnific/Freepik MCP Path

Do not attempt live Magnific generation unless MCP tools are available and the user is logged in. Prefer **Google Nano Banana 2** when it is available in the account model list. Use a current reference-image-capable model only if that exact model name is unavailable.

For product images:

- upload or select every chosen product reference image,
- assign roles in order: `@img1` primary visible product, `@img2+` identity locks,
- call image generation with the strict product-preservation prompt,
- download the completed output to the requested local path, normally `outputs/graphics/planning/planned-item-<id>/option-<n>.png`,
- register or hand off the downloaded file so Marketing OS can preview it,
- keep the result in review until product accuracy is confirmed.

When a post/caption has already been drafted:

- include the hook, story move, and body gist in the image prompt,
- include the platform, format, CTA behavior, and whether the copy is optimized for comments, saves, shares, search, or professional discussion,
- choose props/environment that reinforce the story,
- avoid visual ideas that only restate the product category,
- reject image options that could belong to any caption.

When Magnific MCP is unavailable, produce a complete handoff:

- reference image roles
- model/provider preference: Google Nano Banana 2
- prompt
- aspect ratio and resolution
- upload/generation/wait/download/review steps
- product-preservation checklist
- output registration notes

Read `references/mcp-magnific-workflow.md` before preparing this path.

## Built-In Image Generation Fallback

Use the available image generation tool directly only when Magnific cannot be used or exact product preservation is not the central risk. Write prompts with:

- subject and action
- environment and context
- composition and crop
- lighting and mood
- brand style
- aspect ratio or destination format
- text/no-text rule
- avoid list

If the user supplied or selected a reference image and asked for product-preserving work, use the image editing path with actual attached reference files rather than describing changes as text.

## Video Art Boards

When the request is for an Art Studio video scene card, treat the still as the start frame for Veo or Magnific video generation, not as a standalone social image.

- Use the Video Content Planner's selected effect style and card briefs.
- Opening card: create the finished scene immediately; do not make a plain product-card opening or listing-photo background.
- Ending card: do not create one by default. If the planner specifically asks for it, use the generated opening card as the scene and composition reference whenever available, then change only what the selected effect requires.
- For focus pull, change only the focus plane.
- For living painting, change only ambient light, micro highlights, shadows, or environmental texture.
- For time-freeze timelapse, change time-of-day, shadows, condensation, background activity blur, or atmosphere while the product and staging stay locked.
- For bullet time, shift the camera position only a small 15-25 degree orbit around the unchanged static product.
- For vertigo/dolly zoom, keep the product the same on-screen size and placement while changing background perspective/compression.
- For hyperlapse sweep, move the camera viewpoint along one plausible path or arc while keeping the product grounded and unchanged.
- Never bake in a specific staging surface such as a table unless the strategist selected that scene. Use neutral language like staging surface, display plane, shelf, roadside surface, counter, or environment floor as appropriate.
- Preserve the exact duck silhouette, colors, accessories, print layer texture, facial details, proportions, material, and scale. Do not add yellow pieces, extra parts, new props attached to the duck, duplicates, text, logos, or watermarks.

## References

- Read `references/prompt-format.md` for the shared prompt format.
- Read `references/destination-image-playbooks.md` for destination-specific visual requirements.
- Read `references/product-preservation.md` when a real product or reference image must remain accurate.
- Read `references/mcp-magnific-workflow.md` for the Magnific/Freepik handoff path.
- Read `references/image-quality-rubric.md` before final review.
- Read `references/examples.md` for compact examples.
- Read `references/source-map.md` only when working inside this Marketing OS repo.

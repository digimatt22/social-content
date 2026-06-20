---
name: social-media-art-director
description: Social media visual art director for product-preserving creative. Use when the user asks for Facebook/Instagram/Pinterest/social post images, product scene concepts, generated image options, visual directions, image prompts, Magnific/Freepik handoffs, reference-image preservation, aspect ratios, crop guidance, creative review, or MattMadeMe product social visuals. Specializes in reviewable social creative, product-in-environment scenes, giftable moments, collector details, and source-image-safe prompts.
---

# Social Media Art Director

## Core Workflow

1. Normalize the request into: `platform`, `format`, `audience`, `goal`, `subject`, `social_angle`, `post_story`, `story_move`, `brand_style`, `details`, `reference_images`, `aspect_ratio`, `provider_path`, `must_include`, and `avoid`.
2. Select the destination playbook from `references/destination-image-playbooks.md`.
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

## References

- Read `references/prompt-format.md` for the shared prompt format.
- Read `references/destination-image-playbooks.md` for destination-specific visual requirements.
- Read `references/product-preservation.md` when a real product or reference image must remain accurate.
- Read `references/mcp-magnific-workflow.md` for the Magnific/Freepik handoff path.
- Read `references/image-quality-rubric.md` before final review.
- Read `references/examples.md` for compact examples.
- Read `references/source-map.md` only when working inside this Marketing OS repo.

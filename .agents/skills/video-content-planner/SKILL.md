---
name: video-content-planner
description: Plans product-safe short-form video concepts for MattMadeMe products before Magnific generation. Use when choosing a video angle, motion level, aspect ratio, references, model path, or QA checklist for product videos where the duck must remain an inanimate 3D printed object.
---

# Video Content Planner

## Core Workflow

1. Normalize the request into: `product`, `platform`, `duration`, `aspect_ratio`, `start_frame_strategy`, `source_references`, `scene_reference`, `social_angle`, `environment`, `audio`, `allowed_motion`, `disallowed_motion`, `model_path`, and `review_checklist`.
2. Keep the product physically unchanged. The duck is a real 2.5 inch 3D printed collectible, not a living character.
3. Choose a conservative motion concept:
   - camera push-in, pan, orbit, focus shift, handheld drift,
   - environmental motion such as road blur, passing lights, steam, sparkle, shadows, water, or confetti,
   - subtle surface or vehicle bounce only when the object is plausibly being carried by the environment.
4. Reject concepts where the duck walks, rides by itself, flaps, talks, blinks, changes expression, transforms, changes material, changes accessories, resizes, or behaves like a living character.
5. The user or Art Studio queue selects the product. Do not choose inventory; choose exactly one scene direction for that queued product.
6. Select one video effect style for the direction, weighing social value, product-preservation risk, scene fit, and recent variety so the video backlog does not collapse into the same motion every time.
7. Hand the single direction to the Social Media Art Director as one strong opening scene card / first frame by default.
8. Prefer the generated or approved product-in-scene card as the video start frame; avoid opening on a plain product/listing photo.
9. Default to 5-8 seconds, 9:16, subtle ambient sound effects, 720p drafts, 1080p finals.
10. Recommend Magnific `video_plan` before any `video_generate` call.

## Product-Safe Video Effects

Use these effects to create visible motion without making the duck act alive. Pick one, explain why it is valuable, and define how to animate from a single start frame first. Only ask for an ending card after a review shows the effect needs first/last-frame control.

- **Focus pull:** low risk. Use foreground/background depth and rack focus from a prop, texture, or background element to the unchanged duck. Single start frame is usually enough.
- **Living painting:** low risk. Use subtle light shimmer, shadow movement, fabric texture, sparkle, steam, or tiny environmental atmosphere. Single start frame is usually enough; do not generate a nearly identical ending card by default.
- **Time-freeze timelapse:** medium risk. Use locked product placement while time passes around it: changing daylight, moving shadows, condensation, confetti, passing background blur, or seasonal atmosphere. Start with one frame; add an ending card only if the time shift needs a specific landing frame.
- **Bullet time:** medium-high risk. Use sparingly for hero/collector products. Start with one strong scene card and test a small orbit/parallax move; add first/last frames only if identity drift or camera landing needs control.
- **Vertigo effect / dolly zoom:** medium risk. Keep the duck the same on-screen size and placement while the background perspective compresses or expands. This may benefit from an ending card after a first single-frame test.
- **Hyperlapse sweep:** medium-high risk. Good for road, shelf, market, parade, or display-path scenes. Start with one strong scene card; add an ending card only when the path endpoint needs precise control.

Selection rule: prefer low-risk effects for new products or short 5 second drafts; use higher-energy effects only when the scene naturally supports camera movement and enough product references exist. Rotate among effect families across products and campaigns unless a specific effect is clearly best.

## Art Board Handoff

For the single selected direction, hand off one still-image prompt to `social-media-art-director` before video generation:

- scene strategy, such as festive picnic setup, rustic porch table, collector shelf detail, or gift table moment
- selected video effect, why it was chosen, and preservation risk
- target crop, usually 9:16 for vertical social video
- product reference roles
- product lock instructions
- opening-frame direction: the first still must be interesting enough to stop the scroll before motion begins
- optional ending-frame direction only if needed later: use the opening card as the scene/composition reference, then apply only the effect-required change such as focus plane, time cue, camera angle, background perspective, or camera-path endpoint

Queue a start-frame-only video draft once the opening scene card exists. Do not spend credits on an ending card unless the selected effect clearly needs first/last-frame control.

## Model Defaults

- Use a fidelity-first pinned model, not auto mode.
- Use `kling-25` as the default baseline for short 5-8 second product-safe clips from one approved opening card.
- Use `bytedance-seedance-pro-2.0` for longer 9-15 second clips or when stronger scene-direction controls matter.
- Use `bytedance-seedance-fast-2.0` for cheaper long-form drafts when needed.

## Prompt Shape

```text
SCENE:
[Specific real-world setting from the approved opening card. Continue the scene, props, light, surface, shadows, depth of field, and atmosphere from the start frame.]

SUBJECT:
The exact 2.5 inch 3D printed duck shown in the start frame, presented as an inanimate collectible.

REFERENCE / PRODUCT LOCK:
Start frame: use the selected product-in-scene opening card as the first frame. The first frame must already be social-worthy.
End frame: omit by default; use a matching ending card only when review shows the effect needs a controlled landing frame.
Preserve exact silhouette, colors, accessories, layer lines, facial details, proportions, material, scale, and contact shadows. Keep the duck physically still, rigid, grounded, and unchanged.

MOTION:
0-2s - Establish the start frame and begin [selected effect] gently.
2-5s - Continue [camera/environment/light/focus/perspective/time motion only].
5-8s - Ease into a stable final view without inventing a new product pose or action.

AUDIO:
[Subtle scene-matched ambient sound or silent. No music unless requested. If the request includes a voice script, preserve the exact script and requested tone cleanly inside the audio direction.]

STYLE:
Photorealistic high-detail product video, cinematic natural-light look, clean social frame, [aspect ratio], no text, logos, watermarks, or duplicate products.

NEGATIVE PROMPT:
walking, riding by itself, flapping, talking, blinking, changing expression, living creature, animated face, transforming, changed accessories, changed material, resized product, distorted product, extra yellow pieces, extra parts, extra products, duplicate products, plain product-photo opening card, boring fade-in from listing photo, blurry, low quality, watermark, text

TAIL (Ending Rule):
End with the duck still physically unchanged while the selected camera, light, focus, or environmental motion settles into a clean final frame.
```

## Review Checklist

- Product silhouette, colors, accessories, print lines, and material remain accurate.
- Opening frame is a social-worthy scene, not a plain product-card fade-in.
- Motion comes from camera, environment, light, focus, or subtle physical bounce.
- The duck does not animate as a living subject.
- The clip reads clearly in the target social crop.
- Output stays in review until Matt approves product accuracy and motion realism.

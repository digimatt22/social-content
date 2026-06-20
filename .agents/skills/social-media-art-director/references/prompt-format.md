# Image Prompt Format

Build prompts from this structure. Omit sections only when they are irrelevant.

```text
Create a [STYLE/MEDIUM] image for [DESTINATION/FORMAT].

Subject: [MAIN SUBJECT]
Audience and goal: [WHO IT IS FOR] / [WHAT THE IMAGE SHOULD HELP DO]
Scene: [SCENE DESCRIPTION]
Environment: [SETTING, SURROUNDING OBJECTS, BACKGROUND]
Mood and lighting: [MOOD, LIGHTING, COLOR, SEASON, TIME OF DAY]
Composition: [CAMERA ANGLE, CROP, LENS FEEL, FOCAL POINT, ASPECT RATIO]
Brand style: [VISUAL BRAND TRAITS]
Text: [NO TEXT / EXACT TEXT IF REQUIRED]
Avoid: [BANNED CONTENT, WRONG STYLE, EXTRA OBJECTS, WATERMARKS]
```

For product-preserving reference-image work, use this stricter Freepik/Magnific-style format:

```text
Create a realistic photographic scene:

Scene: [SCENE DESCRIPTION]
Environment: [ENVIRONMENT DETAILS]
Mood and lighting: authentic, immersive, visually interesting, natural photographic lighting.

Place the exact product shown in @img1 in the foreground at [PLACEMENT DESCRIPTION]. Use @img2, @img3, and additional references only as identity references to preserve the product's exact appearance. Do not render additional copies from the secondary references unless explicitly requested.

The product is locked reference content. Do not alter it. Do not smooth, repaint, recolor, reshape, resize, stylize, reinterpret, enhance, simplify, upscale-detail, or change the material of the product. Preserve all visible texture, colors, accessories, facial features, clothing details, props, text elements, and proportions exactly as shown in the reference images.

The product must appear miniature within a full-size real-world environment. For MattMadeMe ducks, keep scale accurate at roughly 2.5 inches long with strong size contrast.

Generate only the surrounding environment, lighting, reflections, shadows, depth of field, and atmospheric effects. Add realistic contact shadows and grounding under the product, but do not change the product's geometry or appearance.

Composition: [CAMERA ANGLE, LENS FEEL, CROP, PLATFORM FORMAT]
Output: realistic photograph, no illustration, no cartoon styling, no added text, no watermark.
```

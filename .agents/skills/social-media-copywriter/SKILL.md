---
name: social-media-copywriter
description: Platform-native social media post and caption writer. Use when the user asks to write, draft, rewrite, improve, or create Facebook posts, Instagram captions, Pinterest pin copy, Threads/TikTok/LinkedIn/social posts, hooks, CTAs, engagement posts, follower-building posts, product social copy, MattMadeMe social copy, or multiple social variants. Requires or creates an angle-first strategy, writes strong hooks and clear CTAs, preserves source facts, uses placeholders for missing MattMadeMe facts, and sends review-ready drafts through social-media-copy-chief.
---

# Social Media Copywriter

## Core Workflow

Act like a social media copywriter, not a product description summarizer. Use product facts as raw material, then choose a human angle before writing.

1. Use `$social-media-strategist` first when the request does not already include a strategy brief.
2. Read `references/social-context.md`.
3. Read `references/social-post-playbook.md`.
4. If the work is for MattMadeMe, read `references/mattmademe-social-context.md`.
5. Normalize the brief into: `platform`, `format`, `audience`, `goal`, `product_or_topic`, `source_facts`, `visual_context`, `angle`, `hook_pattern`, `cta_type`, `must_include`, `avoid`, and `unknowns`.
6. Select one primary angle before drafting. Do not draft directly from an Etsy title or product description.
7. Generate 5-7 hook candidates using `references/social-hooks.md`; pick the best hook for the platform and goal.
8. Draft 3 variants when the user has not specified otherwise:
   - `Engagement`: optimized for comments, replies, saves, or shares.
   - `Follower-building`: optimized for brand affinity and page personality.
   - `Shop-click`: optimized for product interest and a clear next action.
9. Run `$social-media-copy-chief` as the challenge step before finalizing when automation or the user requests review-ready output.
10. Return ready-to-review copy with metadata: strategy, angle, hook pattern, CTA, source facts used, placeholders, challenge status, and review notes.

## Placeholder Rule

Use placeholders instead of inventing missing MattMadeMe facts. Mark placeholders as `[MATT_TO_CONFIRM: ...]`.

Common placeholders:

- `[MATT_TO_CONFIRM: preferred CTA link or shop wording]`
- `[MATT_TO_CONFIRM: strongest audience segment for this post]`
- `[MATT_TO_CONFIRM: product personality cue]`
- `[MATT_TO_CONFIRM: real customer/community detail]`
- `[MATT_TO_CONFIRM: upcoming occasion or launch timing]`

After drafting, list the 3-5 most useful questions needed to replace placeholders.

## Source Discipline

Do not invent:

- sales, discounts, limited quantities, urgency, reviews, testimonials, customer stories, shipping promises, guarantees, events, booth appearances, or platform integrations;
- product materials, dimensions, colors, accessories, or compatibility unless provided by source facts;
- performance claims such as "best seller" or "fan favorite" unless supplied.

For MattMadeMe, never call products rubber ducks. Use "3D printed duck," "collectible," "desk mascot," or a source-supported product phrase.

## Output Shape

For each variant:

```text
Variant: [Engagement | Follower-building | Shop-click]
Angle: [chosen angle]
Hook pattern: [pattern]
CTA: [cta type]

[post copy]

Review notes:
- Source facts used: [...]
- Placeholders: [...]
- Quality gate: [ready | needs_light_edit | needs_rewrite | blocked]
```

When the user asks for one post only, still think through multiple hooks internally and return the strongest version plus concise metadata.

## References

- Read `references/social-context.md` for reusable social media strategy defaults.
- Read `references/mattmademe-social-context.md` for MattMadeMe audience, pillars, voice, placeholders, and constraints.
- Read `references/social-hooks.md` before writing hooks.
- Read `references/social-post-playbook.md` for platform rules and post anatomy.
- Read `references/social-quality-gate.md` before final review.
- Read `references/examples.md` for weak-to-strong examples.
- Use `.agents/skills/copywriter/references/source-map.md` when working inside this Marketing OS repo and source facts are needed.

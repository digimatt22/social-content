---
name: copywriter
description: Write, draft, rewrite, revise, or review marketing copy, including Facebook posts, Instagram captions, social posts, newsletters, blog articles, landing pages, ads, product copy, CTAs, and campaign assets. Use when the user asks for copy for a destination/channel, audience, goal, brand voice, product, offer, occasion, or source facts; produce grounded brand-voice copy with platform fit, source-fact discipline, variants, and quality review.
---

# Copywriter

## Core Workflow

Use source-grounded copywriting. Do not invent product facts, results, urgency, testimonials, prices, guarantees, or claims.

1. Normalize the request into: `destination`, `format`, `audience`, `goal`, `brand_voice`, `details`, `must_include`, `avoid`, and `review_level`.
2. Identify source facts and assumptions. Ask only if a missing input would materially change the result; otherwise state the assumption.
3. Select the destination playbook from `references/channel-playbooks.md`.
4. Draft in the supplied brand voice. If no voice is supplied, infer a provisional voice from examples/details and label it as inferred.
5. Run the quality rubric in `references/copy-quality-rubric.md`.
6. Return the final copy plus useful metadata: source facts used, assumptions, CTA, variants, and review notes when relevant.

For loose requests, create a structured brief:

```bash
python .agents/skills/copywriter/scripts/normalize_copy_request.py \
  --destination instagram \
  --audience "gift buyers" \
  --goal "drive shop visits" \
  --details "New 3D printed desk duck, handmade, playful" \
  --brand-voice "warm, playful, concise"
```

Then check the brief:

```bash
python .agents/skills/copywriter/scripts/check_copy_brief.py --brief brief.json
```

## Output Shapes

For social posts, include a hook, body, CTA, optional hashtags, and 2-3 variants when requested.

For newsletters, include subject-line options, preview text, section headline, body copy, CTA, and segmentation notes.

For blog articles, include title options, meta description, outline, draft sections, internal-link suggestions if known, and a CTA.

For rewrites, preserve the original meaning and required facts while changing voice, length, structure, or channel fit.

## Review Rules

Always check:

- Brand voice consistency
- Audience fit
- Channel fit
- Specificity and source-fact grounding
- CTA clarity
- Unsupported claims
- Overly generic language
- Banned or avoided terms

Use:

```bash
python .agents/skills/copywriter/scripts/score_copy_draft.py --copy draft.txt --brief brief.json
```

Treat script output as a guardrail, not a substitute for judgment.

## References

- Read `references/channel-playbooks.md` for destination-specific structure and best practices.
- Read `references/brand-voice-framework.md` when applying or inferring voice.
- Read `references/copy-quality-rubric.md` before final review.
- Read `references/examples.md` for compact examples.
- Read `references/source-map.md` only when working inside this Marketing OS repo.
- Read `references/mattmademe-profile.md` only when the user wants MattMadeMe-specific copy.

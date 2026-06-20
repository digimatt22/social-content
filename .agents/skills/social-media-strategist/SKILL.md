---
name: social-media-strategist
description: Social media strategy planner for the required pre-writing step. Use when the user asks what to post, what angle to use, how to position a product socially, how to grow followers or engagement, which content pillar/CTA/audience/platform to choose, or when automation needs the strategy stage before Facebook, Instagram, Pinterest, Threads, TikTok, LinkedIn, or MattMadeMe social copy. Output a concise strategy brief for social-media-copywriter; do not write final post copy.
---

# Social Media Strategist

## Core Workflow

Create the strategy brief before writing copy. Do not draft final post copy.

1. Read `.agents/skills/social-media-copywriter/references/social-context.md`.
2. For MattMadeMe, read `.agents/skills/social-media-copywriter/references/mattmademe-social-context.md`.
3. Normalize the source facts into: `platform`, `audience`, `goal`, `product_or_topic`, `content_pillar`, `social_angle`, `cta_type`, `visual_context`, `must_include`, `avoid`, and `unknowns`.
4. Choose one primary content pillar and one primary social angle.
5. Choose the best CTA type for the platform and goal.
6. Define the variant plan: engagement, follower-building, and shop-click.
7. Mark missing facts as `[MATT_TO_CONFIRM: ...]`; do not invent them.

## Output Shape

```json
{
  "role": "social-media-strategist",
  "platform": "Facebook",
  "audience": "...",
  "goal": "...",
  "content_pillar": "Duck Personality | Gift Moments | Flock Building | Maker Process | Cruise And Sharing | Seasonal And Occasion",
  "social_angle": "giftable | collectible | personality | maker_process | occasion | community_prompt | shop_action",
  "cta_type": "comment | share | save | shop | follow | community",
  "variant_plan": ["Engagement", "Follower-building", "Shop-click"],
  "unknowns": ["[MATT_TO_CONFIRM: ...]"],
  "reasoning": "One concise sentence explaining the strategic choice."
}
```

## Guardrails

- Strategy must not simply say "promote the product."
- Promotional content should still have a human reason to care.
- For engagement or follower growth, the product link should not be the emotional center of the post.
- For Facebook, prioritize conversation, community, and product personality.

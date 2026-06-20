---
name: social-media-strategist
description: Social media strategy planner for the required pre-writing step. Use when the user asks what to post, what angle to use, how to position a product socially, how to grow followers or engagement, which content pillar/CTA/audience/platform to choose, or when automation needs the strategy stage before Facebook, Instagram, Pinterest, Threads, TikTok, LinkedIn, or MattMadeMe social copy. Output a concise strategy brief for social-media-copywriter; do not write final post copy.
---

# Social Media Strategist

## Core Workflow

Create the strategy brief before writing copy. Do not draft final post copy.

1. Read `.agents/skills/social-media-copywriter/references/social-context.md`.
2. For MattMadeMe, read `.agents/skills/social-media-copywriter/references/mattmademe-social-context.md`.
3. Read `.agents/skills/social-media-copywriter/references/social-post-playbook.md` for platform structure, CTA behavior, and scheduling heuristics.
4. Normalize the source facts into: `platform`, `audience`, `goal`, `product_or_topic`, `content_pillar`, `social_angle`, `story_move`, `cta_type`, `visual_context`, `must_include`, `avoid`, and `unknowns`.
5. Choose one primary content pillar and one primary social angle.
6. Choose a story move before choosing product details. The story move should define how the post creates interest: proof-led product story, tiny scene, surprise, community question, collector observation, playful opinion, gift moment, maker detail, or origin story.
7. Check recent product/topic coverage when that context is available. Avoid repeating the same small subset of products unless there is a deliberate campaign reason.
8. Decide whether this is a product story, audience story, maker story, gift story, or community story. Avoid treating every product as a generic character caption.
9. Choose the best CTA type for the platform and goal.
10. Define the platform-specific best-practice emphasis and scheduling hypothesis. Prefer owned audience analytics when available; otherwise use the playbook default as a starting test, not a universal promise.
11. Define the variant plan: engagement, follower-building, and shop-click.
12. Mark missing facts as `[MATT_TO_CONFIRM: ...]`; do not invent them.

## Output Shape

```json
{
  "role": "social-media-strategist",
  "platform": "Facebook",
  "audience": "...",
  "goal": "...",
  "content_pillar": "Duck Personality | Gift Moments | Flock Building | Maker Process | Cruise And Sharing | Seasonal And Occasion",
  "social_angle": "giftable | collectible | personality | maker_process | occasion | community_prompt | shop_action",
  "story_move": "proof_led_product_story | origin_story | audience_story | tiny_scene | surprise_detail | playful_opinion | community_prompt | collector_observation | gift_moment | maker_detail",
  "story_thesis": "One sentence explaining why this post exists beyond describing the product.",
  "proof_points": ["sales/order count, customer group, repeated request, occasion, comment pattern, review theme, or source-backed product fact"],
  "missing_proof": ["[MATT_TO_CONFIRM: order count / customer group / why this product is hot]"],
  "freshness_check": "recently_used | fresh_product | deliberate_repeat | unknown",
  "cta_type": "comment | share | save | shop | follow | community",
  "platform_best_practices": ["..."],
  "scheduled_time_recommendation": {
    "local_time": "HH:MM",
    "reasoning": "One concise sentence tying the time to the platform behavior and available evidence.",
    "test_plan": "What to watch after posting."
  },
  "variant_plan": ["Engagement", "Follower-building", "Shop-click"],
  "unknowns": ["[MATT_TO_CONFIRM: ...]"],
  "reasoning": "One concise sentence explaining the strategic choice."
}
```

## Guardrails

- Strategy must not simply say "promote the product."
- Promotional content should still have a human reason to care.
- Do not let the post strategy become "hook, product description, CTA." If the middle is only a feature summary, the strategy is incomplete.
- Product details are proof points, not the story. Choose the emotional or social reason first.
- When a product has evidence of demand, make the demand the story: who is buying it, who it honors, what moment it serves, why it caught on, and what that says about the audience.
- Do not invent popularity. If order counts, customer groups, comments, or timing are missing, ask for them or use placeholders.
- Strategy should keep the product mix fresh. Recently featured products need a specific reason to repeat.
- For engagement or follower growth, the product link should not be the emotional center of the post.
- For Facebook, prioritize conversation, community, and product personality.
- For Instagram, prioritize visual payoff, save/share behavior, and caption hooks that do not restate the product title.
- For Pinterest, prioritize searchable title/description language, gift/occasion keywords, and evergreen discovery.
- Do not schedule every platform at the same clock time unless the user explicitly asks for a synchronized campaign moment.

# Social Quality Gate

Score each draft before returning it.

## Must Pass

- The post has a clear angle before product details.
- The first line is a hook, not an announcement.
- The body gives a human reason to care.
- The middle uses a story move before product facts.
- The middle continues the bit, scene, personality, audience meaning, or community prompt instead of becoming a product-description sentence.
- Product facts, if used, appear as punchline, proof, interesting detail, or scene support, not as a stacked feature list.
- Product facts are omitted when they do not add attention value or credibility.
- If the post implies demand or popularity, it includes source-backed proof or a placeholder.
- The post answers at least one of: what happened, who it is for, why it is resonating, or why now.
- The CTA matches the goal and asks for one action.
- The copy uses supplied facts and marks unknowns with placeholders.
- The platform format is respected.
- MattMadeMe copy avoids banned claims and phrases.

## Fail Conditions

Mark `needs_rewrite` if the draft:

- mostly restates the Etsy title or product description;
- follows the stale pattern `hook -> product description -> CTA` without a story move;
- uses a playful hook and CTA but lets the middle collapse into a feature inventory;
- adds product facts only because the structure expects them, even though they weaken the flow;
- includes stacked visual details or use cases as the main middle sentence when the platform is not Pinterest;
- could paste the middle sentence into an Etsy listing with little or no editing;
- claims a product is hot, viral, popular, requested, or widely ordered without source-backed proof;
- never gets beyond "this is a good gift/product for X";
- starts with "Check out," "Introducing," or "New in the shop" by default;
- could apply to almost any product in the shop;
- has no audience emotion, story, opinion, question, or use case;
- stacks multiple CTAs;
- invents popularity, reviews, urgency, scarcity, discounts, or events;
- calls a MattMadeMe duck a rubber duck.

Mark `blocked` if a required fact is missing and cannot be safely replaced with a placeholder.

## Review Labels

- `ready`: strong enough for human review.
- `needs_light_edit`: direction is right; refine voice, length, or CTA.
- `needs_rewrite`: weak angle, weak hook, generic body, or unsupported claims.
- `blocked`: cannot proceed without a required fact.

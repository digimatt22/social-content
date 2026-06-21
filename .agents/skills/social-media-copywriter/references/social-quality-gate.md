# Social Quality Gate

Score each draft before returning it.

## Must Pass

- The post has a clear angle before product details.
- The first line is a hook, not an announcement.
- The body gives a human reason to care.
- The draft follows a platform-specific structure, not a generic caption shape.
- The middle uses a story move before product facts.
- The middle continues the bit, scene, personality, audience meaning, or community prompt instead of becoming a product-description sentence.
- Product facts, if used, appear as punchline, proof, interesting detail, or scene support, not as a stacked feature list.
- Product facts are omitted when they do not add attention value or credibility.
- Search keywords are used only where they help the platform, especially Pinterest and sometimes Instagram.
- If the post implies demand or popularity, it includes source-backed proof or a placeholder.
- If the post uses internal sales data, it avoids exact counts, revenue, rankings, and best-seller comparisons unless Matt explicitly approved publication.
- The post answers at least one of: what happened, who it is for, why it is resonating, or why now.
- Any review-derived idea has been checked for sentiment and context before use.
- The CTA matches the goal and asks for one action.
- The copy uses supplied facts and marks unknowns with placeholders.
- The platform format is respected.
- Cross-platform batches are meaningfully adapted for each destination.
- If stronger platform performance needs a different visual format or scene, the draft notes this for art direction instead of pretending the current image is ideal.
- MattMadeMe copy avoids banned claims and phrases.

## Fail Conditions

Mark `needs_rewrite` if the draft:

- mostly restates the Etsy title or product description;
- follows the stale pattern `hook -> product description -> CTA` without a story move;
- sounds like the same Facebook-style caption reused for Instagram, Pinterest, Threads, or LinkedIn;
- returns one universal caption when the request asks for multiple destination-specific posts;
- uses a playful hook and CTA but lets the middle collapse into a feature inventory;
- adds product facts only because the structure expects them, even though they weaken the flow;
- includes stacked visual details or use cases as the main middle sentence when the platform is not Pinterest;
- could paste the middle sentence into an Etsy listing with little or no editing;
- claims a product is hot, viral, popular, requested, or widely ordered without source-backed proof;
- exposes exact sales counts, revenue, product rankings, or best-seller comparisons from internal sales data without explicit approval;
- never gets beyond "this is a good gift/product for X";
- starts with "Check out," "Introducing," or "New in the shop" by default;
- could apply to almost any product in the shop;
- has no audience emotion, story, opinion, question, or use case;
- uses hashtags as the main discovery strategy for Pinterest or overloads hashtags on Facebook, Threads, or LinkedIn;
- writes Pinterest output as a caption instead of a title and description;
- writes LinkedIn output without a real maker, process, customer, or business insight;
- stacks multiple CTAs;
- invents popularity, reviews, urgency, scarcity, discounts, or events;
- exposes internal source analysis phrases like "review language," "proof point," "reviewers call out," or "demand signal" in final copy;
- uses negative, mixed, unclear, or shipping-only reviews as positive product proof;
- calls a MattMadeMe duck a rubber duck.

Mark `blocked` if a required fact is missing and cannot be safely replaced with a placeholder.

## Review Labels

- `ready`: strong enough for human review.
- `needs_light_edit`: direction is right; refine voice, length, or CTA.
- `needs_rewrite`: weak angle, weak hook, generic body, or unsupported claims.
- `blocked`: cannot proceed without a required fact.

# Social Quality Gate

Score each draft before returning it.

## Must Pass

- The post has a clear angle before product details.
- The first line is a hook, not an announcement.
- The body gives a human reason to care.
- The CTA matches the goal and asks for one action.
- The copy uses supplied facts and marks unknowns with placeholders.
- The platform format is respected.
- MattMadeMe copy avoids banned claims and phrases.

## Fail Conditions

Mark `needs_rewrite` if the draft:

- mostly restates the Etsy title or product description;
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

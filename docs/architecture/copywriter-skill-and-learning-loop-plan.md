# Copywriter Skill And Learning Loop Plan

Date: 2026-06-17

## Recommendation

Create a dedicated Marketing OS copywriter service for posts and future blog drafts.

The copywriter should produce fewer, better pieces of copy instead of flooding the plan with generic drafts. It should write in MattMadeMe's tone, cite the product/source facts it used, support human review, and improve over time from performance notes and metrics.

## Goal

Generate high-quality marketing copy that sounds like MattMadeMe and gets better as the system learns what actually works.

The first implementation target is one Facebook post.

The copywriter should answer:

- What product, audience, and occasion is this for?
- Which source facts were used?
- What is the hook?
- What is the call to action?
- Does it sound like MattMadeMe?
- What was changed during review?
- How did the post perform after it was used?
- What should the system do differently next time?

## Inputs

Use existing and imported context:

- `docs/business/brand-voice.md`
- `docs/business/audiences.md`
- `docs/business/business-goals.md`
- `docs/business/marketing-channels.md`
- `docs/business/products.md`
- `docs/business/product-catalog.json`
- Etsy imported listing facts
- MattMadeMe website imported product/blog facts
- approved source or generated assets
- previous task metrics and review notes

## Copywriter Boundary

Suggested service:

```text
marketing_os/services/copywriter.py
```

Suggested methods:

- `generate_facebook_post(request)`
- `generate_instagram_caption(request)`
- `generate_blog_draft_outline(request)`
- `score_copy_against_voice(copy, context)`
- `record_copy_review(copy_id, decision, notes)`
- `summarize_copy_performance(product_id=None, channel=None)`

Routes and templates should call the service. Prompt construction, tone rules, and scoring checks should not live directly in Flask route functions or Jinja templates.

## Facebook Post Requirements

The first generated Facebook post should include:

- product or campaign name
- audience or occasion
- hook
- post body
- CTA
- optional hashtags only if they feel natural
- source facts used
- suggested image or asset
- review checklist
- copy button from the task workflow

The post should avoid:

- generic hype
- fake scarcity
- unsupported claims
- too many hashtags
- emoji-heavy or over-polished voice
- product details not found in source facts
- treating generated images as accurate without review

## Review Workflow

Every generated copy candidate starts in `needs_review`.

Review states:

- `needs_review`
- `approved`
- `needs_rewrite`
- `rejected`
- `posted`

Review should capture:

- edited body
- review decision
- notes
- reason for rewrite or rejection
- posted URL when available
- metric due date

## Learning Loop

The system should connect copy to outcomes.

Track:

- task ID
- copy candidate ID
- product ID
- channel
- source asset ID
- generated asset ID, if used
- hook style
- CTA type
- audience
- post URL
- metric due date
- reach, likes, comments, shares, clicks, visits, orders, or manual notes
- qualitative outcome notes

Learning summaries should identify:

- messages that got useful engagement
- products or audiences that repeatedly underperform
- CTAs that produced visits or sales
- image styles that helped or hurt
- copy patterns that needed heavy editing
- topics worth turning into blog drafts

## Acceptance Criteria

- One Facebook post can be generated from real source context.
- The generated post stores product, channel, audience, source facts, CTA, and review state.
- The operator can approve, edit, request rewrite, reject, and copy the post.
- The posted task can store a URL, metric due date, metrics, and outcome notes.
- The app can summarize at least one lesson from copy review or performance data.
- Copy generation remains separate from automatic publishing.


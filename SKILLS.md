# Marketing OS Skills

This repo keeps project-specific Codex skills under `.agents/skills/`, the standard repo-discovery location for Codex skills. Each skill uses the standard folder shape:

```text
.agents/skills/<skill-name>/
├── SKILL.md
├── agents/openai.yaml
├── references/
└── scripts/
```

The per-skill `SKILL.md` file is the canonical trigger and workflow document. This root `SKILLS.md` is only an index for humans and repo agents.

## Available Skills

- `copywriter`: Top-level marketing copy lead. Routes focused work, drafts/reviews broad campaign and product copy, and keeps source-fact discipline across channels. Social posts should route through `social-media-strategist`, `social-media-copywriter`, and `social-media-copy-chief`.
- `social-media-strategist`: Plans social platform strategy, content pillar, angle, CTA type, and variant plan before drafting.
- `social-media-copywriter`: Writes platform-native social posts, captions, hooks, and CTA variants with angle-first drafting, MattMadeMe social context, and engagement/follower/shop-click variants.
- `social-media-copy-chief`: Challenges social drafts before human review, checking hook strength, angle, CTA, source discipline, platform fit, and MattMadeMe voice.
- `social-media-art-director`: Prepares social creative concepts, image prompts, and Magnific/Freepik handoffs for product-preserving Facebook/Instagram/Pinterest visuals.
- `video-content-planner`: Plans conservative, product-safe short-form video concepts, motion rules, references, and model paths for MattMadeMe products.
- `video-editor`: Prepares Magnific video handoffs/import metadata and enforces review-safe product video motion QA.

## Current Context

Start current project work from:

- `README.md`
- `docs/getting-started.md`
- `docs/operating-guides/local-web-console.md`
- `docs/operating-guides/magnific-mcp-creative-assets.md`
- `docs/reviews/phase5-current-state-2026-06-17.md`

Superseded implementation plans and proof artifacts live under `docs/archive/`.

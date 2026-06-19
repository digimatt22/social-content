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

- `copywriter`: Drafts, revises, and reviews brand-consistent copy for social posts, newsletters, blog articles, product copy, ads, and campaign assets. It can use MattMadeMe context when requested, but the workflow is reusable across projects.
- `image-creator`: Prepares marketing image prompts for built-in image generation or Magnific/Freepik MCP handoffs, including destination-specific formats, reference-image roles, and review checklists.

## Current Context

Start current project work from:

- `README.md`
- `docs/getting-started.md`
- `docs/operating-guides/local-web-console.md`
- `docs/operating-guides/magnific-mcp-creative-assets.md`
- `docs/reviews/phase5-current-state-2026-06-17.md`

Superseded implementation plans and proof artifacts live under `docs/archive/`.

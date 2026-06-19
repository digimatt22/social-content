# Marketing OS Agent Guide

## Working Context

Marketing OS is a local-first Python/Flask/SQLAlchemy/SQLite app for MattMadeMe marketing planning, review, and operator workflows. Business facts live in `docs/business/`; runtime data lives in `data/`; generated graphics and manifests live in `outputs/graphics/`.

Start from `docs/reviews/phase5-current-state-2026-06-17.md` for current status. Treat files under `docs/archive/` as historical unless the user explicitly asks to reopen an archived plan.

## Repo Conventions

- Keep the app local-first. Do not add public hosting, publishing automation, or write-enabled external platform integrations without explicit instruction.
- Keep generated copy and generated creative behind human review.
- Use service boundaries in `marketing_os/services/` instead of putting business logic directly in Flask routes or Jinja templates.
- Use existing docs and templates before creating new structures.
- Keep source assets and generated outputs out of git unless the user explicitly wants sample artifacts committed.

## Useful Commands

```bash
python run_local.py
python -m unittest discover -s tests
python -m marketing_os.jobs.content_production --limit 10
python -m marketing_os.jobs.phase5_readiness
python -m marketing_os.jobs.phase5_readiness --fail-on-incomplete
```

## Skills

Use repo skills in `.agents/skills/` for specialized work. This is the standard Codex repo-discovery location, so natural prompts should trigger them without requiring a file path. They are reusable beyond this repo, with optional MattMadeMe references where needed:

- `.agents/skills/copywriter/SKILL.md`
- `.agents/skills/image-creator/SKILL.md`

See `SKILLS.md` for the skill index.

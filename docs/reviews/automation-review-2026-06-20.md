# Automation Review - 2026-06-20

## Current State

Marketing OS has three automation layers:

1. `./scripts/run-weekly-social-planner.sh` creates next-week Planning items and exports `weekly-social-strategy.json`.
2. `./scripts/run-codex-content-automation.sh` prepares copy and image handoff files under `data/exports/content-automation/`.
3. `docs/operating-guides/codex-weekly-automation-prompt.md` is the Codex agent prompt that turns those handoffs into human-review copy and image candidates using the repo skills.

The old broad image skill name is no longer part of the active automation path. Active skill names are:

- `copywriter`
- `social-media-strategist`
- `social-media-copywriter`
- `social-media-copy-chief`
- `social-media-art-director`

The stale `AGENTS.md` reference to `image-creator` was removed so future agents discover the same structure the automation uses.

## Codex App Automation

The weekly agent run should be created as a Codex App standalone project automation, not as launchd, cron, or another OS scheduler. The app automation should target:

```text
/Users/matt/Documents/marketing-os
```

Recommended schedule:

```cron
0 20 * * 0
```

Use the prompt in `docs/operating-guides/codex-weekly-automation-prompt.md`.

## Push Instead Of Schedule

The better long-term control model is still a deliberate in-app "run weekly plan now" action. It should prepare deterministic planner output in Marketing OS, then ask the human to start or confirm the Codex App automation run.

This avoids surprise unattended generation and lets the human run the weekly plan when sales CSV imports and product sync are fresh.

Recommended next implementation:

1. Add a local web-console action on the Planning or Settings page: "Run weekly plan now".
2. That action should enqueue a local job record and run only the deterministic planner/prepare steps from Flask.
3. The UI should then show the Codex App automation prompt and status checklist.
4. If Codex exposes a first-class app automation trigger later, wire the button to that supported surface rather than an OS scheduler.

The lock matters. Without it, a manual push and scheduled run could both generate candidates for the same planned items. The existing planner is idempotent for weekly item creation, but the agent generation layer should still have an explicit run lock.

## Codex CLI Fit

Codex CLI remains a possible future option for supervised local push runs, but it should not be the default path for this workspace while Codex App automations are already the chosen operating model.

If CLI support is revisited, keep it as a plan or explicit operator action until the safety model and logs are reviewed.

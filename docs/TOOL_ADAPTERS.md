# Tool Adapter Guidance

Use tool-specific instruction files only when a project actually uses that tool. Keep each adapter thin so `AGENTS.md` and `docs/` remain the source of truth.

## Principle
An adapter should point back to the harness instead of copying its rules. Duplicated instructions drift.

## Recommended Adapter Shape
Each adapter should include:
- A one-line purpose statement
- A link to `AGENTS.md`
- A link to the most relevant workflow doc
- Tool-specific setup notes only when required
- No duplicated project policy unless the tool cannot follow links

## Example `CLAUDE.md`
```md
# CLAUDE.md

Follow the repository instructions in [AGENTS.md](AGENTS.md).

Use [docs/WORKFLOW.md](docs/WORKFLOW.md) for the standard change process.
Use [docs/VALIDATION.md](docs/VALIDATION.md) for validation expectations.
Keep durable project knowledge in `docs/`.
```

## Example `.github/copilot-instructions.md`
```md
Follow the repository guidance in `AGENTS.md`.

Primary durable docs:
- `docs/PROJECT_CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/AUTOMATIONS.md`
- `docs/WORKFLOW.md`
- `docs/VALIDATION.md`

Do not duplicate long-running project rules here. Update `AGENTS.md` or `docs/` instead.
```

## When To Add An Adapter
Add an adapter when:
- The tool is actively used by contributors.
- The tool does not automatically read `AGENTS.md`.
- The adapter prevents repeated onboarding mistakes.
- The adapter can stay short and low-maintenance.

For a project-creation plugin or slash command, keep the adapter as a wrapper around `scripts/install-harness.sh` or `scripts/new-project.sh`. The script is the reviewed command contract; the adapter should only collect arguments and invoke it.

## When Not To Add An Adapter
Do not add an adapter when:
- The tool is not actively used.
- The adapter would duplicate large sections of docs.
- The adapter would create a second source of truth.
- The adapter is only speculative compatibility work.

## Maintenance
When changing durable project instructions:
- Update `AGENTS.md` or `docs/` first.
- Check whether adapters still point to the right files.
- Keep adapter-specific notes limited to tool behavior, not project policy.

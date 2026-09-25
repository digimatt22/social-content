# References

These references shaped the starter pack. Keep this list short and curated.

## Core References
- [OpenAI: Harness Engineering](https://openai.com/index/harness-engineering/)
  Rationale: establishes the pattern of a short `AGENTS.md`, repo-local durable knowledge, and executable plans as first-class artifacts.
- [OpenAI: How OpenAI uses Codex](https://cdn.openai.com/pdf/6a2631dc-783e-479b-b1a4-af0cfbd38630/how-openai-uses-codex.pdf)
  Rationale: reinforces practical repo conventions for agent-readable project guidance and execution planning.
- [Anthropic Claude Code docs: Memory and project instructions](https://docs.anthropic.com/en/docs/claude-code/memory)
  Rationale: supports keeping always-loaded instruction files concise and pushing deeper project knowledge into linked docs.
- [GitHub Copilot customization cheat sheet](https://docs.github.com/copilot/reference/customization-cheat-sheet)
  Rationale: aligns with splitting durable repo guidance from tool-specific customization layers.

## How This Starter Pack Uses Those References
- Keep `AGENTS.md` short and stable.
- Put operational truth in `docs/`.
- Store implementation plans in-repo.
- Add other tool-specific instruction files only as thin adapters when there is a concrete need.

## Optional Future Extensions
- Add `CLAUDE.md` only if Claude Code becomes a primary contributor and it can stay as a thin pointer to `docs/`.
- Add `.github/copilot-instructions.md` only if GitHub Copilot is actively used in the repo.
- Add path-specific guidance only when the codebase grows enough that broad repo-level docs are no longer sufficient.

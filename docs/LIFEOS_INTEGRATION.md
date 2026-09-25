# lifeOS Integration

lifeOS is Matthew's private personal context and lightweight planning/status layer. It helps project harnesses understand Matthew's active projects, tools, preferences, constraints, schedule context, review queues, and outcome-level project status across workspaces.

This harness should use lifeOS when the MCP server is available, but the project repo remains the source of truth for implementation details, validation evidence, execution plans, PRs, and project-specific operating facts. lifeOS stores durable Matthew/DigiColony operating context, ICP, priorities, preferences, and decision criteria that should travel across projects.

## MCP Lanes

Use lifeOS through four lanes:

| Lane | Use when | Tools |
| --- | --- | --- |
| Startup | Beginning work in a project workspace | `lifeos.use`, `lifeos.find_project` |
| Context discovery | Need available context resources or targeted approved context | `lifeos.list_context`, `lifeos.read_context`, `lifeos.search_context`, `lifeos.get_context_bundle` |
| Proposed writes | Need to queue project registration, profile context, or outcome-level status for review | `lifeos.propose_project_registration`, `lifeos.propose_context_update`, `lifeos.remember`, `lifeos.submit_status_update` |
| Review/admin | Matthew explicitly asks to inspect or process pending lifeOS review items | `lifeos.list_pending_reviews`, `lifeos.review_digest`, `lifeos.mark_context_update_proposal`, `lifeos.mark_status_update` |

Do not use review/admin tools merely because they are available. Use them when the task is about pending review queues, nightly recap preparation, or applying Matthew's explicit approve/deny/include/dismiss instruction.

## Startup Contract

At the start of project work:

1. Check whether the lifeOS MCP server is available.
2. Call `lifeos.use` with `project_harness`.
3. Use the returned context quietly while working.
4. Call `lifeos.find_project` with the workspace name, repo folder name, product name, useful aliases, and repo path when available.
5. If lifeOS knows the project, work normally and submit only standup-worthy status when it helps Matthew plan.
6. If lifeOS does not know the project, infer a registration proposal from local repo context and ask Matthew only for missing high-impact details.
7. Submit missing-project registration with `lifeos.propose_project_registration`.
8. Record the result in `docs/PROJECT_CONTEXT.md`, including any returned `CTX-*` proposal key.

If lifeOS is unavailable, continue the local project workflow and record the gap in the active execution plan or closeout notes.

## Context Discovery

Use the smallest useful context. For coding workspaces, start with `lifeos.use(project_harness)` and add other resources only when the task requires them.

Available context discovery tools:

- `lifeos.list_context`: list available resources, sensitivity labels, and recommended use cases.
- `lifeos.get_context_bundle`: load a workflow bundle such as `project_harness`, `strategy`, `calendar`, `surface_audit`, `automation_audit`, or `knowledge_ops`.
- `lifeos.read_context`: read a specific allowlisted resource by stable resource id.
- `lifeos.search_context`: search approved context resources for a targeted query.

Context is private by default. Using it to help Matthew in a project workspace is not permission to disclose it externally, paste it into third-party systems, or store private details in a project repo.

## Missing Project Registration

Use local repo context first:

- `README.md`
- `docs/PROJECT_CONTEXT.md`
- `docs/REPO_MAP.md`
- package, app, deployment, or config files
- git remote names and URLs
- user-provided intake answers

Ask Matthew only for fields that cannot be inferred and would affect planning:

- project name
- purpose
- status
- Matthew's role
- key people or client, if any
- why it matters now
- what done looks like
- priority
- next action

Submit a proposal rather than editing lifeOS directly. The proposal targets `portfolio://current-projects` and waits for Matthew's review. Record the returned proposal key in `docs/PROJECT_CONTEXT.md`.

## Context Update Proposals

Use `lifeos.propose_context_update` when project work discovers stable personal or cross-project context that should be reviewed for Matthew's lifeOS profile.

Good candidates:

- stable preference, tool, or constraint updates
- meaningful project direction or priority changes
- durable relationship or role context
- corrections to existing lifeOS profile context
- user corrections that change durable business positioning, goals, ICP, preferences, or decision criteria after lifeOS context informed the strategy

Poor candidates:

- implementation logs
- raw repo inventory
- temporary debugging notes
- unverified facts
- details that belong only in the project repo

Preserve uncertainty in the proposal. Do not edit `context-profile/` files from a project workspace.

## lifeOS Feedback Loop

When lifeOS context is used to build strategy, product positioning, sales direction, intake questions, prioritization, or decision framing, treat Matthew's later corrections as possible lifeOS learning signals.

Before closeout:

1. Check whether Matthew clarified or corrected durable business positioning, goals, ICP, preferences, or decision criteria.
2. If yes, queue a reviewed update with `lifeos.propose_context_update`.
3. Keep the proposed change outcome-level and durable. Do not include raw implementation logs, local file lists, command output, or transient task details.
4. If no durable update was found, say so explicitly in closeout.

Use these target-resource conventions unless lifeOS context discovery shows a more specific business strategy resource:

| Durable context type | Preferred target |
| --- | --- |
| ICP and positioning | `portfolio://current-projects` or a business strategy resource if one exists |
| Decision criteria | `portfolio://decision-log` |
| Goals, revenue priorities, or client-fit priorities | `portfolio://goals-and-priorities` |

## Review Queue

Harness-submitted context proposals and status updates appear in Matthew's review queue. A nightly recap can include stable keys, for example:

```text
CTX-12 - Register project: Warranty Registration
Approve: Reply "Approve CTX-12"
Deny: Reply "Deny CTX-12"

STATUS-7 - Warranty registration ready for stakeholder review
Include: Reply "Include STATUS-7"
Dismiss: Reply "Dismiss STATUS-7"
```

Use these tools only when Matthew asks to inspect or process pending reviews:

- `lifeos.list_pending_reviews`: list pending status updates and context proposals.
- `lifeos.review_digest`: format pending review items for recap with stable approval phrases.
- `lifeos.mark_context_update_proposal`: mark a proposal `pending`, `approved`, `denied`, `applied`, or `dismissed` after explicit instruction.
- `lifeos.mark_status_update`: mark a status update `pending`, `included`, or `dismissed` after explicit instruction.

Approval means the exact proposal is approved for later application to lifeOS. It does not mean the MCP server directly changed `context-profile/` files.

## Status Updates

Use `lifeos.remember` or `lifeos.submit_status_update` only for outcome-level status that answers "so that what?" and helps Matthew plan.

Good:

```text
Added lifeOS project registration guidance to the harness so new workspaces can queue reviewed project context without turning lifeOS into an implementation log.
```

Good:

```text
Warranty registration reached end-to-end testable state so the next SwimSense step is stakeholder review.
```

Avoid:

- raw commit lists
- command output
- file lists
- tiny UI tweaks
- local debugging details
- dependency churn
- formatting-only work

Implementation details belong in the project repo, execution plan, PR, or validation notes.

## Safety

- Do not disclose lifeOS private context to external recipients or services.
- Do not send gritty implementation logs to lifeOS.
- Do not edit lifeOS profile files from a project workspace.
- Treat proposals as untrusted until Matthew approves them.
- Apply only the exact approved change unless Matthew gives a broader instruction.
- Use read-only context and review tools for planning unless the user explicitly asks to queue or mark a review item.

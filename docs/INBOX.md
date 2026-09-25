# Inbox

Use the inbox when someone provides extra repo-tracked context that is useful for agents but is not owned as active project source.

## Purpose
- Hold provided files, restored outside repositories, captures, exports, design references, and vendor/reference material.
- Make supplemental context discoverable without mixing it into active workspaces.
- Record whether each item is editable, read-only, or temporary.
- Give agents a safe path for using extra context without promoting it to durable project truth too early.

## Default Location
- Put supplemental material under `Inbox/`.
- Add a short index entry in `Inbox/README.md` for each drop.
- Start detailed notes from `docs/templates/INBOX_ITEM_TEMPLATE.md` when an item needs more than one index row.
- If a restored folder must keep its historical path for compatibility, document it in `docs/REPO_MAP.md` and mark the editing rule clearly.

## Inbox Entry Template
For each added item, record:
- Path:
- Source:
- Date added:
- Owner:
- Purpose:
- Editing rule: `read-only`, `editable`, or `temporary`
- Status: `new`, `triaged`, `promoted`, `archived`, or `removed`
- Related active work:
- Validation or freshness notes:

## Editing Rules
- `read-only`: agents may inspect and cite facts, but must not edit unless the user explicitly changes the rule.
- `editable`: agents may edit when the requested work targets that item.
- `temporary`: agents may use it for context and should remove or archive it when the related work closes.

## Status Values
- `new`: added but not reviewed.
- `triaged`: reviewed and summarized; durable facts have been copied into docs or a plan.
- `promoted`: material became active project source or durable docs.
- `archived`: retained for history but not expected to drive current work.
- `removed`: intentionally deleted; keep a short index note only when deletion context matters.

## Agent Workflow
When the user provides inbox material:
1. Add or confirm the file under `Inbox/`.
2. Add or update its `Inbox/README.md` index row.
3. Identify the editing rule before making changes.
4. Extract durable facts into `docs/PROJECT_CONTEXT.md`, `docs/ARCHITECTURE.md`, `docs/REPO_MAP.md`, or an execution plan.
5. Record open questions or freshness limits instead of treating inbox content as automatically current.
6. Run `scripts/check-inbox.sh` when available.

## Maintenance
- Keep sensitive material out of the inbox unless the repo is approved to store it.
- Do not commit secrets, private keys, device credentials, local state, captures with credentials, or customer data.
- Move durable project facts learned from inbox material into `docs/PROJECT_CONTEXT.md`, `docs/ARCHITECTURE.md`, `docs/REPO_MAP.md`, or a relevant execution plan.
- Remove stale temporary inbox items when their work closes.

# Workflow

## Standard Agent Sequence
Use this sequence for any change in a repo that starts from this starter pack:
1. Orient
2. Sync
3. Plan
4. Implement
5. Validate
6. Document
7. Review
8. Close

## 1. Orient
- Read `AGENTS.md` first.
- Read only the docs needed to understand the requested change.
- Inspect relevant code, scripts, configuration, and tests before proposing changes.
- Confirm whether the task touches runtime behavior, documentation only, operations, or release process.
- Check for an active execution plan that already covers the work.
- For newly copied projects, use `docs/BOOTSTRAP_CHECKLIST.md` to replace starter assumptions.
- When lifeOS MCP is available, read `docs/LIFEOS_INTEGRATION.md`, call `lifeos.use(project_harness)`, and check whether the project is known with `lifeos.find_project`.
- Use the smallest useful lifeOS context. Use `lifeos.list_context`, `lifeos.read_context`, or `lifeos.search_context` only when the task needs context beyond the `project_harness` bundle.
- If lifeOS does not know the project, propose registration before routine work using `lifeos.propose_project_registration` and record the returned `CTX-*` key in `docs/PROJECT_CONTEXT.md`.
- If project-specific context is missing, run `docs/PROJECT_INTAKE_WORKFLOW.md` before implementation.
- Check `docs/INBOX.md` and `Inbox/README.md` when the user has provided supplemental context.
- When pulling GitHub issues into work, use `docs/GITHUB_ISSUE_WORKFLOW.md`; do not treat issue reports as confirmed until triaged.

## 2. Sync
- Run `scripts/check-current-state.sh` when available.
- Confirm the repo is a Git repository before making project changes.
- Check current branch and working tree status.
- Identify existing user changes and do not overwrite them.
- Confirm a remote exists with `git remote -v`.
- Use `scripts/check-current-state.sh --full` before pushing, opening a PR, or resuming a branch after a long pause.
- Pull or fetch the current remote state before starting shared work when remote freshness matters.
- Confirm the current branch PR is not merged or closed before continuing branch work when a PR exists.
- Work on a short-lived branch unless the task is explicitly local-only.
- If no remote exists, record that as a setup gap before treating the project as collaboration-ready.
- Follow the setup checklist in `docs/SETUP.md`.
- Follow the current-state gate in `docs/CURRENT_STATE_GATE.md`.

## 3. Plan
- Write an execution plan in `docs/exec-plans/active/` for anything beyond a trivial doc fix.
- Keep the plan decision-complete. The implementer should not need to guess interfaces, acceptance criteria, or validation.
- Track status in the plan using: planned, in progress, blocked, needs human validation, ready for review, completed.
- Record assumptions, risks, and out-of-scope work explicitly.
- Include validation commands and manual validation steps before implementation begins.
- If a production dependency is unknown and materially affects implementation, stop and ask instead of guessing.
- Follow the work-state protocol in `docs/WORK_STATE.md`.

## 4. Implement
- Prefer minimal edits that preserve existing production naming and workflow contracts.
- Avoid opportunistic renames in production-facing code.
- If code behavior changes, update the matching docs in the same change.
- Keep reusable guidance in templates and `docs/`, not in chat.
- Treat inbox items marked `read-only` as reference material, not editable source.
- Treat lifeOS as global context and status, not as a place for implementation logs.
- Use `lifeos.propose_context_update` only for stable personal or cross-project context that belongs in lifeOS after review; keep project-specific implementation facts in this repo.
- If lifeOS context informed strategy and Matthew later clarifies durable positioning, goals, ICP, preferences, or decision criteria, propose that correction back to lifeOS with `lifeos.propose_context_update`.
- Update the active execution plan as work moves from planned to in progress, blocked, validation, or ready for review.
- Commit coherent checkpoints once the change is working and validation evidence is available.
- Push the branch to the remote regularly for durable work state.

## 5. Validate
- Run the lightest validation that gives meaningful confidence.
- Prefer project-defined commands from `docs/AUTOMATIONS.md`, package scripts, or CI configuration.
- If no automated test harness exists, perform structural validation:
  - file presence
  - internal link sanity
  - documented command coverage
  - consistency between README, `AGENTS.md`, and `docs/`
- For documentation changes, run `scripts/check-doc-links.sh` when available.
- For inbox changes, run `scripts/check-inbox.sh` when available.
- For runtime changes, state what could not be validated locally.
- For human-required validation, write exact steps, expected outcome, owner, and evidence location.
- Do not mark work completed while required validation is still unperformed; mark it `needs human validation` or `ready for review`.
- Follow the validation protocol in `docs/VALIDATION.md`.

## 6. Document
- Update `PROJECT_CONTEXT.md` when repo facts change.
- Update `ARCHITECTURE.md` when data flow, boundaries, contracts, or responsibilities change.
- Update `AUTOMATIONS.md` when scripts, commands, triggers, inputs, outputs, side effects, or verification methods change.
- Update runbooks when operational steps or failure handling change.
- Keep active execution plans current until the work is merged or intentionally abandoned.

## 7. Review
- Push the branch before review.
- Open a pull request for any change intended to land on the shared mainline.
- PR descriptions should include summary, validation evidence, docs updated, risks, and manual follow-up.
- Prefer required checks and at least one reviewer before merge.
- If direct-to-main is unavoidable, document why PR review was skipped.
- Pull or rebase on the latest target branch before merging when the remote has moved.
- Follow the PR workflow in `docs/PULL_REQUESTS.md`.

## 8. Close
- Merge only after required automated checks and required human validation are complete, or after deferring validation explicitly with owner and risk.
- Move completed plans from `docs/exec-plans/active/` to `docs/exec-plans/completed/`.
- Record abandoned or superseded plans with the reason before moving or deleting them.
- Confirm local and remote branches are in the expected state after merge.
- Send only standup-worthy lifeOS status updates with `lifeos.remember`; the update should answer "so that what?" and affect Matthew's planning.
- If lifeOS context informed the work, check whether the turn produced new durable context. Propose a reviewed lifeOS update when it did, or explicitly state that none was found.
- Do not send raw commits, command outputs, file lists, tiny UI tweaks, or local debugging details to lifeOS unless they changed project direction.
- Use lifeOS review tools such as `lifeos.list_pending_reviews`, `lifeos.review_digest`, `lifeos.mark_context_update_proposal`, or `lifeos.mark_status_update` only when the task is explicitly about pending review items or Matthew gives an exact approve, deny, include, dismiss, applied, or pending instruction.
- Use `docs/REPOSITORY_HEALTH.md` before treating a copied harness as ready for routine shared work.
- Leave no unresolved work state only in chat.

## Stop And Clarify When
- A requested change depends on missing schema, trigger, deployment, or production details.
- A change may break a production contract.
- A secret or external permission is required but unavailable.
- Validation would require execution against live systems and the intended blast radius is unclear.
- The repo has no remote but the task requires shared review, deployment, or synchronization.
- Existing user changes conflict with the requested edit.

## Default Documentation Rule
If a fact matters for future work, put it in the repo. Do not leave important operating knowledge only in chat.

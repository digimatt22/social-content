# GitHub Issue Session Workflow

Use this workflow when the user wants an agent to pull GitHub issues into active work.

## Kickoff Prompt
Ask an agent:

```text
Start an issue session for these GitHub issues: <issue numbers or URLs>. Triage each issue, comment back on GitHub with status/questions, create issue branches for confirmed work, roll completed issue branches into one session branch, and prepare a final session PR for testing.
```

## Principles
- Reported issues are not automatically true. Treat each issue as a claim to verify.
- Ask clarifying questions on the GitHub issue when details are missing or the report appears inconsistent.
- If the issue is already fixed, duplicate, not reproducible, or out of scope, comment with evidence and proposed disposition.
- Keep issue state durable in the repo and visible on GitHub.
- Use one testable session branch to collect all issue work for a user-visible test pass.
- Import the issue title, body, labels, and comments by default so triage includes reporter context and any feedback on prior status updates.
- Rerunning the issue-session script for an existing session refreshes the imported GitHub snapshot, including new comments and current open/closed state, while preserving local triage and implementation notes.

## Branch Model
- Session branch: `session/<slug>`
- Issue branch: `issue/<number>-<short-description>`
- Final PR: `session/<slug>` into the target branch, usually `main`

Recommended flow:
1. Start from latest target branch.
2. Create `session/<slug>`.
3. For each confirmed issue, create an issue branch from `session/<slug>`.
4. Implement and validate one issue on its issue branch.
5. Merge or PR the issue branch back into `session/<slug>`.
6. Test the full session branch.
7. Open one final PR from `session/<slug>` to the target branch.

## Status Values
GitHub issue state:
- `open`: issue is still open in GitHub.
- `closed`: issue is closed in GitHub.

Workflow status:
- `imported`: issue copied into a session for triage.
- `needs verification`: the report needs reproduction or evidence.
- `needs info`: the issue needs user/reporter clarification.
- `confirmed`: the issue is valid and accepted for work.
- `in progress`: active branch work has started.
- `blocked`: work cannot continue without external input.
- `not reproducible`: attempted verification did not reproduce the issue.
- `already fixed`: current code appears to address the report.
- `completed`: issue work is merged into the session branch and validated.
- `deferred`: intentionally left out of the current session.

## GitHub Comment Expectations
Post a comment when:
- The issue is imported into a session.
- Triage changes the issue status.
- The agent needs clarification.
- Work starts on an issue branch.
- The issue branch is merged into the session branch.
- The final session PR is opened.
- The issue is closed, deferred, or found invalid.

Do not post a duplicate import comment when refreshing an already-imported issue. Refreshing should update the local issue file with new comments and current GitHub state; post to GitHub only when the workflow status or question changes.

Comments should include:
- Current status
- Branch or PR link when available
- Evidence, command output summary, or reproduction notes
- Specific questions when blocked
- Next expected action

## Session Files
Store active session state under:

```text
docs/issue-sessions/active/<session-slug>/
```

Use:
- `README.md` for the session overview
- `issues/<issue-number>.md` for per-issue triage and work state

Each issue work item should preserve:
- GitHub URL, title, reporter, state, labels, created date, and updated date
- The issue body as imported
- All comments visible at import time
- Last synced date
- Any follow-up status, question, work-start, merge, completion, or deferral comments posted by the agent

Move completed sessions to:

```text
docs/issue-sessions/completed/<session-slug>/
```

## Triage Checklist
For each issue:
- Read the imported issue body, labels, and comments.
- Check whether comments include feedback on earlier agent status updates before deciding the next action.
- Inspect the current repo state before assuming the report is current.
- Search for related code, tests, docs, open PRs, and previous work.
- Decide whether the issue is confirmed, needs info, already fixed, duplicate, not reproducible, or deferred.
- Comment on GitHub with the triage result.
- Create work only for confirmed issues.

## Completion Criteria
An issue is complete when:
- The issue branch is merged into the session branch.
- Relevant validation has passed.
- GitHub issue has a status comment with evidence.
- Remaining human validation is documented.
- The session overview links to the issue branch, validation, and final disposition.

The session is complete when:
- All issues have a final disposition.
- The session branch has been tested as an integrated change set.
- A final PR is opened or the session is explicitly abandoned.

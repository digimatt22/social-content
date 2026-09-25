# Current-State Gate

Agents must verify the current repo state before starting or resuming work. This prevents work from continuing on stale branches, merged PR branches, or local state that no longer matches the remote.

## When To Run
Run this gate:
- Before starting a new task
- Before resuming an interrupted task
- Before pushing more commits to an existing branch
- Before opening or updating a PR

## Standard Check
From the repo root:

```sh
scripts/check-current-state.sh
```

The default script path is intentionally fast for large repos. It:
- Confirms the folder is a Git repository
- Confirms `origin` is configured
- Reports the current branch and upstream
- Reports ahead/behind status from the locally known upstream state
- Checks tracked working-tree changes
- Skips remote fetch, GitHub PR lookup, and untracked-file scanning

## Deeper Checks
Use the heavier checks when remote freshness matters, such as before pushing, opening a PR, resuming a branch after a long pause, or starting shared issue-session work.

Refresh `origin` before checking ahead/behind:

```sh
scripts/check-current-state.sh --remote
```

Check the current branch PR state with GitHub CLI:

```sh
scripts/check-current-state.sh --pr
```

Run the full gate:

```sh
scripts/check-current-state.sh --full
```

`--full` fetches/prunes `origin`, checks the current branch PR, and scans for untracked files. It is safer but may be slow in large repositories.

Additional option:

```sh
scripts/check-current-state.sh --untracked
```

Use `--untracked` when you need to know whether new files are present; the default skips this because untracked scans can be expensive in large repos.

## Manual Fallback
If the script is unavailable, run:

```sh
git status -sb
git branch --show-current
git remote -v
```

When remote freshness matters, run:

```sh
git fetch --prune origin
git status -sb
```

If the current branch may have a PR, inspect it:

```sh
/opt/local/bin/gh pr view --json state,mergedAt,url,headRefName,baseRefName
```

## Required Response
If the branch PR is merged or closed:
- Stop work on that branch.
- Switch to the latest target branch.
- Pull with `--ff-only`.
- Create a new branch for any new work.
- Cherry-pick only intentional unmerged commits.

If the local branch is behind its upstream:
- Pull or rebase before editing, unless doing so would overwrite local user changes.

If the working tree has uncommitted changes:
- Identify whether they are yours or user changes.
- Do not overwrite unrelated user changes.
- Record the state in the active execution plan before proceeding.

If the default fast gate skipped remote fetch, PR lookup, or untracked scan:
- Decide whether the task needs those checks before editing or pushing.
- Prefer `--full` before push/PR work and after long pauses.
- Prefer the default check during frequent local iterations.

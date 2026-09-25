#!/usr/bin/env bash
set -euo pipefail

fetch_remote=0
check_pr=0
include_untracked=0

usage() {
  cat <<'EOF'
Usage: scripts/check-current-state.sh [--remote] [--pr] [--full] [--untracked]

Default mode is intentionally fast:
  - no network fetch
  - no GitHub PR lookup
  - no untracked-file scan

Options:
  --remote     Fetch/prune origin before checking ahead/behind.
  --pr         Check the current branch PR state with GitHub CLI.
  --full       Equivalent to --remote --pr --untracked.
  --untracked  Include untracked files in the working-tree summary.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote)
      fetch_remote=1
      shift
      ;;
    --pr)
      check_pr=1
      shift
      ;;
    --full)
      fetch_remote=1
      check_pr=1
      include_untracked=1
      shift
      ;;
    --untracked)
      include_untracked=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 1
      ;;
  esac
done

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Not inside a Git repository"
  exit 1
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "No origin remote configured"
  exit 1
fi

if [[ "$fetch_remote" -eq 1 ]]; then
  git fetch --prune origin
else
  echo "Remote fetch: skipped (use --remote or --full to refresh origin)"
fi

branch="$(git branch --show-current)"
if [[ -z "$branch" ]]; then
  echo "Detached HEAD; create or switch to a branch before shared work"
  exit 1
fi

upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
echo "Branch: $branch"
echo "Upstream: ${upstream:-none}"

if [[ -n "$upstream" ]]; then
  counts="$(git rev-list --left-right --count "$upstream"...HEAD)"
  behind="${counts%%[[:space:]]*}"
  ahead="${counts##*[[:space:]]}"
  echo "Ahead: $ahead"
  echo "Behind: $behind"
  if [[ "$behind" != "0" ]]; then
    echo "Branch is behind upstream; sync before editing or pushing"
    exit 1
  fi
fi

if [[ "$check_pr" -eq 1 ]]; then
  gh_bin="${GH:-}"
  if [[ -z "$gh_bin" ]]; then
    if [[ -x /opt/local/bin/gh ]]; then
      gh_bin="/opt/local/bin/gh"
    elif command -v gh >/dev/null 2>&1; then
      gh_bin="$(command -v gh)"
    fi
  fi

  if [[ -n "$gh_bin" ]]; then
    pr_info="$("$gh_bin" pr view --json state,url --jq '[.state, .url] | @tsv' 2>/dev/null || true)"
    state="${pr_info%%$'\t'*}"
    url="${pr_info#*$'\t'}"
    if [[ "$url" == "$state" ]]; then
      url=""
    fi
    if [[ -n "$state" ]]; then
      echo "PR: ${url:-unknown}"
      echo "PR state: ${state:-unknown}"
      case "$state" in
        MERGED|CLOSED)
          echo "Current branch PR is $state; create a fresh branch from the latest target branch before continuing"
          exit 1
          ;;
      esac
    else
      echo "PR: none found for current branch"
    fi
  else
    echo "GitHub CLI not found; skipped PR state check"
  fi
else
  echo "PR check: skipped (use --pr or --full to query GitHub)"
fi

if ! git diff --quiet --ignore-submodules -- || ! git diff --cached --quiet --ignore-submodules --; then
  echo "Working tree has tracked uncommitted changes; review them before proceeding"
else
  echo "Tracked working tree clean"
fi

if [[ "$include_untracked" -eq 1 ]]; then
  if [[ -n "$(git ls-files --others --exclude-standard)" ]]; then
    echo "Untracked files present"
  else
    echo "No untracked files"
  fi
else
  echo "Untracked scan: skipped (use --untracked or --full)"
fi

echo "Current-state check passed"

#!/usr/bin/env bash
set -euo pipefail

base="main"
post_comments=1

usage() {
  echo "Usage: scripts/start-issue-session.sh [--base main] [--no-comments] <session-slug> <issue-number-or-url>..."
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base)
      base="${2:-}"
      shift 2
      ;;
    --no-comments)
      post_comments=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      break
      ;;
  esac
done

if [[ $# -lt 2 ]]; then
  usage
  exit 1
fi

session_slug="$1"
shift

gh_bin="${GH:-}"
if [[ -z "$gh_bin" ]]; then
  if [[ -x /opt/local/bin/gh ]]; then
    gh_bin="/opt/local/bin/gh"
  elif command -v gh >/dev/null 2>&1; then
    gh_bin="$(command -v gh)"
  else
    echo "GitHub CLI not found"
    exit 1
  fi
fi

if [[ -x scripts/check-current-state.sh ]]; then
  scripts/check-current-state.sh
fi

session_branch="session/$session_slug"
git fetch --prune origin

if git show-ref --verify --quiet "refs/heads/$session_branch"; then
  git switch "$session_branch"
  git pull --ff-only origin "$session_branch" || true
elif git ls-remote --exit-code --heads origin "$session_branch" >/dev/null 2>&1; then
  git switch --track "origin/$session_branch"
else
  git switch "$base"
  git pull --ff-only origin "$base"
  git switch -c "$session_branch"
fi

session_dir="docs/issue-sessions/active/$session_slug"
mkdir -p "$session_dir/issues"

cat > "$session_dir/README.md" <<EOF
# Issue Session: $session_slug

## Status
- Session: $session_slug
- Status: imported
- Target branch: $base
- Session branch: $session_branch
- Final PR: TBD
- Owner: TBD
- Last updated: $(date +%F)

## Summary
- Issues included: $*
- Goal: Triage and complete confirmed issues as one testable session.
- Explicitly out of scope: TBD

## Issue Table
| Issue | GitHub state | Workflow status | Issue branch | Session merge | Validation | GitHub update |
| --- | --- | --- | --- | --- | --- | --- |
EOF

for issue_ref in "$@"; do
  issue_number="$("$gh_bin" issue view "$issue_ref" --json number --jq '.number')"
  title="$("$gh_bin" issue view "$issue_ref" --json title --jq '.title')"
  state="$("$gh_bin" issue view "$issue_ref" --json state --jq '.state | ascii_downcase')"
  url="$("$gh_bin" issue view "$issue_ref" --json url --jq '.url')"
  author="$("$gh_bin" issue view "$issue_ref" --json author --jq '.author.login')"
  created_at="$("$gh_bin" issue view "$issue_ref" --json createdAt --jq '.createdAt')"
  updated_at="$("$gh_bin" issue view "$issue_ref" --json updatedAt --jq '.updatedAt')"
  labels="$("$gh_bin" issue view "$issue_ref" --json labels --jq '[.labels[].name] | if length == 0 then "none" else join(", ") end')"
  comment_count="$("$gh_bin" issue view "$issue_ref" --json comments --jq '.comments | length')"
  issue_branch="issue/$issue_number-$(printf '%s' "$title" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//; s/-$//' | cut -c1-48)"
  issue_file="$session_dir/issues/$issue_number.md"
  import_action="imported"
  workflow_status="needs verification"
  preserved_work_state=""

  if [[ -f "$issue_file" ]]; then
    import_action="refreshed"
    workflow_status="$(sed -n 's/^- Current status: //p' "$issue_file" | head -1)"
    if [[ -z "$workflow_status" ]]; then
      workflow_status="needs verification"
    fi
    preserved_work_state="$(awk 'found { print } /^## Reported Claim$/ { found = 1; print }' "$issue_file")"
  fi

  cat > "$issue_file" <<EOF
# Issue $issue_number: $title

## Issue
- GitHub issue: $url
- Title: $title
- Reporter: $author
- GitHub state: $state
- Labels: $labels
- Created: $created_at
- Updated: $updated_at
- Imported comments: $comment_count
- Imported status: imported
- Current status: $workflow_status
- Issue branch: $issue_branch
- Session: $session_slug
- Last synced from GitHub: $(date +%F)

## Imported Issue Body
EOF

  "$gh_bin" issue view "$issue_ref" --json body --jq 'if (.body // "") == "" then "_No issue body provided._" else .body end' >> "$issue_file"

  cat >> "$issue_file" <<EOF

## Imported Comments
EOF

  if [[ "$comment_count" -eq 0 ]]; then
    echo "_No comments at import time._" >> "$issue_file"
  else
    "$gh_bin" issue view "$issue_ref" --json comments --jq '.comments[] | "### Comment by \(.author.login) at \(.createdAt)\n\n\(.body)\n"' >> "$issue_file"
  fi

  if [[ -n "$preserved_work_state" ]]; then
    printf '\n%s\n' "$preserved_work_state" >> "$issue_file"
  else
    cat >> "$issue_file" <<EOF

## Reported Claim
Summarize the issue without assuming it is correct.

## Triage
- Evidence inspected: TBD
- Reproduction steps: TBD
- Current behavior: TBD
- Expected behavior: TBD
- Disposition: needs verification

## GitHub Comments
- Import comment: posted by \`scripts/start-issue-session.sh\` unless comments were disabled
- Triage comment: TBD
- Question comment: TBD
- Work-start comment: TBD
- Completion comment: TBD

## Implementation
- Files or areas: TBD
- Approach: TBD
- Risks: TBD

## Validation
- Commands: TBD
- Results: TBD
- Human validation: TBD

## Session Merge
- Merged into session branch: no
- Session validation impact: TBD

## Closeout
- Final issue status: TBD
- Follow-up: TBD
EOF
  fi

  printf '| [#%s](%s) | %s | %s | `%s` | no | TBD | %s |\n' "$issue_number" "$url" "$state" "$workflow_status" "$issue_branch" "$import_action" >> "$session_dir/README.md"

  if [[ "$post_comments" -eq 1 ]]; then
    if [[ "$import_action" == "imported" ]]; then
      "$gh_bin" issue comment "$issue_ref" --body "Imported into issue session \`$session_slug\` on branch \`$session_branch\`. This report is queued for triage and verification; it is not being treated as confirmed until reproduction/current-code review is complete."
    fi
  fi
done

cat >> "$session_dir/README.md" <<EOF

## Session Branch Validation
- Commands: TBD
- Human validation: TBD
- Evidence: TBD

## GitHub Updates
- Import comments posted: $([[ "$post_comments" -eq 1 ]] && echo yes || echo no)
- Triage comments posted: TBD
- Completion comments posted: TBD
- Open questions: TBD

## Closeout
- Final status: TBD
- Final PR: TBD
- Issues closed: TBD
- Issues deferred: TBD
- Follow-up work: TBD
EOF

echo "Created issue session at $session_dir on $session_branch"
echo "Next: triage each issue, comment on GitHub, then create issue branches from $session_branch."

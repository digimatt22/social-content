#!/usr/bin/env bash
set -euo pipefail

dry_run=0
force=0
yes=0
init_git=0
target_dir="."
source_dir=""
project_name=""

usage() {
  cat <<'EOF'
Usage: scripts/install-harness.sh [options]

Install or update the DigiColony development harness in a project directory.

Options:
  --target DIR    Install or update the harness in DIR. Defaults to current directory.
  --source DIR    Use DIR as the harness source checkout. Defaults to this script's repo.
  --dry-run       Show what would change without writing files.
  --force         Allow overwriting locally modified protected harness files.
  --yes           Allow migration from very old harness installs missing core metadata.
  --init-git      Initialize Git in the target folder if it is not already a Git repo.
  --name NAME     Record the intended project name in the completion message.
  -h, --help      Show this help.
EOF
}

fail() {
  echo "Error: $*" >&2
  exit 1
}

read_json_string() {
  local file="$1"
  local key="$2"
  if [[ -f "$file" ]]; then
    sed -n "s/.*\"$key\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" "$file" | head -1
  fi
}

project_owned_file() {
  case "$1" in
    README.md) return 0 ;;
    .harness/version.json) return 0 ;;
    docs/PROJECT_CONTEXT.md) return 0 ;;
    docs/ARCHITECTURE.md) return 0 ;;
    docs/AUTOMATIONS.md) return 0 ;;
    docs/VALIDATION.md) return 0 ;;
    docs/REPO_MAP.md) return 0 ;;
    docs/REFERENCES.md) return 0 ;;
    docs/PROJECT_OVERRIDES.md) return 0 ;;
    docs/REPOSITORY_HEALTH.md) return 0 ;;
    docs/exec-plans/*) return 0 ;;
    docs/issue-sessions/*) return 0 ;;
    Inbox/*) return 0 ;;
    *) return 1 ;;
  esac
}

skip_source_file() {
  case "$1" in
    .git/*) return 0 ;;
    .harness/version.json) return 0 ;;
    docs/exec-plans/active/*.md) return 0 ;;
    docs/exec-plans/completed/*.md) return 0 ;;
    docs/issue-sessions/*) return 0 ;;
    *) return 1 ;;
  esac
}

copy_file() {
  local source_file="$1"
  local target_file="$2"

  if [[ "$dry_run" -eq 0 ]]; then
    mkdir -p "$(dirname "$target_file")"
    cp -p "$source_file" "$target_file"
  fi
}

same_file_content() {
  local left="$1"
  local right="$2"
  [[ -f "$left" && -f "$right" ]] && cmp -s "$left" "$right"
}

target_has_git_changes() {
  local target_root="$1"
  local path="$2"

  if [[ -d "$target_root/.git" ]]; then
    [[ -n "$(git -C "$target_root" status --porcelain -- "$path")" ]]
  else
    return 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      target_dir="${2:-}"
      [[ -n "$target_dir" ]] || fail "--target requires a value"
      shift 2
      ;;
    --source)
      source_dir="${2:-}"
      [[ -n "$source_dir" ]] || fail "--source requires a value"
      shift 2
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    --force)
      force=1
      shift
      ;;
    --yes)
      yes=1
      shift
      ;;
    --init-git)
      init_git=1
      shift
      ;;
    --name)
      project_name="${2:-}"
      [[ -n "$project_name" ]] || fail "--name requires a value"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unexpected argument: $1"
      ;;
  esac
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "$source_dir" ]]; then
  source_dir="$(cd "$script_dir/.." && pwd)"
fi

[[ -d "$source_dir" ]] || fail "Harness source does not exist: $source_dir"
[[ -f "$source_dir/.harness/core-files.txt" ]] || fail "Source does not contain .harness/core-files.txt"
[[ -f "$source_dir/.harness/version.template.json" ]] || fail "Source does not contain .harness/version.template.json"

if [[ "$dry_run" -eq 0 ]]; then
  mkdir -p "$target_dir"
fi

if [[ -d "$target_dir" ]]; then
  target_abs="$(cd "$target_dir" && pwd)"
else
  case "$target_dir" in
    /*) target_abs="$target_dir" ;;
    *) target_abs="$(pwd)/$target_dir" ;;
  esac
fi

source_abs="$(cd "$source_dir" && pwd)"
case "$target_abs" in
  "$source_abs"|"$source_abs"/*)
    fail "Target must not be inside the harness source checkout: $target_abs"
    ;;
esac

source_commit="unknown"
if [[ -d "$source_abs/.git" ]]; then
  source_commit="$(git -C "$source_abs" rev-parse HEAD)"
fi
source_version="$(read_json_string "$source_abs/.harness/version.template.json" "version")"
source_upstream="$(read_json_string "$source_abs/.harness/version.template.json" "upstream")"
previous_version="$(read_json_string "$target_abs/.harness/version.json" "version")"
previous_commit="$(read_json_string "$target_abs/.harness/version.json" "sourceCommit")"
imported_at="$(date +%F)"

echo "Source: $source_abs"
echo "Source commit: $source_commit"
echo "Source version: ${source_version:-unknown}"
echo "Target: $target_abs"
if [[ -n "$previous_version" || -n "$previous_commit" ]]; then
  echo "Installed version: ${previous_version:-unknown}"
  echo "Installed source commit: ${previous_commit:-unknown}"
fi
if [[ -n "$project_name" ]]; then
  echo "Project name: $project_name"
fi
if [[ "$dry_run" -eq 1 ]]; then
  echo "Mode: dry run"
fi

if [[ -d "$target_abs/.harness" && ! -f "$target_abs/.harness/core-files.txt" && "$force" -eq 0 && "$yes" -eq 0 && "$dry_run" -eq 0 ]]; then
  fail "Target looks like an older harness install but lacks .harness/core-files.txt. Rerun with --yes after reviewing the dry run, or --force to accept overwrite risk."
fi
if [[ -d "$target_abs/.harness" && ! -f "$target_abs/.harness/core-files.txt" && "$dry_run" -eq 1 ]]; then
  echo "Older harness metadata detected: .harness/core-files.txt is missing"
  echo "Dry run will use the upstream managed-file allowlist. Rerun with --yes after review to migrate."
fi

if [[ "$force" -eq 0 && -d "$target_abs/.git" ]]; then
  blocked=0
  while IFS= read -r path; do
    case "$path" in
      ""|\#*) continue ;;
    esac

    if [[ -e "$target_abs/$path" ]] && target_has_git_changes "$target_abs" "$path" && ! same_file_content "$source_abs/$path" "$target_abs/$path"; then
      echo "Protected harness file has local changes: $path"
      blocked=1
    fi
  done < "$source_abs/.harness/core-files.txt"

  if [[ "$blocked" -ne 0 ]]; then
    fail "Move project-specific changes to docs/PROJECT_OVERRIDES.md or rerun with --force after review."
  fi
fi

changed=0
while IFS= read -r path; do
  case "$path" in
    ""|\#*) continue ;;
  esac

  if [[ ! -e "$source_abs/$path" ]]; then
    echo "Skipping missing source path: $path"
    continue
  fi

  if same_file_content "$source_abs/$path" "$target_abs/$path"; then
    echo "Current $path"
    continue
  fi

  echo "Sync $path"
  copy_file "$source_abs/$path" "$target_abs/$path"
  changed=1
done < "$source_abs/.harness/core-files.txt"

if [[ -d "$source_abs/.git" ]]; then
  source_files="$(git -C "$source_abs" ls-files)"
else
  source_files="$(cd "$source_abs" && find . -type f | sed 's#^\./##')"
fi

for required_file in scripts/install-harness.sh scripts/bootstrap-install.sh; do
  if [[ -f "$source_abs/$required_file" ]] && ! printf '%s\n' "$source_files" | grep -qx "$required_file"; then
    source_files="${source_files}"$'\n'"$required_file"
  fi
done

while IFS= read -r path; do
  [[ -n "$path" ]] || continue
  if skip_source_file "$path"; then
    continue
  fi
  if ! project_owned_file "$path"; then
    continue
  fi
  if [[ -e "$target_abs/$path" ]]; then
    continue
  fi

  echo "Create missing project-owned starter $path"
  copy_file "$source_abs/$path" "$target_abs/$path"
  changed=1
done <<< "$source_files"

if [[ "$dry_run" -eq 0 ]]; then
  mkdir -p "$target_abs/.harness"
  cat > "$target_abs/.harness/version.json" <<EOF
{
  "schema": 1,
  "name": "DigiColony Harness",
  "upstream": "${source_upstream:-git@github.com:MATT-Agent/DigiColony-Harness.git}",
  "version": "${source_version:-unknown}",
  "sourceCommit": "$source_commit",
  "importedAt": "$imported_at",
  "previousVersion": "${previous_version:-none}",
  "previousSourceCommit": "${previous_commit:-none}",
  "localDeviations": []
}
EOF

  mkdir -p "$target_abs/docs/exec-plans/active" "$target_abs/docs/exec-plans/completed"
  touch "$target_abs/docs/exec-plans/active/.gitkeep" "$target_abs/docs/exec-plans/completed/.gitkeep"

  if compgen -G "$target_abs/scripts/*.sh" >/dev/null; then
    chmod +x "$target_abs"/scripts/*.sh
  fi

  if [[ "$init_git" -eq 1 && ! -d "$target_abs/.git" ]]; then
    if ! git -C "$target_abs" init -b main >/dev/null 2>&1; then
      git -C "$target_abs" init
      git -C "$target_abs" branch -M main
    fi
  fi
fi

if [[ "$dry_run" -eq 1 ]]; then
  echo "Dry run complete"
elif [[ "$changed" -eq 0 && "${previous_version:-}" == "${source_version:-}" && "${previous_commit:-}" == "$source_commit" ]]; then
  echo "Harness already current"
else
  echo "Harness install/update complete at $target_abs"
  echo "Next: run project intake if this is a new project, or review the harness sync diff before committing."
  echo "For new projects, use lifeOS project_harness context, propose registration if missing, and record any CTX review key in docs/PROJECT_CONTEXT.md."
fi

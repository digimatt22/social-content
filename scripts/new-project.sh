#!/usr/bin/env bash
set -euo pipefail

dry_run=0
init_git=0
force=0
project_name=""
target_dir=""

usage() {
  cat <<'EOF'
Usage: scripts/new-project.sh [--dry-run] [--init-git] [--force] [--name "Project Name"] <target-dir>

Create a new project folder from this development harness.

Options:
  --dry-run       Show what would be copied without writing files.
  --init-git      Initialize Git in the target folder after copying.
  --force         Allow installing into a non-empty target folder.
  --name NAME     Record the intended project name in the completion message.
  -h, --help      Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      dry_run=1
      shift
      ;;
    --init-git)
      init_git=1
      shift
      ;;
    --force)
      force=1
      shift
      ;;
    --name)
      project_name="${2:-}"
      if [[ -z "$project_name" ]]; then
        echo "--name requires a value" >&2
        exit 1
      fi
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ -n "$target_dir" ]]; then
        echo "Unexpected argument: $1" >&2
        usage
        exit 1
      fi
      target_dir="$1"
      shift
      ;;
  esac
done

if [[ -z "$target_dir" ]]; then
  usage
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_dir="$(cd "$script_dir/.." && pwd)"

if [[ ! -x "$source_dir/scripts/install-harness.sh" ]]; then
  echo "Could not locate scripts/install-harness.sh from $script_dir" >&2
  exit 1
fi

target_parent="$(dirname "$target_dir")"
target_name="$(basename "$target_dir")"

if [[ "$dry_run" -eq 0 ]]; then
  mkdir -p "$target_parent"
fi

if [[ -d "$target_parent" ]]; then
  target_parent_abs="$(cd "$target_parent" && pwd)"
else
  case "$target_parent" in
    /*) target_parent_abs="$target_parent" ;;
    *) target_parent_abs="$(pwd)/$target_parent" ;;
  esac
fi

target_abs="$target_parent_abs/$target_name"

if [[ -e "$target_abs" && ! -d "$target_abs" ]]; then
  echo "Target exists and is not a directory: $target_abs" >&2
  exit 1
fi

if [[ -d "$target_abs" && "$force" -eq 0 ]]; then
  if find "$target_abs" -mindepth 1 -maxdepth 1 | read -r _; then
    echo "Target directory is not empty: $target_abs" >&2
    echo "Use --force only after reviewing existing contents." >&2
    exit 1
  fi
fi

installer_args=(--source "$source_dir" --target "$target_abs")
if [[ "$dry_run" -eq 1 ]]; then
  installer_args+=(--dry-run)
fi
if [[ "$force" -eq 1 ]]; then
  installer_args+=(--force)
fi
if [[ "$init_git" -eq 1 ]]; then
  installer_args+=(--init-git)
fi
if [[ -n "$project_name" ]]; then
  installer_args+=(--name "$project_name")
fi

"$source_dir/scripts/install-harness.sh" "${installer_args[@]}"

if [[ "$dry_run" -eq 1 ]]; then
  echo "New project dry run complete"
else
  echo "New project harness created at $target_abs"
  echo "Next: from that folder, run project intake and update README.md plus docs/PROJECT_CONTEXT.md."
  if [[ -n "$project_name" ]]; then
    echo "Suggested prompt: Use lifeOS project_harness context for \"$project_name\", then run project intake. If lifeOS does not know it, infer details from this repo, propose project registration for review, and record any CTX key in docs/PROJECT_CONTEXT.md."
  else
    echo "Suggested prompt: Use lifeOS project_harness context, then run project intake. If lifeOS does not know it, infer details from this repo, propose project registration for review, and record any CTX key in docs/PROJECT_CONTEXT.md."
  fi
fi

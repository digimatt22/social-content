#!/usr/bin/env bash
set -euo pipefail

repo_url="git@github.com:MATT-Agent/DigiColony-Harness.git"
source_dir=""
ref=""
installer_args=("--target" ".")

usage() {
  cat <<'EOF'
Usage: scripts/update-harness.sh [options] [source-checkout]

Update the current project from the upstream DigiColony development harness.

Options:
  --dry-run       Show what would change without writing files.
  --force         Allow overwriting locally modified protected harness files.
  --yes           Allow migration from very old harness installs missing core metadata.
  --ref REF       Clone a specific branch, tag, or commit when no source checkout is passed.
  -h, --help      Show this help.

If source-checkout is omitted, the script clones:
  git@github.com:MATT-Agent/DigiColony-Harness.git
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run|--force|--yes)
      installer_args+=("$1")
      shift
      ;;
    --ref)
      ref="${2:-}"
      if [[ -z "$ref" ]]; then
        echo "--ref requires a value" >&2
        exit 1
      fi
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ -n "$source_dir" ]]; then
        echo "Unexpected argument: $1" >&2
        usage
        exit 1
      fi
      source_dir="$1"
      shift
      ;;
  esac
done

if [[ -n "$source_dir" ]]; then
  if [[ ! -x "$source_dir/scripts/install-harness.sh" ]]; then
    echo "Source checkout does not contain scripts/install-harness.sh: $source_dir" >&2
    exit 1
  fi
  "$source_dir/scripts/install-harness.sh" --source "$source_dir" "${installer_args[@]}"
  exit 0
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is required to update the DigiColony harness" >&2
  exit 1
fi

tmp="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp"
}
trap cleanup EXIT

if [[ -n "$ref" ]]; then
  git clone --depth 1 --branch "$ref" "$repo_url" "$tmp"
else
  git clone --depth 1 "$repo_url" "$tmp"
fi

"$tmp/scripts/install-harness.sh" "${installer_args[@]}"

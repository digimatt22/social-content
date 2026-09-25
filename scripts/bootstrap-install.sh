#!/usr/bin/env bash
set -euo pipefail

repo_url="${DIGICOLONY_HARNESS_REPO_URL:-git@github.com:MATT-Agent/DigiColony-Harness.git}"
ref=""

usage() {
  cat <<'EOF'
Usage: bootstrap-install.sh [installer options]

Bootstrap the DigiColony development harness from the private GitHub repo.

Common examples:
  curl -fsSL https://harness.digicolony.com/install | bash
  curl -fsSL https://harness.digicolony.com/install | bash -s -- --target /path/to/project

Options handled by the bootstrapper:
  --ref REF       Clone a specific branch, tag, or commit before running the installer.
  -h, --help      Show this help.

All other options are passed through to scripts/install-harness.sh.
EOF
}

installer_args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
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
      installer_args+=("$1")
      shift
      ;;
  esac
done

if ! command -v git >/dev/null 2>&1; then
  echo "git is required to install the DigiColony harness" >&2
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

if [[ "${#installer_args[@]}" -eq 0 ]]; then
  "$tmp/scripts/install-harness.sh"
else
  "$tmp/scripts/install-harness.sh" "${installer_args[@]}"
fi

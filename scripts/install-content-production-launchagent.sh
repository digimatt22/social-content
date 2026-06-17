#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.mattmademe.marketing-os.content-production"
SOURCE_PLIST="$ROOT_DIR/docs/automation/$LABEL.plist"
TARGET_DIR="$HOME/Library/LaunchAgents"
TARGET_PLIST="$TARGET_DIR/$LABEL.plist"
ACTION="${1:-install}"

run() {
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    printf '[dry-run] %q' "$1"
    shift
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

unload_existing() {
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    printf '[dry-run] launchctl unload %q || true\n' "$TARGET_PLIST"
  else
    launchctl unload "$TARGET_PLIST" 2>/dev/null || true
  fi
}

report() {
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "Would $1"
  else
    echo "$1"
  fi
}

if [[ "$ACTION" == "--dry-run" ]]; then
  DRY_RUN=1
  ACTION="${2:-install}"
fi

case "$ACTION" in
  install)
    run mkdir -p "$ROOT_DIR/data/logs" "$TARGET_DIR"
    run cp "$SOURCE_PLIST" "$TARGET_PLIST"
    unload_existing
    run launchctl load "$TARGET_PLIST"
    report "install $LABEL from $TARGET_PLIST"
    ;;
  uninstall)
    unload_existing
    run rm -f "$TARGET_PLIST"
    report "uninstall $LABEL"
    ;;
  status)
    launchctl list | grep "$LABEL" || true
    ;;
  *)
    echo "Usage: $0 [--dry-run] [install|uninstall|status]" >&2
    exit 2
    ;;
esac

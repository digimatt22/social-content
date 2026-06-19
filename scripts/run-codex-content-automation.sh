#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${MARKETING_OS_LOG_DIR:-$ROOT_DIR/data/logs}"
OUTPUT_DIR="${MARKETING_OS_CODEX_AUTOMATION_DIR:-$ROOT_DIR/data/exports/content-automation}"
LIMIT="${MARKETING_OS_CONTENT_LIMIT:-10}"
DAYS_AHEAD="${MARKETING_OS_CONTENT_DAYS_AHEAD:-14}"

mkdir -p "$LOG_DIR" "$OUTPUT_DIR"
cd "$ROOT_DIR"

{
  echo "== $(date '+%Y-%m-%d %H:%M:%S %z') codex content automation prepare start =="
  python -m marketing_os.jobs.content_automation \
    --limit "$LIMIT" \
    --days-ahead "$DAYS_AHEAD" \
    --output-dir "$OUTPUT_DIR" \
    "$@"
  echo "== $(date '+%Y-%m-%d %H:%M:%S %z') codex content automation prepare complete =="
} >> "$LOG_DIR/codex-content-automation.log" 2>&1

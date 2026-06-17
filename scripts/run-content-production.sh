#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${MARKETING_OS_LOG_DIR:-$ROOT_DIR/data/logs}"
BRIEF_DIR="${MARKETING_OS_CONTENT_BRIEF_DIR:-$ROOT_DIR/data/exports/content-briefs}"
LIMIT="${MARKETING_OS_CONTENT_LIMIT:-10}"
DAYS_AHEAD="${MARKETING_OS_CONTENT_DAYS_AHEAD:-14}"

mkdir -p "$LOG_DIR" "$BRIEF_DIR"
cd "$ROOT_DIR"

{
  echo "== $(date '+%Y-%m-%d %H:%M:%S %z') content production start =="
  python -m marketing_os.jobs.content_production \
    --limit "$LIMIT" \
    --days-ahead "$DAYS_AHEAD" \
    --export-briefs-dir "$BRIEF_DIR" \
    "$@"
  echo "== $(date '+%Y-%m-%d %H:%M:%S %z') content production complete =="
} >> "$LOG_DIR/content-production.log" 2>&1

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${MARKETING_OS_LOG_DIR:-$ROOT_DIR/data/logs}"
OUTPUT_DIR="${MARKETING_OS_WEEKLY_SOCIAL_PLAN_DIR:-$ROOT_DIR/data/exports/weekly-social-plans}"
SLOTS="${MARKETING_OS_WEEKLY_SOCIAL_SLOTS:-7}"
LOOKBACK_DAYS="${MARKETING_OS_SALES_LOOKBACK_DAYS:-90}"

mkdir -p "$LOG_DIR" "$OUTPUT_DIR"
cd "$ROOT_DIR"

{
  echo "== $(date '+%Y-%m-%d %H:%M:%S %z') weekly social planner start =="
  python -m marketing_os.jobs.weekly_social_planner \
    --output-dir "$OUTPUT_DIR" \
    --slots "$SLOTS" \
    --sales-lookback-days "$LOOKBACK_DAYS" \
    "$@"
  echo "== $(date '+%Y-%m-%d %H:%M:%S %z') weekly social planner complete =="
} >> "$LOG_DIR/weekly-social-planner.log" 2>&1

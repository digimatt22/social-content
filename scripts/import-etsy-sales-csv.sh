#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /path/to/etsy-sales.csv [extra job args...]" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${MARKETING_OS_LOG_DIR:-$ROOT_DIR/data/logs}"
CSV_PATH="$1"
shift

mkdir -p "$LOG_DIR"
cd "$ROOT_DIR"

{
  echo "== $(date '+%Y-%m-%d %H:%M:%S %z') Etsy sales CSV import start =="
  python -m marketing_os.jobs.import_etsy_sales_csv "$CSV_PATH" "$@"
  echo "== $(date '+%Y-%m-%d %H:%M:%S %z') Etsy sales CSV import complete =="
} >> "$LOG_DIR/etsy-sales-csv-import.log" 2>&1

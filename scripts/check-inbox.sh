#!/usr/bin/env bash
set -euo pipefail

inbox_dir="${1:-Inbox}"
index="$inbox_dir/README.md"
failed=0

if [[ ! -d "$inbox_dir" ]]; then
  echo "Inbox directory not found: $inbox_dir"
  exit 1
fi

if [[ ! -f "$index" ]]; then
  echo "Inbox index not found: $index"
  exit 1
fi

while IFS= read -r item; do
  rel="${item#./}"
  case "$rel" in
    "$index") continue ;;
  esac

  if ! grep -Fq "$rel" "$index" && ! grep -Fq "$rel/" "$index"; then
    echo "Top-level inbox item is missing from index: $rel"
    failed=1
  fi
done < <(find "$inbox_dir" -mindepth 1 -maxdepth 1 | sort)

while IFS='|' read -r _ path _; do
  path="$(printf '%s' "$path" | sed 's/^ *//; s/ *$//')"
  case "$path" in
    ""|"Path"|"---"|"TBD") continue ;;
  esac

  if [[ ! -e "$path" ]]; then
    echo "Indexed inbox path does not exist: $path"
    failed=1
  fi
done < "$index"

if [[ "$failed" -ne 0 ]]; then
  exit 1
fi

echo "Inbox check passed"

#!/usr/bin/env bash
set -euo pipefail

root="${1:-.}"
failed=0

while IFS= read -r file; do
  while IFS= read -r target; do
    case "$target" in
      http://*|https://*|mailto:*|"") continue ;;
      \#*) continue ;;
    esac

    path="${target%%#*}"
    path="${path%%:*}"
    path="${path#<}"
    path="${path%>}"

    if [[ "$path" = /* ]]; then
      echo "Absolute local link in $file: $target"
      failed=1
      continue
    fi

    base="$(dirname "$file")"
    if [[ "$path" == */* ]]; then
      candidate="$root/$path"
    else
      candidate="$base/$path"
    fi

    if [[ ! -e "$candidate" ]]; then
      echo "Broken link in $file: $target"
      failed=1
    fi
  done < <(awk '
    /^```/ { fenced = !fenced; next }
    !fenced { print }
  ' "$file" | grep -Eo '\[[^]]+\]\([^)]+\)' | sed -E 's/^.*\]\(([^)]+)\)$/\1/' || true)
done < <(find "$root" -name '*.md' -type f | sort)

if [[ "$failed" -ne 0 ]]; then
  exit 1
fi

echo "Markdown link check passed"

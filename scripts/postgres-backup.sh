#!/usr/bin/env bash
set -euo pipefail

backup_root="${1:-}"
if [[ -z "$backup_root" ]]; then
  echo "Usage: $0 BACKUP_DIRECTORY" >&2
  exit 2
fi
if [[ -z "${MARKETING_OS_DB_URL:-}" ]]; then
  echo "MARKETING_OS_DB_URL is required." >&2
  exit 2
fi
if [[ -z "${MARKETING_OS_BACKUP_AGE_RECIPIENT:-}" ]]; then
  echo "MARKETING_OS_BACKUP_AGE_RECIPIENT is required; plaintext production backups are refused." >&2
  exit 2
fi
command -v pg_dump >/dev/null
command -v age >/dev/null

mkdir -p "$backup_root"
umask 077
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
temporary_dump="$(mktemp "${TMPDIR:-/tmp}/marketing-os-${timestamp}.XXXXXX.dump")"
encrypted_dump="$backup_root/marketing-os-${timestamp}.dump.age"
trap 'rm -f "$temporary_dump"' EXIT

pg_dump --format=custom --no-owner --no-acl --file="$temporary_dump" "$MARKETING_OS_DB_URL"
age --recipient "$MARKETING_OS_BACKUP_AGE_RECIPIENT" --output "$encrypted_dump" "$temporary_dump"
shasum -a 256 "$encrypted_dump" > "$encrypted_dump.sha256"
echo "$encrypted_dump"

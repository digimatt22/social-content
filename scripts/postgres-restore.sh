#!/usr/bin/env bash
set -euo pipefail

encrypted_dump="${1:-}"
restore_url="${2:-}"
if [[ -z "$encrypted_dump" || -z "$restore_url" ]]; then
  echo "Usage: $0 ENCRYPTED_DUMP_AGE RESTORE_DATABASE_URL" >&2
  exit 2
fi
if [[ "${MARKETING_OS_RESTORE_TARGET_CLASS:-}" != "disposable" && "${MARKETING_OS_RESTORE_TARGET_CLASS:-}" != "authority" ]]; then
  echo "Set MARKETING_OS_RESTORE_TARGET_CLASS=disposable or authority; restore is refused by default." >&2
  exit 3
fi
command -v age >/dev/null
command -v pg_restore >/dev/null
command -v psql >/dev/null

checksum_file="$encrypted_dump.sha256"
if [[ ! -f "$checksum_file" ]]; then
  echo "Missing checksum file: $checksum_file" >&2
  exit 3
fi
shasum -a 256 -c "$checksum_file"

target_identity="$(psql "$restore_url" -Atc "SELECT current_database() || '|' || COALESCE(inet_server_addr()::text, 'local') || '|' || inet_server_port()")"
authority_identity=""
if [[ -n "${MARKETING_OS_DB_URL:-}" ]]; then
  authority_identity="$(psql "$MARKETING_OS_DB_URL" -Atc "SELECT current_database() || '|' || COALESCE(inet_server_addr()::text, 'local') || '|' || inet_server_port()")"
fi
if [[ "$target_identity" == "$authority_identity" || "${MARKETING_OS_RESTORE_TARGET_CLASS}" == "authority" ]]; then
  if [[ "${MARKETING_OS_ALLOW_AUTHORITY_RESTORE:-}" != "YES_I_ACCEPT_DATA_LOSS" ]]; then
    echo "Authority restore requires MARKETING_OS_ALLOW_AUTHORITY_RESTORE=YES_I_ACCEPT_DATA_LOSS." >&2
    exit 3
  fi
elif [[ "${MARKETING_OS_RESTORE_TARGET_CLASS}" != "disposable" ]]; then
  echo "Non-authority targets must be explicitly attested as disposable." >&2
  exit 3
fi

temporary_dump="$(mktemp "${TMPDIR:-/tmp}/marketing-os-restore.XXXXXX.dump")"
trap 'rm -f "$temporary_dump"' EXIT
age --decrypt --output "$temporary_dump" "$encrypted_dump"
pg_restore --clean --if-exists --no-owner --no-acl --dbname="$restore_url" "$temporary_dump"
echo "Restore completed; run migration and relationship verification before cutover."

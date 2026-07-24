#!/usr/bin/env sh
set -eu

: "${MARKETING_OS_DB_BACKUP_URL:?MARKETING_OS_DB_BACKUP_URL is required}"

if [ "${SHELDON_BACKUP_OUTPUT:-}" != "-" ] ||
   [ "${SHELDON_BACKUP_PROTOCOL:-}" != "sheldon-envelope-v1" ]; then
  printf 'Sheldon backup envelope protocol is required\n' >&2
  exit 1
fi

evidence="$(scripts/sheldon-protected-rows.sh "$MARKETING_OS_DB_BACKUP_URL")"
schema_revision="$(printf '%s\n' "$evidence" | sed -n '1p')"
protected_rows="$(printf '%s\n' "$evidence" | sed -n '2p')"

metadata="$(
  SHELDON_SCHEMA_REVISION="$schema_revision" \
  SHELDON_PROTECTED_ROWS="$protected_rows" \
  python -c '
import base64
import json
import os

document = {
    "schema": 1,
    "schema_revision": os.environ["SHELDON_SCHEMA_REVISION"],
    "protected_rows": json.loads(os.environ["SHELDON_PROTECTED_ROWS"]),
}
print(base64.urlsafe_b64encode(
    json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
).decode().rstrip("="), end="")
'
)"

printf 'SHELDON-BACKUP-METADATA %s\n' "$metadata"
exec pg_dump "$MARKETING_OS_DB_BACKUP_URL" \
  --format=custom \
  --no-owner \
  --no-acl

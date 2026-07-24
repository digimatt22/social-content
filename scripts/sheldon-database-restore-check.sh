#!/usr/bin/env sh
set -eu

if [ "${SHELDON_BACKUP_INPUT:-}" != "-" ] ||
   [ "${SHELDON_RESTORE_RESULT:-}" != "-" ]; then
  printf 'Sheldon restore-check stream protocol is required\n' >&2
  exit 1
fi

restore_root="$(mktemp -d /tmp/marketing-os-restore-check.XXXXXX)"
database_dir="$restore_root/database"
socket_dir="$restore_root/socket"
backup_path="$restore_root/source.dump"
mkdir -p "$socket_dir"

pg_bindir="$(pg_config --bindir)"

cleanup() {
  if [ -s "$database_dir/postmaster.pid" ]; then
    "$pg_bindir/pg_ctl" -D "$database_dir" -m immediate stop >/dev/null 2>&1 || true
  fi
  rm -rf "$restore_root"
}
trap cleanup EXIT INT TERM

cat >"$backup_path"
pg_restore --list "$backup_path" >/dev/null

"$pg_bindir/initdb" --pgdata="$database_dir" --auth-local=trust --auth-host=reject >/dev/null
"$pg_bindir/pg_ctl" -D "$database_dir" \
  -o "-c listen_addresses='' -c unix_socket_directories='$socket_dir'" \
  -w start >/dev/null

database_user="$(id -un)"
createdb --host="$socket_dir" --username="$database_user" marketing_os
restore_url="postgresql:///marketing_os?host=$socket_dir"
pg_restore \
  --no-owner \
  --no-acl \
  --exit-on-error \
  --dbname="$restore_url" \
  "$backup_path"

evidence="$(scripts/sheldon-protected-rows.sh "$restore_url")"
schema_revision="$(printf '%s\n' "$evidence" | sed -n '1p')"
protected_rows="$(printf '%s\n' "$evidence" | sed -n '2p')"

SHELDON_SCHEMA_REVISION="$schema_revision" \
SHELDON_PROTECTED_ROWS="$protected_rows" \
python -c '
import json
import os

print(json.dumps({
    "schema": 1,
    "schema_revision": os.environ["SHELDON_SCHEMA_REVISION"],
    "protected_rows": json.loads(os.environ["SHELDON_PROTECTED_ROWS"]),
}, separators=(",", ":"), sort_keys=True))
'

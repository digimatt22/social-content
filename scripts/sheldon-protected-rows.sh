#!/usr/bin/env sh
set -eu

database_url="${1:?database URL is required}"

table_names="$(
  psql "$database_url" --no-psqlrc --tuples-only --no-align \
    --set ON_ERROR_STOP=1 <<'SQL'
SELECT tablename
  FROM pg_catalog.pg_tables
 WHERE schemaname = 'public'
 ORDER BY tablename;
SQL
)"

rows_json="{"
separator=""
for table_name in $table_names; do
  case "$table_name" in
    *[!a-z0-9_]*|'')
      printf 'unexpected public table name\n' >&2
      exit 1
      ;;
  esac
  table_count="$(
    psql "$database_url" --no-psqlrc --tuples-only --no-align \
      --set ON_ERROR_STOP=1 \
      --command "SELECT count(*)::bigint FROM \"$table_name\""
  )"
  rows_json="${rows_json}${separator}\"${table_name}\":${table_count}"
  separator=","
done
rows_json="${rows_json}}"

schema_revision="$(
  psql "$database_url" --no-psqlrc --tuples-only --no-align \
    --set ON_ERROR_STOP=1 \
    --command "SELECT version_num FROM alembic_version LIMIT 1"
)"

if [ -z "$schema_revision" ]; then
  printf 'Alembic migration ledger is empty\n' >&2
  exit 1
fi

printf '%s\n%s\n' "$schema_revision" "$rows_json"

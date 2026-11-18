#!/usr/bin/env sh
set -eu

database_url="${1:?database URL is required}"

table_names="$(
  psql "$database_url" --no-psqlrc --tuples-only --no-align \
    --set ON_ERROR_STOP=1 <<'SQL'
SELECT CASE WHEN schemaname = 'public' THEN tablename ELSE schemaname || '.' || tablename END
  FROM pg_catalog.pg_tables
 WHERE schemaname IN ('public', 'social_studio')
 ORDER BY schemaname, tablename;
SQL
)"

rows_json="{"
separator=""
for table_name in $table_names; do
  case "$table_name" in
    *[!a-z0-9_.]*|'')
      printf 'unexpected protected table name\n' >&2
      exit 1
      ;;
  esac
  case "$table_name" in
    social_studio.*) table_identifier="social_studio.\"${table_name#social_studio.}\"" ;;
    *.*) printf 'unexpected protected schema\n' >&2; exit 1 ;;
    *) table_identifier="public.\"$table_name\"" ;;
  esac
  table_count="$(
    psql "$database_url" --no-psqlrc --tuples-only --no-align \
      --set ON_ERROR_STOP=1 \
      --command "SELECT count(*)::bigint FROM $table_identifier"
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

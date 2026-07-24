#!/usr/bin/env sh
set -eu

: "${MARKETING_OS_DB_URL:?MARKETING_OS_DB_URL is required}"

observed="$(
  psql "$MARKETING_OS_DB_URL" --no-psqlrc --tuples-only --no-align \
    --set ON_ERROR_STOP=1 <<'SQL'
SELECT current_database(),
       current_user,
       current_setting('server_version_num'),
       (SELECT rolconnlimit::text
          FROM pg_roles
         WHERE rolname = 'marketing_os_runtime'),
       (SELECT count(*)::text
          FROM pg_roles
         WHERE rolname = 'marketing_os_migrator'
           AND NOT rolsuper
           AND NOT rolcreatedb
           AND NOT rolcreaterole),
       (SELECT version_num FROM alembic_version LIMIT 1);
SQL
)"

IFS='|' read -r database_name runtime_role version_number connection_limit migration_roles schema_revision <<EOF
$observed
EOF

if [ "$database_name" != "marketing_os" ] ||
   [ "$runtime_role" != "marketing_os_runtime" ] ||
   [ "$version_number" != "170010" ] ||
   [ "$connection_limit" != "20" ] ||
   [ "$migration_roles" != "1" ] ||
   [ "$schema_revision" != "0005_pinterest_control_plane" ]; then
  printf 'Marketing OS database readiness contract failed\n' >&2
  exit 1
fi

printf '%s\n' \
  '{"profile":"application-owned-postgresql","engine":"postgresql","version":"17.10","database":"marketing_os","runtime_role":"marketing_os_runtime","migration_role":"marketing_os_migrator","isolation_tier":"stateful-automation","connection_limit":20,"schema_revision":"0005_pinterest_control_plane","health":"healthy"}'

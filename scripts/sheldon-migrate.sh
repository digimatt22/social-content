#!/usr/bin/env sh
set -eu

: "${MARKETING_OS_DB_MIGRATION_URL:?MARKETING_OS_DB_MIGRATION_URL is required}"

export MARKETING_OS_DB_URL="$MARKETING_OS_DB_MIGRATION_URL"
exec alembic upgrade head

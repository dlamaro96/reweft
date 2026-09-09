#!/bin/sh
set -eu

psql --set ON_ERROR_STOP=1 \
  --set temporal_user="$TEMPORAL_DB_USER" \
  --set temporal_password="$TEMPORAL_DB_PASSWORD" \
  --set temporal_database="$TEMPORAL_DB_NAME" \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'temporal_user', :'temporal_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'temporal_user') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'temporal_database', :'temporal_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'temporal_database') \gexec
SQL


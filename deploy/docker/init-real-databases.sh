#!/bin/sh
set -eu

psql --set ON_ERROR_STOP=1 \
  --set app_user="$REWEFT_APP_DB_USER" \
  --set app_password="$REWEFT_APP_DB_PASSWORD" \
  --set app_database="$REWEFT_APP_DB_NAME" \
  --set temporal_user="$TEMPORAL_DB_USER" \
  --set temporal_password="$TEMPORAL_DB_PASSWORD" \
  --set temporal_database="$TEMPORAL_DB_NAME" \
  --set visibility_database="$TEMPORAL_VISIBILITY_DB_NAME" \
  --username "$POSTGRES_USER" --dbname postgres <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_user') \gexec
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'temporal_user', :'temporal_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'temporal_user') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'app_database', :'app_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'app_database') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'temporal_database', :'temporal_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'temporal_database') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'visibility_database', :'temporal_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'visibility_database') \gexec
SQL

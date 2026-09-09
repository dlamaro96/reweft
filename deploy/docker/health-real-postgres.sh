#!/bin/sh
set -eu

check_database() {
  database=$1
  user=$2
  password=$3
  PGPASSWORD=$password psql --host 127.0.0.1 --username "$user" --dbname "$database" \
    --set ON_ERROR_STOP=1 --tuples-only --no-align --command 'SELECT 1' | grep -qx 1
}

check_database "$REWEFT_APP_DB_NAME" "$REWEFT_APP_DB_USER" "$REWEFT_APP_DB_PASSWORD"
check_database "$TEMPORAL_DB_NAME" "$TEMPORAL_DB_USER" "$TEMPORAL_DB_PASSWORD"
check_database "$TEMPORAL_VISIBILITY_DB_NAME" "$TEMPORAL_DB_USER" "$TEMPORAL_DB_PASSWORD"

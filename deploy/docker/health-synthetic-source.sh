#!/bin/sh
set -eu

result=$(PGPASSWORD=$REWEFT_SOURCE_READER_PASSWORD psql \
  --host 127.0.0.1 \
  --username "$REWEFT_SOURCE_READER_USER" \
  --dbname "$POSTGRES_DB" \
  --set ON_ERROR_STOP=1 \
  --tuples-only --no-align \
  --command "SELECT to_regclass('$REWEFT_SOURCE_SCHEMA.work_orders') IS NOT NULL AND to_regclass('$REWEFT_SOURCE_SCHEMA.adjusted_revenue') IS NOT NULL")
[ "$result" = "t" ]

#!/usr/bin/env sh
set -eu

repo_dir=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_dir"
umask 077

for command_name in docker curl openssl awk; do
  command -v "$command_name" >/dev/null 2>&1 || { echo "$command_name is required for the real runtime." >&2; exit 1; }
done
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is required." >&2; exit 1; }

runtime_env=${REWEFT_REAL_ENV_FILE:-.data/real-runtime.env}
key_dir=.secrets/real-runtime
mkdir -p "$(dirname "$runtime_env")" "$key_dir"
chmod 700 "$key_dir"
if [ ! -f "$runtime_env" ]; then
  cp deploy/examples/real-runtime.env.example "$runtime_env"
fi
chmod 600 "$runtime_env"

generate_secret() { openssl rand -hex 32; }
set_if_empty() {
  key=$1
  value=$2
  if ! grep -Eq "^${key}=.+" "$runtime_env"; then
    temporary_file="${runtime_env}.tmp.$$"
    awk -v key="$key" -v value="$value" '
      BEGIN { FS=OFS="=" }
      $1==key { $0=key OFS value; found=1 }
      { print }
      END { if (!found) print key OFS value }
    ' "$runtime_env" > "$temporary_file"
    chmod 600 "$temporary_file"
    mv "$temporary_file" "$runtime_env"
  fi
}

set_if_empty REWEFT_SECRET_KEY "$(generate_secret)"
set_if_empty REWEFT_BOOTSTRAP_TOKEN "$(generate_secret)"
set_if_empty REWEFT_COLLECTOR_SERVICE_TOKEN "$(generate_secret)"
set_if_empty REWEFT_ANALYSIS_SERVICE_TOKEN "$(generate_secret)"
set_if_empty POSTGRES_PASSWORD "$(generate_secret)"
set_if_empty DATABASE_URL "postgresql://inactive:inactive@invalid/inactive"
set_if_empty REWEFT_DB_ADMIN_PASSWORD "$(generate_secret)"
set_if_empty REWEFT_APP_DB_PASSWORD "$(generate_secret)"
set_if_empty TEMPORAL_DB_PASSWORD "$(generate_secret)"
set_if_empty REWEFT_SOURCE_ADMIN_PASSWORD "$(generate_secret)"
set_if_empty REWEFT_SOURCE_READER_PASSWORD "$(generate_secret)"

env_value() {
  awk -F= -v key="$1" '$1==key {sub(/^[^=]*=/, ""); value=$0} END {print value}' "$runtime_env"
}
for key in REWEFT_DB_ADMIN_USER REWEFT_APP_DB_USER REWEFT_APP_DB_NAME TEMPORAL_DB_USER TEMPORAL_DB_NAME TEMPORAL_VISIBILITY_DB_NAME REWEFT_SOURCE_ADMIN_USER REWEFT_SOURCE_READER_USER REWEFT_SOURCE_DB_NAME REWEFT_SOURCE_SCHEMA; do
  value=$(env_value "$key")
  case "$value" in
    ""|[0-9]*|*[!A-Za-z0-9_]*)
      echo "$key must be a non-empty SQL identifier containing only letters, digits, and underscores, and it may not start with a digit." >&2
      exit 1
      ;;
  esac
done
port=$(env_value REWEFT_REAL_HTTP_PORT)
case "$port" in ""|*[!0-9]*) echo "REWEFT_REAL_HTTP_PORT must be an integer from 1 through 65535." >&2; exit 1;; esac
[ "$port" -ge 1 ] && [ "$port" -le 65535 ] || { echo "REWEFT_REAL_HTTP_PORT must be an integer from 1 through 65535." >&2; exit 1; }

private_key="$key_dir/permit-signing.pem"
public_key="$key_dir/permit-verification.pem"
if [ ! -f "$private_key" ]; then
  if [ -f "$public_key" ]; then
    echo "Permit public key exists without its private key. Refusing to rotate or replace either key automatically." >&2
    exit 1
  fi
  openssl genpkey -algorithm Ed25519 -out "$private_key"
  chmod 600 "$private_key"
fi
if [ ! -f "$public_key" ]; then
  openssl pkey -in "$private_key" -pubout -out "$public_key"
  chmod 644 "$public_key"
fi

docker compose --env-file "$runtime_env" --profile real-runtime config --quiet
# Explicit service targets avoid starting or replacing the independent demo path.
docker compose --env-file "$runtime_env" --profile real-runtime up --build --detach \
  real-postgres real-temporal synthetic-source-postgres deterministic-test-provider \
  real-api real-analysis-worker real-inference-worker real-collector real-gateway
REWEFT_REAL_ENV_FILE="$runtime_env" ./scripts/real-runtime-ready.sh

echo "Reweft real-runtime profile is ready at http://127.0.0.1:${port}"
echo "The inference endpoint is a deterministic synthetic CI provider; it performs no model inference."

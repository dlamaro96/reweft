#!/usr/bin/env sh
# shellcheck disable=SC2016 # Variables in single quotes expand inside the target container.
set -eu

repo_dir=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_dir"
runtime_env=${REWEFT_REAL_ENV_FILE:-.data/real-runtime.env}
backup_root=${1:-.data/backups}
case "$backup_root" in /*|*..*) echo "Backup directory must be a relative path without '..'." >&2; exit 2;; esac
test -f "$runtime_env" || { echo "Missing $runtime_env; real runtime is not configured." >&2; exit 1; }
REWEFT_REAL_ENV_FILE="$runtime_env" ./scripts/real-runtime-ready.sh >/dev/null

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
temporary="$backup_root/.partial-${timestamp}-$$"
destination="$backup_root/reweft-real-${timestamp}-$$"
mkdir -p "$temporary"
chmod 700 "$backup_root" "$temporary"

compose() { docker compose --env-file "$runtime_env" --profile real-runtime "$@"; }
restart_processors() {
  compose start real-temporal deterministic-test-provider real-api \
    real-analysis-worker real-inference-worker real-collector real-gateway >/dev/null
}
processors_stopped=0
restore_runtime_on_exit() {
  if [ "$processors_stopped" -eq 1 ]; then
    restart_processors || true
  fi
}
trap restore_runtime_on_exit EXIT
compose stop real-gateway real-api real-analysis-worker real-inference-worker real-collector real-temporal deterministic-test-provider >/dev/null
processors_stopped=1

compose exec -T real-postgres sh -c 'pg_dump --format=custom --no-acl --no-owner --username "$POSTGRES_USER" --dbname "$REWEFT_APP_DB_NAME"' > "$temporary/application.dump"
compose exec -T real-postgres sh -c 'pg_dump --format=custom --no-acl --no-owner --username "$POSTGRES_USER" --dbname "$TEMPORAL_DB_NAME"' > "$temporary/temporal.dump"
compose exec -T real-postgres sh -c 'pg_dump --format=custom --no-acl --no-owner --username "$POSTGRES_USER" --dbname "$TEMPORAL_VISIBILITY_DB_NAME"' > "$temporary/temporal-visibility.dump"
compose exec -T synthetic-source-postgres sh -c 'pg_dump --format=custom --no-owner --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"' > "$temporary/synthetic-source.dump"
docker run --rm --volume reweft_real_evidence:/data:ro --volume "$repo_dir/$temporary:/backup" alpine:3.22.1 tar -C /data -czf /backup/evidence.tar.gz .

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'; else shasum -a 256 "$1" | awk '{print $1}'; fi
}
for name in application.dump temporal.dump temporal-visibility.dump synthetic-source.dump evidence.tar.gz; do
  printf '%s  %s\n' "$(hash_file "$temporary/$name")" "$name" >> "$temporary/checksums.sha256"
done
revision=$(git rev-parse --verify HEAD 2>/dev/null || printf 'uncommitted')
printf '{"schema_version":"reweft.backup/v1","created_at":"%s","revision":"%s","includes":["application","temporal","temporal_visibility","synthetic_source","evidence"],"includes_secrets":false}\n' "$timestamp" "$revision" > "$temporary/manifest.json"
chmod 600 "$temporary"/*
mv "$temporary" "$destination"
restart_processors
processors_stopped=0
REWEFT_REAL_ENV_FILE="$runtime_env" ./scripts/real-runtime-ready.sh >/dev/null
echo "Backup created at $destination"
echo "Permit keys and environment secrets are intentionally excluded and must be protected separately."

#!/usr/bin/env sh
# shellcheck disable=SC2016 # Variables in single quotes expand inside the target container.
set -eu

repo_dir=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_dir"
runtime_env=${REWEFT_REAL_ENV_FILE:-.data/real-runtime.env}
backup=${1:-}
confirmation=${2:-}
if [ -z "$backup" ] || [ "$confirmation" != "--confirm-overwrite" ]; then
  echo "Usage: $0 BACKUP_DIRECTORY --confirm-overwrite" >&2
  echo "Restore replaces database schemas and overwrites same-named evidence files; volumes and configuration are not deleted." >&2
  exit 2
fi
case "$backup" in /*|*..*) echo "Backup directory must be a relative path without '..'." >&2; exit 2;; esac
test -f "$runtime_env" || { echo "Missing $runtime_env." >&2; exit 1; }
test -f "$backup/manifest.json" && test -f "$backup/checksums.sha256" || { echo "Backup manifest/checksums are missing." >&2; exit 1; }

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'; else shasum -a 256 "$1" | awk '{print $1}'; fi
}
for name in application.dump temporal.dump temporal-visibility.dump synthetic-source.dump evidence.tar.gz; do
  expected=$(awk -v name="$name" '$2==name {print $1}' "$backup/checksums.sha256")
  actual=$(hash_file "$backup/$name")
  [ -n "$expected" ] && [ "$expected" = "$actual" ] || { echo "Checksum mismatch: $name" >&2; exit 1; }
done

compose() { docker compose --env-file "$runtime_env" --profile real-runtime "$@"; }
restart_runtime() {
  compose up --detach \
    real-postgres real-temporal synthetic-source-postgres deterministic-test-provider \
    real-api real-analysis-worker real-inference-worker real-collector real-gateway >/dev/null
}
runtime_stopped=0
restore_runtime_on_exit() {
  if [ "$runtime_stopped" -eq 1 ]; then
    restart_runtime || true
  fi
}
trap restore_runtime_on_exit EXIT
compose stop real-gateway real-api real-analysis-worker real-inference-worker real-collector real-temporal deterministic-test-provider
runtime_stopped=1

compose exec -T real-postgres sh -c 'pg_restore --clean --if-exists --no-owner --role "$REWEFT_APP_DB_USER" --username "$POSTGRES_USER" --dbname "$REWEFT_APP_DB_NAME"' < "$backup/application.dump"
compose exec -T real-postgres sh -c 'pg_restore --clean --if-exists --no-owner --role "$TEMPORAL_DB_USER" --username "$POSTGRES_USER" --dbname "$TEMPORAL_DB_NAME"' < "$backup/temporal.dump"
compose exec -T real-postgres sh -c 'pg_restore --clean --if-exists --no-owner --role "$TEMPORAL_DB_USER" --username "$POSTGRES_USER" --dbname "$TEMPORAL_VISIBILITY_DB_NAME"' < "$backup/temporal-visibility.dump"
compose exec -T synthetic-source-postgres sh -c 'pg_restore --clean --if-exists --no-owner --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"' < "$backup/synthetic-source.dump"
docker run --rm --volume reweft_real_evidence:/data --volume "$repo_dir/$backup:/backup:ro" alpine:3.22.1 tar -C /data -xzf /backup/evidence.tar.gz

restart_runtime
runtime_stopped=0
REWEFT_REAL_ENV_FILE="$runtime_env" ./scripts/real-runtime-ready.sh
echo "Restore completed from $backup. Existing volume identities and runtime configuration were preserved."

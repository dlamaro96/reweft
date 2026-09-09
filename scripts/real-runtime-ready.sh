#!/usr/bin/env sh
set -eu

repo_dir=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_dir"
runtime_env=${REWEFT_REAL_ENV_FILE:-.data/real-runtime.env}
test -f "$runtime_env" || { echo "Missing $runtime_env; run scripts/bootstrap-real-runtime.sh first." >&2; exit 1; }

services="real-postgres real-temporal synthetic-source-postgres deterministic-test-provider real-api real-analysis-worker real-inference-worker real-collector real-gateway"
attempt=0
while :; do
  pending=""
  for service in $services; do
    container_id=$(docker compose --env-file "$runtime_env" --profile real-runtime ps -q "$service")
    if [ -z "$container_id" ]; then
      pending="$pending $service(absent)"
      continue
    fi
    state=$(docker inspect --format '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$container_id")
    [ "$state" = "running/healthy" ] || pending="$pending $service($state)"
  done
  [ -z "$pending" ] && break
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 90 ]; then
    echo "Real runtime did not become ready:$pending" >&2
    docker compose --env-file "$runtime_env" --profile real-runtime ps >&2
    exit 1
  fi
  sleep 2
done

port=$(awk -F= '$1=="REWEFT_REAL_HTTP_PORT" {print $2}' "$runtime_env")
port=${port:-8180}
health=$(curl --fail --silent --show-error "http://127.0.0.1:${port}/api/v1/health")
python3 -c 'import json,sys; body=json.loads(sys.argv[1]); assert body.get("status")=="ok" and body.get("persistence")=="postgresql", body' "$health"
echo "All real-runtime services report healthy and the gateway API health response is ok."

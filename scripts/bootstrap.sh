#!/usr/bin/env sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_dir"

mode=normal
if [ "${1:-}" = "--demo" ]; then mode=demo; elif [ "$#" -gt 0 ]; then
  echo "Usage: $0 [--demo]" >&2
  exit 2
fi

command -v docker >/dev/null 2>&1 || { echo "Docker is required. Install Docker Engine/Desktop with Compose v2." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is required ('docker compose')." >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "curl is required for the local readiness check." >&2; exit 1; }
command -v openssl >/dev/null 2>&1 || { echo "OpenSSL is required for local secret generation." >&2; exit 1; }

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
fi

generate_secret() {
  openssl rand -hex 32
}

set_if_empty() {
  key=$1
  value=$2
  if ! grep -Eq "^${key}=.+" .env; then
    tmp_file=".env.tmp.$$"
    awk -v key="$key" -v value="$value" 'BEGIN{FS=OFS="="} $1==key {$0=key OFS value} {print}' .env > "$tmp_file"
    chmod 600 "$tmp_file"
    mv "$tmp_file" .env
  fi
}

set_if_empty REWEFT_SECRET_KEY "$(generate_secret)"
set_if_empty POSTGRES_PASSWORD "$(generate_secret)"
set_if_empty TEMPORAL_DB_PASSWORD "$(generate_secret)"
if [ "$mode" = demo ]; then
  sed -i.bak 's/^REWEFT_MODE=.*/REWEFT_MODE=synthetic_demo/' .env && rm -f .env.bak
fi

docker compose --env-file .env config >/dev/null
docker compose --env-file .env up --build --detach

port=$(awk -F= '$1=="REWEFT_HTTP_PORT" {print $2}' .env)
port=${port:-8080}
i=0
until curl --fail --silent --show-error "http://127.0.0.1:${port}/api/v1/health" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 60 ]; then
    echo "Reweft did not become healthy. Inspect: docker compose logs api gateway" >&2
    exit 1
  fi
  sleep 2
done

echo "Reweft is available at http://127.0.0.1:${port}"
if [ "$mode" = demo ]; then echo "Mode: SYNTHETIC DEMONSTRATION — no live source or inference provider is used."; fi

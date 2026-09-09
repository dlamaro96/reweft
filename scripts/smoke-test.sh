#!/usr/bin/env sh
set -eu
port=${REWEFT_HTTP_PORT:-8080}
curl --fail --silent --show-error "http://127.0.0.1:${port}/api/v1/health" >/dev/null
curl --fail --silent --show-error "http://127.0.0.1:${port}/" >/dev/null
echo "Smoke test passed for http://127.0.0.1:${port}"


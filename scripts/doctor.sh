#!/usr/bin/env sh
set -eu
fail=0
for command_name in docker git curl openssl; do
  if command -v "$command_name" >/dev/null 2>&1; then echo "ok: $command_name"; else echo "missing: $command_name"; fail=1; fi
done
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then echo "ok: docker compose v2"; else echo "missing: docker compose v2"; fail=1; fi
exit "$fail"

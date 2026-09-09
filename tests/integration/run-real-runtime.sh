#!/usr/bin/env sh
# shellcheck disable=SC2016 # Variables in single quotes expand inside the target container.
set -eu

repo_dir=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$repo_dir"
command -v python3 >/dev/null 2>&1 || { echo "python3 is required by the integration harness." >&2; exit 1; }
runtime_env=${REWEFT_REAL_ENV_FILE:-.data/real-runtime.env}
REWEFT_REAL_ENV_FILE="$runtime_env" ./scripts/bootstrap-real-runtime.sh
compose() { docker compose --env-file "$runtime_env" --profile real-runtime "$@"; }

assert_no_published_port() {
  service=$1
  target=$2
  published=$(compose port "$service" "$target" 2>/dev/null || true)
  case "$published" in
    ""|:0|0.0.0.0:0|"[::]:0") ;;
    *) echo "$service unexpectedly publishes $target at $published" >&2; exit 1 ;;
  esac
}
assert_no_published_port real-postgres 5432
assert_no_published_port real-temporal 7233
assert_no_published_port synthetic-source-postgres 5432
assert_no_published_port deterministic-test-provider 8090

compose exec -T --user reweft real-api sh -c 'test -r /run/reweft-keys/permit-signing.pem && test ! -e /run/reweft-keys/permit-verification.pem && test ! -w /run/reweft-keys/permit-signing.pem'
compose exec -T real-collector sh -c 'test -r /run/reweft-keys/permit-verification.pem && test ! -e /run/reweft-keys/permit-signing.pem'
compose exec -T real-api sh -c 'test -n "$REWEFT_COLLECTOR_SERVICE_TOKEN" && test -n "$REWEFT_ANALYSIS_SERVICE_TOKEN"'
compose exec -T real-collector sh -c 'test -n "$REWEFT_COLLECTOR_SERVICE_TOKEN" && test -z "${REWEFT_ANALYSIS_SERVICE_TOKEN:-}"'
compose exec -T real-analysis-worker sh -c 'test -n "$REWEFT_ANALYSIS_SERVICE_TOKEN" && test -z "${REWEFT_COLLECTOR_SERVICE_TOKEN:-}"'
compose exec -T real-inference-worker sh -c 'test -z "${REWEFT_ANALYSIS_SERVICE_TOKEN:-}" && test -z "${REWEFT_COLLECTOR_SERVICE_TOKEN:-}"'
compose exec -T real-collector sh -c 'test -r /opt/reweft/artifacts/estate/manifest.yaml && test -r /opt/reweft/artifacts/estate-resolved/manifest.yaml && ! touch /opt/reweft/artifacts/estate/.write-test'

expect_dns_failure() {
  service=$1
  host=$2
  if compose exec -T "$service" python -c "import socket; socket.gethostbyname('$host')" >/dev/null 2>&1; then
    echo "$service unexpectedly resolves isolated host $host" >&2
    exit 1
  fi
}
expect_dns_failure real-api synthetic-source-postgres
expect_dns_failure real-api deterministic-test-provider
expect_dns_failure real-analysis-worker synthetic-source-postgres
expect_dns_failure real-analysis-worker deterministic-test-provider
expect_dns_failure real-collector deterministic-test-provider
expect_dns_failure real-inference-worker synthetic-source-postgres

compose exec -T real-inference-worker python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://deterministic-test-provider:8090/healthz',timeout=2)); assert d=={'status':'ok','synthetic':True}"
compose exec -T real-inference-worker python -c "import json,urllib.request; body=json.dumps({'model':'reweft-deterministic-test-v1','input':'bounded fixture'}).encode(); r=urllib.request.urlopen(urllib.request.Request('http://deterministic-test-provider:8090/v1/responses',data=body,headers={'content-type':'application/json'}),timeout=2); d=json.load(r); assert r.headers['X-Reweft-Synthetic-Provider']=='true'; assert d['metadata']['reweft_fixture']=='true'"

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
output="tests/integration/evidence/real-runtime-${timestamp}-$$.json"
revision=$(git rev-parse --verify HEAD 2>/dev/null || printf 'uncommitted')
python3 - "$output" "$timestamp" "$revision" <<'PY'
import json, sys
path, timestamp, revision = sys.argv[1:]
record = {
    "schema_version": "reweft.integration-evidence/v1",
    "executed_at": timestamp,
    "revision": revision,
    "checks": {
        "all_service_healthchecks": "passed",
        "gateway_api_health": "passed",
        "no_internal_ports_published": "passed",
        "permit_key_separation": "passed",
        "service_token_separation": "passed",
        "artifact_mount_read_only": "passed",
        "source_provider_network_separation": "passed",
        "deterministic_provider_contract": "passed",
    },
    "limitations": [
        "Synthetic source and deterministic provider only.",
        "No proprietary, cloud, external inference, scale, HA, or production validation.",
    ],
}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(record, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
assessment_output="tests/integration/evidence/assessment-${timestamp}-$$.json"
python3 tests/integration/run_assessment.py \
  --env-file "$runtime_env" \
  --output "$assessment_output"
echo "Integration harness passed; sanitized evidence: $output"
echo "Assessment evidence: $assessment_output"
echo "Services remain running and no volumes or configuration were deleted."

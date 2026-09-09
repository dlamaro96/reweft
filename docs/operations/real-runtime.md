# Real-runtime integration profile

The real-runtime profile exercises the intended process topology with application PostgreSQL, Temporal, API, analysis worker, inference worker, collector, a separate read-only synthetic source PostgreSQL, and a deterministic OpenAI-compatible test provider. It is an integration environment, not a production or live-connector claim.

Start it without altering the independent demo:

```bash
./scripts/bootstrap-real-runtime.sh
```

Use a non-default environment-file location by setting the reference on every lifecycle command:

```bash
REWEFT_REAL_ENV_FILE=.data/team-real-runtime.env ./scripts/bootstrap-real-runtime.sh
REWEFT_REAL_ENV_FILE=.data/team-real-runtime.env tests/integration/run-real-runtime.sh
REWEFT_REAL_ENV_FILE=.data/team-real-runtime.env ./scripts/backup-real-runtime.sh
```

Bootstrap writes the environment file with mode `0600` and the permit-key directory with mode `0700`. It creates `REWEFT_SECRET_KEY`, bootstrap and service tokens, database passwords, the Ed25519 private issuer key, and its public verification key only when absent; it never prints secret values. Do not commit `.data/` or `.secrets/`, pass the private key to the collector, or put a provider API key in `profile-seed.yaml`. Preserve the generated environment file and keypair separately from ordinary database backups. Changing database passwords in the file does not rotate roles inside existing named volumes.

The generated environment file is `.data/real-runtime.env`; permit keys are under `.secrets/real-runtime/`. Existing files are preserved. If only a public permit key exists, bootstrap fails instead of silently rotating identity. Two clearly marked compatibility variables let Compose parse the inactive legacy profiles; real-runtime services do not consume them. The real gateway binds to loopback on port 8180 by default. Databases, Temporal, source, provider, API, and workers have no host-published ports.

The API receives the Ed25519 permit issuer private key. Its root-only startup shim copies the mode-`0600` host file into a private tmpfs as a mode-`0400` file owned by the non-root `reweft` runtime user, then drops privileges before starting Uvicorn. The collector receives only the public verification key. Independent generated service tokens are shared only between API/collector and API/analysis respectively. A dedicated inference worker is the only application process attached to `provider-egress`; the analysis worker has no provider network or provider settings. The collector is the only application process attached to `source-egress`. All three workers have distinct Temporal task queues. Both egress networks are internal. The fixture provider is prominently synthetic, deterministic, request-size bounded, returns a synthetic header/metadata marker, and performs no inference.

The source is the fictional **Atlas Foundry** database `loom_source`, schema `ops_atlas`. Its collector role has CONNECT, schema USAGE, and SELECT only, with temporary database access revoked. Neutral collector settings are `REWEFT_SOURCE_DSN`, `REWEFT_SOURCE_SCHEMA`, and `REWEFT_ARTIFACT_ROOT`; `REWEFT_SOURCE_ENVIRONMENT=synthetic_fixture` preserves the validation boundary. The unresolved and resolved artifact fixtures mount read-only below `/opt/reweft/artifacts/`. The inference worker receives a non-secret deterministic provider profile seed mounted read-only from `deploy/test-provider/profile-seed.yaml`.

Readiness requires every service healthcheck plus the gateway API response. Worker `--health-check` commands prove configured PostgreSQL/Temporal connectivity; the collector additionally checks its Ed25519 verifier, artifact root, and a read-only source/schema query, while the inference worker checks endpoint policy, DNS, and provider transport reachability without making a potentially billable model request. The integration harness separately exercises the deterministic provider's Responses contract. Bootstrap fails instead of reporting readiness when any of these checks fails.

Run the integration harness with:

```bash
tests/integration/run-real-runtime.sh
```

Sanitized results go under `tests/integration/evidence/`. The harness checks unpublished internal ports, key and service-token separation, read-only artifacts, DNS/network separation, provider labels, and service health. It then creates an authenticated workspace, configures and tests PostgreSQL and model paths, executes unresolved and resolved artifact assessments, restarts the analysis worker during a run, checks duplicate suppression, validates a DuckDB target, and scans an authorized export for generated secrets. It leaves services and named volumes in place.

## Backup and restore

Create an application, Temporal, synthetic-source, and evidence backup:

```bash
./scripts/backup-real-runtime.sh
```

Backups default to `.data/backups/`, use restrictive local permissions, include SHA-256 checksums, and intentionally exclude secrets and permit keys. Secure those separately. The backup briefly quiesces request-processing and Temporal services so the database dumps and evidence archive are not captured while workflows are mutating them; a cleanup trap restarts those services if backup fails.

Restore is deliberately explicit and overwrites database schemas and same-named evidence files without deleting volumes or runtime configuration:

```bash
./scripts/restore-real-runtime.sh .data/backups/reweft-real-TIMESTAMP-PID --confirm-overwrite
```

Restore validates every checksum, stops request-processing services, performs repeatable `--clean --if-exists` restores, restarts the same topology, and requires full readiness. Evidence extraction does not remove files absent from the backup; retention cleanup is a separate operation.

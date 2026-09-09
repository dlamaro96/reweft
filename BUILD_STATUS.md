# Build status

Last updated: 2026-09-09

Reweft is a pre-release implementation in active construction. The source repository is public, but no release or container image has been published and no production/live-system certification is claimed.

## Status vocabulary

| State | Meaning |
|---|---|
| proposed | Contract or design exists; implementation is not implied. |
| implemented | Code exists and has been reviewed locally; execution is not implied. |
| fixture-tested | Tests passed only against synthetic or recorded data. |
| environment-tested | A named external environment was exercised and evidence recorded. |
| not-run | The documented verification has not been executed. |

## Current verification boundary

The machine-readable record is [contracts/acceptance.yaml](contracts/acceptance.yaml). At repository bootstrap, every release acceptance check is `not_run`. Contributors may advance a result only with a command, date, environment, and durable evidence path. Live SAP, BI SaaS, cloud-target, OIDC, publication, image-signing, and multi-node/HA validation require separately authorized environments and are never inferred from fixtures.

The current default Compose model covers only the synthetic gateway/API path. The API persists its development state in a dedicated SQLite volume. PostgreSQL is opt-in under the `durable` profile and is not connected to application persistence. The `workers` profile contains topology placeholders for PostgreSQL, Temporal, the analysis worker, and the collector; the worker process modules and durable Temporal integration are not implemented or runnable.

## Publication

- Git remote: `https://github.com/dlamaro96/reweft.git` (`main`).
- Public source: https://github.com/dlamaro96/reweft under the authenticated `dlamaro96` account.
- Repository features: Issues, Discussions, and private vulnerability reporting enabled.
- Release and image locations: none.
- Supported production versions: none; pre-release only.

## Local checks executed on 2026-09-09

| Check | Result | Boundary |
|---|---|---|
| `sh -n scripts/*.sh deploy/docker/init-databases.sh` | Passed | Shell syntax only; PowerShell was not executed. |
| Default and `workers` `docker compose config --quiet` | Passed | Compose model resolution only. Default service list was exactly `api`, `gateway`. |
| `tests/contracts/validate_contracts.py` via uv with PyYAML/jsonschema | Passed | JSON Schema/YAML and acceptance-registry structure only. |
| `scripts/release-check.sh` | Passed | Required policy files and a small private-key/AWS-key pattern set only; not a complete secret scan. |
| `uv run --project backend --extra dev pytest` | Passed: 9 tests | Local Python 3.12.10; API, connector-runtime, and source-controller tests. Two upstream deprecation warnings were emitted. This is not the full acceptance suite. |
| `npm test` in pinned Node 22.22.2 container | Passed: 6 tests | Synthetic UI rendering and interaction coverage; not full browser E2E or accessibility certification. |
| `npm run build` in pinned Node 22.22.2 container | Passed | Strict TypeScript check and production Vite build. |
| API and gateway image build | Passed | Local ARM64 Docker/Colima build; no image publication, SBOM, signing, or multi-architecture test. |
| `./scripts/bootstrap.sh --demo` twice | Passed | Local existing-machine run, not a clean-machine installation test. Second run preserved the `.env` content hash and existing named volume. |
| `scripts/smoke-test.sh` and demo snapshot request | Passed | Local HTTP health/root plus `mode=synthetic-demo`; not full browser/E2E/accessibility validation. |
| Desktop and mobile in-app browser inspection | Passed for inspected routes | 1440×900 overview and 390×844 connections workspace; synthetic fixture only. Captures are under `docs/assets/screenshots/`. |

The local default demo was left running at `http://127.0.0.1:8080` for inspection. These checks do not advance the composite release checks in `contracts/acceptance.yaml`.

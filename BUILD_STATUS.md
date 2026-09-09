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

The default Compose model remains the separate labeled synthetic gateway/API path on SQLite. The opt-in `real-runtime` profile is now runnable: it uses PostgreSQL application persistence, Alembic migrations, Temporal, distinct analysis/inference/collector workers, separate source/provider egress networks, a least-privileged synthetic source PostgreSQL, and a labeled deterministic provider. This checkpoint is single-node integration infrastructure, not production certification.

## Publication

- Git remote: `https://github.com/dlamaro96/reweft.git` (`main`).
- Public source: https://github.com/dlamaro96/reweft under the authenticated `dlamaro96` account.
- Published documentation: https://dlamaro96.github.io/reweft/ from the `docs/` directory on `main`.
- Repository features: Issues, Discussions, and private vulnerability reporting enabled. `main` requires the three CI job contexts, linear history, and resolved review conversations; force-push and deletion are disabled. Repository administrators retain the documented emergency bypass.
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

The local default demo was left running at `http://127.0.0.1:8080` for inspection. Those baseline checks alone did not advance the composite release checks in `contracts/acceptance.yaml`; the separate real-runtime checkpoint below advances only requirements it exercised completely.

## Real-runtime checkpoint executed on 2026-09-09

| Check | Result | Boundary |
|---|---|---|
| `make test` | Passed: 44 backend, 11 frontend; 1 opt-in live-PostgreSQL pytest skipped | Unit/API/workflow/connector/security-boundary tests plus contract validation; not a production suite. |
| `make lint` and `make compose-check` | Passed | Production frontend build and Compose resolution. |
| `tests/integration/run-real-runtime.sh` | Passed | Real local PostgreSQL/Temporal processes with a synthetic Atlas source/artifact estate and a clearly labeled deterministic provider. |
| Unresolved assessment | Passed | Persisted three evidence artifacts and three evidence-driven findings; completed-with-gaps with explicit settlement/outbound gaps. |
| Analysis-worker restart during a second run | Passed | Temporal resumed to 100% persisted task progress with no duplicate task, source-operation, or finding keys. |
| Collector outage plus pause/resume/cancel | Passed | Work remained durably queued while collection was unavailable; resumed work completed and cancellation left no active unsafe operation. |
| API and PostgreSQL/controller loss | Passed | API restart preserved the active run. During database loss a new transition failed closed; after recovery its original queued version remained with zero source operations. |
| Provider and adversarial failures | Passed | Provider loss degraded to explicit gaps within bounded attempts; malformed/incomplete outputs, prompt injection, endpoint denials, strict schemas, partial scans, and cross-workspace access were exercised. |
| Changed resolved artifact bundle | Passed | A subsequent run completed without gaps, removed the retirement blocker, and propagated the changed `COALESCE` formula into the generated specification. |
| DuckDB target and authorized export | Passed | Independent expected values matched; ZIP included generated target SQL/manifest and no generated token/password/private-key canaries. |
| Backup then confirmed restore | Passed | Checksums verified; workspace identity, configuration, evidence, and sampled run outcomes survived restoration. |
| Runtime secret scan | Passed | Generated credentials were absent from every Compose service log, the full evidence volume, and the authorized export. |
| Demo bootstrap twice | Passed | A regression involving inactive-profile interpolation was fixed; both runs preserved the `.env` hash and named evidence-volume identity. |
| Browser inspection | Passed within stated boundary | Desktop navigation/filtering, live connection gate, explicit demo opt-in, 390×844 layout, accessible labels/skip link, and console logs were inspected. Authenticated live browser entry and a full automated accessibility suite remain open. |

The sanitized committed summary is [tests/integration/evidence/20260909-real-runtime-summary.json](tests/integration/evidence/20260909-real-runtime-summary.json). The runtime was left healthy at `http://127.0.0.1:8180`; its volumes, generated configuration, identities, evidence, and backup were preserved.

Remaining release blockers include password/session lifecycle and OIDC, collaboration, native SAP BW and reporting connectors, real model inference, shared inference budgets and policy-compatible fallback, active source-native reconciliation for every cancellation/unknown operation, incremental dependency-aware invalidation, cloud targets, authenticated browser onboarding and full automated accessibility, multi-node/HA, upgrade testing, SBOM/signing, and publication. The existing deprecation warnings for FastAPI event hooks and Starlette's current test client are also still visible.

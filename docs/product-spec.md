# Reweft product specification

Specification date: 9 September 2026  
Status: pre-release implementation specification

## Product

Reweft is an open-source, self-hosted application that investigates a heterogeneous analytics estate and produces evidence-backed assessment and modernization outputs. It reconstructs lineage, business rules, analytical semantics, history, security, operations, and downstream dependencies; compares target scenarios; and produces versioned models, pipeline contracts, mappings, tests, migration work packages, and retirement conditions.

The normal journey is: deploy, open the light-mode UI, configure connections and inference, select an objective, run unattended within policy, and inspect evidence-backed outputs. SAP BW retirement is a major specialization, but an estate without SAP must work.

Reweft assesses and designs. It does not silently deploy a target, publish customer artifacts, alter source settings, move production data at migration scale, or decommission a legacy system.

## Non-negotiable invariants

1. Model/agent code never connects to a source. Typed evidence requests are authorized and admitted by the shared workload controller, then executed by a collector.
2. All source operations—including tests, health checks, preflight, metadata, profiling, retries, and remote collectors—consume the actual resource group's shared budget.
3. Credentials and source execution are isolated from inference and generated-code execution.
4. Assessment provides no source mutation or arbitrary production query path.
5. Replicas, aliases, credentials, or workspaces do not create independent capacity against the same constrained backend. Deployment policy caps the aggregate without revealing another workspace's details.
6. A client timeout, workflow timeout, lease expiry, cancellation request, confirmed source termination, and unknown remote execution are distinct states. Unknown execution retains capacity until reconciled or administratively resolved.
7. Missing evidence and lack of observed use never become false deletion or disuse claims. Coverage records known denominators, scope, permissions, observation periods, and unknowns.
8. Collected facts, deterministic derivations, AI interpretations, user assertions, independent verification, generated artifacts, compiled artifacts, fixture tests, and live/environment tests are distinguishable.
9. Significant findings and decisions cite resolvable evidence spans or explicit assumptions.
10. Workspace authorization applies to evidence, caches, graph/search, events, prompts, model calls, exports, and jobs. Global content deduplication must not reveal cross-workspace existence.
11. Provider fallback is opt-in and cannot broaden data classification, organization, or regional egress. Private/local data never silently falls back to a public endpoint.
12. No customer, provider model, cloud, region, domain, source count, price, duration, KPI, coverage, or savings value is invented or hard-coded as truth.

## Architecture

Domain logic is a modular monolith with a small number of deployable roles:

- Gateway/static frontend serving one origin.
- API for authentication, configuration, queries, mutations, and event delivery.
- Durable orchestration and analysis worker.
- Collector worker holding only permitted source credentials.
- PostgreSQL for application state, graph edges, budgets, journals, audit/event metadata, and Temporal persistence through separate databases/users.
- Temporal for durable execution.
- Protected local evidence storage for compact installs; S3-compatible storage for shared deployments.
- Optional isolated artifact-validation sandbox and remote collector.

The compact Compose installation is single-node. Multi-node deployments need shared evidence storage plus explicitly operated PostgreSQL and Temporal availability. PostgreSQL, Temporal administration, collectors, and metrics are not publicly exposed by default, and no service mounts the host Docker socket.

The source path is:

```text
authorized UI/CLI/API -> assessment workflow -> typed evidence request
  -> policy and shared workload admission -> connector/collector -> source
  -> evidence validation/store -> normalized graph -> offline analysis/design
```

Inference uses a separate model gateway with its own egress and budget policy. The gateway receives authorized evidence context, not source credentials.

## Evidence and investigation

The canonical domain model stores workspaces/projects, sources/connections/resource groups, assets and versions, fields and typed edges, evidence artifacts/locators, coverage manifests, observations/hypotheses/findings/assumptions, runs/tasks/model invocations/source operations, target scenarios/assets/mappings/work packages/tests, decisions/comments, and exports.

Evidence envelopes include authorization, stable native identity, platform/environment, version when known, collection interval, content hash/type/size, location, collector/parser versions, scope/permission context, classification/retention, status, and snapshot/run. Locators identify API IDs, code lines, JSON paths, XML nodes, workbook cells, or precise document ranges.

Investigation uses a coordinator and bounded specialist roles. A decision proposes one typed action such as requesting evidence, analysis, comparison, target design, verification, deferral, or finish. Reweft validates authorization, policy, evidence references, novelty, budgets, and connector capability before executing. Repeated calls, circular delegation, and non-progressing hypotheses terminate with explicit gaps.

Temporal workflows remain replay-deterministic. I/O, database access, clocks/randomness outside workflow primitives, source activity, and model calls live in activities. Tasks use stable IDs, idempotency journals, bounded retries with one retry owner, compact references rather than evidence bodies in workflow history, transactional result/event publication, stable SSE sequences, and Continue-As-New where appropriate. Exactly-once external execution is not claimed.

Runs distinguish queued, collecting, analyzing, designing, verifying, user/policy/budget pause, completed, completed with gaps, failed, and cancelled. Cancellation prevents new work and attempts source-native termination where supported; the UI reports confirmed, still-running, or unknown operations.

## Source workload control

A request carries authorized workspace/project/run/task/source IDs, resource groups, connector and version, operation, asset scope, validated parameters, evidence fingerprint, idempotency key, policy version, deadline, and estimated operation class. Only the controller issues a fenced permit. The collector validates it before execution and returns source execution state, source-native reference, evidence/coverage references, actual usage, sanitized error, cancellation confirmation, and cursor.

Admission is authoritative and shared, using short database transactions. Policies bound concurrency, rate, pages, bytes, rows, time, retries, query shapes, windows, and profiling. Adaptive reduction is conservative and auditable; health uncertainty never raises capacity. A model cannot mint a permit, submit credentials/URLs, widen scope, or execute arbitrary code.

## Connectors

Release-critical paths are native PostgreSQL metadata, supported BW definition imports, a separately packaged BW live adapter with honest version/environment status, reporting/pipeline artifact analysis, and OpenLineage import. Static imports never execute DAGs, macros, workbook formulas, or project code. Proprietary binary formats and dynamic code retain explicit unresolved boundaries.

Each connector manifest states visibility, operations, configuration, maturity, fixture status, live status, versions, evidence, and limitations. A form or manifest alone is not a usable connector. Optional SAP JCo is operator-supplied and not redistributed.

## Assessment and modernization

Versioned deterministic rules calculate metrics while bounded model interpretation explains, compares, hypothesizes, and proposes. Findings have stable identities, affected assets, evidence, interpretation, impact, options, severity basis, knowledge state, assumptions, unresolved questions, verification, and linked work.

Assessment covers inventory/coverage, lineage, duplicated or divergent logic, metric semantics, grain/keys/joins, calendars/timezones/currency/units, non-additivity, custom/dynamic logic, history and reconstructability, delta/delete behavior, scheduling/recovery, runtime/quality evidence, security, write-back/planning, exports, applications, and infrequent consumers.

Report disposition is one of retain-and-reconnect, adapt semantic model, rebuild, consolidate, archive, retire candidate, or unresolved—with evidence and prerequisites. Similar names or one period's equal totals do not prove equivalence.

The versioned target-neutral specification maps current behavior to target behavior, artifacts, validation, and migration dependencies. It separates current-state reconstruction from recommendations and can compare scenarios using stated fit, complexity, history, freshness, security/hosting, team, operations, portability, and supplied cost assumptions.

Models separate source-preserving records, reusable domain identity/crosswalks, and analytical facts/dimensions/metrics. Every model states grain, keys, precision, relationships, history, privacy, lineage, consumers, quality tests, and unresolved issues. Pipelines state initial/incremental strategies and prerequisites, inserts/updates/deletes, ordering/deduplication/replay, schema evolution/quarantine, schedules/retries/backfill, observability, security, and reconciliation.

Target adapters translate the canonical specification for a local DuckDB demonstration and reference packs for Databricks, Microsoft Fabric, Snowflake, and BigQuery. Their machine-readable capability records distinguish planned, generated, schema-validated, fixture-tested, and environment-tested states. No cloud execution is implied.

## Configuration and inference

Deployment security boundaries dominate environment/secret-file settings; workspace settings select defaults within them; run settings may only narrow scope/budget. Each run pins an immutable resolved configuration without secret contents. YAML/JSON rejects unknown keys and invalid combinations and supports migration and read-only effective views.

Inference profiles support native OpenAI, Azure-hosted OpenAI/Foundry, Anthropic, Google/Vertex, AWS Bedrock, and OpenAI-compatible endpoints according to verified provider capabilities. Profile fields are provider-specific; OpenAI-compatible does not imply feature parity. A bounded synthetic preflight tests relevant structured output/tool/streaming behavior without real evidence. Usage reservations and reconciliation are shared across delegated work. Unknown price displays as unknown, never zero.

The no-key demo uses synthetic fixtures and prerecorded synthetic decisions. It never registers fake live providers or switches a real assessment into demo mode.

## UX and deliverables

Light mode is default. Primary areas cover onboarding, overview, sources, inference, runs/live events, evidence, lineage with accessible table fallback, findings/gaps, reports, modernization scenarios, models, pipelines, mappings/waves, verification, decisions/comments, exports, diagnostics, and settings. Progressive disclosure keeps the first path to one workspace, one model, one source, one objective.

Exports are authenticated, versioned, evidence-linked, secret-free, and retain validation status. Customer artifacts are never published to this public project. Optional Git export acts only on an explicitly configured intended repository.

## Verification and release

Tests are layered into unit/property, connector contracts, local integrations, agent evaluations, security, resilience, UI/E2E/accessibility, and release checks. Synthetic fixtures are not live-system certification. Benchmarks state hardware, versions, data, configuration, latency distributions, memory, and storage or are not published.

`contracts/acceptance.yaml` is the release gate and evidence index. Failed and unexecuted checks remain visible; unavailable live environments use `not_live_verified` only after relevant fixture/contract evidence exists. Release automation does not use privileged fork code, and no stable or production-proven label is permitted without evidence.


# Reweft agent guide

## Commands

- `make bootstrap-demo`: start the synthetic single-node profile.
- `make test`: run available backend, frontend, and contract tests.
- `make lint`: run available linters and type checks.
- `make contracts`: validate checked-in JSON/YAML contracts.
- `make compose-check`: resolve the Compose model without starting it.

## Boundaries

- Agents and model code never connect to sources. All source operations use the shared policy/workload controller and collector boundary.
- Assessment mode is read-only: no source mutations or arbitrary production query execution.
- Keep secrets out of source, logs, evidence exports, test fixtures, prompts, and generated artifacts. Synthetic fixtures must be original and clearly labeled.
- Workspace identity and authorization are mandatory on persisted evidence, graph, cache, events, exports, and background work.
- Treat timeouts, cancellation confirmation, and unknown remote execution as distinct states. Never release uncertain capacity merely because a lease expired.
- Preserve evidence provenance and distinguish collected, derived, AI-inferred, generated, tested, and live-validated states.

## Completion

Update `contracts/acceptance.yaml` only with evidence from commands actually run. Add tests for changed behavior, keep docs/commands synchronized, and do not claim proprietary/live validation from fixtures. Do not weaken a safety invariant to make a check pass.


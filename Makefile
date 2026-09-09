.PHONY: help doctor bootstrap bootstrap-demo compose-check contracts frontend-build frontend-test test lint smoke release-check

help:
	@echo "doctor          Check required local tools"
	@echo "bootstrap-demo  Start the isolated synthetic demo"
	@echo "compose-check   Resolve Compose configuration"
	@echo "contracts       Validate JSON/YAML syntax and JSON schemas"
	@echo "lint            Run available backend/frontend checks"
	@echo "test            Run available backend/frontend tests"

doctor:
	./scripts/doctor.sh

bootstrap:
	./scripts/bootstrap.sh

bootstrap-demo:
	./scripts/bootstrap.sh --demo

compose-check:
	REWEFT_SECRET_KEY=compose-check-only POSTGRES_PASSWORD=compose-check-only TEMPORAL_DB_PASSWORD=compose-check-only DATABASE_URL=postgresql://reweft:compose-check-only@postgres:5432/reweft docker compose --env-file .env.example config --quiet

contracts:
	uv run --with pyyaml --with jsonschema python tests/contracts/validate_contracts.py

frontend-build:
	@if command -v node >/dev/null 2>&1 && [ "$$(node -p "Number(process.versions.node.split('.')[0]) >= 22")" = true ]; then \
		cd frontend && npm run build; \
	elif command -v docker >/dev/null 2>&1; then \
		echo "Host Node 22+ unavailable; building frontend in the pinned Node container."; \
		docker run --rm -v "$(CURDIR)/frontend:/app" -v /app/node_modules -w /app node:22.22.2-bookworm-slim sh -lc 'npm ci --no-audit --no-fund && npm run build'; \
	else \
		echo "frontend build requires Node 22+ or Docker" >&2; exit 1; \
	fi

frontend-test:
	@if command -v node >/dev/null 2>&1 && [ "$$(node -p "Number(process.versions.node.split('.')[0]) >= 22")" = true ]; then \
		cd frontend && npm test; \
	elif command -v docker >/dev/null 2>&1; then \
		echo "Host Node 22+ unavailable; testing frontend in the pinned Node container."; \
		docker run --rm -v "$(CURDIR)/frontend:/app" -v /app/node_modules -w /app node:22.22.2-bookworm-slim sh -lc 'npm ci --no-audit --no-fund && npm test'; \
	else \
		echo "frontend tests require Node 22+ or Docker" >&2; exit 1; \
	fi

lint: frontend-build
	@if command -v uv >/dev/null 2>&1; then cd backend && uv run python -m compileall -q src tests; else echo "skip backend lint: uv unavailable"; fi

test: contracts frontend-test
	@if command -v uv >/dev/null 2>&1; then cd backend && uv run pytest; else echo "skip backend tests: uv unavailable"; fi

smoke:
	./scripts/smoke-test.sh

release-check: contracts
	./scripts/release-check.sh

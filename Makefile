# Thin wrappers over docker compose and the per-package toolchains.
# Windows without make: use scripts/rl.ps1 (same targets).

COMPOSE ?= docker compose

.PHONY: dev up down logs migrate seed reset-demo test test-backend test-frontend test-demo \
        verify-oracles lint typecheck clean-artifacts

dev up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

migrate:
	$(COMPOSE) run --rm migrate alembic upgrade head

seed:
	$(COMPOSE) run --rm migrate python -m reprolab.db.seed

reset-demo:
	$(COMPOSE) exec api python -m reprolab.demo.reset

test: test-backend test-frontend test-demo

test-backend:
	cd backend && uv run pytest

test-frontend:
	cd frontend && npm test

test-demo:
	cd demo-target && npm test

verify-oracles:
	cd demo-target && npm run build && npm run verify-oracles -- --runs 2

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint

typecheck:
	cd backend && uv run mypy
	cd frontend && npm run typecheck
	cd demo-target && npm run typecheck

clean-artifacts:
	@read -p "Delete ALL stored investigation artifacts? [y/N] " ans && [ "$$ans" = "y" ] && \
	  $(COMPOSE) run --rm --entrypoint sh api -c 'rm -rf /data/artifacts/*' || echo "aborted"

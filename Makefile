# All tooling runs inside Docker. The host needs only docker and make.

HOST_UID ?= $(shell id -u)
HOST_GID ?= $(shell id -g)
export HOST_UID HOST_GID

COMPOSE  := docker compose
BACKEND  := $(COMPOSE) run --rm --build backend
BACKEND_NODEPS := $(COMPOSE) run --rm --build --no-deps backend
FRONTEND := $(COMPOSE) run --rm --build --no-deps frontend

.DEFAULT_GOAL := help
.PHONY: help dev down logs build test lint lint-backend lint-frontend format typecheck \
        check migrate seed types lock psql

help: ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

.env:
	cp .env.example .env
	@echo "Created .env from .env.example — edit it if needed."

dev: .env ## Start db, backend and frontend with hot reload
	$(COMPOSE) up --build --renew-anon-volumes

down: ## Stop the dev stack
	$(COMPOSE) down

logs: ## Follow dev stack logs
	$(COMPOSE) logs -f

build: .env ## Rebuild dev images
	$(COMPOSE) build

test: .env ## Run backend tests
	$(BACKEND) pytest

lint-backend: .env
	$(BACKEND_NODEPS) sh -c "ruff check . && ruff format --check ."

lint-frontend: .env
	$(FRONTEND) sh -c "npm run lint && npm run format:check"

lint: lint-backend lint-frontend ## Run ruff, eslint and prettier checks

format: .env ## Auto-format backend and frontend
	$(BACKEND_NODEPS) sh -c "ruff check --fix . && ruff format ."
	$(FRONTEND) npm run format

typecheck: .env ## Run the TypeScript type check
	$(FRONTEND) npm run typecheck

check: lint typecheck test ## Lint + type check + tests (must pass before a phase is done)

migrate: .env ## Apply Alembic migrations
	$(BACKEND) alembic upgrade head

seed: .env ## Run the idempotent seed script
	$(BACKEND) python -m app.scripts.seed

types: .env ## Regenerate frontend TS types from the FastAPI OpenAPI schema
	$(BACKEND_NODEPS) python -m app.scripts.export_openapi > frontend/.openapi.json
	$(FRONTEND) npx openapi-typescript .openapi.json -o src/api/schema.d.ts
	rm -f frontend/.openapi.json

UV_IMAGE := ghcr.io/astral-sh/uv:0.13.7-python3.15-trixie-slim

# Runs outside the backend image, so it works even when uv.lock is stale.
lock: ## Re-lock backend dependencies after editing pyproject.toml
	docker run --rm -u $(HOST_UID):$(HOST_GID) -e UV_CACHE_DIR=/tmp/uv-cache \
		-v $(CURDIR)/backend:/app -w /app $(UV_IMAGE) uv lock

psql: ## Open psql in the running db container
	$(COMPOSE) exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

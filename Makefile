.PHONY: up down logs build migrate test test-backend test-frontend shell-backend shell-frontend pull-model airflow-setup

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

migrate:
	docker compose exec backend alembic upgrade head

# `test` runs both suites. A `make test` that quietly covered only one of them
# is how the other one stops being run.
test: test-backend test-frontend

# --no-deps because the suites mock their way past Postgres, ChromaDB and the
# LLM: they need the images, not the stack, and requiring `make up` first is
# how a documented command stays unrun.
test-backend:
	docker compose run --rm --no-deps backend python -m pytest tests/ -v

test-frontend:
	docker compose run --rm --no-deps frontend npm test

shell-backend:
	docker compose exec backend bash

shell-frontend:
	docker compose exec frontend sh

pull-model:
	ollama pull llama3.2

ps:
	docker compose ps

restart:
	docker compose restart $(service)

airflow-setup:
	docker compose exec postgres psql -U securag -c "CREATE DATABASE airflow OWNER securag;" 2>/dev/null || true
	docker compose run --rm airflow-init

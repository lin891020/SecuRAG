.PHONY: up down logs build migrate shell-backend shell-frontend pull-model

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

shell-backend:
	docker compose exec backend bash

shell-frontend:
	docker compose exec frontend sh

pull-model:
	docker compose exec ollama ollama pull llama3.2

ps:
	docker compose ps

restart:
	docker compose restart $(service)

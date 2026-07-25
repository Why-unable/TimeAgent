.PHONY: up down build logs backend-test frontend-test lint check migrate migrations api-schema frontend-api observability

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

backend-test:
	cd backend && uv run pytest

frontend-test:
	cd frontend && npm test

lint:
	cd backend && uv run ruff check .
	cd backend && uv run mypy .
	cd frontend && npm run lint

check:
	cd backend && uv run python manage.py check --settings=config.settings.test
	cd backend && uv run pytest
	cd backend && uv run ruff check .
	cd backend && uv run mypy .
	cd frontend && npm test
	cd frontend && npm run build

migrate:
	cd backend && uv run python manage.py migrate

migrations:
	cd backend && uv run python manage.py makemigrations --check --dry-run

api-schema:
	cd backend && uv run python manage.py spectacular --file openapi.json --format openapi-json --settings=config.settings.test

frontend-api: api-schema
	cd frontend && npm run generate:api

observability:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.observability.yml up -d prometheus

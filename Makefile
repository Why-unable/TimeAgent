.PHONY: up down build logs backend-test frontend-test lint check migrate migrations api-schema frontend-api observability release-eval release-gate

EVALUATION_MODEL ?= deepseek

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
	docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.observability.yml up -d

release-eval:
	@set -eu; \
		stamp="$$(date -u +%Y%m%dT%H%M%SZ)"; \
		report="backend/evaluation_reports/time-steward-$$stamp.json"; \
		run_dir="backend/evaluation_reports/.run-$$stamp"; \
		mkdir -p backend/evaluation_reports; \
		install -d -m 0777 "$$run_dir"; \
		trap 'rm -f "$$run_dir/report.json"; rmdir "$$run_dir" 2>/dev/null || true' EXIT; \
		status=0; \
		docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm --build \
			-v "$$(pwd)/$$run_dir:/tmp/evaluation-output" \
			-e GIT_COMMIT_SHA="$$(git rev-parse HEAD)" \
			django python manage.py evaluate_time_steward --model $(EVALUATION_MODEL) \
			--minimum-pass-rate 1 \
			--output /tmp/evaluation-output/report.json || status=$$?; \
		if [ -f "$$run_dir/report.json" ]; then install -m 0600 "$$run_dir/report.json" "$$report"; fi; \
		exit $$status

release-gate: check migrations release-eval

.PHONY: dev test coverage lint up ui ui-build ui-test temporal worker

up:
	docker compose up -d postgres

dev:
	uv run uvicorn --app-dir src interactors.api.app:create_app --factory --reload

test:
	uv run pytest

coverage:
	uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80

lint:
	uv run ruff check src tests

ui:
	cd ui && npm run dev

ui-build:
	cd ui && npm run build

ui-test:
	cd ui && npm test

temporal:
	docker compose up -d temporal

worker:
	uv run python -m interactors.worker_main

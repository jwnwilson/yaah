.PHONY: dev test coverage lint up

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

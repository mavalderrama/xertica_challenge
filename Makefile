.PHONY: install dev-install migrate makemigrations run test test-unit test-integration lint format typecheck docker-up docker-down index-regulations clean

install:
	uv sync --frozen

dev-install:
	uv sync --frozen --group dev

migrate:
	uv run python -m django migrate --settings=config.settings.local

makemigrations:
	uv run python -m django makemigrations --settings=config.settings.local

run:
	uv run uvicorn compliance_agent.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest tests/ -x --cov=compliance_agent --cov-fail-under=60

test-unit:
	uv run pytest tests/unit/ -x

test-integration:
	uv run pytest tests/integration/ -x -m integration

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy compliance_agent/ --ignore-missing-imports

docker-up:
	docker compose up -d

docker-down:
	docker compose down

index-regulations:
	uv run python -m compliance_agent.rag.indexer

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -type f -name "*.pyc" -delete; \
	rm -rf .coverage htmlcov .pytest_cache .mypy_cache

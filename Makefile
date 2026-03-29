.PHONY: install dev-install migrate makemigrations run test test-unit test-integration lint format typecheck docker-up docker-down seed seed-clear index-regulations live-test live-test-judge populate clean

BACKEND := backend

install:
	cd $(BACKEND) && uv sync --frozen

dev-install:
	cd $(BACKEND) && uv sync --frozen --group dev

migrate:
	cd $(BACKEND) && uv run python manage.py migrate --settings=config.settings.local

makemigrations:
	cd $(BACKEND) && uv run python manage.py makemigrations --settings=config.settings.local

run:
	cd $(BACKEND) && uv run uvicorn compliance_agent.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	cd $(BACKEND) && uv run pytest tests/ -x --cov=compliance_agent --cov-fail-under=60

test-unit:
	cd $(BACKEND) && uv run pytest tests/unit/ -x

test-integration:
	cd $(BACKEND) && uv run pytest tests/integration/ -x -m integration

lint:
	cd $(BACKEND) && uv run ruff check .

format:
	cd $(BACKEND) && uv run ruff format .

typecheck:
	cd $(BACKEND) && uv run mypy compliance_agent/ --ignore-missing-imports

docker-up:
	docker compose up -d

docker-down:
	docker compose down

seed:
	cd $(BACKEND) && uv run python manage.py seed_data --settings=config.settings.local

seed-clear:
	cd $(BACKEND) && uv run python manage.py seed_data --clear --settings=config.settings.local

index-regulations:
	cd $(BACKEND) && uv run python manage.py index_regulations --settings=config.settings.local

live-test:
	bash scripts/live_test.sh $(if $(S),-s $(S)) $(if $(L),-l $(L)) $(SCENARIO)

live-test-judge:
	bash scripts/live_test.sh all http://localhost:8000 --judge

populate: migrate seed index-regulations

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -type f -name "*.pyc" -delete; \
	cd $(BACKEND) && rm -rf .coverage htmlcov .pytest_cache .mypy_cache

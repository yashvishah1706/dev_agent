.PHONY: help install dev test lint format typecheck quality clean docker-up docker-down

# Default target
help:
	@echo ""
	@echo "Dev Agent Platform — available commands:"
	@echo ""
	@echo "  make install     Install all dependencies"
	@echo "  make dev         Run the API locally with hot reload"
	@echo "  make test        Run tests with coverage"
	@echo "  make lint        Run ruff linter"
	@echo "  make format      Run black formatter"
	@echo "  make typecheck   Run mypy type checker"
	@echo "  make quality     Run lint + format check + typecheck (all at once)"
	@echo "  make clean       Remove __pycache__ and .pytest_cache"
	@echo "  make docker-up   Start all services via docker-compose"
	@echo "  make docker-down Stop all services"
	@echo ""

install:
	pip install -r requirements.txt
	pip install pytest pytest-asyncio pytest-cov ruff black mypy

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=70

lint:
	ruff check app/ tests/

format:
	black app/ tests/

format-check:
	black --check app/ tests/

typecheck:
	mypy app/ --ignore-missing-imports

quality: lint format-check typecheck
	@echo "All quality checks passed!"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "Cleaned."

docker-up:
	docker-compose up --build

docker-down:
	docker-compose down

# Create DB tables (requires postgres running)
db-init:
	python -m app.db.models

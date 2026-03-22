.PHONY: help dev up down test test-unit test-int lint format migrate

VENV := cd backend && source .venv/bin/activate &&

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Docker ───────────────────────────────────────────────────────────────────

up:  ## Start all services
	docker compose up -d

up-build:  ## Rebuild and start all services
	docker compose up -d --build

down:  ## Stop all services
	docker compose down

logs:  ## Follow logs
	docker compose logs -f

# ── Backend ──────────────────────────────────────────────────────────────────

dev:  ## Run backend dev server locally (requires venv)
	$(VENV) uvicorn app.main:app --reload --port 8000

test:  ## Run all backend tests
	$(VENV) python -m pytest -v

test-unit:  ## Run backend unit tests
	$(VENV) python -m pytest tests/unit/ -v

test-int:  ## Run backend integration tests
	$(VENV) python -m pytest tests/integration/ -v

test-cov:  ## Run tests with coverage
	$(VENV) python -m pytest --cov=app --cov-report=term-missing -v

lint:  ## Lint backend code
	$(VENV) ruff check .

format:  ## Format backend code
	$(VENV) ruff format .

# ── Database ─────────────────────────────────────────────────────────────────

migrate:  ## Run database migrations
	$(VENV) alembic upgrade head

migration:  ## Create a new migration (usage: make migration msg="add users table")
	$(VENV) alembic revision --autogenerate -m "$(msg)"

# ── Frontend ─────────────────────────────────────────────────────────────────

dev-frontend:  ## Run frontend dev server locally
	cd frontend && npm run dev

test-frontend:  ## Run frontend tests
	cd frontend && npm test

build-frontend:  ## Build frontend for production
	cd frontend && npm run build

install-frontend:  ## Install frontend dependencies
	cd frontend && npm install

# ── Setup ────────────────────────────────────────────────────────────────────

install:  ## Install all dependencies (creates venv)
	cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
	cd frontend && npm install

setup:  ## Full local setup (venv + deps + migrations)
	cp -n .env.example .env || true
	$(MAKE) install
	$(MAKE) migrate
	@echo "\n✅ Setup complete! Run: make dev (backend) / make dev-frontend (frontend)"

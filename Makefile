.PHONY: install dev frontend backend migrate seed build up down logs

install:
	cd frontend && npm install
	python -m venv .venv
	.venv/Scripts/python -m pip install -r services/node/requirements.txt

frontend:
	cd frontend && npm run dev

backend:
	.venv/Scripts/python -m uvicorn app.main:app --app-dir services/node --reload --host 0.0.0.0 --port 8000

migrate:
	.venv/Scripts/python -m alembic upgrade head

seed:
	.venv/Scripts/python scripts/seed_nodes.py

dev:
	@echo "Start frontend and backend in separate terminals with: make frontend / make backend"

build:
	cd frontend && npm run build
	docker compose build

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

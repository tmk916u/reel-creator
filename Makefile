.PHONY: up down build test logs clean

# Docker Compose
up:
	docker compose up --build

up-d:
	docker compose up --build -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

# Backend
test:
	cd backend && PYTHONPATH=. pytest tests/ -v

# Frontend
dev:
	cd frontend && npm run dev

# Cleanup
clean:
	docker compose down -v
	find backend/tmp -mindepth 1 -delete 2>/dev/null || true

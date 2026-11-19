.PHONY: install test build serve dev-api dev-ui

install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm ci

test:
	cd backend && PYTHONPATH=. .venv/bin/pytest -q

build:
	cd frontend && npm run build

serve:
	cd backend && .venv/bin/uvicorn api:app --port 8000

dev-api:
	cd backend && ORBIT_DEV=1 .venv/bin/uvicorn api:app --reload --port 8000

dev-ui:
	cd frontend && NEXT_PUBLIC_API=http://localhost:8000 npm run dev

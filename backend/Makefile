PYTHON := .venv/bin/python
RUFF := .venv/bin/ruff
MYPY := .venv/bin/mypy
PYTEST := .venv/bin/pytest
UVICORN := .venv/bin/uvicorn
ALEMBIC := .venv/bin/alembic

.PHONY: install run worker-vpn worker-payments worker-referrals worker-telegram telegram-webhooks lint format typecheck test test-integration check migrate revision

install:
	python3 -m venv .venv
	$(PYTHON) -m pip install -e '.[dev]'

run:
	$(UVICORN) app.main:app --reload --host 127.0.0.1 --port 8000

worker-vpn:
	$(PYTHON) -m app.workers.run_vpn_sync

worker-payments:
	$(PYTHON) -m app.workers.run_payments

worker-referrals:
	$(PYTHON) -m app.workers.run_referrals

worker-telegram:
	$(PYTHON) -m app.workers.run_telegram_notifications

telegram-webhooks:
	$(PYTHON) -m app.workers.setup_telegram_bots

lint:
	$(RUFF) check .
	$(RUFF) format --check .

format:
	$(RUFF) check . --fix
	$(RUFF) format .

typecheck:
	$(MYPY) app

test:
	$(PYTEST) -m 'not integration' --cov=app --cov-report=term-missing

test-integration:
	$(PYTEST) -m integration -vv

check: lint typecheck test

migrate:
	$(ALEMBIC) upgrade head

revision:
	$(ALEMBIC) revision -m "$(message)"

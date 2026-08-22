# Hazbit Remnawave Adapter

Private anti-corruption service for the Remnawave Panel API v3.3.2. Platform
API and workers call `/internal/v1/*`; only this service stores the panel token.

```bash
cd services/remnawave-adapter
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp .env.example .env
.venv/bin/uvicorn remnawave_adapter.main:app --host 127.0.0.1 --port 8010
```

Internal calls require `Authorization: Bearer <internal-token>`. Production
configuration requires HTTPS and non-local panel/internal tokens.

Checks:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy remnawave_adapter
.venv/bin/pytest
```

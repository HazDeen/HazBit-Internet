# STEP 3 — Backend Foundation

## 1. Что создано

Создан запускаемый backend foundation на Python 3.12:

- FastAPI application factory и versioned API router;
- Pydantic Settings v2 с nested environment variables и production guards;
- SQLAlchemy 2.x async engine/session factory на `asyncpg`;
- Alembic с initial migration полной STEP 2 schema;
- `/health/live` и `/health/ready`;
- structured logging через `structlog`;
- request correlation middleware с UUID `X-Request-ID`;
- RFC 9457-style `application/problem+json` errors;
- Trusted Host protection;
- unit и PostgreSQL integration tests;
- Ruff, mypy strict, pytest/coverage и Makefile commands.

На момент завершения STEP 3 бизнес-endpoint’ы и authentication еще не были
реализованы. Они добавлены следующим этапом и описаны в
[STEP 4](step-04-authentication.md).

## 2. Структура

```text
backend/
├── app/
│   ├── api/
│   │   ├── dependencies.py
│   │   ├── health.py
│   │   └── router.py
│   ├── core/
│   │   ├── config.py
│   │   ├── errors.py
│   │   ├── logging.py
│   │   └── middleware.py
│   ├── database/
│   │   ├── base.py
│   │   └── session.py
│   ├── models/
│   ├── modules/
│   ├── schemas/
│   │   └── health.py
│   ├── services/
│   │   └── health.py
│   └── main.py
├── alembic/
│   ├── versions/20260822_0001_initial_schema.py
│   ├── env.py
│   └── script.py.mako
├── tests/
│   ├── unit/
│   └── integration/
├── .env.example
├── alembic.ini
├── Makefile
└── pyproject.toml
```

## 3. Почему application factory

`create_app(settings)` не зависит от глобального environment state. Это дает:

- отдельную безопасную конфигурацию для каждого test app;
- возможность запускать API, bot-facing API или future worker health surface с
  разными settings;
- контролируемый lifespan для создания и закрытия connection pool;
- отсутствие DB connection во время обычного module import.

Экспорт `app = create_app()` сохранен только как стандартная ASGI entry point для
Uvicorn/Gunicorn.

## 4. Конфигурация

Settings читаются из environment с prefix `HAZBIT_`. Вложенные поля используют
двойное подчеркивание:

```text
HAZBIT_ENVIRONMENT=local
HAZBIT_LOG_FORMAT=console
HAZBIT_ALLOWED_HOSTS=["localhost","127.0.0.1"]
HAZBIT_DATABASE__URL=postgresql+asyncpg://hazbit:hazbit@localhost:5432/hazbit_vpn
HAZBIT_DATABASE__POOL_SIZE=10
```

Production validation запрещает:

- `debug=true`;
- console logging вместо JSON;
- включенные Swagger/ReDoc endpoints;
- wildcard `allowed_hosts=["*"]`.

Database URL валидируется: runtime API принимает только
`postgresql+asyncpg://`. Alembic автоматически преобразует его в
`postgresql+psycopg://`, потому что migrations выполняются синхронно и
транзакционно.

Пароль БД не выводится при startup: URL проходит через `hide_password=True`.

## 5. Database lifecycle

`DatabaseManager` владеет одним process-local async engine и
`async_sessionmaker`:

- `pool_pre_ping=True` отбрасывает мертвые connections;
- pool size, overflow и timeouts ограничены settings;
- `expire_on_commit=False` подходит для application service response mapping;
- исключение внутри session context вызывает rollback;
- commit остается явной обязанностью application service;
- engine гарантированно закрывается в FastAPI lifespan.

FastAPI dependency `SessionDependency` выдает session на один request, но не
скрывает transaction boundary. Domain command service должен явно использовать
`session.begin()`/`commit()` вокруг state change + outbox event.

`Base` уже задает schema `app`, naming convention для constraints и reusable
UUID/timestamp mixins. Typed domain ORM mappings будут добавляться по bounded
context вместе с реализацией соответствующего этапа, чтобы foundation не
содержал пустых behavioral models.

## 6. Alembic

Initial revision применяет проверенную STEP 2 schema целиком. Migration читает
`database/schema.sql` и сверяет frozen SHA-256. Если reference schema будет
молча изменена, migration останавливается и требует новую revision.

Это временный bridge от архитектурного reference DDL к migration history:

```text
database/schema.sql
        │ exact SHA-256
        ▼
20260822_0001_initial_schema.py
        │ Alembic transaction
        ▼
PostgreSQL app schema + public.alembic_version
```

После STEP 3 файл `database/schema.sql` считается immutable baseline. Все
следующие изменения выполняются новыми Alembic revisions. `downgrade()` initial
revision удаляет только schema `app`; shared PostgreSQL extensions не удаляются.

## 7. Health checks

### `GET /health/live`

Показывает, что ASGI process и event loop отвечают. Не зависит от PostgreSQL и
не должен вызывать restart cascade при кратком outage базы.

```json
{
  "status": "ok",
  "service": "Hazbit VPN Platform API",
  "version": "0.1.0",
  "environment": "production",
  "checks": null
}
```

### `GET /health/ready`

В исходном STEP 3 endpoint выполнял `SELECT 1` через async engine. Начиная со
STEP 4 readiness параллельно проверяет PostgreSQL и Redis и возвращает HTTP 503,
если хотя бы одна обязательная dependency недоступна:

```json
{
  "status": "not_ready",
  "service": "Hazbit VPN Platform API",
  "version": "0.1.0",
  "environment": "production",
  "checks": {
    "database": {"status": "down", "latency_ms": 10.12},
    "redis": {"status": "up", "latency_ms": 1.02}
  }
}
```

Health response не раскрывает hostname, credentials или текст DB exception.

## 8. Logging и request context

Каждый HTTP request получает UUID request ID. Валидный входящий `X-Request-ID`
сохраняется; произвольная или слишком свободная строка заменяется новым UUID.
Идентификатор возвращается в response header и добавляется через structlog
contextvars ко всем логам request scope.

HTTP access event содержит:

```json
{
  "event": "http_request_completed",
  "request_id": "...",
  "http_method": "GET",
  "http_path": "/health/live",
  "status_code": 200,
  "duration_ms": 1.34
}
```

Uvicorn access logger отключен, чтобы не создавать вторую несвязанную запись.
Production использует JSON; local development — читаемый console renderer.

## 9. Error contract

HTTP, validation, application и unexpected exceptions приводятся к одному
`application/problem+json` envelope:

```json
{
  "type": "https://api.hazbit.example/problems/validation_error",
  "title": "Validation error",
  "status": 422,
  "detail": "The request payload is invalid.",
  "instance": "/api/v1/example",
  "code": "validation_error",
  "errors": []
}
```

Unexpected exception логируется с traceback, но клиент получает нейтральный
detail без внутреннего exception message.

## 10. Как запустить

Требования: Python 3.12 и PostgreSQL 15+.

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Проверка:

```bash
curl -sS http://127.0.0.1:8000/health/live
curl -sS http://127.0.0.1:8000/health/ready
```

Эквивалентные команды Makefile:

```bash
make install
make migrate
make run
```

## 11. Quality gates

```bash
make lint
make typecheck
make test
make check
```

Integration suite требует отдельную пустую PostgreSQL database:

```bash
export HAZBIT_TEST_DATABASE_URL='postgresql://user:password@localhost:5432/hazbit_test'
make test-integration
```

Тест migration проверяет `alembic upgrade head`, наличие 39 таблиц и revision в
`public.alembic_version`. Второй integration test проверяет реальное подключение
через asyncpg и SQLAlchemy async session.

## 12. Результаты проверки STEP 3

- Ruff lint: passed;
- Ruff format: passed;
- mypy strict: passed;
- unit tests: passed;
- PostgreSQL integration tests: passed на новой пустой PostgreSQL 15 database;
- initial Alembic migration: создает 39 таблиц;
- asyncpg connection/session: passed.

## 13. Возможные улучшения

- OpenTelemetry traces и Prometheus exporter — при подключении observability
  stack;
- разделение readiness Redis по API и future worker deployment profiles;
- generated OpenAPI contract diff в CI;
- migration duration/lock budget tests на production-like snapshot;
- full ORM mappings по domain modules;
- repositories/unit-of-work только там, где они уменьшают повторяемость, без
  скрывания возможностей SQLAlchemy;
- separate settings для API, workers и bots поверх общей base config;
- container image и Docker Compose относятся к deployment stage.

## 14. Критерии готовности STEP 3

- [x] FastAPI application запускается через ASGI entry point.
- [x] Конфигурация typed и fail-fast для небезопасного production режима.
- [x] Async SQLAlchemy pool и request-scoped sessions реализованы.
- [x] STEP 2 schema включена в Alembic history.
- [x] Liveness не зависит от внешних сервисов.
- [x] Readiness проверяет PostgreSQL и возвращает 503 при outage.
- [x] Логи структурированы и связаны request ID.
- [x] Ошибки имеют единый безопасный контракт.
- [x] Unit, lint, type и PostgreSQL integration checks проходят.

Следующий этап: **STEP 4 — Authentication**: email OTP, Telegram Mini App
signature validation, JWT access tokens, rotating refresh sessions, RBAC,
rate-limiting и anti-abuse policy.

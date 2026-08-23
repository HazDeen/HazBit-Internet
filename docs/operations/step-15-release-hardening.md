# STEP 15 — VPS deployment and release hardening

## Результат

Production-контур запускает единую платформу через Docker Compose:

- `caddy`: automatic HTTPS, HTTP/3, security headers, SPA hosting и reverse proxy;
- `platform`: FastAPI и четыре durable worker-процесса под `pm2-runtime`;
- `remnawave-adapter`: закрытый service-to-service API без опубликованного порта;
- PostgreSQL 16, Redis 7 и MinIO с persistent volumes;
- Alembic migration gate перед запуском приложения;
- health checks, restart policies, read-only application filesystems и non-root users.

Публичные адреса:

| Адрес | Назначение |
|---|---|
| `https://example.com` | Customer Web/PWA |
| `https://admin.example.com` | Admin Panel |
| `https://app.example.com` | Telegram Mini App |
| `https://api.example.com` | API и Telegram webhooks |

Каждый UI также проксирует `/api/*` на backend. Поэтому production-сборки используют
same-origin `/api/v1`, без жёстко зашитого VPS-адреса.

## Требования к VPS

- Linux x86_64/arm64, минимум 2 vCPU, 4 GB RAM и 30 GB SSD;
- Docker Engine с Compose v2;
- открытые TCP 80/443 и UDP 443;
- DNS A/AAAA для root, `admin`, `app` и `api` на IP сервера;
- внешний HTTPS Remnawave panel, SMTP и Gemini API key.

PM2 работает внутри `platform` container как supervisor API и workers. Не надо
устанавливать Node.js, PM2, PostgreSQL или Caddy непосредственно на VPS.

## Первый запуск

```bash
git clone https://github.com/HazDeen/HazBit-Internet.git
cd HazBit-Internet
cp deploy/.env.production.example deploy/.env.production
chmod 600 deploy/.env.production
```

Затем заменить все `example.com`, пустые API/bot credentials и значения с
`local-`. Независимые секреты можно создать так:

```bash
openssl rand -base64 48
```

Пароли, входящие в PostgreSQL/Redis URL, должны быть URL-encoded. Значения
`POSTGRES_PASSWORD` и `HAZBIT_DATABASE__URL`, а также `REDIS_PASSWORD` и
`HAZBIT_REDIS__URL`, обязаны совпадать.

### Первый администратор и тарифы

Первый запуск выполняет idempotent bootstrap после миграций. Он создаёт каталог
`Basic`, `Premium`, `Family`, подтверждённую email identity владельца, роли `USER` и
`SUPER_ADMIN`, а также указанные реальные цены. Повторный restart не создаёт
дубликаты, не откатывает изменённые через Admin Panel цены и не активирует заново
отключённые администратором тарифы. Email из `.env` используется для recovery только
если в системе не осталось ни одного активного `SUPER_ADMIN`.

Указать email владельца и цены в minor units (`49900` = `499.00 RUB`):

```dotenv
HAZBIT_LAUNCH__SUPER_ADMIN_EMAIL=owner@your-domain.ru
HAZBIT_LAUNCH__PLAN_PRICES=[{"plan_slug":"basic","term_months":1,"duration_days":30,"currency":"RUB","amount_minor":49900},{"plan_slug":"premium","term_months":1,"duration_days":30,"currency":"RUB","amount_minor":79900},{"plan_slug":"family","term_months":1,"duration_days":30,"currency":"RUB","amount_minor":119900}]
```

Значения выше показывают формат, а не задают коммерческое решение: перед deploy
заменить суммы на фактические. Production-конфигурация отклоняет пустой email,
нулевые суммы и отсутствие цены хотя бы для одного из трёх тарифов.

### SMTP для Email OTP

Для порта `587` использовать STARTTLS:

```dotenv
HAZBIT_AUTH__EMAIL__BACKEND=smtp
HAZBIT_AUTH__EMAIL__FROM_ADDRESS=no-reply@your-domain.ru
HAZBIT_AUTH__EMAIL__FROM_NAME=Hazbit
HAZBIT_AUTH__EMAIL__SMTP_HOST=smtp.provider.example
HAZBIT_AUTH__EMAIL__SMTP_PORT=587
HAZBIT_AUTH__EMAIL__SMTP_USERNAME=no-reply@your-domain.ru
HAZBIT_AUTH__EMAIL__SMTP_PASSWORD=replace-with-smtp-key
HAZBIT_AUTH__EMAIL__SMTP_START_TLS=true
HAZBIT_AUTH__EMAIL__SMTP_USE_TLS=false
```

Для implicit TLS на порту `465` выставить `SMTP_START_TLS=false` и
`SMTP_USE_TLS=true`. Одновременное включение двух TLS-режимов запрещено. На DNS
домена отправителя настроить SPF, DKIM и DMARC; SMTP key хранить только в
`deploy/.env.production`.

Рекомендуемый запуск одной проверяемой командой:

```bash
chmod +x deploy/scripts/launch.sh
deploy/scripts/launch.sh
```

Скрипт последовательно проверяет Compose, собирает образы, валидирует production
settings до открытия сервиса, запускает stack, повторяет preflight внутри рабочего
контейнера и отправляет тестовое письмо первому `SUPER_ADMIN`. Эквивалентный ручной
запуск и проверка:

```bash
docker compose --env-file deploy/.env.production -f compose.prod.yml config --quiet
docker compose --env-file deploy/.env.production -f compose.prod.yml up -d --build
docker compose --env-file deploy/.env.production -f compose.prod.yml ps
curl -fsS https://api.example.com/health/ready
```

Entry point автоматически выполняет миграции, bootstrap и launch preflight.
Preflight проверяет PostgreSQL, Redis, наличие активных цен и роль первого
`SUPER_ADMIN`; при неполной конфигурации API не откроется.

После старта отправить реальное тестовое письмо:

```bash
docker compose --env-file deploy/.env.production -f compose.prod.yml exec platform \
  python -m app.operations.cli test-email
```

Только после получения письма открывать публичный вход для пользователей.

Caddy сам получает и обновляет TLS-сертификаты. Backend применяет Alembic migrations,
регистрирует Telegram webhooks и только затем запускает PM2. Ошибка Telegram API не
останавливает основной сервис; повторная регистрация выполняется следующим restart
или вручную:

```bash
docker compose --env-file deploy/.env.production -f compose.prod.yml exec platform \
  python -m app.workers.setup_telegram_bots
```

## Operations

```bash
# Статус
docker compose --env-file deploy/.env.production -f compose.prod.yml ps

# Все логи
docker compose --env-file deploy/.env.production -f compose.prod.yml logs -f --tail=200

# PM2-процессы
docker compose --env-file deploy/.env.production -f compose.prod.yml exec platform pm2 list

# Обновление
git pull --ff-only
docker compose --env-file deploy/.env.production -f compose.prod.yml up -d --build

# Откат приложения на известный commit
git checkout <known-good-commit>
docker compose --env-file deploy/.env.production -f compose.prod.yml up -d --build
```

Перед rollback базы проверить совместимость migration. Alembic downgrade автоматически
не выполняется, потому что потеря данных опаснее короткого controlled maintenance.

## Backup и restore

Backup содержит PostgreSQL dump, payment evidence из MinIO и SHA-256 manifest:

```bash
chmod +x deploy/scripts/backup.sh deploy/scripts/restore.sh
deploy/scripts/backup.sh
```

Копировать каталог `backups/<timestamp>` в зашифрованное off-site хранилище. Restore
останавливает Caddy и platform, заменяет текущую БД и синхронизирует object storage;
сначала проверять его на staging:

```bash
CONFIRM_RESTORE=hazbit-vpn deploy/scripts/restore.sh /absolute/path/to/backup
```

## Security and release gates

- production settings отклоняют debug/docs, wildcard hosts/CORS, local secrets,
  insecure cookies, local payment storage и HTTP к публичному Remnawave adapter;
- внутренний HTTP разрешён только для явно доверенного DNS-имени
  `remnawave-adapter`/`*.internal` в закрытой Compose network;
- adapter и database не публикуют ports на VPS;
- backend/adapter работают non-root с read-only filesystem;
- GitHub Actions проверяет Ruff, mypy, pytest, TypeScript, три Vite build,
  Compose model и все production images;
- `.env`, private keys, local databases, build output и dependencies исключены из Git.

## Observability и ограничения текущего этапа

Structured JSON logs, request IDs, health endpoints, PM2 process state и Docker health
дают базовую operational visibility. Для production масштаба следующим hardening
increment должны стать remote log/metric collection (Loki/Prometheus/OpenTelemetry),
external uptime checks, alert routing, image digest pinning, SBOM/vulnerability scan,
off-site backup schedule и staging end-to-end tests с реальными Telegram, Gemini и
Remnawave sandbox credentials.

Локальные integration tests backend требуют отдельный PostgreSQL через
`HAZBIT_TEST_DATABASE_URL` или Docker daemon. Без этого они корректно пропускаются.

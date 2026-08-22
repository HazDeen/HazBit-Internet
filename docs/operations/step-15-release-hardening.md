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

Запуск и проверка:

```bash
docker compose --env-file deploy/.env.production -f compose.prod.yml config --quiet
docker compose --env-file deploy/.env.production -f compose.prod.yml up -d --build
docker compose --env-file deploy/.env.production -f compose.prod.yml ps
curl -fsS https://api.example.com/health/ready
```

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

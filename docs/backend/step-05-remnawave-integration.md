# STEP 5 — VPN Integration с Remnawave

## 1. Что создано

STEP 5 реализует production-oriented VPN provisioning boundary для приложенной
Remnawave OpenAPI v3.3.2:

Текущая продуктовая конфигурация Hazbit использует **VLESS**. Клиенты получают
subscription URL от Remnawave и передают его совместимому VLESS-клиенту; UI не
должен обещать другой протокол, конкретный узел или статическую задержку, которых
нет в подтверждённом API state.

- отдельный deployable `remnawave-adapter` FastAPI service;
- typed panel client и versioned private API `/internal/v1`;
- bearer service authentication и production HTTPS guards;
- Platform API client, не имеющий доступа к panel token;
- desired/observed VPN account state в PostgreSQL;
- durable `vpn_sync_commands` queue с idempotency, retry, dead-letter и stale-lock reclaim;
- методы `create_user`, `disable_user`, `enable_user`, `extend_subscription`,
  `create_device`, `remove_device`, `get_user_status` и reconciliation primitives;
- encrypted storage subscription URL;
- public account/config/device API с ownership checks;
- device limits из immutable `plan_versions`;
- append-only audit events для device mutations;
- migration `20260822_0002`, добавляющая команду `create_device`;
- worker entry point для обработки команд.

## 2. Почему отдельный adapter

Platform API не вызывает Remnawave Panel напрямую:

```text
Web / Telegram Mini App
          │ user JWT
          ▼
     Platform API ───── PostgreSQL desired state
          │                    │
          │ durable command    ▼
          │              VPN sync worker
          │                    │ internal bearer
          │                    ▼
          └──────── Remnawave Adapter
                               │ panel bearer token
                               ▼
                         Remnawave v3.3.2
```

Только adapter знает panel token, vendor paths, camelCase DTO и error codes
`Axxx`. Platform работает с нормализованными моделями и безопасными error codes.
Это не дает panel-specific contract распространиться в subscriptions, devices
и будущую admin-логику.

## 3. Сопоставление Remnawave API

| Domain operation | Remnawave v3.3.2 |
|---|---|
| `create_user()` | `POST /api/users` |
| `get_user_status()` | `GET /api/users/{userId}` |
| Resolve idempotent create | `GET /api/users/by-username/{username}` |
| Update absolute entitlement | `PATCH /api/users` |
| `disable_user()` | `POST /api/users/{userId}/actions/disable` |
| `enable_user()` | `POST /api/users/{userId}/actions/enable` |
| `extend_user()` adapter capability | `POST /api/users/{userId}/actions/extend` |
| `create_device()` | `POST /api/hwid/devices` |
| `list_devices()` | `GET /api/hwid/devices/{userId}` |
| `remove_device()` | `POST /api/hwid/devices/delete` |
| Readiness | `GET /api/system/health` |

Platform extension command записывает абсолютный `desired_expires_at` и
применяет его через update, а не повторяет относительное `+N days`. Это делает
повторную обработку безопасной после timeout/crash.

## 4. Desired/observed state

PostgreSQL остается источником коммерческой истины:

- `desired_status`, `desired_expires_at` — состояние, которое должно быть в panel;
- `observed_status`, `observed_expires_at`, `last_synced_at` — последний
  подтвержденный state Remnawave;
- `last_sync_error_code` — нормализованная причина рассинхронизации;
- numeric `remnawave_user_id` — внешний identity;
- `subscription_url_ciphertext` — зашифрованная Fernet-ссылка подписки.

Username детерминирован из internal user UUID (`hz_<24 hex>`). Перед
`POST /api/users` worker делает lookup по username. Поэтому повтор после
неопределенного network outcome находит уже созданного пользователя, а не
создает дубль.

## 5. Durable commands и worker

HTTP request никогда не держит transaction открытой во время panel call.
Локальное изменение и команда фиксируются одной транзакцией. Worker:

1. забирает batch через `FOR UPDATE SKIP LOCKED`;
2. увеличивает `attempt_count` и ставит `processing`;
3. вызывает private adapter вне DB transaction;
4. атомарно сохраняет observed state и `succeeded`;
5. при transient error ставит `retry_scheduled` с exponential backoff;
6. при permanent error или исчерпании попыток ставит `dead_letter`.

Зависший `processing` command возвращается в работу после configurable lock
timeout. Create/remove device используют PostgreSQL advisory lock по
`Idempotency-Key`, поэтому concurrent duplicate requests не обходят
дедупликацию.

Команды:

```text
ensure_account  enable  disable  extend  sync
create_device   remove_device  revoke
```

Запуск worker:

```bash
cd backend
make worker-vpn
```

## 6. Device lifecycle

`POST /api/v1/devices` требует user JWT и `Idempotency-Key`:

```text
validate ownership + active VPN account
  -> lock vpn_account
  -> verify plan device_limit
  -> reserve first free slot
  -> insert local device(status=reserved)
  -> insert create_device command
  -> HTTP 202

worker
  -> list remote HWIDs first
  -> create only if HWID is absent
  -> mark local device observed
```

Удаление сначала устанавливает desired local state `revoked` и создает
`remove_device` command. Worker проверяет отсутствие/presence HWID перед
mutation, поэтому повторная доставка остается идемпотентной.

Детальная проверка приложенного OpenAPI исправила раннее архитектурное
предположение: v3.3.2 действительно поддерживает `POST /api/hwid/devices`.
ADR-006 и STEP 2 documentation обновлены.

## 7. Public Platform API

| Method | Path | Назначение |
|---|---|---|
| `GET` | `/api/v1/vpn/account` | Desired/observed account status |
| `GET` | `/api/v1/vpn/config` | Расшифрованная subscription URL |
| `GET` | `/api/v1/devices` | Активные устройства текущего user |
| `POST` | `/api/v1/devices` | Зарезервировать и поставить HWID creation в очередь |
| `DELETE` | `/api/v1/devices/{id}` | Отозвать устройство и поставить удаление в очередь |

Config response содержит `Cache-Control: no-store` и доступен только owner.
Provisioning account не вынесен в публичный endpoint: subscription/trial
application service вызывает `ensure_account()` после подтвержденной entitlement
transition. Это будет точкой подключения STEP 6 и referral/trial workflows.

## 8. Security

- Panel token существует только в adapter process.
- Platform ↔ adapter использует отдельный internal bearer token; user JWT там не принимается.
- Production требует HTTPS для panel и adapter URLs.
- Vendor response/error body не логируется и не прокидывается клиенту.
- Subscription URL шифруется отдельным secret и никогда не хранится plaintext.
- API ownership проверяется по authenticated `principal.user_id`.
- Device mutations требуют scoped idempotency key.
- Audit не содержит HWID payload, subscription URL или panel token.
- Panel GET calls имеют bounded retry; неоднозначные mutations не ретраятся внутри
  HTTP client — их безопасно повторяет desired-state worker после lookup.

Для deployment рекомендуется добавить mTLS/network policy между Platform и
adapter. Internal bearer уже обеспечивает application-level authentication, но
не заменяет transport isolation.

## 9. Конфигурация

Platform API/worker:

```text
HAZBIT_VPN__ADAPTER__BASE_URL=http://127.0.0.1:8010
HAZBIT_VPN__ADAPTER__INTERNAL_TOKEN=...
HAZBIT_VPN__SUBSCRIPTION_URL_SECRET=...
HAZBIT_VPN__COMMAND_MAX_ATTEMPTS=8
HAZBIT_VPN__COMMAND_LOCK_TIMEOUT_SECONDS=300
HAZBIT_VPN__COMMAND_POLL_INTERVAL_SECONDS=1
HAZBIT_VPN__RETRY_BASE_SECONDS=5
HAZBIT_VPN__RETRY_MAX_SECONDS=3600
```

Adapter:

```text
REMNAWAVE_ADAPTER_PANEL_BASE_URL=https://panel.example.com
REMNAWAVE_ADAPTER_PANEL_TOKEN=...
REMNAWAVE_ADAPTER_INTERNAL_TOKEN=...
REMNAWAVE_ADAPTER_CONNECT_TIMEOUT_SECONDS=2
REMNAWAVE_ADAPTER_READ_TIMEOUT_SECONDS=10
REMNAWAVE_ADAPTER_MAX_GET_ATTEMPTS=3
```

## 10. Как запустить

```bash
# 1. Database migration
cd backend
.venv/bin/alembic upgrade head

# 2. Adapter
cd ../services/remnawave-adapter
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/uvicorn remnawave_adapter.main:app --host 127.0.0.1 --port 8010

# 3. Platform API and worker (separate processes)
cd ../../backend
make run
make worker-vpn
```

Adapter liveness не зависит от panel. `/health/ready` проверяет Remnawave
`/api/system/health`. Platform readiness намеренно не вызывает panel: временный
outage обрабатывается durable queue и не должен выводить customer API из
service discovery.

## 11. Проверки

Покрыты:

- exact v3.3.2 request/response mapping;
- bearer isolation Platform → adapter → panel;
- transient GET retries и vendor error normalization;
- отсутствие secret leakage при contract mismatch;
- encrypted subscription URL round trip;
- migration новой command type;
- PostgreSQL provisioning lifecycle;
- device slot limit и `reserved → observed → revoked`;
- duplicate-safe preflight remote lookup;
- audit events;
- transient worker failure → `retry_scheduled` и future `next_attempt_at`;
- API route contract и production configuration guards.

## 12. Возможные улучшения

- mTLS и short-lived service JWT со scopes вместо long-lived opaque token;
- Prometheus metrics для latency/error code/queue age/dead letters;
- periodic full device reconciliation и drift repair scheduler;
- subscription URL encryption key versioning/rotation;
- admin UI для replay/dead-letter commands;
- per-account command sequencing для parallel multi-worker throughput;
- contract test против dedicated staging Remnawave instance;
- webhook ingestion, если panel deployment публикует надежные user/device events.

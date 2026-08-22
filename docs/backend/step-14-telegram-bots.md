# STEP 14 — Telegram Bots

## Результат

STEP 14 добавляет два независимых Telegram bot channel поверх существующих
application services:

- **customer bot** — onboarding, Mini App login, статус подписки/VPN, устройства,
  оплата и переход в поддержку;
- **operations bot** — уведомления о payment manual review и urgent tickets,
  approve/reject платежа из подписанного inline callback.

Боты не содержат отдельной копии subscription, payment или support правил.
Customer status строится через `PortalService`, payment review проходит через
`PaymentService`, а Telegram settlement использует общий `approve_payment` и
ledger/outbox pipeline.

## HTTP endpoints

Telegram вызывает два webhook endpoint:

| Method | Endpoint | Bot |
|---|---|---|
| `POST` | `/api/v1/bots/customer/webhook` | customer |
| `POST` | `/api/v1/bots/operations/webhook` | operations |

Оба endpoint исключены из OpenAPI, потому что не являются публичным customer API.
Каждый запрос обязан содержать `X-Telegram-Bot-Api-Secret-Token`; значение
сравнивается constant-time с отдельным secret конкретного бота.

## Customer bot

Поддерживаются команды:

- `/start`, `/help` — onboarding и главное меню;
- `/status` — subscription, observed VPN state, devices и open tickets;
- `/vpn` — deep link в раздел устройств Mini App;
- `/pay` — deep link в тарифы/оплату;
- `/support` — deep link в support.

Если задан `required_channel_id`, `/start` вызывает `getChatMember` и показывает
кнопку повторной проверки. Привязка identity не выполняется по недоверенному
`telegram_user_id`: пользователь открывает Mini App, а backend проверяет signed
`initData` существующим STEP 4 flow.

`successful_payment` поддерживается отдельно. `invoice_payload` обязан быть
HMAC-signed callback с action `inv` и payment UUID; затем проверяются владелец,
status, amount и currency. Ledger posting и activation outbox остаются
идемпотентными.

## Operations bot

Доступ разрешён только Telegram identity, связанной с активным `users` account и
ролью `SUPPORT`, `ADMIN` или `SUPER_ADMIN`. Payment approve/reject дополнительно
требует `ADMIN` или `SUPER_ADMIN`.

Inline callbacks содержат action, payment UUID, expected version, expiration и
усечённую HMAC-SHA256 подпись. Полный callback не превышает Telegram limit 64
bytes. Optimistic version предотвращает повторное решение после другого
reviewer.

## Idempotency и anti-abuse

- webhook update ID резервируется в Redis коротким processing lock;
- после успеха сохраняется receipt с TTL;
- duplicate update получает `200 OK`, но повторно не dispatch'ится;
- unexpected failure освобождает lock, чтобы Telegram retry мог восстановить
  обработку;
- customer и operations updates имеют независимые sliding-window rate limits;
- callback имеет TTL и constant-time HMAC verification;
- операции дополнительно защищены database RBAC и payment optimistic locking.

## Outbox notifications

Payment AI создаёт `payment.manual_review_requested`. Support уже публикует
`support.ticket.created`; worker выбирает только `priority=urgent`.

Запуск:

```bash
cd backend
make worker-telegram
```

Worker claim'ит события через `FOR UPDATE SKIP LOCKED`, выставляет lease в
`available_at`, отправляет во все `operations_chat_ids`, затем ставит
`published_at`. Ошибки получают exponential backoff и безопасный `last_error`.

## Конфигурация Telegram

Основные переменные перечислены в `backend/.env.example`:

- `HAZBIT_AUTH__TELEGRAM__BOT_TOKEN` — customer bot и Mini App initData secret;
- `HAZBIT_TELEGRAM_BOTS__OPERATIONS_BOT_TOKEN`;
- отдельные customer/operations webhook secrets;
- callback HMAC secret;
- public HTTPS API, Mini App и Admin URLs;
- optional required channel;
- operations chat IDs.

После публикации HTTPS endpoints зарегистрировать webhook, команды и Mini App
menu button:

```bash
cd backend
make telegram-webhooks
```

Production validation запрещает local secrets, HTTP URLs и пустой список
operations chats.

## Проверки

- callback round-trip, size limit, tampering и expiry;
- Telegram aliases и `successful_payment` payload parsing;
- webhook secret validation;
- duplicate update acknowledgement без повторного dispatch;
- Ruff, mypy и unit test suite.

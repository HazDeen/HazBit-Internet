# STEP 9 — Support Ticket System

## 1. Результат

STEP 9 реализует диалог пользователя со службой поддержки:

```text
User creates ticket → OPEN
  → Support/Admin replies → WAITING_USER
  → User replies → OPEN
  → Operator investigates → IN_PROGRESS
  → Operator resolves → CLOSED
```

Поддерживаются четыре состояния из product brief:

| Product status | API/DB value | Назначение |
|---|---|---|
| `OPEN` | `open` | Новый вопрос или новый ответ пользователя |
| `IN_PROGRESS` | `in_progress` | Тикет активно обрабатывается |
| `WAITING_USER` | `waiting_user` | Support ожидает ответ пользователя |
| `CLOSED` | `closed` | Обращение завершено |

Тикет получает UUID для API и последовательный `public_number` для общения с
пользователем и оператором.

## 2. Customer API

Все endpoints требуют Bearer JWT и изолируют данные по текущему пользователю:

| Method | Path | Назначение |
|---|---|---|
| `POST` | `/api/v1/tickets` | Создать тикет вместе с первым сообщением |
| `GET` | `/api/v1/tickets` | Список собственных тикетов, фильтр по status |
| `GET` | `/api/v1/tickets/{id}` | Тикет и начальная страница переписки |
| `GET` | `/api/v1/tickets/{id}/messages` | Cursor pagination сообщений |
| `POST` | `/api/v1/tickets/{id}/messages` | Отправить новое сообщение |

Пользователь не может получить чужой тикет: API возвращает одинаковый `404`, не
раскрывая существование ресурса. `internal_note` никогда не попадает в customer
responses.

Создание и отправка сообщения требуют `Idempotency-Key`. Тот же key и payload
возвращают исходный ресурс; тот же key с другим payload даёт `409`.

## 3. Support/Admin API

Endpoints доступны ролям `support`, `admin` и `super_admin`:

| Method | Path | Назначение |
|---|---|---|
| `GET` | `/api/v1/admin/tickets` | Рабочая очередь с фильтрами status/mine/unassigned |
| `GET` | `/api/v1/admin/tickets/{id}` | Полный тикет, включая internal notes |
| `GET` | `/api/v1/admin/tickets/{id}/messages` | Полная cursor-paginated переписка |
| `POST` | `/api/v1/admin/tickets/{id}/messages` | Публичный reply или internal note |
| `PATCH` | `/api/v1/admin/tickets/{id}` | Status, priority и assignee |

Первый ответ автоматически назначает тикет сотруднику, если assignee отсутствует.
Явно назначить тикет можно только active пользователю с ролью support/admin.
Очередь сортируется `urgent → high → normal → low`, затем по времени ожидания.

`PATCH` принимает `expected_version`: два оператора не могут молча перезаписать
решения друг друга. При stale version API возвращает `ticket_version_conflict`.

## 4. Status workflow

Разрешённые административные переходы:

```text
OPEN          → IN_PROGRESS | WAITING_USER | CLOSED
IN_PROGRESS   → OPEN | WAITING_USER | CLOSED
WAITING_USER  → OPEN | IN_PROGRESS | CLOSED
CLOSED        → OPEN
```

Дополнительные правила:

- публичный admin reply по умолчанию ставит `WAITING_USER`;
- user reply из `WAITING_USER` ставит `OPEN` и возвращает тикет в очередь;
- `closed_at` существует только в `CLOSED`;
- закрытый тикет не принимает публичные сообщения;
- internal note разрешена в закрытом тикете и не меняет status;
- изменение status добавляет системное сообщение в историю.

## 5. Сообщения и приватность

Типы сообщений:

- `message` — виден пользователю и support;
- `internal_note` — виден только support/admin;
- `system` — серверная запись о смене состояния.

Тексты сообщений не копируются в AuditLog или Outbox. Эти журналы содержат только
идентификаторы и state metadata, что уменьшает распространение потенциально
чувствительных данных. Тела остаются в `ticket_messages` согласно support retention
policy.

Таблица `ticket_attachments` уже предусмотрена STEP 2, но upload endpoint не входит
в текущий product scope. Его можно добавить поверх существующего безопасного object
storage pipeline.

## 6. Транзакции, события и уведомления

Ticket/message, status transition, AuditLog, idempotency record и Outbox event
фиксируются атомарно. HTTP request не вызывает Telegram/email напрямую.

Events:

- `support.ticket.created`;
- `support.ticket.user_replied`;
- `support.ticket.admin_replied`;
- `support.ticket.updated`.

Будущий notification worker сможет доставлять эти события в Telegram и email без
риска потерять обращение при временной недоступности внешнего сервиса. Internal note
не создаёт пользовательское событие.

## 7. Database

STEP 2 уже содержал все необходимые таблицы:

- `tickets` — owner, assignee, category, priority, status и optimistic version;
- `ticket_messages` — immutable conversation history;
- `ticket_attachments` — связь с object storage;
- `idempotency_records` — защита повторов;
- `audit_logs` и `outbox_events` — аудит и side effects.

Поэтому новая Alembic migration для STEP 9 не потребовалась; актуальный head остаётся
`20260822_0004`.

## 8. Конфигурация и anti-abuse

```text
HAZBIT_SUPPORT__CREATE_RATE_LIMIT_PER_DAY=10
HAZBIT_SUPPORT__MESSAGE_RATE_LIMIT_PER_HOUR=120
HAZBIT_SUPPORT__IDEMPOTENCY_TTL_HOURS=24
HAZBIT_SUPPORT__INITIAL_MESSAGE_LIMIT=100
```

Customer mutations защищены Redis sliding-window rate limits. Subject ограничен
200 символами, сообщение — 5000 символами, пустые значения после trim отклоняются.

## 9. Проверки

Unit tests покрывают API registration и request validation. PostgreSQL integration
test проверяет:

- создание тикета и первого сообщения;
- idempotent retry и конфликт изменённого payload;
- недоступность чужого тикета;
- unassigned admin queue;
- support reply и auto-assignment;
- скрытие internal note от пользователя;
- `WAITING_USER → OPEN` после ответа пользователя;
- допустимые переходы и optimistic version conflict;
- проверку assignee role;
- закрытие, запрет сообщения и переоткрытие;
- pagination, AuditLog и Outbox counts.

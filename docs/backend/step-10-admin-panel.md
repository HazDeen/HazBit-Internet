# STEP 10 — Admin Panel

## 1. Результат

STEP 10 добавляет защищённый operational dashboard для ролей `admin` и
`super_admin`. Панель объединяет данные пользователей, подписок, платежей,
support, промокодов, тарифов и VPN-устройств, не копируя бизнес-логику в UI.

Разделы frontend:

- Dashboard;
- Users;
- Subscriptions;
- Payments;
- Tickets;
- Promo Codes;
- Plans;
- Family Groups;
- VPN Devices;
- Settings.

## 2. Admin API

| Method | Path | Назначение |
|---|---|---|
| `GET` | `/api/v1/admin/dashboard` | KPI, очереди и 7-дневный trend |
| `GET` | `/api/v1/admin/users` | Поиск, status filter и pagination |
| `GET` | `/api/v1/admin/users/{id}` | Профиль, платежи и устройства |
| `POST` | `/api/v1/admin/users/{id}/block` | Блокировка пользователя |
| `POST` | `/api/v1/admin/users/{id}/unblock` | Снятие блокировки |
| `POST` | `/api/v1/admin/users/{id}/subscription/extend` | Продление на 1–365 дней |
| `PATCH` | `/api/v1/admin/users/{id}/subscription/plan` | Смена активной версии тарифа |
| `GET` | `/api/v1/admin/users/{id}/devices` | Устройства пользователя |
| `GET` | `/api/v1/admin/subscriptions` | Реестр подписок |
| `GET` | `/api/v1/admin/payments` | Реестр платежей |
| `GET` | `/api/v1/admin/plans` | Тарифы, версии и цены |
| `POST` | `/api/v1/admin/plans` | Создание тарифа и первой immutable-версии |
| `PATCH` | `/api/v1/admin/plans/{id}` | Изменение метаданных тарифа |
| `POST` | `/api/v1/admin/plans/{id}/versions` | Новая версия entitlement и цен |
| `DELETE` | `/api/v1/admin/plans/{id}` | Безопасная архивация тарифа |
| `GET` | `/api/v1/admin/family-groups` | Реестр семейных групп |
| `GET` | `/api/v1/admin/family-groups/{id}` | Группа и активные участники |
| `DELETE` | `/api/v1/admin/family-groups/{id}/members/{user_id}` | Удаление участника с audit reason |
| `DELETE` | `/api/v1/admin/family-groups/{id}/invitations/{invitation_id}` | Отзыв приглашения |
| `GET` | `/api/v1/admin/vpn-devices` | Общий парк VPN-устройств |
| `GET` | `/api/v1/admin/settings` | Только безопасные runtime-параметры |

Подтверждение платежа использует существующий audited endpoint
`POST /api/v1/admin/payments/{id}/review` с `expected_version`.

## 3. Users page

Таблица показывает отдельные колонки `ID`, `Email`, `Telegram ID`,
`Subscription`, `Devices`, `Trial`, `Payments`, `Status`, `Actions`.
Профиль пользователя открывается в центрированном modal window с blur backdrop и показывает identity,
entitlement, статистику платежей и фактический список VPN-устройств.

Доступные действия:

- блокировать и разблокировать пользователя;
- продлевать текущую подписку;
- менять активную версию тарифа;
- просматривать устройства;
- подтверждать платежи из manual review.

Каждая мутация требует audit reason. Администратор не может заблокировать сам
себя.

## 4. Надёжность и безопасность

Блокировка атомарно меняет статус пользователя, отзывает все активные refresh
sessions, переводит VPN account в `disabled` и создаёт durable Remnawave command.
Разблокировка, продление и смена тарифа также синхронизируют entitlement через
очередь `vpn_sync_commands`, а не прямым HTTP-вызовом из request transaction.

Все изменения записывают `AuditLog` и transactional Outbox event. Продление
создаёт отдельный непересекающийся `subscription_period` с source `admin`.
Settings endpoint никогда не возвращает JWT, OTP, Gemini или Remnawave secrets.

Удаление тарифа или промокода является soft archive: связанные подписки,
redemptions и финансовый audit trail остаются воспроизводимыми.

Frontend использует Email OTP, short-lived JWT в `sessionStorage`, rotating
HttpOnly refresh cookie и CSRF token для refresh. Backend повторно применяет
RBAC ко всем admin routes; скрытие кнопки в UI не является контролем доступа.

Для локального SPA разрешены только явно заданные CORS origins. Wildcard CORS
запрещён production validation.

## 5. Frontend

React 19 + TypeScript + Vite находятся в `frontend/`. Production API URL задаётся
через `VITE_API_URL`. Реалистичный showcase режим включается только явно:

```bash
cd frontend
npm install
VITE_DEMO_MODE=true npm run dev
```

Интерфейс адаптивен: fixed navigation превращается в mobile drawer, таблицы
получают горизонтальный scroll, dashboard cards и operational panels перестраиваются
на узких экранах. Учитывается `prefers-reduced-motion`.

В панели работают payment review/details, ticket chat и status transition,
создание/редактирование/архивация промокодов и тарифов, notification inbox с
переходами в operational queues, а также просмотр Family Groups и участников.

## 6. Проверки

Unit tests проверяют регистрацию всех admin routes и ограничения request schemas.
PostgreSQL integration test проверяет dashboard aggregation, user search/detail,
self-block protection, отзыв сессии, disable/enable VPN projection, продление,
смену тарифа, catalog/list endpoints, AuditLog и Outbox.

Frontend проходит `tsc --noEmit` и production build. Визуально проверены desktop
Dashboard, Users table, user drawer, action dialog, mobile navigation и responsive
Dashboard; browser console остаётся без warnings/errors.

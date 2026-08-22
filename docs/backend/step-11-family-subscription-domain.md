# STEP 11 — Family Subscription Domain

## 1. Результат

STEP 11 превращает подготовленные в STEP 2 таблицы Family в полноценный
доменный vertical slice. Владельцы семейных подписок могут управлять группой и
приглашениями, участники — принимать приглашение или выходить, а entitlement
асинхронно проецируется в Remnawave через durable command queue.

Состав домена:

- `family_groups` — группа, владелец, подписка и snapshot лимита участников;
- `family_invitations` — одноразовые приглашения с хешем токена и TTL;
- `family_members` — история вступления и выхода без физического удаления;
- `vpn_accounts`, `devices`, `vpn_sync_commands` — общий VPN entitlement;
- `audit_logs`, `outbox_events` — проверяемый журнал и уведомления.

Новая миграция не требуется: STEP 11 активирует схему, заранее созданную в
initial migration. Модель `FamilyInvitation` теперь также зарегистрирована в
SQLAlchemy metadata.

## 2. Customer API

Все пути находятся под `/api/v1`, требуют JWT и используют текущего
пользователя как actor.

| Method | Path | Назначение |
|---|---|---|
| `POST` | `/family/groups` | Создать группу для активной family-подписки |
| `GET` | `/family/group` | Получить свою группу, участников, приглашения и лимиты |
| `PATCH` | `/family/groups/{group_id}` | Переименовать группу владельцем |
| `POST` | `/family/groups/{group_id}/invitations` | Пригласить по `user_id` или email |
| `GET` | `/family/invitations` | Входящие приглашения пользователя |
| `POST` | `/family/invitations/accept` | Принять приглашение по одноразовому токену |
| `POST` | `/family/invitations/decline` | Отклонить приглашение |
| `DELETE` | `/family/groups/{group_id}/invitations/{invitation_id}` | Отозвать приглашение владельцем |
| `DELETE` | `/family/members/me` | Выйти из группы |
| `DELETE` | `/family/groups/{group_id}/members/{user_id}` | Удалить участника владельцем |

У приглашения может быть ровно одна цель: `invited_user_id` или
`invited_email`. Исходный token возвращается только в ответе на создание;
в PostgreSQL хранится HMAC digest. Срок действия по умолчанию — 72 часа.

## 3. Инварианты и конкурентный доступ

- один пользователь может состоять только в одной активной группе;
- одна подписка имеет не более одной неархивной группы;
- владелец является первым участником и не может покинуть или удалить себя;
- число активных участников вместе с pending invitations не превышает
  `family_member_limit` snapshot группы;
- участник с другим live VPN entitlement не может принять приглашение, пока
  конфликт не разрешён;
- создание, приглашение, принятие и удаление сериализуются PostgreSQL advisory
  locks и повторно проверяют инварианты внутри транзакции;
- истёкшие приглашения исключаются из inbox и capacity.

Лимит устройств считается по всей shared subscription, а не отдельно для
каждого VPN account. Поэтому участники семьи совместно расходуют
`plan_versions.device_limit`.

## 4. Remnawave projection

Принятие приглашения создаёт или активирует `vpn_account` участника на подписке
владельца и ставит идемпотентную команду `ensure_account`. Команда содержит
expiration, traffic/device limits и squad IDs из immutable plan version.

Выход или удаление участника переводит его account в desired state `disabled`
и ставит команду `disable`. Внешний HTTP-вызов не выполняется внутри customer
transaction: worker безопасно повторяет команду, а reconciler устраняет drift.

## 5. Security и anti-abuse

- JWT authentication и owner/member authorization на каждом endpoint;
- RBAC `ADMIN`/`SUPER_ADMIN` для административного вмешательства;
- rate limits по user ID, хешированному IP и хешированному device fingerprint;
- opaque invitation tokens, HMAC digest at rest и ограниченный TTL;
- audit запись для каждой мутации с IP, user agent и request ID;
- transactional Outbox events `family.*` для customer/admin notifications;
- CORS разрешает явный `X-Device-Fingerprint` header;
- email нормализуется, self-invite и повторные pending invitations запрещены.

Параметры задаются через `HAZBIT_FAMILIES__INVITATION_TTL_HOURS` и
`HAZBIT_FAMILIES__INVITE_LIMIT_PER_DAY`.

## 6. Admin operations и UI

Admin API дополнен операциями:

| Method | Path | Назначение |
|---|---|---|
| `DELETE` | `/admin/family-groups/{group_id}/members/{user_id}` | Удалить участника с обязательной причиной |
| `DELETE` | `/admin/family-groups/{group_id}/invitations/{invitation_id}` | Отозвать pending invitation |

Family command center показывает владельца, тариф, состояние подписки,
участников, приглашения, member/device capacity и статус Remnawave projection.
Интерфейс адаптивен, полностью работает в RU/EN и сохраняет общий premium
visual language панели: blur backdrop, gradient entitlement card, мягкие
анимации, компактные operational actions.

## 7. Проверки

- unit: customer/admin route registration, bearer security и request validation;
- integration: create → invite → accept → Remnawave `ensure_account` → remove →
  Remnawave `disable`, AuditLog и Outbox;
- backend: Ruff, Mypy и unit Pytest;
- frontend: TypeScript check и production Vite build;
- browser QA: RU desktop Family list/dialog и revoke action; mobile breakpoint
  закреплён отдельными responsive rules и проверяется production build.

Integration test требует отдельный PostgreSQL URL в
`HAZBIT_TEST_DATABASE_URL`; без него тест корректно помечается skipped.

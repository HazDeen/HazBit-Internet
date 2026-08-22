# STEP 8 — Promo Codes

## 1. Результат

STEP 8 реализует два типа промокодов из product brief:

```text
discount_percent: 20%
  → preview for selected plan price
  → payment intent with reduced expected amount
  → approved payment posts cash credit + promo credit

free_days: 30 days
  → immediate atomic redemption
  → create/extend subscription period
  → durable VPN synchronization command
```

Code сравнивается case-insensitive через PostgreSQL `citext`; API дополнительно
нормализует его в uppercase. Проверки срока действия, общего лимита, лимита на
пользователя, валюты и тарифного scope выполняются сервером.

## 2. API

Customer endpoints требуют Bearer JWT:

| Method | Path | Назначение |
|---|---|---|
| `POST` | `/api/v1/promo-codes/preview` | Проверить code и рассчитать скидку/доступный free plan |
| `POST` | `/api/v1/promo-codes/redeem` | Активировать `free_days` code |
| `GET` | `/api/v1/promo-codes/redemptions` | История применений текущего пользователя |

Admin/Super Admin endpoints:

| Method | Path | Назначение |
|---|---|---|
| `POST` | `/api/v1/admin/promo-codes` | Создать промокод |
| `GET` | `/api/v1/admin/promo-codes` | Список, scope и фактический usage count |
| `PATCH` | `/api/v1/admin/promo-codes/{id}` | Включить/отключить, изменить expiration/usage limit |

Discount code передаётся при создании payment intent:

```json
{
  "plan_price_id": "019...",
  "promo_code": "SAVE20"
}
```

`PaymentResponse` содержит исходную цену, скидку и итоговую сумму:

```json
{
  "original_amount_minor": 50000,
  "discount_amount_minor": 10000,
  "expected_amount_minor": 40000,
  "promo_code": "SAVE20"
}
```

Деньги всегда представлены integer minor units; float для денежных расчётов не
используется.

## 3. Создание и eligibility

Admin задаёт:

- `code`;
- `promo_type`: `discount_percent` или `free_days`;
- `value`: процент или число дней;
- `starts_at` и `expires_at`;
- `usage_limit` и `per_user_limit`;
- необязательную валюту для discount;
- необязательный список `plan_version_ids`.

Пустой список планов означает “доступен для всех тарифов”. Процент ограничен
диапазоном 1–99, чтобы bank-transfer intent всегда имел положительную сумму.
Free-days code без plan scope использует latest active version плана
`HAZBIT_PROMOTIONS__DEFAULT_PLAN_SLUG`.

Redemption сериализуется advisory locks по code и паре user+code. Usage считается
по non-revoked redemptions. Неоплаченный истёкший intent и rejected/cancelled payment
не занимают лимит. Manual rejection ставит `revoked_at` у discount redemption.

## 4. Discount и ledger

Discount резервируется в той же транзакции, где создаётся payment intent. Поэтому
невозможен payment с уменьшенной суммой без redemption или redemption без payment.
Повторный `Idempotency-Key` с тем же plan/code возвращает тот же intent; другой
plan/code даёт conflict.

После approve создаются две balanced double-entry операции:

1. `payment_credit`: фактически полученная сумма → user wallet;
2. `promo_credit`: величина скидки, `promo_expense` → user wallet.

Например, цена 500 RUB и скидка 20% дают cash credit 400 RUB и promo credit
100 RUB. Wallet получает полные 500 RUB для будущего subscription debit, а скидка
явно отражается как расход промокампании.

## 5. Free subscription

`free_days` redemption в одной PostgreSQL transaction:

1. блокирует promo, user и live subscription;
2. создаёт immutable `promo_redemptions` row;
3. создаёт subscription либо продлевает её ровно от текущего конца;
4. добавляет non-overlapping `subscription_periods(source_type=promo)`;
5. создаёт/обновляет local VPN account;
6. ставит idempotent `ensure_account`/`extend` command;
7. пишет AuditLog и transactional Outbox event.

Если live subscription использует другой plan version, scoped promo отклоняется:
промокод не может продлить неподходящий тариф. Suspended subscription получает
дни, но redemption не обходит suspension и не включает VPN.

Внешний вызов Remnawave не выполняется внутри HTTP transaction. Его надёжно
доставляет существующий процесс:

```bash
cd backend
make worker-vpn
```

## 6. Database и идемпотентность

STEP 2 уже содержал business tables:

- `promo_codes`;
- `promo_code_plan_versions`;
- `promo_redemptions`.

Migration `20260822_0004` добавляет partial unique indexes: один active redemption
на payment и один active redemption на subscription period. Остальные гарантии:

- unique case-insensitive code;
- PostgreSQL row/advisory locks для usage limits;
- exclusion constraint против пересечения subscription periods;
- unique transaction/outbox/VPN idempotency keys;
- append-only audit и redemption history.

Events:

- `promo.discount.applied` — скидка закреплена за payment intent;
- `promo.discount.redeemed` — payment approved и promo credit posted;
- `promo.free_days.redeemed` — entitlement и VPN command сохранены.

## 7. Конфигурация

```text
HAZBIT_PROMOTIONS__DEFAULT_PLAN_SLUG=basic
HAZBIT_PROMOTIONS__PREVIEW_RATE_LIMIT_PER_HOUR=30
HAZBIT_PROMOTIONS__REDEEM_RATE_LIMIT_PER_HOUR=10
```

Preview и redeem защищены Redis sliding-window rate limit. Создание и изменение
кодов доступны только ролям `admin` и `super_admin`.

## 8. Проверки

Unit tests проверяют API registration, normalization и validation. PostgreSQL
integration test покрывает:

- admin create/list/update;
- 20% preview и payment application;
- idempotent payment intent;
- общий и per-user usage limits;
- cash + promo double-entry ledger;
- 30 free days, subscription period и VPN command;
- redemption history, AuditLog и Outbox events;
- отключение промокода.

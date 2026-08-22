# STEP 7 — Referral System

## 1. Результат

STEP 7 реализует production-ready referral lifecycle из product brief:

```text
User A creates/shares code
  → User B claims code
  → eligibility + anti-abuse
      ├─ allow  → qualified
      ├─ review → attributed → admin approve | reject
      └─ deny   → rejected
  → reward worker
      ├─ User B: +3 days and TrialGrant
      └─ User A: +5 days
  → referral rewarded + VPN sync commands + outbox
```

Attribution и выдача наград разделены. HTTP claim не держит транзакцию во время
внешнего VPN вызова и не изменяет mutable “days balance”. Каждая награда получает
собственный `subscription_periods` row со ссылкой на `referral_rewards`.

## 2. API

Customer endpoints требуют Bearer JWT и работают только с текущим user:

| Method | Path | Назначение |
|---|---|---|
| `POST` | `/api/v1/referrals/code` | Идемпотентно получить или создать active code |
| `POST` | `/api/v1/referrals/claim` | Claim code и выполнить eligibility/risk evaluation |
| `GET` | `/api/v1/referrals/statistics` | Invites, statuses, pending/granted days и собственный referred reward |
| `GET` | `/api/v1/admin/referrals/review-queue` | Suspicious claims, только admin/super_admin |
| `POST` | `/api/v1/admin/referrals/{id}/review` | Manual approve/reject с обязательной причиной |

Claim принимает normalized ASCII code и необязательный `X-Device-Fingerprint`.
Telegram Bot позже передаст payload `/start ref_<code>` в этот API после завершения
проверенного Telegram authentication flow. URL для share формируется из
`HAZBIT_REFERRALS__SHARE_URL_PREFIX`.

## 3. Eligibility

Referral trial доступен только если:

- code active, не истёк и не исчерпал usage limit;
- referrer и referred — разные active users;
- referred account создан внутри configurable new-user window;
- у referred ещё нет referral attribution;
- нет `trial_grants`, subscriptions и approved payments;
- один referred user не может сменить code повторным request.

Code row и referred user сериализуются PostgreSQL locks/advisory lock. Usage limit
проверяется под lock, поэтому concurrent claims не превышают лимит. Повтор того же
claim возвращает существующий referral; другой code даёт conflict.

## 4. Anti-abuse

IP и device fingerprint хэшируются существующим keyed `SignalHasher`; raw fingerprint
не хранится. Policy проверяет сигналы последних 30 дней:

- совпадение device с referrer — deterministic deny;
- совпадение IP с referrer — manual review;
- shared-IP velocity и reused-device thresholds — manual review;
- отсутствие fingerprint повышает risk, но само по себе не блокирует claim.

Результат записывается в `risk_signals(signal_type=referral)` с score, decision и
машиночитаемыми reasons. Customer response не раскрывает чужие IP/device данные.
Claim endpoints дополнительно защищены Redis sliding-window rate limits по user и
keyed IP hash.

## 5. Reward worker

Worker выбирает `qualified` referrals через `FOR UPDATE SKIP LOCKED` и в одной
PostgreSQL transaction:

1. блокирует обоих beneficiaries;
2. проверяет наличие ровно двух pending rewards;
3. создаёт или продлевает subscription каждого user;
4. добавляет non-overlapping referral subscription period;
5. для referred создаёт единственный `TrialGrant(duration_days=3)`;
6. переводит обе rewards в `granted`;
7. создаёт/обновляет local VPN account и durable Remnawave command;
8. пишет audit и transactional outbox events;
9. только после успеха обеих сторон ставит referral в `rewarded`.

Для нового user используется последняя active version плана
`HAZBIT_REFERRALS__DEFAULT_PLAN_SLUG`. Если subscription уже active, reward начинает
действовать ровно после `current_period_ends_at`; PostgreSQL exclusion constraint
не допускает пересечение periods. Suspended subscription получает дни, но reward не
обходит suspension и не включает VPN.

Повторный worker run безопасен благодаря status state machine, unique
`(referral_id, reward_side)`, unique outbox keys и idempotent VPN command keys.

Запуск:

```bash
cd backend
make worker-referrals
```

VPN mutations выполняет уже существующий `make worker-vpn`. Повторный
`ensure_account` теперь приводит найденного Remnawave user к абсолютным expiry,
traffic и device limits; последовательные бонусы не теряются.

## 6. Statistics

`GET /referrals/statistics` возвращает:

- active code и готовый Telegram share URL;
- total/attributed/qualified/rewarded/rejected counts;
- pending и granted referrer days;
- состояние referral, по которому пригласили текущего user;
- фактически granted referred days.

Статистика строится из referrals/rewards, а не из кешированного счётчика, поэтому
остаётся согласованной после manual review и retry worker.

## 7. Конфигурация

```text
HAZBIT_REFERRALS__REFERRED_DAYS=3
HAZBIT_REFERRALS__REFERRER_DAYS=5
HAZBIT_REFERRALS__DEFAULT_PLAN_SLUG=basic
HAZBIT_REFERRALS__CODE_LENGTH=10
HAZBIT_REFERRALS__CLAIM_NEW_USER_MAX_AGE_DAYS=14
HAZBIT_REFERRALS__SHARED_IP_REVIEW_THRESHOLD=5
HAZBIT_REFERRALS__SHARED_DEVICE_REVIEW_THRESHOLD=2
HAZBIT_REFERRALS__CLAIM_RATE_LIMIT_PER_HOUR=8
HAZBIT_REFERRALS__WORKER_BATCH_SIZE=25
HAZBIT_REFERRALS__WORKER_POLL_INTERVAL_SECONDS=1
HAZBIT_REFERRALS__SHARE_URL_PREFIX=https://t.me/your_bot?start=ref_
```

Перед production запуском замените `example_bot` на реальный bot username и
убедитесь, что seed содержит active `basic` plan version.

## 8. Database и события

STEP 2 уже содержал необходимые таблицы и constraints, поэтому новая business-table
migration не понадобилась:

- `referral_codes` — unique code и один active code на owner;
- `referrals` — единственная attribution на referred user;
- `referral_rewards` — отдельные referred/referrer rewards;
- `trial_grants` — защита от повторного trial;
- `subscription_periods` — история entitlement;
- `vpn_sync_commands` — durable provisioning;
- `audit_logs` и `outbox_events` — append-only observability/side effects.

Events:

- `referral.reward.granted` — по одному на beneficiary;
- `referral.rewarded` — после успешной выдачи обеих сторон.

## 9. Проверки

Unit tests покрывают risk policy, code normalization и API contract. PostgreSQL
integration test проверяет:

- code creation и idempotent claim;
- automatic qualification;
- B +3 days и единственный TrialGrant;
- A +5 days;
- subscription periods, VPN commands и outbox;
- повторный worker без duplicate rewards;
- statistics;
- suspicious shared IP → admin queue → manual approval;
- последовательное продление referrer до +10 days;
- self-referral rejection.

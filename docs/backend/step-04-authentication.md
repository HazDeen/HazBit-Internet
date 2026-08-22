# STEP 4 — Authentication

## 1. Что создано

STEP 4 добавляет production-oriented authentication domain поверх схемы STEP 2 и
backend foundation STEP 3:

- Email OTP login/registration с одноразовым challenge и ограничением попыток;
- Telegram Mini App authentication через серверную проверку `initData`;
- короткоживущий JWT access token;
- opaque refresh token в `HttpOnly` cookie с ротацией и reuse detection;
- double-submit CSRF для refresh/logout;
- RBAC для `SUPER_ADMIN`, `ADMIN`, `SUPPORT`, `USER`;
- Redis sliding-window rate limiting;
- IP/device anti-abuse scoring и hashed signals;
- append-only security audit events;
- SMTP delivery и безопасный local console backend;
- PostgreSQL integration test полного auth lifecycle.

## 2. API contract

Все endpoints находятся под `/api/v1/auth`.

| Method | Path | Назначение |
|---|---|---|
| `POST` | `/email/start` | Создать OTP challenge и отправить код |
| `POST` | `/email/verify` | Проверить OTP, создать/найти user и открыть session |
| `POST` | `/telegram` | Проверить Telegram `initData` и открыть session |
| `POST` | `/refresh` | Ротировать refresh token и выдать новый access token |
| `POST` | `/logout` | Отозвать refresh session и очистить cookies |
| `GET` | `/me` | Вернуть текущего пользователя по Bearer JWT |

Access token возвращается в JSON и передается как
`Authorization: Bearer <token>`. Refresh token никогда не попадает в response
body: API записывает его в `HttpOnly`, `SameSite=Strict` cookie. Отдельная
readable CSRF cookie должна совпасть с `X-CSRF-Token` на refresh/logout.

Ответ `/email/start` одинаков для любого адреса и не раскрывает, существует ли
аккаунт. Ошибки OTP также намеренно одинаковы для неверного, истекшего и уже
использованного кода.

## 3. Email OTP flow

```text
email/start
  -> rate limit: IP + keyed email identity
  -> invalidate previous active challenges
  -> generate CSPRNG numeric code
  -> store only HMAC(challenge_id || code)
  -> send through SMTP

email/verify
  -> rate limit: IP + keyed email identity
  -> SELECT challenge FOR UPDATE
  -> atomically increment failed attempts or consume challenge
  -> create/link user and USER role
  -> anti-abuse assessment
  -> create refresh session + JWT
  -> append audit event
```

OTP живет 10 минут, имеет шесть цифр и максимум пять попыток по default settings.
Повторный `/email/start` инвалидирует предыдущие активные challenges. Код не
хранится в открытом виде. Console sender, который логирует код, разрешен только
в local/test; production settings требуют SMTP.

## 4. Telegram Mini App authentication

Backend принимает только raw `Telegram.WebApp.initData`, а не доверяет
`initDataUnsafe`. Валидатор:

1. строго разбирает query string и запрещает duplicate fields;
2. исключает `hash`, сортирует остальные поля и формирует data-check-string;
3. получает secret key как HMAC-SHA256 bot token с ключом `WebAppData`;
4. constant-time сравнивает вычисленный HMAC с `hash`;
5. проверяет `auth_date` и ограничивает возраст payload;
6. валидирует JSON пользователя typed Pydantic schema.

Создание Telegram identity сериализовано PostgreSQL advisory transaction lock по
`telegram_user_id`, поэтому параллельные первые login requests не создадут двух
users.

Официальный контракт проверки: <https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app>.

## 5. JWT и session model

JWT access token использует HS256 и обязательные claims:

- `iss`, `aud`;
- `sub` — user UUID;
- `sid` — auth session UUID;
- `jti` — UUIDv7 token ID;
- `roles`;
- `token_type=access`;
- `iat`, `nbf`, `exp`.

Default lifetime access token — 15 минут. Проверка access token включает не
только подпись и claims: backend читает session и user из PostgreSQL, проверяет
expiry/revocation/status и повторно загружает актуальные roles. Поэтому logout,
block пользователя и refresh replay начинают действовать немедленно, не ожидая
JWT expiry.

Refresh token — CSPRNG opaque value. В `auth_sessions` хранится только keyed HMAC
digest. При refresh:

1. старая row блокируется `FOR UPDATE`;
2. создается successor session в той же token family;
3. старая session получает `revoked_at`, reason `rotated` и ссылку на successor;
4. client получает новую refresh/CSRF cookie pair;
5. повторное предъявление predecessor token считается кражей и отзывает всю
   активную family с reason `refresh_token_reuse`.

## 6. RBAC

`require_roles(...)` — FastAPI dependency factory. Доступ разрешается, если у
principal есть хотя бы одна требуемая активная role. Roles загружаются из
`user_roles` на каждый authenticated request; роль из JWT не считается
источником истины.

Пример для будущего admin endpoint:

```python
@router.get("/admin/example")
async def example(
    principal: Annotated[
        Principal,
        Depends(require_roles(Role.ADMIN, Role.SUPER_ADMIN)),
    ],
) -> dict[str, str]:
    return {"user_id": str(principal.user_id)}
```

## 7. Rate limiting и anti-abuse

Redis Lua script реализует atomic sliding window на sorted set и использует
серверное время Redis. Политики разделены по endpoint и identity:

| Flow | IP limit | Identity limit |
|---|---:|---:|
| Email start | 5 / 10 min | 3 / 10 min |
| Email verify | 10 / 10 min | 8 / 10 min |
| Telegram | 20 / 5 min | 10 / 5 min |
| Refresh | 30 / 5 min | 10 / 5 min per token |

Email, Telegram ID, IP и fingerprint не записываются в Redis keys в открытом
виде: используются keyed HMAC digests. При превышении API возвращает `429` и
`Retry-After`. Authentication rate limiter fail-closed: outage Redis дает `503`,
а не отключает защиту.

После успешной первичной аутентификации anti-abuse service считает количество
разных users на IP/device за 30 дней и сохраняет hashed `risk_signals`. Высокий
score дает decision `review`; сам login не блокируется, чтобы shared NAT не
создавал массовые false positives. Решение предназначено для STEP 5/trial
eligibility и дальнейшей fraud policy.

## 8. Audit и privacy

В append-only `audit_logs` записываются:

- успешный Email OTP login;
- успешный Telegram login;
- refresh rotation;
- refresh token reuse и family revocation;
- logout.

Audit event содержит actor, session, request ID, IP и user agent, но не содержит
OTP, JWT, refresh token или Telegram `initData`. Fingerprints и risk signals
хранятся как keyed digests. OTP и refresh secrets также не сохраняются в
открытом виде.

## 9. Конфигурация

Основные environment variables:

```text
HAZBIT_REDIS__URL=redis://localhost:6379/0
HAZBIT_AUTH__JWT__SECRET=...
HAZBIT_AUTH__OTP__SECRET=...
HAZBIT_AUTH__REFRESH_TOKEN_SECRET=...
HAZBIT_AUTH__FINGERPRINT_SECRET=...
HAZBIT_AUTH__TELEGRAM__BOT_TOKEN=...
HAZBIT_AUTH__EMAIL__BACKEND=smtp
HAZBIT_AUTH__EMAIL__SMTP_HOST=smtp.example.com
HAZBIT_AUTH__COOKIES__SECURE=true
```

Production startup fail-fast запрещает local default secrets, console email,
пустой Telegram bot token и insecure cookies. Secrets должны поступать из
deployment secret manager, а не коммититься в `.env`.

## 10. Как запустить

Нужны PostgreSQL 15+ и Redis:

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Для local режима OTP печатается structured log event `development_otp`.
Readiness теперь требует одновременно PostgreSQL и Redis.

```bash
make check
export HAZBIT_TEST_DATABASE_URL='postgresql://user:password@localhost/hazbit_test'
make test-integration
```

Alembic autogenerate временно запрещен: ORM metadata содержит только уже активные
domain mappings, тогда как initial migration создает все 39 STEP 2 tables.
Следующие migrations нужно создавать вручную и review-ить, чтобы autogenerate не
предложил удалить еще не подключенные домены.

## 11. Проверки

Автоматические тесты покрывают:

- UUIDv7, OTP HMAC, opaque refresh digest, JWT и Argon2id;
- валидный, измененный, просроченный и duplicate-field Telegram `initData`;
- Redis allow/deny/fail-closed paths и `Retry-After`;
- RBAC allow/deny;
- CSRF и API payload contract;
- production configuration guards;
- реальный PostgreSQL lifecycle: failed OTP attempt persistence, successful
  login, JWT session validation, refresh rotation, replay family revocation и
  append-only audit events.

## 12. Возможные улучшения

- asymmetric JWT signing (`EdDSA`/`RS256`) и `kid` rotation при появлении
  нескольких token issuers/consumers;
- transactional email outbox вместо direct SMTP для гарантированной доставки;
- CAPTCHA/proof-of-work после progressive rate-limit thresholds;
- ASN/GeoIP/reputation signals и настраиваемая risk policy;
- управление активными sessions пользователем;
- trusted-proxy policy для нормализованного client IP на deployment stage;
- WebAuthn/passkeys как дополнительный authentication method.

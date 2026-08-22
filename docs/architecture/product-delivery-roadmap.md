# Hazbit product delivery roadmap

## Что уже является общей платформой

STEP 1–10 создали единое ядро: PostgreSQL schema, FastAPI, authentication,
Remnawave projection, payments AI, referrals, promo codes, support и admin
operations. Следующие клиенты не должны повторять эту бизнес-логику — они
используют общие API, entitlement rules и дизайн-систему.

## Следующая последовательность

### STEP 11 — Family Subscription Domain

Статус: **реализован**. Детали и контракты зафиксированы в
[`step-11-family-subscription-domain.md`](../backend/step-11-family-subscription-domain.md).

- создание и переименование группы владельцем;
- приглашение, принятие и отзыв приглашения;
- выход и удаление участника;
- проверка member/device limits;
- перенос entitlement в Remnawave projection;
- anti-abuse, audit и customer/admin notifications.

### STEP 12 — Customer Web App

Статус: **реализован**. Детали интерфейса, API façade, PWA и security-модель
зафиксированы в [`step-12-customer-web-pwa.md`](../frontend/step-12-customer-web-pwa.md).

Один responsive React-клиент для desktop и mobile/PWA: onboarding,
подписка, оплата, устройства, VPN setup, Family, promo/referral и support.
Desktop-сайт и мобильное веб-приложение разделяют feature modules и API client,
а не развиваются как две несовместимые кодовые базы.

### STEP 13 — Telegram Mini App

Статус: **реализован**. Bootstrap, platform adapter, deep links и customer flows
зафиксированы в [`step-13-telegram-mini-app.md`](../frontend/step-13-telegram-mini-app.md).

Mini App использует те же customer feature modules и дизайн-токены, но отдельный
Telegram bootstrap: init-data authentication, viewport/safe-area, back button,
invoice/deep-link flows и platform-specific navigation.

### STEP 14 — Telegram Bots

Статус: **реализован**. Webhook contracts, customer/operations flows, security и
outbox delivery зафиксированы в
[`step-14-telegram-bots.md`](../backend/step-14-telegram-bots.md).

- customer bot: login links, subscription status, VPN setup, payment and support;
- operations bot: payment-review and urgent-ticket notifications;
- signed callbacks, idempotency, RBAC and rate limiting.

### STEP 15 — Release hardening

Статус: **реализован базовый production-контур**. Deployment, operations и
security gates описаны в
[`step-15-release-hardening.md`](../operations/step-15-release-hardening.md).

Docker Compose запускает PostgreSQL, Redis, MinIO, private Remnawave adapter,
FastAPI и workers под PM2, а Caddy публикует три клиента и API с automatic HTTPS.
Добавлены CI, health checks, migration gate, secret-safe templates и backup/restore.
Remote telemetry, scheduled off-site backup drills и live-provider E2E остаются
следующим эксплуатационным increment после появления production credentials.

## Delivery rule

Сначала закрывается доменная логика и API одного vertical slice, затем этот slice
подключается в customer Web/PWA и Mini App. Так Family, payments или devices не
расходятся между сайтом, Telegram и ботами.

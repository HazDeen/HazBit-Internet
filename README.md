# Hazbit VPN Platform

Production-oriented VPN subscription platform for Web, Telegram Mini App, and
administration workflows.

## Current delivery stage

The project is intentionally developed in stages. **STEP 1 — System
Architecture Design**, **STEP 2 — Database Schema**, **STEP 3 — Backend
Foundation**, **STEP 4 — Authentication**, **STEP 5 — VPN Integration**,
**STEP 6 — Payments AI**, **STEP 7 — Referral System**, **STEP 8 — Promo Codes**,
**STEP 9 — Support Ticket System**, **STEP 10 — Admin Panel**, **STEP 11 —
Family Subscription Domain**, **STEP 12 — Customer Web/PWA**, **STEP 13 —
Telegram Mini App**, **STEP 14 — Telegram Bots**, and the base production scope of
**STEP 15 — Release Hardening** are complete.

- [System architecture](docs/architecture/step-01-system-architecture.md)
- [Architecture decisions](docs/architecture/decisions.md)
- [Database schema and ER diagrams](docs/database/step-02-database-schema.md)
- [Executable PostgreSQL reference schema](database/schema.sql)
- [Backend foundation](docs/backend/step-03-backend-foundation.md)
- [Authentication](docs/backend/step-04-authentication.md)
- [Remnawave VPN integration](docs/backend/step-05-remnawave-integration.md)
- [Payments AI](docs/backend/step-06-payments-ai.md)
- [Referral System](docs/backend/step-07-referral-system.md)
- [Promo Codes](docs/backend/step-08-promo-codes.md)
- [Support Ticket System](docs/backend/step-09-support-ticket-system.md)
- [Admin Panel](docs/backend/step-10-admin-panel.md)
- [Family Subscription Domain](docs/backend/step-11-family-subscription-domain.md)
- [Customer Web/PWA](docs/frontend/step-12-customer-web-pwa.md)
- [Telegram Mini App](docs/frontend/step-13-telegram-mini-app.md)
- [Telegram Bots](docs/backend/step-14-telegram-bots.md)
- [VPS deployment and release hardening](docs/operations/step-15-release-hardening.md)
- [Product delivery roadmap](docs/architecture/product-delivery-roadmap.md)
- [Admin frontend](frontend/README.md)
- [Customer Web/PWA](customer-frontend/README.md)
- [Telegram Mini App](telegram-miniapp/README.md)
- [Remnawave adapter service](services/remnawave-adapter/README.md)
- [Backend run instructions](backend/README.md)

The FastAPI runtime, initial Alembic migration, Email OTP/Telegram authentication,
JWT sessions, RBAC, Redis rate limiting, anti-abuse signals, durable Remnawave
provisioning, HWID device management, Gemini receipt extraction, deterministic
payment approval, immutable ledger posting, referral rewards, promo discounts,
free-day grants, durable VPN provisioning, and audit trail are implemented. The
support module adds private customer conversations, a prioritized staff queue,
ticket assignment, and audited status transitions. The React admin console adds
an operational dashboard, user/subscription/payment controls, VPN device views,
RBAC-protected mutations, and responsive desktop/mobile layouts.

## Production deployment

The production Compose stack serves Customer Web/PWA, Admin Panel, Telegram Mini
App and API through Caddy, supervises FastAPI and all workers with PM2, and keeps
PostgreSQL, Redis, MinIO and the Remnawave adapter private.

```bash
cp deploy/.env.production.example deploy/.env.production
# Replace every placeholder and local-only secret.
docker compose --env-file deploy/.env.production -f compose.prod.yml up -d --build
```

Startup applies migrations, idempotently creates the initial plan catalog and first
`SUPER_ADMIN`, verifies PostgreSQL/Redis/catalog readiness, and refuses to expose the
API when required launch data is missing. SMTP delivery can be checked from the
running platform container with `python -m app.operations.cli test-email --to ...`.

See the [STEP 15 runbook](docs/operations/step-15-release-hardening.md) before the
first VPS launch, especially DNS, secrets, backup and restore requirements.

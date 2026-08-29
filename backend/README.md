# Hazbit Backend

FastAPI foundation for the Hazbit subscription platform.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
```

Health endpoints (readiness requires PostgreSQL and Redis):

- `GET /health/live`
- `GET /health/ready`

Quality gate:

```bash
make check
```

Authentication endpoints are available under `/api/v1/auth`.
VPN account and device endpoints are available under `/api/v1/vpn` and
`/api/v1/devices`. Payment intent, evidence, and admin review endpoints are
available under `/api/v1/payments` and `/api/v1/admin/payments`. Run
`make worker-vpn`, `make worker-payments`, and `make worker-referrals` as
separate worker processes. Referral endpoints are available under
`/api/v1/referrals` and `/api/v1/admin/referrals`. Promo preview, redemption,
history, and administration are available under `/api/v1/promo-codes` and
`/api/v1/admin/promo-codes`. Support conversations and the staff queue are
available under `/api/v1/tickets` and `/api/v1/admin/tickets`.
The consolidated dashboard, user controls, subscription catalog, payment index,
device fleet, and safe runtime settings are available under `/api/v1/admin`.
Telegram customer/operations webhooks are available under `/api/v1/bots`.
Run `make worker-telegram` for outbox notifications and `make telegram-webhooks`
once after configuring public HTTPS URLs and both bot tokens.

- [STEP 3 — Backend Foundation](../docs/backend/step-03-backend-foundation.md)
- [STEP 4 — Authentication](../docs/backend/step-04-authentication.md)
- [STEP 5 — Remnawave Integration](../docs/backend/step-05-remnawave-integration.md)
- [STEP 6 — Payments AI](../docs/backend/step-06-payments-ai.md)
- [STEP 7 — Referral System](../docs/backend/step-07-referral-system.md)
- [STEP 8 — Promo Codes](../docs/backend/step-08-promo-codes.md)
- [STEP 9 — Support Ticket System](../docs/backend/step-09-support-ticket-system.md)
- [STEP 10 — Admin Panel](../docs/backend/step-10-admin-panel.md)
- [STEP 14 — Telegram Bots](../docs/backend/step-14-telegram-bots.md)

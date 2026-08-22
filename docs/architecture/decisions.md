# Architecture Decision Log

This log records the decisions that constrain later implementation stages.

## ADR-001 — Modular monolith for the business core

**Status:** Accepted for the initial production release.

The Platform API is one deployable FastAPI application, split into strict
domain modules. It owns identities, subscriptions, billing, families,
referrals, promo codes, support, and administration.

This avoids distributed transactions across immature domain boundaries while
keeping module contracts explicit enough to extract a service later. Separate
deployment units are used only where operational isolation already brings a
clear benefit: Remnawave Adapter, Telegram Bot, background workers, and web UI.

## ADR-002 — Remnawave is isolated behind an internal adapter

**Status:** Accepted.

The Platform API never calls the panel directly. It calls a private
`remnawave-adapter` service through a versioned internal API. Only the adapter
stores the Remnawave token, understands panel DTOs, normalizes errors, applies
timeouts/retries, and emits integration metrics.

This limits the blast radius of panel changes and prevents a vendor-specific
schema from leaking into the business domain.

## ADR-003 — PostgreSQL is the source of business truth

**Status:** Accepted.

PostgreSQL owns commercial subscription state, entitlements, payment decisions,
family membership, referrals, and audit history. Remnawave owns the effective
VPN account and observed HWID-device state. Synchronization is explicit and
eventually consistent; a reconciliation job repairs drift.

## ADR-004 — Transactional outbox for side effects

**Status:** Accepted.

Every state transition and its domain event are committed in one PostgreSQL
transaction. Workers publish/process outbox messages with idempotency keys.
Remnawave mutations, Telegram notifications, email, referral rewards, and
subscription activation must not depend on an in-process fire-and-forget task.

## ADR-005 — Payment screenshots require two independent states

**Status:** Accepted.

Payment verification and subscription activation are separate state machines.
Gemini returns structured evidence and a confidence score; deterministic rules
make the auto/manual decision. A worker activates the entitlement only after a
payment reaches `APPROVED`. Gemini never changes balances or subscriptions
directly.

## ADR-006 — HWID operations are isolated behind the adapter

**Status:** Corrected and accepted during STEP 5.

Detailed contract inspection confirmed that the supplied Remnawave OpenAPI
v3.3.2 exposes `POST /api/hwid/devices` in addition to list, delete, delete-all,
and statistics operations. The earlier claim that HWID creation was unavailable
was incorrect.

Platform reserves a local device slot and commits a durable `create_device`
command atomically. The adapter then invokes the panel operation; successful
reconciliation moves the device from `reserved` to `observed`. This preserves
device limits and idempotency in PostgreSQL while using the supported panel API.

## ADR-007 — Access tokens are short-lived; sessions are server-controlled

**Status:** Accepted.

JWT access tokens live for 10–15 minutes. Rotating opaque refresh tokens are
hashed in PostgreSQL and grouped into session families; reuse revokes the whole
family. Web clients use Secure, HttpOnly, SameSite cookies. Telegram Mini App
authentication starts by server-side validation of signed `initData`, never by
trusting user JSON from the client.

## ADR-008 — One frontend workspace, separate route surfaces

**Status:** Accepted.

The customer web application and Telegram Mini App share typed customer
contracts, brand tokens and backend feature APIs inside one workspace, while
Telegram bootstrap, route bundles and admin access policies remain separate.
This provides consistent domain behavior without shipping admin code in the
customer entry path or forcing desktop components into Telegram sheets.

## ADR-009 — Referral attribution and reward issuance are separate states

**Status:** Accepted during STEP 7.

Claiming a code only creates immutable attribution and a risk decision. Automatic
or administrative qualification creates two pending rewards; a database worker
then grants both subscription-day periods atomically and marks the referral
`rewarded`. A failed or repeated worker run cannot grant only one side or duplicate
an entitlement. IP/device hashes are risk signals, not public referral identifiers,
and suspicious household/device matches require review instead of silent reward.

## ADR-010 — Promo discounts are explicit ledger credits

**Status:** Accepted during STEP 8.

A discount redemption reduces the bank-transfer amount but does not silently
change the catalog price. On payment approval the ledger posts the received cash
and a separate `promo_credit` funded by `promo_expense`; together they equal the
full plan price available for the subscription debit. Free-day promotions create
an explicit subscription period instead of mutating a generic day counter. This
keeps campaign cost, entitlements, retries, and revocation auditable.

## ADR-011 — Support conversations are private stateful aggregates

**Status:** Accepted during STEP 9.

A ticket owns its ordered message history and status version. Customer reads are
always scoped by ticket owner; internal notes are filtered at the repository/API
boundary. Staff changes use optimistic version checks, while create/reply retries
use the shared idempotency store. Notification intent is committed to the Outbox
with the conversation update, so Telegram/email delivery cannot determine whether
the support transaction succeeds.

## ADR-012 — Admin UI orchestrates domain services; it does not bypass them

**Status:** Accepted during STEP 10.

The admin dashboard is an operational client of the same authenticated API and
domain state machines used by workers and customer flows. Administrative
mutations require a reason, create audit/outbox records, and project entitlement
changes through the durable VPN command queue. The UI never calls Remnawave,
changes ledger rows, or exposes deployment secrets directly. This keeps emergency
operator actions observable and retry-safe without creating a privileged second
business implementation in the browser.

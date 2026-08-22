-- Hazbit VPN Platform — STEP 2 reference schema
-- Target: PostgreSQL 15+
-- This file is an executable design artifact. Alembic migrations are created in STEP 3.

BEGIN;

CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE SCHEMA IF NOT EXISTS app;
SET search_path TO app, public;

CREATE FUNCTION app.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = clock_timestamp();
    RETURN NEW;
END;
$$;

CREATE FUNCTION app.reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME
        USING ERRCODE = '55000';
END;
$$;

-- UUID defaults are operational fallbacks. The application will normally supply UUIDv7.

-- -----------------------------------------------------------------------------
-- Identity and access
-- -----------------------------------------------------------------------------

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    public_name varchar(120),
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'blocked', 'pending_deletion', 'deleted')),
    locale varchar(16) NOT NULL DEFAULT 'ru',
    timezone varchar(64) NOT NULL DEFAULT 'UTC',
    blocked_at timestamptz,
    blocked_reason text,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((status = 'blocked') = (blocked_at IS NOT NULL)),
    CHECK ((status = 'deleted') = (deleted_at IS NOT NULL))
);

CREATE INDEX ix_users_status_created_at ON users (status, created_at DESC);

CREATE TABLE user_emails (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email citext NOT NULL,
    is_primary boolean NOT NULL DEFAULT false,
    verified_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (email)
);

CREATE UNIQUE INDEX uq_user_emails_one_primary
    ON user_emails (user_id) WHERE is_primary;
CREATE INDEX ix_user_emails_user_id ON user_emails (user_id);

CREATE TABLE telegram_accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    telegram_user_id bigint NOT NULL,
    username citext,
    first_name varchar(255),
    last_name varchar(255),
    language_code varchar(16),
    channel_verified_at timestamptz,
    linked_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (telegram_user_id),
    UNIQUE (user_id)
);

CREATE INDEX ix_telegram_accounts_username
    ON telegram_accounts (username) WHERE username IS NOT NULL;

CREATE TABLE user_roles (
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('super_admin', 'admin', 'support', 'user')),
    granted_by uuid REFERENCES users(id) ON DELETE SET NULL,
    granted_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    PRIMARY KEY (user_id, role),
    CHECK (revoked_at IS NULL OR revoked_at >= granted_at)
);

CREATE INDEX ix_user_roles_active_role
    ON user_roles (role, user_id) WHERE revoked_at IS NULL;

CREATE TABLE auth_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_family_id uuid NOT NULL,
    refresh_token_hash bytea NOT NULL,
    user_agent text,
    ip_address inet,
    device_fingerprint_hash bytea,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    revoke_reason text,
    replaced_by_session_id uuid REFERENCES auth_sessions(id) ON DELETE SET NULL,
    UNIQUE (refresh_token_hash),
    CHECK (expires_at > created_at),
    CHECK ((revoked_at IS NULL) = (revoke_reason IS NULL))
);

CREATE INDEX ix_auth_sessions_user_active
    ON auth_sessions (user_id, expires_at DESC) WHERE revoked_at IS NULL;
CREATE INDEX ix_auth_sessions_family_active
    ON auth_sessions (token_family_id) WHERE revoked_at IS NULL;

CREATE TABLE otp_challenges (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email citext NOT NULL,
    purpose text NOT NULL CHECK (purpose IN ('register', 'login', 'link_email')),
    code_hash bytea NOT NULL,
    attempts smallint NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 5),
    max_attempts smallint NOT NULL DEFAULT 5 CHECK (max_attempts BETWEEN 1 AND 10),
    requested_ip inet,
    device_fingerprint_hash bytea,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    CHECK (expires_at > created_at),
    CHECK (attempts <= max_attempts),
    CHECK (consumed_at IS NULL OR consumed_at >= created_at)
);

CREATE INDEX ix_otp_challenges_lookup
    ON otp_challenges (email, purpose, created_at DESC)
    WHERE consumed_at IS NULL;
CREATE INDEX ix_otp_challenges_expiry ON otp_challenges (expires_at);

CREATE TABLE risk_signals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    signal_type text NOT NULL
        CHECK (signal_type IN ('ip', 'device', 'email_domain', 'telegram', 'velocity', 'referral')),
    signal_hash bytea NOT NULL,
    score smallint NOT NULL CHECK (score BETWEEN 0 AND 100),
    decision text NOT NULL CHECK (decision IN ('allow', 'review', 'deny')),
    context jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(context) = 'object'),
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_risk_signals_hash_created_at
    ON risk_signals (signal_type, signal_hash, created_at DESC);
CREATE INDEX ix_risk_signals_user_id ON risk_signals (user_id, created_at DESC);

-- -----------------------------------------------------------------------------
-- Plans and pricing
-- -----------------------------------------------------------------------------

CREATE TABLE plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug citext NOT NULL,
    name varchar(120) NOT NULL,
    description text,
    is_active boolean NOT NULL DEFAULT true,
    sort_order integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (slug)
);

CREATE TABLE plan_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id uuid NOT NULL REFERENCES plans(id) ON DELETE RESTRICT,
    version integer NOT NULL CHECK (version > 0),
    device_limit smallint NOT NULL CHECK (device_limit > 0),
    family_member_limit smallint NOT NULL DEFAULT 0 CHECK (family_member_limit >= 0),
    traffic_limit_bytes bigint CHECK (traffic_limit_bytes IS NULL OR traffic_limit_bytes > 0),
    remnawave_policy jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(remnawave_policy) = 'object'),
    valid_from timestamptz NOT NULL DEFAULT now(),
    valid_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (plan_id, version),
    CHECK (valid_until IS NULL OR valid_until > valid_from)
);

CREATE INDEX ix_plan_versions_current
    ON plan_versions (plan_id, valid_from DESC) WHERE valid_until IS NULL;

CREATE TABLE plan_prices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_version_id uuid NOT NULL REFERENCES plan_versions(id) ON DELETE RESTRICT,
    term_months smallint NOT NULL CHECK (term_months IN (1, 3, 6, 12)),
    duration_days smallint NOT NULL CHECK (duration_days > 0),
    currency char(3) NOT NULL CHECK (currency = upper(currency)),
    amount_minor bigint NOT NULL CHECK (amount_minor >= 0),
    is_active boolean NOT NULL DEFAULT true,
    valid_from timestamptz NOT NULL DEFAULT now(),
    valid_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (plan_version_id, term_months, currency, valid_from),
    CHECK (valid_until IS NULL OR valid_until > valid_from)
);

CREATE INDEX ix_plan_prices_catalog
    ON plan_prices (plan_version_id, currency, term_months)
    WHERE is_active AND valid_until IS NULL;

-- -----------------------------------------------------------------------------
-- Commercial subscriptions and grants
-- -----------------------------------------------------------------------------

CREATE TABLE subscriptions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    plan_version_id uuid NOT NULL REFERENCES plan_versions(id) ON DELETE RESTRICT,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'grace_period', 'suspended', 'expired', 'cancelled')),
    source text NOT NULL CHECK (source IN ('trial', 'purchase', 'promo', 'referral', 'admin')),
    starts_at timestamptz,
    current_period_ends_at timestamptz,
    grace_ends_at timestamptz,
    cancel_at_period_end boolean NOT NULL DEFAULT false,
    cancelled_at timestamptz,
    suspended_at timestamptz,
    suspension_reason text,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, owner_user_id),
    CHECK (current_period_ends_at IS NULL OR starts_at IS NOT NULL),
    CHECK (current_period_ends_at IS NULL OR current_period_ends_at > starts_at),
    CHECK (grace_ends_at IS NULL OR grace_ends_at > current_period_ends_at),
    CHECK ((suspended_at IS NULL) = (suspension_reason IS NULL))
);

CREATE UNIQUE INDEX uq_subscriptions_one_live_per_owner
    ON subscriptions (owner_user_id)
    WHERE status IN ('pending', 'active', 'grace_period', 'suspended');
CREATE INDEX ix_subscriptions_expiry
    ON subscriptions (current_period_ends_at)
    WHERE status IN ('active', 'grace_period');
CREATE INDEX ix_subscriptions_plan_status
    ON subscriptions (plan_version_id, status);

CREATE TABLE subscription_periods (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id uuid NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    source_type text NOT NULL
        CHECK (source_type IN ('trial', 'payment', 'promo', 'referral', 'admin', 'renewal')),
    source_id uuid,
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    plan_snapshot jsonb NOT NULL CHECK (jsonb_typeof(plan_snapshot) = 'object'),
    price_minor bigint CHECK (price_minor IS NULL OR price_minor >= 0),
    currency char(3) CHECK (currency IS NULL OR currency = upper(currency)),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (ends_at > starts_at),
    CHECK ((price_minor IS NULL) = (currency IS NULL)),
    EXCLUDE USING gist (
        subscription_id WITH =,
        tstzrange(starts_at, ends_at, '[)') WITH &&
    )
);

CREATE INDEX ix_subscription_periods_ends_at ON subscription_periods (ends_at);

CREATE TABLE trial_grants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    subscription_id uuid NOT NULL REFERENCES subscriptions(id) ON DELETE RESTRICT,
    duration_days smallint NOT NULL DEFAULT 3 CHECK (duration_days > 0),
    decision text NOT NULL CHECK (decision IN ('granted', 'review', 'denied', 'revoked')),
    risk_score smallint CHECK (risk_score BETWEEN 0 AND 100),
    decision_reason text,
    granted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id),
    UNIQUE (subscription_id),
    FOREIGN KEY (subscription_id, user_id)
        REFERENCES subscriptions(id, owner_user_id) ON DELETE RESTRICT,
    CHECK ((decision IN ('granted', 'revoked')) = (granted_at IS NOT NULL))
);

-- -----------------------------------------------------------------------------
-- Family subscriptions
-- -----------------------------------------------------------------------------

CREATE TABLE family_groups (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    subscription_id uuid NOT NULL REFERENCES subscriptions(id) ON DELETE RESTRICT,
    name varchar(120) NOT NULL DEFAULT 'Family',
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'archived')),
    member_limit smallint NOT NULL CHECK (member_limit > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    UNIQUE (subscription_id),
    FOREIGN KEY (subscription_id, owner_user_id)
        REFERENCES subscriptions(id, owner_user_id) ON DELETE RESTRICT,
    CHECK ((status = 'archived') = (archived_at IS NOT NULL))
);

CREATE UNIQUE INDEX uq_family_groups_active_owner
    ON family_groups (owner_user_id) WHERE status <> 'archived';

CREATE TABLE family_invitations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    family_group_id uuid NOT NULL REFERENCES family_groups(id) ON DELETE CASCADE,
    invited_by_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    invited_user_id uuid REFERENCES users(id) ON DELETE CASCADE,
    invited_email citext,
    token_hash bytea NOT NULL,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'declined', 'expired', 'revoked')),
    expires_at timestamptz NOT NULL,
    accepted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (token_hash),
    CHECK (num_nonnulls(invited_user_id, invited_email) = 1),
    CHECK (expires_at > created_at),
    CHECK ((status = 'accepted') = (accepted_at IS NOT NULL))
);

CREATE UNIQUE INDEX uq_family_pending_invited_user
    ON family_invitations (family_group_id, invited_user_id)
    WHERE status = 'pending' AND invited_user_id IS NOT NULL;
CREATE UNIQUE INDEX uq_family_pending_invited_email
    ON family_invitations (family_group_id, invited_email)
    WHERE status = 'pending' AND invited_email IS NOT NULL;
CREATE INDEX ix_family_invitations_expiry
    ON family_invitations (expires_at) WHERE status = 'pending';

CREATE TABLE family_members (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    family_group_id uuid NOT NULL REFERENCES family_groups(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    invitation_id uuid REFERENCES family_invitations(id) ON DELETE SET NULL,
    joined_at timestamptz NOT NULL DEFAULT now(),
    left_at timestamptz,
    removed_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    remove_reason text,
    CHECK (left_at IS NULL OR left_at >= joined_at),
    CHECK (left_at IS NOT NULL OR removed_by_user_id IS NULL),
    CHECK (left_at IS NOT NULL OR remove_reason IS NULL)
);

CREATE UNIQUE INDEX uq_family_members_active_group_user
    ON family_members (family_group_id, user_id) WHERE left_at IS NULL;
CREATE UNIQUE INDEX uq_family_members_one_active_group
    ON family_members (user_id) WHERE left_at IS NULL;
CREATE INDEX ix_family_members_group_history
    ON family_members (family_group_id, joined_at DESC);

-- -----------------------------------------------------------------------------
-- VPN accounts, devices, and synchronization
-- -----------------------------------------------------------------------------

CREATE TABLE vpn_accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    subscription_id uuid NOT NULL REFERENCES subscriptions(id) ON DELETE RESTRICT,
    remnawave_user_id bigint,
    remnawave_user_uuid uuid,
    username citext NOT NULL,
    desired_status text NOT NULL DEFAULT 'pending'
        CHECK (desired_status IN ('pending', 'active', 'disabled', 'revoked')),
    observed_status text
        CHECK (observed_status IS NULL OR observed_status IN ('active', 'disabled', 'limited', 'expired', 'unknown')),
    desired_expires_at timestamptz,
    observed_expires_at timestamptz,
    subscription_url_ciphertext bytea,
    last_synced_at timestamptz,
    last_sync_error_code varchar(80),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (username),
    UNIQUE (remnawave_user_id),
    UNIQUE (remnawave_user_uuid)
);

CREATE UNIQUE INDEX uq_vpn_accounts_one_live_per_user
    ON vpn_accounts (user_id)
    WHERE desired_status IN ('pending', 'active', 'disabled');
CREATE INDEX ix_vpn_accounts_subscription ON vpn_accounts (subscription_id);
CREATE INDEX ix_vpn_accounts_reconcile
    ON vpn_accounts (last_synced_at NULLS FIRST)
    WHERE desired_status <> 'revoked';

CREATE TABLE devices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    vpn_account_id uuid NOT NULL REFERENCES vpn_accounts(id) ON DELETE CASCADE,
    slot_number smallint NOT NULL CHECK (slot_number > 0),
    label varchar(120),
    external_hwid varchar(255),
    fingerprint_hash bytea,
    platform varchar(60),
    status text NOT NULL DEFAULT 'reserved'
        CHECK (status IN ('reserved', 'observed', 'revoked')),
    first_seen_at timestamptz,
    last_seen_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (vpn_account_id, slot_number),
    CHECK (status <> 'observed' OR external_hwid IS NOT NULL),
    CHECK ((status = 'revoked') = (revoked_at IS NOT NULL)),
    CHECK (last_seen_at IS NULL OR first_seen_at IS NOT NULL),
    CHECK (last_seen_at IS NULL OR last_seen_at >= first_seen_at)
);

CREATE UNIQUE INDEX uq_devices_external_hwid
    ON devices (vpn_account_id, external_hwid) WHERE external_hwid IS NOT NULL;
CREATE INDEX ix_devices_user_status ON devices (user_id, status);

CREATE TABLE vpn_sync_commands (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    vpn_account_id uuid NOT NULL REFERENCES vpn_accounts(id) ON DELETE CASCADE,
    command_type text NOT NULL
        CHECK (command_type IN ('ensure_account', 'enable', 'disable', 'extend', 'sync', 'remove_device', 'revoke')),
    idempotency_key varchar(255) NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload) = 'object'),
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'retry_scheduled', 'succeeded', 'dead_letter')),
    attempt_count smallint NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    locked_at timestamptz,
    completed_at timestamptz,
    last_error_code varchar(80),
    last_error_detail text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (idempotency_key)
);

CREATE INDEX ix_vpn_sync_commands_claim
    ON vpn_sync_commands (next_attempt_at, created_at)
    WHERE status IN ('pending', 'retry_scheduled');

-- -----------------------------------------------------------------------------
-- Object storage and payments
-- -----------------------------------------------------------------------------

CREATE TABLE storage_objects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    bucket varchar(120) NOT NULL,
    object_key varchar(512) NOT NULL,
    original_filename varchar(255),
    content_type varchar(120) NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    sha256 bytea NOT NULL,
    status text NOT NULL DEFAULT 'pending_scan'
        CHECK (status IN ('pending_scan', 'clean', 'quarantined', 'deleted')),
    retention_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    UNIQUE (bucket, object_key),
    CHECK ((status = 'deleted') = (deleted_at IS NOT NULL))
);

CREATE INDEX ix_storage_objects_owner ON storage_objects (owner_user_id, created_at DESC);
CREATE INDEX ix_storage_objects_retention
    ON storage_objects (retention_until) WHERE status <> 'deleted';

CREATE TABLE payments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    plan_price_id uuid NOT NULL REFERENCES plan_prices(id) ON DELETE RESTRICT,
    status text NOT NULL DEFAULT 'awaiting_upload'
        CHECK (status IN (
            'awaiting_upload', 'uploaded', 'analyzing', 'auto_approved',
            'manual_review', 'approved', 'rejected', 'activation_pending',
            'activated', 'cancelled'
        )),
    expected_amount_minor bigint NOT NULL CHECK (expected_amount_minor >= 0),
    currency char(3) NOT NULL CHECK (currency = upper(currency)),
    expected_recipient varchar(255) NOT NULL,
    operation_number_normalized varchar(255),
    observed_recipient_normalized varchar(255),
    idempotency_key varchar(255) NOT NULL,
    rejection_reason text,
    expires_at timestamptz NOT NULL,
    uploaded_at timestamptz,
    approved_at timestamptz,
    rejected_at timestamptz,
    activated_at timestamptz,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, idempotency_key),
    CHECK (expires_at > created_at),
    CHECK (status NOT IN ('uploaded', 'analyzing', 'auto_approved', 'manual_review',
                          'approved', 'rejected', 'activation_pending', 'activated')
           OR uploaded_at IS NOT NULL),
    CHECK (status NOT IN ('approved', 'activation_pending', 'activated')
           OR approved_at IS NOT NULL),
    CHECK ((status = 'rejected') = (rejected_at IS NOT NULL)),
    CHECK ((status = 'activated') = (activated_at IS NOT NULL)),
    CHECK ((status = 'rejected') = (rejection_reason IS NOT NULL))
);

CREATE UNIQUE INDEX uq_payments_operation_recipient
    ON payments (operation_number_normalized, observed_recipient_normalized, currency)
    WHERE operation_number_normalized IS NOT NULL
      AND observed_recipient_normalized IS NOT NULL
      AND status IN ('auto_approved', 'approved', 'activation_pending', 'activated');
CREATE INDEX ix_payments_user_created_at ON payments (user_id, created_at DESC);
CREATE INDEX ix_payments_review_queue
    ON payments (created_at) WHERE status = 'manual_review';
CREATE INDEX ix_payments_activation_queue
    ON payments (approved_at) WHERE status = 'activation_pending';

CREATE TABLE payment_evidence (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id uuid NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
    storage_object_id uuid NOT NULL REFERENCES storage_objects(id) ON DELETE RESTRICT,
    evidence_type text NOT NULL DEFAULT 'screenshot'
        CHECK (evidence_type IN ('screenshot', 'document')),
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (payment_id, storage_object_id)
);

CREATE INDEX ix_payment_evidence_payment ON payment_evidence (payment_id);

CREATE TABLE payment_analyses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id uuid NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
    evidence_id uuid NOT NULL REFERENCES payment_evidence(id) ON DELETE CASCADE,
    attempt smallint NOT NULL CHECK (attempt > 0),
    provider text NOT NULL DEFAULT 'gemini',
    model varchar(120) NOT NULL,
    prompt_version varchar(40) NOT NULL,
    status text NOT NULL CHECK (status IN ('succeeded', 'failed')),
    amount_minor bigint CHECK (amount_minor IS NULL OR amount_minor >= 0),
    currency char(3) CHECK (currency IS NULL OR currency = upper(currency)),
    operation_date date,
    operation_number varchar(255),
    bank_name varchar(255),
    recipient varchar(255),
    confidence numeric(5,4) CHECK (confidence BETWEEN 0 AND 1),
    extracted_data jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(extracted_data) = 'object'),
    rule_results jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(rule_results) = 'object'),
    error_code varchar(80),
    started_at timestamptz NOT NULL,
    completed_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (payment_id, attempt),
    CHECK (completed_at >= started_at),
    CHECK ((status = 'failed') = (error_code IS NOT NULL))
);

CREATE INDEX ix_payment_analyses_payment ON payment_analyses (payment_id, attempt DESC);

CREATE TABLE payment_reviews (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id uuid NOT NULL REFERENCES payments(id) ON DELETE RESTRICT,
    reviewer_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    decision text NOT NULL CHECK (decision IN ('approved', 'rejected')),
    reason text NOT NULL,
    payment_version integer NOT NULL CHECK (payment_version > 0),
    reviewed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (payment_id)
);

CREATE INDEX ix_payment_reviews_reviewer ON payment_reviews (reviewer_user_id, reviewed_at DESC);

-- -----------------------------------------------------------------------------
-- Double-entry wallet ledger
-- -----------------------------------------------------------------------------

CREATE TABLE ledger_accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_key varchar(160) NOT NULL,
    owner_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    account_type text NOT NULL
        CHECK (account_type IN ('user_wallet', 'cash_clearing', 'revenue', 'promo_expense', 'referral_expense', 'refunds')),
    currency char(3) NOT NULL CHECK (currency = upper(currency)),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'frozen', 'closed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_key, currency),
    CHECK ((account_type = 'user_wallet') = (owner_user_id IS NOT NULL))
);

CREATE UNIQUE INDEX uq_ledger_accounts_user_currency
    ON ledger_accounts (owner_user_id, currency)
    WHERE account_type = 'user_wallet';

CREATE TABLE transactions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    payment_id uuid REFERENCES payments(id) ON DELETE RESTRICT,
    transaction_type text NOT NULL
        CHECK (transaction_type IN ('payment_credit', 'subscription_debit', 'refund', 'promo_credit', 'referral_credit', 'admin_adjustment', 'reversal')),
    status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'posted')),
    currency char(3) NOT NULL CHECK (currency = upper(currency)),
    idempotency_key varchar(255) NOT NULL,
    description text,
    reverses_transaction_id uuid REFERENCES transactions(id) ON DELETE RESTRICT,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    posted_at timestamptz,
    UNIQUE (idempotency_key),
    UNIQUE (payment_id),
    UNIQUE (reverses_transaction_id),
    CHECK ((status = 'posted') = (posted_at IS NOT NULL)),
    CHECK ((transaction_type = 'reversal') = (reverses_transaction_id IS NOT NULL))
);

CREATE INDEX ix_transactions_user_created_at ON transactions (user_id, created_at DESC);

CREATE TABLE transaction_entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id uuid NOT NULL REFERENCES transactions(id) ON DELETE RESTRICT,
    ledger_account_id uuid NOT NULL REFERENCES ledger_accounts(id) ON DELETE RESTRICT,
    amount_minor bigint NOT NULL CHECK (amount_minor <> 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (transaction_id, ledger_account_id)
);

CREATE INDEX ix_transaction_entries_account
    ON transaction_entries (ledger_account_id, created_at DESC);

CREATE FUNCTION app.assert_transaction_postable()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    entry_count integer;
    entry_sum bigint;
    currency_mismatch boolean;
BEGIN
    IF NEW.status = 'posted' AND OLD.status <> 'posted' THEN
        SELECT count(*), COALESCE(sum(te.amount_minor), 0),
               bool_or(la.currency <> NEW.currency)
          INTO entry_count, entry_sum, currency_mismatch
          FROM transaction_entries te
          JOIN ledger_accounts la ON la.id = te.ledger_account_id
         WHERE te.transaction_id = NEW.id;

        IF entry_count < 2 OR entry_sum <> 0 OR COALESCE(currency_mismatch, false) THEN
            RAISE EXCEPTION 'transaction % is not balanced or has a currency mismatch', NEW.id
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION app.reject_posted_transaction_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status = 'posted' THEN
        RAISE EXCEPTION 'posted transaction % is immutable; create a reversal', OLD.id
            USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION app.reject_posted_entry_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    parent_status text;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        SELECT status INTO parent_status FROM transactions WHERE id = OLD.transaction_id;
        IF parent_status = 'posted' THEN
            RAISE EXCEPTION 'entries of posted transaction % are immutable', OLD.transaction_id
                USING ERRCODE = '55000';
        END IF;
    END IF;

    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        SELECT status INTO parent_status FROM transactions WHERE id = NEW.transaction_id;
        IF parent_status = 'posted' THEN
            RAISE EXCEPTION 'entries of posted transaction % are immutable', NEW.transaction_id
                USING ERRCODE = '55000';
        END IF;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_transactions_assert_postable
BEFORE UPDATE OF status ON transactions
FOR EACH ROW EXECUTE FUNCTION app.assert_transaction_postable();

CREATE TRIGGER trg_transactions_immutable
BEFORE UPDATE OR DELETE ON transactions
FOR EACH ROW EXECUTE FUNCTION app.reject_posted_transaction_change();

CREATE TRIGGER trg_transaction_entries_immutable
BEFORE INSERT OR UPDATE OR DELETE ON transaction_entries
FOR EACH ROW EXECUTE FUNCTION app.reject_posted_entry_change();

-- -----------------------------------------------------------------------------
-- Referral program
-- -----------------------------------------------------------------------------

CREATE TABLE referral_codes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code citext NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    usage_limit integer CHECK (usage_limit IS NULL OR usage_limit > 0),
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, owner_user_id),
    UNIQUE (code)
);

CREATE UNIQUE INDEX uq_referral_codes_one_active_per_owner
    ON referral_codes (owner_user_id) WHERE status = 'active';

CREATE TABLE referrals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    referral_code_id uuid NOT NULL REFERENCES referral_codes(id) ON DELETE RESTRICT,
    referrer_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    referred_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    status text NOT NULL DEFAULT 'attributed'
        CHECK (status IN ('attributed', 'qualified', 'rewarded', 'rejected')),
    rejection_reason text,
    attributed_at timestamptz NOT NULL DEFAULT now(),
    qualified_at timestamptz,
    rewarded_at timestamptz,
    UNIQUE (referred_user_id),
    FOREIGN KEY (referral_code_id, referrer_user_id)
        REFERENCES referral_codes(id, owner_user_id) ON DELETE RESTRICT,
    CHECK (referrer_user_id <> referred_user_id),
    CHECK ((status = 'rejected') = (rejection_reason IS NOT NULL)),
    CHECK (qualified_at IS NULL OR qualified_at >= attributed_at),
    CHECK (rewarded_at IS NULL OR qualified_at IS NOT NULL),
    CHECK ((status = 'rewarded') = (rewarded_at IS NOT NULL))
);

CREATE INDEX ix_referrals_referrer ON referrals (referrer_user_id, attributed_at DESC);

CREATE TABLE referral_rewards (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    referral_id uuid NOT NULL REFERENCES referrals(id) ON DELETE RESTRICT,
    beneficiary_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    reward_side text NOT NULL CHECK (reward_side IN ('referrer', 'referred')),
    reward_type text NOT NULL CHECK (reward_type IN ('subscription_days', 'wallet_credit')),
    days smallint,
    amount_minor bigint,
    currency char(3),
    transaction_id uuid REFERENCES transactions(id) ON DELETE RESTRICT,
    subscription_period_id uuid REFERENCES subscription_periods(id) ON DELETE RESTRICT,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'granted', 'revoked')),
    granted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (referral_id, reward_side),
    CHECK (
        (reward_type = 'subscription_days' AND days IS NOT NULL AND days > 0
         AND amount_minor IS NULL AND currency IS NULL)
        OR
        (reward_type = 'wallet_credit' AND days IS NULL AND amount_minor IS NOT NULL
         AND amount_minor > 0 AND currency IS NOT NULL AND currency = upper(currency))
    ),
    CHECK ((status IN ('granted', 'revoked')) = (granted_at IS NOT NULL))
);

CREATE INDEX ix_referral_rewards_beneficiary
    ON referral_rewards (beneficiary_user_id, created_at DESC);

-- -----------------------------------------------------------------------------
-- Promo codes
-- -----------------------------------------------------------------------------

CREATE TABLE promo_codes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code citext NOT NULL,
    promo_type text NOT NULL CHECK (promo_type IN ('discount_percent', 'free_days')),
    value integer NOT NULL CHECK (value > 0),
    currency char(3),
    usage_limit integer CHECK (usage_limit IS NULL OR usage_limit > 0),
    per_user_limit smallint NOT NULL DEFAULT 1 CHECK (per_user_limit > 0),
    starts_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    is_active boolean NOT NULL DEFAULT true,
    created_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (code),
    CHECK (expires_at IS NULL OR expires_at > starts_at),
    CHECK (promo_type <> 'discount_percent' OR value BETWEEN 1 AND 100),
    CHECK (currency IS NULL OR currency = upper(currency))
);

CREATE INDEX ix_promo_codes_active_window
    ON promo_codes (starts_at, expires_at) WHERE is_active;

CREATE TABLE promo_code_plan_versions (
    promo_code_id uuid NOT NULL REFERENCES promo_codes(id) ON DELETE CASCADE,
    plan_version_id uuid NOT NULL REFERENCES plan_versions(id) ON DELETE CASCADE,
    PRIMARY KEY (promo_code_id, plan_version_id)
);

CREATE TABLE promo_redemptions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    promo_code_id uuid NOT NULL REFERENCES promo_codes(id) ON DELETE RESTRICT,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    payment_id uuid REFERENCES payments(id) ON DELETE RESTRICT,
    subscription_period_id uuid REFERENCES subscription_periods(id) ON DELETE RESTRICT,
    discount_amount_minor bigint CHECK (discount_amount_minor IS NULL OR discount_amount_minor >= 0),
    free_days smallint CHECK (free_days IS NULL OR free_days > 0),
    redeemed_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    CHECK (num_nonnulls(discount_amount_minor, free_days) = 1)
);

CREATE INDEX ix_promo_redemptions_code ON promo_redemptions (promo_code_id, redeemed_at);
CREATE INDEX ix_promo_redemptions_user ON promo_redemptions (user_id, redeemed_at DESC);

-- -----------------------------------------------------------------------------
-- Support tickets
-- -----------------------------------------------------------------------------

CREATE TABLE tickets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    public_number bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    assigned_to_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    subject varchar(200) NOT NULL,
    category text NOT NULL DEFAULT 'general'
        CHECK (category IN ('general', 'connection', 'payment', 'subscription', 'account', 'other')),
    priority text NOT NULL DEFAULT 'normal'
        CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    status text NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'in_progress', 'waiting_user', 'closed')),
    last_message_at timestamptz NOT NULL DEFAULT now(),
    closed_at timestamptz,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((status = 'closed') = (closed_at IS NOT NULL))
);

CREATE INDEX ix_tickets_user_created_at ON tickets (user_id, created_at DESC);
CREATE INDEX ix_tickets_admin_queue
    ON tickets (priority DESC, last_message_at)
    WHERE status IN ('open', 'in_progress');
CREATE INDEX ix_tickets_assignee
    ON tickets (assigned_to_user_id, status) WHERE assigned_to_user_id IS NOT NULL;

CREATE TABLE ticket_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id uuid NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    sender_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    message_type text NOT NULL DEFAULT 'message'
        CHECK (message_type IN ('message', 'internal_note', 'system')),
    body text NOT NULL CHECK (length(btrim(body)) > 0),
    edited_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((message_type = 'system') OR sender_user_id IS NOT NULL)
);

CREATE INDEX ix_ticket_messages_ticket ON ticket_messages (ticket_id, created_at, id);

CREATE TABLE ticket_attachments (
    ticket_message_id uuid NOT NULL REFERENCES ticket_messages(id) ON DELETE CASCADE,
    storage_object_id uuid NOT NULL REFERENCES storage_objects(id) ON DELETE RESTRICT,
    PRIMARY KEY (ticket_message_id, storage_object_id)
);

-- -----------------------------------------------------------------------------
-- Audit, outbox, and idempotency
-- -----------------------------------------------------------------------------

CREATE TABLE audit_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    actor_type text NOT NULL CHECK (actor_type IN ('user', 'admin', 'support', 'service', 'system')),
    action varchar(160) NOT NULL,
    entity_type varchar(120) NOT NULL,
    entity_id uuid,
    reason text,
    before_state jsonb,
    after_state jsonb,
    ip_address inet,
    user_agent text,
    request_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (before_state IS NULL OR jsonb_typeof(before_state) = 'object'),
    CHECK (after_state IS NULL OR jsonb_typeof(after_state) = 'object')
);

CREATE INDEX ix_audit_logs_entity ON audit_logs (entity_type, entity_id, created_at DESC);
CREATE INDEX ix_audit_logs_actor ON audit_logs (actor_user_id, created_at DESC);
CREATE INDEX ix_audit_logs_request_id ON audit_logs (request_id) WHERE request_id IS NOT NULL;

CREATE TRIGGER trg_audit_logs_append_only
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION app.reject_mutation();

CREATE TABLE outbox_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type varchar(120) NOT NULL,
    aggregate_id uuid NOT NULL,
    event_type varchar(160) NOT NULL,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    idempotency_key varchar(255) NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    available_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    attempt_count smallint NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_error text,
    UNIQUE (idempotency_key)
);

CREATE INDEX ix_outbox_events_claim
    ON outbox_events (available_at, occurred_at)
    WHERE published_at IS NULL;

CREATE TABLE idempotency_records (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scope varchar(160) NOT NULL,
    idempotency_key varchar(255) NOT NULL,
    request_hash bytea NOT NULL,
    response_status smallint CHECK (response_status BETWEEN 100 AND 599),
    response_body jsonb,
    resource_type varchar(120),
    resource_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    UNIQUE (scope, idempotency_key),
    CHECK (expires_at > created_at),
    CHECK (response_body IS NULL OR jsonb_typeof(response_body) IN ('object', 'array'))
);

CREATE INDEX ix_idempotency_records_expiry ON idempotency_records (expires_at);

-- -----------------------------------------------------------------------------
-- updated_at triggers
-- -----------------------------------------------------------------------------

CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION app.set_updated_at();
CREATE TRIGGER trg_user_emails_updated_at BEFORE UPDATE ON user_emails
FOR EACH ROW EXECUTE FUNCTION app.set_updated_at();
CREATE TRIGGER trg_telegram_accounts_updated_at BEFORE UPDATE ON telegram_accounts
FOR EACH ROW EXECUTE FUNCTION app.set_updated_at();
CREATE TRIGGER trg_plans_updated_at BEFORE UPDATE ON plans
FOR EACH ROW EXECUTE FUNCTION app.set_updated_at();
CREATE TRIGGER trg_subscriptions_updated_at BEFORE UPDATE ON subscriptions
FOR EACH ROW EXECUTE FUNCTION app.set_updated_at();
CREATE TRIGGER trg_family_groups_updated_at BEFORE UPDATE ON family_groups
FOR EACH ROW EXECUTE FUNCTION app.set_updated_at();
CREATE TRIGGER trg_vpn_accounts_updated_at BEFORE UPDATE ON vpn_accounts
FOR EACH ROW EXECUTE FUNCTION app.set_updated_at();
CREATE TRIGGER trg_devices_updated_at BEFORE UPDATE ON devices
FOR EACH ROW EXECUTE FUNCTION app.set_updated_at();
CREATE TRIGGER trg_vpn_sync_commands_updated_at BEFORE UPDATE ON vpn_sync_commands
FOR EACH ROW EXECUTE FUNCTION app.set_updated_at();
CREATE TRIGGER trg_payments_updated_at BEFORE UPDATE ON payments
FOR EACH ROW EXECUTE FUNCTION app.set_updated_at();
CREATE TRIGGER trg_ledger_accounts_updated_at BEFORE UPDATE ON ledger_accounts
FOR EACH ROW EXECUTE FUNCTION app.set_updated_at();
CREATE TRIGGER trg_referral_codes_updated_at BEFORE UPDATE ON referral_codes
FOR EACH ROW EXECUTE FUNCTION app.set_updated_at();
CREATE TRIGGER trg_promo_codes_updated_at BEFORE UPDATE ON promo_codes
FOR EACH ROW EXECUTE FUNCTION app.set_updated_at();
CREATE TRIGGER trg_tickets_updated_at BEFORE UPDATE ON tickets
FOR EACH ROW EXECUTE FUNCTION app.set_updated_at();

COMMENT ON SCHEMA app IS 'Hazbit VPN Platform business schema';
COMMENT ON TABLE plan_versions IS 'Immutable entitlement policy versions; never rewrite a version referenced by a subscription.';
COMMENT ON TABLE subscription_periods IS 'Non-overlapping entitlement periods and immutable commercial snapshots.';
COMMENT ON TABLE vpn_accounts IS 'Desired local VPN state plus last observed Remnawave state.';
COMMENT ON TABLE devices IS 'Local slots and observed HWIDs. Remnawave v3.3.2 does not expose HWID creation.';
COMMENT ON TABLE payment_analyses IS 'AI extraction evidence; deterministic application rules decide approval.';
COMMENT ON TABLE transaction_entries IS 'Signed double-entry postings; balance is SUM(amount_minor), never a mutable users.balance column.';
COMMENT ON TABLE audit_logs IS 'Append-only security and administrative audit trail.';
COMMENT ON TABLE outbox_events IS 'Transactional outbox; publishers claim unpublished rows with SKIP LOCKED.';

COMMIT;

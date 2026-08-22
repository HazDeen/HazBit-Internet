-- Run with psql -v ON_ERROR_STOP=1 after database/schema.sql.
-- Every row is rolled back; the script verifies high-value invariants.

BEGIN;
SET search_path TO app, public;

INSERT INTO users (id, public_name)
VALUES
    ('00000000-0000-7000-8000-000000000001', 'Owner'),
    ('00000000-0000-7000-8000-000000000002', 'Member');

INSERT INTO user_emails (user_id, email, is_primary, verified_at)
VALUES ('00000000-0000-7000-8000-000000000001', 'Owner@Example.com', true, now());

DO $$
BEGIN
    BEGIN
        INSERT INTO user_emails (user_id, email)
        VALUES ('00000000-0000-7000-8000-000000000002', 'owner@example.com');
        RAISE EXCEPTION 'citext email uniqueness was not enforced';
    EXCEPTION WHEN unique_violation THEN
        NULL;
    END;
END;
$$;

INSERT INTO plans (id, slug, name)
VALUES ('10000000-0000-7000-8000-000000000001', 'smoke_family', 'Smoke Family');

INSERT INTO plan_versions (
    id, plan_id, version, device_limit, family_member_limit
)
VALUES (
    '11000000-0000-7000-8000-000000000001',
    '10000000-0000-7000-8000-000000000001',
    1,
    10,
    5
);

INSERT INTO plan_prices (
    id, plan_version_id, term_months, duration_days, currency, amount_minor
)
VALUES (
    '12000000-0000-7000-8000-000000000001',
    '11000000-0000-7000-8000-000000000001',
    1,
    30,
    'RUB',
    10000
);

INSERT INTO subscriptions (
    id, owner_user_id, plan_version_id, status, source, starts_at,
    current_period_ends_at
)
VALUES (
    '20000000-0000-7000-8000-000000000001',
    '00000000-0000-7000-8000-000000000001',
    '11000000-0000-7000-8000-000000000001',
    'active',
    'purchase',
    '2026-01-01T00:00:00Z',
    '2026-03-01T00:00:00Z'
);

INSERT INTO subscription_periods (
    id, subscription_id, source_type, starts_at, ends_at, plan_snapshot,
    price_minor, currency
)
VALUES (
    '21000000-0000-7000-8000-000000000001',
    '20000000-0000-7000-8000-000000000001',
    'payment',
    '2026-01-01T00:00:00Z',
    '2026-02-01T00:00:00Z',
    '{"plan":"smoke_family","version":1,"device_limit":10,"family_member_limit":5}',
    10000,
    'RUB'
);

DO $$
BEGIN
    BEGIN
        INSERT INTO subscription_periods (
            subscription_id, source_type, starts_at, ends_at, plan_snapshot
        )
        VALUES (
            '20000000-0000-7000-8000-000000000001',
            'admin',
            '2026-01-15T00:00:00Z',
            '2026-02-15T00:00:00Z',
            '{}'::jsonb
        );
        RAISE EXCEPTION 'overlapping subscription period was accepted';
    EXCEPTION WHEN exclusion_violation THEN
        NULL;
    END;
END;
$$;

DO $$
BEGIN
    BEGIN
        INSERT INTO family_groups (
            owner_user_id, subscription_id, name, member_limit
        )
        VALUES (
            '00000000-0000-7000-8000-000000000002',
            '20000000-0000-7000-8000-000000000001',
            'Wrong owner',
            5
        );
        RAISE EXCEPTION 'family group accepted a subscription owned by another user';
    EXCEPTION WHEN foreign_key_violation THEN
        NULL;
    END;
END;
$$;

INSERT INTO family_groups (
    id, owner_user_id, subscription_id, name, member_limit
)
VALUES (
    '30000000-0000-7000-8000-000000000001',
    '00000000-0000-7000-8000-000000000001',
    '20000000-0000-7000-8000-000000000001',
    'Test family',
    5
);

INSERT INTO family_members (family_group_id, user_id)
VALUES (
    '30000000-0000-7000-8000-000000000001',
    '00000000-0000-7000-8000-000000000002'
);

INSERT INTO ledger_accounts (
    id, account_key, owner_user_id, account_type, currency
)
VALUES (
    '40000000-0000-7000-8000-000000000001',
    'wallet:owner',
    '00000000-0000-7000-8000-000000000001',
    'user_wallet',
    'RUB'
), (
    '40000000-0000-7000-8000-000000000002',
    'cash-clearing',
    NULL,
    'cash_clearing',
    'RUB'
);

INSERT INTO transactions (
    id, user_id, transaction_type, currency, idempotency_key
)
VALUES (
    '41000000-0000-7000-8000-000000000001',
    '00000000-0000-7000-8000-000000000001',
    'payment_credit',
    'RUB',
    'smoke:payment-credit'
);

INSERT INTO transactions (
    id, user_id, transaction_type, currency, idempotency_key
)
VALUES (
    '41000000-0000-7000-8000-000000000002',
    '00000000-0000-7000-8000-000000000001',
    'admin_adjustment',
    'RUB',
    'smoke:unbalanced'
);

INSERT INTO transaction_entries (transaction_id, ledger_account_id, amount_minor)
VALUES (
    '41000000-0000-7000-8000-000000000002',
    '40000000-0000-7000-8000-000000000001',
    1
);

DO $$
BEGIN
    BEGIN
        UPDATE transactions
        SET status = 'posted', posted_at = now()
        WHERE id = '41000000-0000-7000-8000-000000000002';
        RAISE EXCEPTION 'unbalanced transaction was posted';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;
END;
$$;

INSERT INTO transaction_entries (transaction_id, ledger_account_id, amount_minor)
VALUES
    ('41000000-0000-7000-8000-000000000001', '40000000-0000-7000-8000-000000000001', 10000),
    ('41000000-0000-7000-8000-000000000001', '40000000-0000-7000-8000-000000000002', -10000);

UPDATE transactions
SET status = 'posted', posted_at = now()
WHERE id = '41000000-0000-7000-8000-000000000001';

DO $$
BEGIN
    BEGIN
        UPDATE transaction_entries
        SET amount_minor = 9999
        WHERE transaction_id = '41000000-0000-7000-8000-000000000001'
          AND ledger_account_id = '40000000-0000-7000-8000-000000000001';
        RAISE EXCEPTION 'posted ledger entry was mutable';
    EXCEPTION WHEN object_not_in_prerequisite_state THEN
        NULL;
    END;
END;
$$;

DO $$
BEGIN
    BEGIN
        INSERT INTO transaction_entries (
            transaction_id, ledger_account_id, amount_minor
        )
        VALUES (
            '41000000-0000-7000-8000-000000000001',
            '40000000-0000-7000-8000-000000000001',
            1
        );
        RAISE EXCEPTION 'new entry was added to a posted transaction';
    EXCEPTION WHEN object_not_in_prerequisite_state THEN
        NULL;
    END;
END;
$$;

DO $$
BEGIN
    IF (
        SELECT COALESCE(sum(te.amount_minor), 0)
        FROM transaction_entries te
        JOIN transactions t ON t.id = te.transaction_id
        WHERE t.status = 'posted'
          AND te.ledger_account_id = '40000000-0000-7000-8000-000000000001'
    ) <> 10000 THEN
        RAISE EXCEPTION 'wallet balance projection is incorrect';
    END IF;
END;
$$;

ROLLBACK;

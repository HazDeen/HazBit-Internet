-- Reference plan catalog from the product brief.
-- Prices are intentionally not seeded: amount/currency are commercial decisions.

BEGIN;
SET search_path TO app, public;

INSERT INTO plans (slug, name, description, sort_order)
VALUES
    ('basic', 'Basic', 'Personal VPN plan', 10),
    ('premium', 'Premium', 'Extended personal VPN plan', 20),
    ('family', 'Family', 'Shared VPN plan for a family group', 30)
ON CONFLICT (slug) DO NOTHING;

INSERT INTO plan_versions (
    plan_id,
    version,
    device_limit,
    family_member_limit,
    remnawave_policy
)
SELECT p.id, 1, seed.device_limit, seed.family_member_limit, '{}'::jsonb
FROM (
    VALUES
        ('basic'::citext, 3::smallint, 0::smallint),
        ('premium'::citext, 5::smallint, 0::smallint),
        ('family'::citext, 10::smallint, 5::smallint)
) AS seed(slug, device_limit, family_member_limit)
JOIN plans p ON p.slug = seed.slug
WHERE NOT EXISTS (
    SELECT 1
    FROM plan_versions pv
    WHERE pv.plan_id = p.id AND pv.version = 1
);

COMMIT;

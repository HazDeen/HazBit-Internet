from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import LaunchPlanPriceSettings, Settings
from app.core.ids import uuid7
from app.database.session import DatabaseManager
from app.integrations.redis import RedisManager


class LaunchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CatalogPlan:
    slug: str
    name: str
    description: str
    sort_order: int
    device_limit: int
    family_member_limit: int


CATALOG = (
    CatalogPlan("basic", "Basic", "Personal VLESS access", 10, 3, 0),
    CatalogPlan("premium", "Premium", "Extended personal VLESS access", 20, 5, 0),
    CatalogPlan("family", "Family", "Shared VLESS access for a family group", 30, 10, 5),
)


async def bootstrap_launch(settings: Settings) -> None:
    database = DatabaseManager(settings.database)
    try:
        async with database.session() as session, session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": "hazbit-launch-bootstrap"},
            )
            versions = await _ensure_catalog(session)
            await _ensure_prices(session, versions, settings.launch.plan_prices)
            active_super_admin = await session.scalar(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM app.users u
                        JOIN app.user_roles ur ON ur.user_id = u.id
                        WHERE u.status = 'active'
                          AND ur.role = 'super_admin'
                          AND ur.revoked_at IS NULL
                    )
                    """
                )
            )
            if not active_super_admin and settings.launch.super_admin_email is not None:
                await _ensure_super_admin(session, str(settings.launch.super_admin_email))
    finally:
        await database.dispose()


async def verify_launch_readiness(settings: Settings) -> None:
    database = DatabaseManager(settings.database)
    redis = RedisManager(settings.redis)
    try:
        await database.ping()
        await redis.ping()
        async with database.session() as session:
            await _verify_catalog(session)
    finally:
        await redis.dispose()
        await database.dispose()


async def _ensure_catalog(session: AsyncSession) -> dict[str, UUID]:
    versions: dict[str, UUID] = {}
    for plan in CATALOG:
        existing_plan = (
            await session.execute(
                text("SELECT id, is_active FROM app.plans WHERE slug = :slug"),
                {"slug": plan.slug},
            )
        ).mappings().one_or_none()
        created = existing_plan is None
        if existing_plan is None:
            plan_id = uuid7()
            plan_is_active = True
            await session.execute(
                text(
                    """
                    INSERT INTO app.plans
                        (id, slug, name, description, is_active, sort_order)
                    VALUES
                        (:id, :slug, :name, :description, true, :sort_order)
                    """
                ),
                {
                    "id": plan_id,
                    "slug": plan.slug,
                    "name": plan.name,
                    "description": plan.description,
                    "sort_order": plan.sort_order,
                },
            )
        else:
            plan_id = existing_plan["id"]
            plan_is_active = bool(existing_plan["is_active"])

        version = (
            await session.execute(
                text(
                    """
                    SELECT id
                    FROM app.plan_versions
                    WHERE plan_id = :plan_id AND valid_until IS NULL
                    ORDER BY version DESC
                    LIMIT 1
                    """
                ),
                {"plan_id": plan_id},
            )
        ).mappings().one_or_none()
        if version is None and created:
            version_id = uuid7()
            await session.execute(
                text(
                    """
                    INSERT INTO app.plan_versions
                        (id, plan_id, version, device_limit, family_member_limit,
                         remnawave_policy)
                    VALUES
                        (:id, :plan_id, 1, :device_limit, :family_member_limit,
                         CAST(:policy AS jsonb))
                    """
                ),
                {
                    "id": version_id,
                    "plan_id": plan_id,
                    "device_limit": plan.device_limit,
                    "family_member_limit": plan.family_member_limit,
                    "policy": "{}",
                },
            )
        elif version is None:
            if plan_is_active:
                raise LaunchError(f"active plan {plan.slug!r} has no current version")
            continue
        else:
            version_id = version["id"]
        if plan_is_active:
            versions[plan.slug] = version_id
    return versions


async def _ensure_prices(
    session: AsyncSession,
    versions: dict[str, UUID],
    prices: list[LaunchPlanPriceSettings],
) -> None:
    for price in prices:
        version_id = versions.get(price.plan_slug)
        if version_id is None:
            continue
        existing = (
            await session.execute(
                text(
                    """
                    SELECT amount_minor, duration_days
                    FROM app.plan_prices
                    WHERE plan_version_id = :version_id
                      AND term_months = :term_months
                      AND currency = :currency
                      AND is_active
                      AND valid_until IS NULL
                    ORDER BY valid_from DESC
                    LIMIT 1
                    """
                ),
                {
                    "version_id": version_id,
                    "term_months": price.term_months,
                    "currency": price.currency,
                },
            )
        ).mappings().one_or_none()
        if existing is not None:
            continue
        await session.execute(
            text(
                """
                INSERT INTO app.plan_prices
                    (id, plan_version_id, term_months, duration_days, currency,
                     amount_minor, is_active)
                VALUES
                    (:id, :version_id, :term_months, :duration_days, :currency,
                     :amount_minor, true)
                """
            ),
            {
                "id": uuid7(),
                "version_id": version_id,
                "term_months": price.term_months,
                "duration_days": price.duration_days,
                "currency": price.currency,
                "amount_minor": price.amount_minor,
            },
        )


async def _ensure_super_admin(session: AsyncSession, email: str) -> None:
    normalized_email = email.strip().casefold()
    existing = (
        await session.execute(
            text(
                """
                SELECT u.id, u.status
                FROM app.users u
                JOIN app.user_emails ue ON ue.user_id = u.id
                WHERE ue.email = :email
                """
            ),
            {"email": normalized_email},
        )
    ).mappings().one_or_none()
    created = existing is None
    if existing is None:
        user_id = uuid7()
        await session.execute(
            text("INSERT INTO app.users (id, status) VALUES (:id, 'active')"),
            {"id": user_id},
        )
        await session.execute(
            text(
                """
                INSERT INTO app.user_emails
                    (id, user_id, email, is_primary, verified_at)
                VALUES
                    (:id, :user_id, :email, true, now())
                """
            ),
            {"id": uuid7(), "user_id": user_id, "email": normalized_email},
        )
    else:
        user_id = existing["id"]
        if existing["status"] != "active":
            raise LaunchError("the configured first super admin user is not active")

    had_active_super_admin = bool(
        await session.scalar(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM app.user_roles
                    WHERE user_id = :user_id
                      AND role = 'super_admin'
                      AND revoked_at IS NULL
                )
                """
            ),
            {"user_id": user_id},
        )
    )
    for role in ("user", "super_admin"):
        await session.execute(
            text(
                """
                INSERT INTO app.user_roles (user_id, role, granted_by, revoked_at)
                VALUES (:user_id, :role, NULL, NULL)
                ON CONFLICT (user_id, role) DO UPDATE
                SET revoked_at = NULL,
                    granted_at = CASE
                        WHEN user_roles.revoked_at IS NULL THEN user_roles.granted_at
                        ELSE now()
                    END
                """
            ),
            {"user_id": user_id, "role": role},
        )

    if not had_active_super_admin:
        await session.execute(
            text(
                """
                INSERT INTO app.audit_logs
                    (actor_user_id, actor_type, action, entity_type, entity_id, after_state)
                VALUES
                    (NULL, 'system', :action, 'user', :user_id,
                     CAST(:after_state AS jsonb))
                """
            ),
            {
                "user_id": user_id,
                "action": (
                    "bootstrap.super_admin.created"
                    if created
                    else "bootstrap.super_admin.granted"
                ),
                "after_state": json.dumps(
                    {"email": normalized_email, "roles": ["user", "super_admin"]}
                ),
            },
        )


async def _verify_catalog(session: AsyncSession) -> None:
    plan_rows = (
        await session.execute(
            text(
                """
                SELECT p.slug, count(pp.id) AS active_price_count
                FROM app.plans p
                JOIN app.plan_versions pv
                  ON pv.plan_id = p.id AND pv.valid_until IS NULL
                LEFT JOIN app.plan_prices pp
                  ON pp.plan_version_id = pv.id
                 AND pp.is_active
                 AND pp.valid_until IS NULL
                WHERE p.is_active
                GROUP BY p.slug
                """
            ),
        )
    ).mappings().all()
    counts = {str(row["slug"]): int(row["active_price_count"]) for row in plan_rows}
    if not counts:
        raise LaunchError("no active plans are configured")
    missing = [slug for slug, count in counts.items() if count == 0]
    if missing:
        raise LaunchError(f"plans without active prices: {', '.join(missing)}")

    super_admin_exists = await session.scalar(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM app.users u
                JOIN app.user_roles ur ON ur.user_id = u.id
                WHERE u.status = 'active'
                  AND ur.role = 'super_admin'
                  AND ur.revoked_at IS NULL
            )
            """
        )
    )
    if not super_admin_exists:
        raise LaunchError("no active super admin is configured")

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApplicationError
from app.modules.portal.repository import PortalRepository
from app.modules.portal.schemas import (
    PortalIdentityResponse,
    PortalOverviewResponse,
    PortalPaymentResponse,
    PortalPlanPriceResponse,
    PortalPlanResponse,
    PortalSubscriptionResponse,
    PortalVpnResponse,
)


class PortalService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = PortalRepository(session)

    async def overview(self, user_id: UUID) -> PortalOverviewResponse:
        identity = await self._repository.identity(user_id)
        if identity is None:
            raise ApplicationError("portal_user_not_found", "User not found.", 404)
        user, email, telegram_user_id, telegram_username = identity
        subscription_row = await self._repository.subscription(user_id)
        account = await self._repository.vpn_account(user_id)
        group = await self._repository.family_group(user_id)
        subscription = None
        if subscription_row is not None:
            value, version, plan = subscription_row
            subscription = PortalSubscriptionResponse(
                id=value.id,
                status=value.status,
                source=value.source,
                plan_version_id=version.id,
                plan_slug=plan.slug,
                plan_name=plan.name,
                starts_at=value.starts_at,
                current_period_ends_at=value.current_period_ends_at,
                device_limit=version.device_limit,
                family_member_limit=version.family_member_limit,
            )
        return PortalOverviewResponse(
            user=PortalIdentityResponse(
                id=user.id,
                public_name=user.public_name,
                email=email,
                telegram_user_id=telegram_user_id,
                telegram_username=telegram_username,
                locale=user.locale,
                created_at=user.created_at,
            ),
            subscription=subscription,
            vpn=(
                PortalVpnResponse(
                    desired_status=account.desired_status,
                    observed_status=account.observed_status,
                    expires_at=account.desired_expires_at,
                    provisioning=account.observed_status != account.desired_status,
                )
                if account
                else None
            ),
            active_device_count=await self._repository.active_device_count(user_id),
            open_ticket_count=await self._repository.open_ticket_count(user_id),
            family_group_id=group.id if group else None,
            family_group_name=group.name if group else None,
        )

    async def catalog(self) -> list[PortalPlanResponse]:
        grouped: dict[UUID, PortalPlanResponse] = {}
        for plan, version, price in await self._repository.catalog(datetime.now(UTC)):
            if plan.id not in grouped:
                grouped[plan.id] = PortalPlanResponse(
                    id=plan.id,
                    slug=plan.slug,
                    name=plan.name,
                    description=plan.description,
                    plan_version_id=version.id,
                    device_limit=version.device_limit,
                    family_member_limit=version.family_member_limit,
                    traffic_limit_bytes=version.traffic_limit_bytes,
                )
            grouped[plan.id].prices.append(
                PortalPlanPriceResponse(
                    id=price.id,
                    term_months=price.term_months,
                    duration_days=price.duration_days,
                    currency=price.currency,
                    amount_minor=price.amount_minor,
                )
            )
        return list(grouped.values())

    async def payments(self, user_id: UUID, limit: int) -> list[PortalPaymentResponse]:
        return [
            PortalPaymentResponse(
                id=item.id,
                plan_price_id=item.plan_price_id,
                status=item.status,
                amount_minor=item.expected_amount_minor,
                currency=item.currency,
                expires_at=item.expires_at,
                uploaded_at=item.uploaded_at,
                approved_at=item.approved_at,
                rejection_reason=item.rejection_reason,
                created_at=item.created_at,
            )
            for item in await self._repository.payments(user_id, limit)
        ]

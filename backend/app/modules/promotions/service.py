from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PromoSettings
from app.core.errors import ApplicationError
from app.core.ids import uuid7
from app.modules.auth.models import AuditLog
from app.modules.auth.rate_limit import RateLimit, RateLimiter
from app.modules.payments.models import OutboxEvent, Payment, PlanPrice
from app.modules.promotions.enums import PromoType
from app.modules.promotions.models import PromoCode, PromoCodePlanVersion, PromoRedemption
from app.modules.promotions.repository import PromotionRepository
from app.modules.promotions.schemas import (
    AdminPromoCodeResponse,
    CreatePromoCodeRequest,
    PromoPreviewResponse,
    PromoRedemptionResponse,
    UpdatePromoCodeRequest,
)
from app.modules.referrals.models import SubscriptionPeriod
from app.modules.vpn.enums import CommandStatus, CommandType, DesiredVpnStatus
from app.modules.vpn.models import PlanVersion, Subscription, VpnAccount, VpnSyncCommand


@dataclass(frozen=True, slots=True)
class PromoClientContext:
    ip_address: str
    user_agent: str | None
    request_id: UUID | None


class PromotionService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: PromoSettings,
        rate_limiter: RateLimiter,
    ) -> None:
        self._session = session
        self._settings = settings
        self._rate_limiter = rate_limiter
        self._repository = PromotionRepository(session)

    async def preview(
        self,
        *,
        user_id: UUID,
        code_value: str,
        plan_price_id: UUID | None,
        plan_version_id: UUID | None,
    ) -> PromoPreviewResponse:
        await self._rate_limiter.enforce(
            RateLimit("promo_preview_user", self._settings.preview_rate_limit_per_hour, 3600),
            str(user_id),
        )
        now = datetime.now(UTC)
        async with self._session.begin():
            promo = await self._require_available(
                code_value=code_value, user_id=user_id, now=now, for_update=False
            )
            if promo.promo_type == PromoType.DISCOUNT_PERCENT.value:
                if plan_price_id is None:
                    raise ApplicationError(
                        "promo_plan_price_required",
                        "A plan price is required to preview this discount.",
                        422,
                    )
                price = await self._repository.active_plan_price(plan_price_id, now)
                if price is None:
                    raise ApplicationError("plan_price_not_found", "Plan price not found.", 404)
                await self._validate_plan_scope(promo.id, price.plan_version_id)
                self._validate_currency(promo, price.currency)
                discount = self._discount_amount(price.amount_minor, promo.value)
                return PromoPreviewResponse(
                    code=promo.code,
                    promo_type=promo.promo_type,
                    value=promo.value,
                    starts_at=promo.starts_at,
                    expires_at=promo.expires_at,
                    plan_version_id=price.plan_version_id,
                    original_amount_minor=price.amount_minor,
                    discount_amount_minor=discount,
                    final_amount_minor=price.amount_minor - discount,
                    currency=price.currency,
                )

            plan = await self._resolve_free_plan(promo, plan_version_id, now)
            return PromoPreviewResponse(
                code=promo.code,
                promo_type=promo.promo_type,
                value=promo.value,
                starts_at=promo.starts_at,
                expires_at=promo.expires_at,
                plan_version_id=plan.id,
                original_amount_minor=None,
                discount_amount_minor=None,
                final_amount_minor=None,
                currency=None,
            )

    async def apply_discount_to_payment(
        self,
        *,
        user_id: UUID,
        code_value: str,
        payment: Payment,
        price: PlanPrice,
        now: datetime,
    ) -> PromoRedemption:
        await self._repository.serialize_key(f"promo:{code_value}")
        await self._repository.serialize_key(f"promo-user:{user_id}:{code_value}")
        promo = await self._require_available(
            code_value=code_value, user_id=user_id, now=now, for_update=True
        )
        if promo.promo_type != PromoType.DISCOUNT_PERCENT.value:
            raise ApplicationError(
                "promo_wrong_redemption_flow",
                "Free-day promo codes must be redeemed through the promo endpoint.",
                409,
            )
        await self._validate_plan_scope(promo.id, price.plan_version_id)
        self._validate_currency(promo, price.currency)
        discount = self._discount_amount(price.amount_minor, promo.value)
        final_amount = price.amount_minor - discount
        if final_amount <= 0:
            raise ApplicationError(
                "promo_discount_invalid_total",
                "This discount does not produce a payable amount.",
                409,
            )
        payment.expected_amount_minor = final_amount
        redemption = PromoRedemption(
            promo_code_id=promo.id,
            user_id=user_id,
            payment_id=payment.id,
            discount_amount_minor=discount,
            free_days=None,
            redeemed_at=now,
        )
        self._session.add(redemption)
        await self._session.flush()
        self._session.add(
            OutboxEvent(
                aggregate_type="promo_redemption",
                aggregate_id=redemption.id,
                event_type="promo.discount.applied",
                payload={
                    "redemption_id": str(redemption.id),
                    "promo_code_id": str(promo.id),
                    "payment_id": str(payment.id),
                    "user_id": str(user_id),
                    "discount_amount_minor": discount,
                    "currency": price.currency,
                },
                idempotency_key=f"promo-discount-applied:{redemption.id}",
            )
        )
        return redemption

    async def redeem_free_days(
        self,
        *,
        user_id: UUID,
        code_value: str,
        plan_version_id: UUID | None,
        client: PromoClientContext,
    ) -> PromoRedemptionResponse:
        await self._rate_limiter.enforce(
            RateLimit("promo_redeem_user", self._settings.redeem_rate_limit_per_hour, 3600),
            str(user_id),
        )
        now = datetime.now(UTC)
        async with self._session.begin():
            await self._repository.serialize_key(f"promo:{code_value}")
            await self._repository.serialize_key(f"promo-user:{user_id}:{code_value}")
            user = await self._repository.user(user_id, for_update=True)
            if user is None or user.status != "active":
                raise ApplicationError("promo_user_inactive", "User is not active.", 403)
            promo = await self._require_available(
                code_value=code_value, user_id=user_id, now=now, for_update=True
            )
            if promo.promo_type != PromoType.FREE_DAYS.value:
                raise ApplicationError(
                    "promo_wrong_redemption_flow",
                    "Discount promo codes must be applied to a payment intent.",
                    409,
                )
            plan = await self._resolve_free_plan(promo, plan_version_id, now)
            redemption = PromoRedemption(
                promo_code_id=promo.id,
                user_id=user_id,
                payment_id=None,
                discount_amount_minor=None,
                free_days=promo.value,
                redeemed_at=now,
            )
            self._session.add(redemption)
            await self._session.flush()
            subscription, effective_plan, period = await self._grant_days(
                redemption=redemption, requested_plan=plan, now=now
            )
            redemption.subscription_period_id = period.id
            await self._enqueue_vpn_sync(
                redemption=redemption,
                subscription=subscription,
                plan=effective_plan,
                now=now,
            )
            self._session.add(
                OutboxEvent(
                    aggregate_type="promo_redemption",
                    aggregate_id=redemption.id,
                    event_type="promo.free_days.redeemed",
                    payload={
                        "redemption_id": str(redemption.id),
                        "promo_code_id": str(promo.id),
                        "user_id": str(user_id),
                        "free_days": promo.value,
                        "subscription_id": str(subscription.id),
                        "subscription_ends_at": period.ends_at.isoformat(),
                    },
                    idempotency_key=f"promo-free-days-redeemed:{redemption.id}",
                )
            )
            self._session.add(
                AuditLog(
                    actor_user_id=user_id,
                    actor_type="user",
                    action="promo.free_days_redeemed",
                    entity_type="promo_redemption",
                    entity_id=redemption.id,
                    after_state={
                        "promo_code_id": str(promo.id),
                        "free_days": promo.value,
                        "subscription_ends_at": period.ends_at.isoformat(),
                    },
                    ip_address=client.ip_address,
                    user_agent=client.user_agent,
                    request_id=client.request_id,
                )
            )
            await self._session.flush()
            return self._redemption_response(redemption, promo, subscription_ends_at=period.ends_at)

    async def user_redemptions(self, user_id: UUID) -> list[PromoRedemptionResponse]:
        rows = await self._repository.redemptions_for_user(user_id)
        result: list[PromoRedemptionResponse] = []
        for redemption, promo in rows:
            ends_at = None
            if redemption.subscription_period_id is not None:
                ends_at = await self._session.scalar(
                    select(SubscriptionPeriod.ends_at).where(
                        SubscriptionPeriod.id == redemption.subscription_period_id
                    )
                )
            result.append(
                self._redemption_response(redemption, promo, subscription_ends_at=ends_at)
            )
        return result

    async def create_code(
        self, *, payload: CreatePromoCodeRequest, admin_user_id: UUID
    ) -> AdminPromoCodeResponse:
        async with self._session.begin():
            await self._repository.serialize_key(f"promo:{payload.code}")
            if await self._repository.code(payload.code) is not None:
                raise ApplicationError("promo_code_exists", "Promo code already exists.", 409)
            if not await self._repository.plan_versions_exist(payload.plan_version_ids):
                raise ApplicationError(
                    "promo_plan_version_not_found", "One or more plan versions do not exist.", 404
                )
            promo = PromoCode(
                code=payload.code,
                promo_type=payload.promo_type,
                value=payload.value,
                currency=payload.currency,
                usage_limit=payload.usage_limit,
                per_user_limit=payload.per_user_limit,
                starts_at=payload.starts_at,
                expires_at=payload.expires_at,
                is_active=True,
                created_by_user_id=admin_user_id,
            )
            self._session.add(promo)
            await self._session.flush()
            self._session.add_all(
                PromoCodePlanVersion(promo_code_id=promo.id, plan_version_id=version_id)
                for version_id in payload.plan_version_ids
            )
            self._session.add(
                AuditLog(
                    actor_user_id=admin_user_id,
                    actor_type="admin",
                    action="promo.created",
                    entity_type="promo_code",
                    entity_id=promo.id,
                    after_state={
                        "code": promo.code,
                        "promo_type": promo.promo_type,
                        "value": promo.value,
                        "usage_limit": promo.usage_limit,
                        "per_user_limit": promo.per_user_limit,
                        "plan_version_ids": [str(value) for value in payload.plan_version_ids],
                    },
                )
            )
            await self._session.flush()
            return await self._admin_response(promo, payload.plan_version_ids)

    async def update_code(
        self,
        *,
        promo_id: UUID,
        payload: UpdatePromoCodeRequest,
        admin_user_id: UUID,
    ) -> AdminPromoCodeResponse:
        async with self._session.begin():
            promo = await self._repository.code_by_id(promo_id, for_update=True)
            if promo is None:
                raise ApplicationError("promo_code_not_found", "Promo code not found.", 404)
            before = {
                "is_active": promo.is_active,
                "expires_at": promo.expires_at.isoformat() if promo.expires_at else None,
                "usage_limit": promo.usage_limit,
            }
            if "is_active" in payload.model_fields_set:
                promo.is_active = bool(payload.is_active)
            if "expires_at" in payload.model_fields_set:
                if payload.expires_at is not None and payload.expires_at <= promo.starts_at:
                    raise ApplicationError(
                        "promo_invalid_expiration",
                        "Expiration must be after the start time.",
                        422,
                    )
                promo.expires_at = payload.expires_at
            if "usage_limit" in payload.model_fields_set:
                if payload.usage_limit is not None:
                    used = await self._repository.active_usage_count(promo.id, datetime.now(UTC))
                    if payload.usage_limit < used:
                        raise ApplicationError(
                            "promo_usage_limit_below_usage",
                            "Usage limit cannot be lower than current usage.",
                            409,
                        )
                promo.usage_limit = payload.usage_limit
            promo.updated_at = datetime.now(UTC)
            plan_ids = await self._repository.plan_version_ids(promo.id)
            self._session.add(
                AuditLog(
                    actor_user_id=admin_user_id,
                    actor_type="admin",
                    action="promo.updated",
                    entity_type="promo_code",
                    entity_id=promo.id,
                    before_state=before,
                    after_state={
                        "is_active": promo.is_active,
                        "expires_at": promo.expires_at.isoformat() if promo.expires_at else None,
                        "usage_limit": promo.usage_limit,
                    },
                )
            )
            await self._session.flush()
            return await self._admin_response(promo, plan_ids)

    async def list_codes(self, limit: int) -> list[AdminPromoCodeResponse]:
        result: list[AdminPromoCodeResponse] = []
        for promo in await self._repository.list_codes(limit=limit):
            result.append(
                await self._admin_response(promo, await self._repository.plan_version_ids(promo.id))
            )
        return result

    async def archive_code(
        self, *, promo_id: UUID, reason: str, admin_user_id: UUID
    ) -> AdminPromoCodeResponse:
        async with self._session.begin():
            promo = await self._repository.code_by_id(promo_id, for_update=True)
            if promo is None:
                raise ApplicationError("promo_code_not_found", "Promo code not found.", 404)
            before = {"is_active": promo.is_active, "expires_at": None}
            promo.is_active = False
            promo.updated_at = datetime.now(UTC)
            plan_ids = await self._repository.plan_version_ids(promo.id)
            self._session.add(
                AuditLog(
                    actor_user_id=admin_user_id,
                    actor_type="admin",
                    action="promo.archived",
                    entity_type="promo_code",
                    entity_id=promo.id,
                    reason=reason,
                    before_state=before,
                    after_state={"is_active": False},
                )
            )
            self._session.add(
                OutboxEvent(
                    aggregate_type="promo_code",
                    aggregate_id=promo.id,
                    event_type="promo.archived",
                    payload={"promo_code_id": str(promo.id), "code": promo.code},
                    idempotency_key=f"promo-archived:{promo.id}:{uuid7()}",
                )
            )
            await self._session.flush()
            return await self._admin_response(promo, plan_ids)

    async def _require_available(
        self,
        *,
        code_value: str,
        user_id: UUID,
        now: datetime,
        for_update: bool,
    ) -> PromoCode:
        promo = await self._repository.code(code_value, for_update=for_update)
        if promo is None:
            raise ApplicationError("promo_code_not_found", "Promo code not found.", 404)
        if not promo.is_active:
            raise ApplicationError("promo_code_inactive", "Promo code is inactive.", 409)
        if promo.starts_at > now:
            raise ApplicationError("promo_code_not_started", "Promo code is not active yet.", 409)
        if promo.expires_at is not None and promo.expires_at <= now:
            raise ApplicationError("promo_code_expired", "Promo code has expired.", 409)
        usage = await self._repository.active_usage_count(promo.id, now)
        if promo.usage_limit is not None and usage >= promo.usage_limit:
            raise ApplicationError(
                "promo_code_usage_limit_reached", "Promo code usage limit has been reached.", 409
            )
        user_usage = await self._repository.active_user_usage_count(promo.id, user_id, now)
        if user_usage >= promo.per_user_limit:
            raise ApplicationError(
                "promo_code_user_limit_reached",
                "Promo code usage limit for this user has been reached.",
                409,
            )
        return promo

    async def _validate_plan_scope(self, promo_id: UUID, plan_version_id: UUID) -> None:
        allowed = await self._repository.plan_version_ids(promo_id)
        if allowed and plan_version_id not in allowed:
            raise ApplicationError(
                "promo_plan_not_eligible", "Promo code does not apply to this plan.", 409
            )

    async def _resolve_free_plan(
        self, promo: PromoCode, requested_id: UUID | None, now: datetime
    ) -> PlanVersion:
        allowed = await self._repository.plan_version_ids(promo.id)
        selected_id = requested_id
        if selected_id is None and len(allowed) == 1:
            selected_id = allowed[0]
        if selected_id is None and len(allowed) > 1:
            raise ApplicationError(
                "promo_plan_required", "Choose one of the eligible plan versions.", 422
            )
        if selected_id is not None:
            if allowed and selected_id not in allowed:
                raise ApplicationError(
                    "promo_plan_not_eligible", "Promo code does not apply to this plan.", 409
                )
            plan = await self._repository.active_plan_version(selected_id, now)
        else:
            plan = await self._repository.active_default_plan_version(
                self._settings.default_plan_slug, now
            )
        if plan is None:
            raise ApplicationError(
                "promo_plan_unavailable", "Promo subscription plan is unavailable.", 409
            )
        return plan

    async def _grant_days(
        self, *, redemption: PromoRedemption, requested_plan: PlanVersion, now: datetime
    ) -> tuple[Subscription, PlanVersion, SubscriptionPeriod]:
        days = redemption.free_days or 0
        subscription = await self._repository.live_subscription_for_update(redemption.user_id)
        if subscription is None:
            plan = requested_plan
            starts_at = now
            ends_at = now + timedelta(days=days)
            subscription = Subscription(
                owner_user_id=redemption.user_id,
                plan_version_id=plan.id,
                status="active",
                source="promo",
                starts_at=starts_at,
                current_period_ends_at=ends_at,
                grace_ends_at=None,
                cancel_at_period_end=False,
                cancelled_at=None,
                suspended_at=None,
                suspension_reason=None,
                version=1,
            )
            self._session.add(subscription)
            await self._session.flush()
        else:
            plan = await self._repository.plan_version(subscription.plan_version_id)
            if plan.id != requested_plan.id:
                raise ApplicationError(
                    "promo_plan_not_eligible",
                    "Promo code does not apply to the current subscription plan.",
                    409,
                )
            starts_at = max(subscription.current_period_ends_at or now, now)
            ends_at = starts_at + timedelta(days=days)
            subscription.starts_at = subscription.starts_at or now
            subscription.current_period_ends_at = ends_at
            if subscription.status in {"pending", "grace_period"}:
                subscription.status = "active"
            subscription.version += 1
        period = SubscriptionPeriod(
            subscription_id=subscription.id,
            source_type="promo",
            source_id=redemption.id,
            starts_at=starts_at,
            ends_at=ends_at,
            plan_snapshot=self._plan_snapshot(plan),
            price_minor=None,
            currency=None,
        )
        self._session.add(period)
        await self._session.flush()
        return subscription, plan, period

    async def _enqueue_vpn_sync(
        self,
        *,
        redemption: PromoRedemption,
        subscription: Subscription,
        plan: PlanVersion,
        now: datetime,
    ) -> None:
        if subscription.current_period_ends_at is None:
            raise RuntimeError("promo subscription has no expiry")
        account = await self._repository.vpn_account_for_update(redemption.user_id)
        if account is None:
            account = VpnAccount(
                user_id=redemption.user_id,
                subscription_id=subscription.id,
                username=f"hz_{redemption.user_id.hex[:24]}",
                desired_status=DesiredVpnStatus.ACTIVE.value,
                desired_expires_at=subscription.current_period_ends_at,
            )
            self._session.add(account)
            await self._session.flush()
        else:
            account.subscription_id = subscription.id
            account.desired_expires_at = subscription.current_period_ends_at
            if subscription.status != "suspended":
                account.desired_status = DesiredVpnStatus.ACTIVE.value
        if subscription.status == "suspended":
            return
        command_key = f"vpn:promo:{account.id}:{redemption.id}"
        if await self._repository.vpn_command_by_key(command_key) is not None:
            return
        if account.remnawave_user_id is None:
            email, telegram_id = await self._repository.identity_contacts(redemption.user_id)
            command_type = CommandType.ENSURE_ACCOUNT.value
            payload: dict[str, Any] = {
                "username": account.username,
                "expire_at": subscription.current_period_ends_at.isoformat(),
                "traffic_limit_bytes": plan.traffic_limit_bytes or 0,
                "device_limit": plan.device_limit,
                "email": email,
                "telegram_id": telegram_id,
                "internal_squad_ids": self._squad_ids(plan.remnawave_policy),
            }
        else:
            command_type = CommandType.EXTEND.value
            payload = {"expires_at": subscription.current_period_ends_at.isoformat()}
        self._session.add(
            VpnSyncCommand(
                vpn_account_id=account.id,
                command_type=command_type,
                idempotency_key=command_key,
                payload=payload,
                status=CommandStatus.PENDING.value,
                attempt_count=0,
                next_attempt_at=now,
            )
        )

    async def _admin_response(
        self, promo: PromoCode, plan_ids: list[UUID]
    ) -> AdminPromoCodeResponse:
        return AdminPromoCodeResponse(
            id=promo.id,
            code=promo.code,
            promo_type=promo.promo_type,
            value=promo.value,
            currency=promo.currency,
            usage_limit=promo.usage_limit,
            per_user_limit=promo.per_user_limit,
            starts_at=promo.starts_at,
            expires_at=promo.expires_at,
            is_active=promo.is_active,
            plan_version_ids=plan_ids,
            usage_count=await self._repository.active_usage_count(promo.id, datetime.now(UTC)),
            created_by_user_id=promo.created_by_user_id,
            created_at=promo.created_at,
        )

    @staticmethod
    def _redemption_response(
        redemption: PromoRedemption,
        promo: PromoCode,
        *,
        subscription_ends_at: datetime | None,
    ) -> PromoRedemptionResponse:
        return PromoRedemptionResponse(
            id=redemption.id,
            code=promo.code,
            promo_type=promo.promo_type,
            value=promo.value,
            payment_id=redemption.payment_id,
            subscription_period_id=redemption.subscription_period_id,
            discount_amount_minor=redemption.discount_amount_minor,
            free_days=redemption.free_days,
            redeemed_at=redemption.redeemed_at,
            revoked_at=redemption.revoked_at,
            subscription_ends_at=subscription_ends_at,
        )

    @staticmethod
    def _discount_amount(amount_minor: int, percent: int) -> int:
        return amount_minor * percent // 100

    @staticmethod
    def _validate_currency(promo: PromoCode, currency: str) -> None:
        if promo.currency is not None and promo.currency != currency:
            raise ApplicationError(
                "promo_currency_not_eligible", "Promo code does not apply to this currency.", 409
            )

    @staticmethod
    def _plan_snapshot(plan: PlanVersion) -> dict[str, Any]:
        return {
            "plan_version_id": str(plan.id),
            "version": plan.version,
            "device_limit": plan.device_limit,
            "family_member_limit": plan.family_member_limit,
            "traffic_limit_bytes": plan.traffic_limit_bytes,
            "remnawave_policy": plan.remnawave_policy,
        }

    @staticmethod
    def _squad_ids(policy: dict[str, Any]) -> list[str]:
        values = policy.get("internal_squad_ids", [])
        if not isinstance(values, list):
            raise RuntimeError("invalid promo plan Remnawave policy")
        try:
            return [str(UUID(str(value))) for value in values]
        except ValueError as exc:
            raise RuntimeError("invalid promo plan Remnawave squad ID") from exc

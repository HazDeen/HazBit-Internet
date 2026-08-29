from __future__ import annotations

from fastapi import APIRouter

from app.core.config import Settings
from app.modules.admin.router import create_admin_router
from app.modules.auth.router import create_auth_router
from app.modules.billing.router import create_billing_router
from app.modules.bots.router import create_telegram_bots_router
from app.modules.families.router import create_family_router
from app.modules.payments.router import create_payment_router
from app.modules.portal.router import create_portal_router, create_public_catalog_router
from app.modules.promotions.router import create_promotion_router
from app.modules.referrals.router import create_referral_router
from app.modules.staff.router import create_staff_router
from app.modules.support.router import create_support_router
from app.modules.vpn.router import create_vpn_router


def create_api_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix=settings.api_v1_prefix)
    router.include_router(create_auth_router(settings))
    router.include_router(create_billing_router())
    router.include_router(create_telegram_bots_router(settings))
    router.include_router(create_family_router())
    router.include_router(create_vpn_router())
    router.include_router(create_payment_router())
    router.include_router(create_portal_router())
    router.include_router(create_public_catalog_router())
    router.include_router(create_referral_router())
    router.include_router(create_promotion_router())
    router.include_router(create_support_router())
    router.include_router(create_staff_router())
    router.include_router(create_admin_router())
    return router

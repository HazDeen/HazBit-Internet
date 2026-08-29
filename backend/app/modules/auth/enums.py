from __future__ import annotations

from enum import StrEnum


class UserStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    PENDING_DELETION = "pending_deletion"
    DELETED = "deleted"


class Role(StrEnum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    SUPPORT = "support"
    NETWORK = "network"
    FINANCE = "finance"
    CONTENT = "content"
    USER = "user"


class Permission(StrEnum):
    DASHBOARD_READ = "dashboard.read"
    USERS_READ = "users.read"
    USERS_MANAGE = "users.manage"
    SUBSCRIPTIONS_READ = "subscriptions.read"
    SUBSCRIPTIONS_MANAGE = "subscriptions.manage"
    PAYMENTS_READ = "payments.read"
    PAYMENTS_REVIEW = "payments.review"
    TICKETS_READ = "tickets.read"
    TICKETS_REPLY = "tickets.reply"
    TICKETS_MANAGE = "tickets.manage"
    PROMOTIONS_MANAGE = "promotions.manage"
    PLANS_MANAGE = "plans.manage"
    FAMILIES_MANAGE = "families.manage"
    VPN_READ = "vpn.read"
    VPN_NODES_MANAGE = "vpn.nodes.manage"
    SETTINGS_READ = "settings.read"
    STAFF_MANAGE = "staff.manage"


class OtpPurpose(StrEnum):
    REGISTER = "register"
    LOGIN = "login"
    LINK_EMAIL = "link_email"


class RiskDecision(StrEnum):
    ALLOW = "allow"
    REVIEW = "review"
    DENY = "deny"

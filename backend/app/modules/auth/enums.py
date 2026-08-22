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
    USER = "user"


class OtpPurpose(StrEnum):
    REGISTER = "register"
    LOGIN = "login"
    LINK_EMAIL = "link_email"


class RiskDecision(StrEnum):
    ALLOW = "allow"
    REVIEW = "review"
    DENY = "deny"

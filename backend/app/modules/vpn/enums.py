from __future__ import annotations

from enum import StrEnum


class DesiredVpnStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    DISABLED = "disabled"
    REVOKED = "revoked"


class ObservedVpnStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    LIMITED = "limited"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class DeviceStatus(StrEnum):
    RESERVED = "reserved"
    OBSERVED = "observed"
    REVOKED = "revoked"


class CommandType(StrEnum):
    ENSURE_ACCOUNT = "ensure_account"
    ENABLE = "enable"
    DISABLE = "disable"
    EXTEND = "extend"
    SYNC = "sync"
    CREATE_DEVICE = "create_device"
    REMOVE_DEVICE = "remove_device"
    REVOKE = "revoke"


class CommandStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    DEAD_LETTER = "dead_letter"

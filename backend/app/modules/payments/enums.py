from __future__ import annotations

from enum import StrEnum


class PaymentStatus(StrEnum):
    AWAITING_UPLOAD = "awaiting_upload"
    UPLOADED = "uploaded"
    ANALYZING = "analyzing"
    AUTO_APPROVED = "auto_approved"
    MANUAL_REVIEW = "manual_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVATION_PENDING = "activation_pending"
    ACTIVATED = "activated"
    CANCELLED = "cancelled"


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"

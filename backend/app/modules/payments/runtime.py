from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.modules.payments.gemini import GeminiReceiptExtractor, ReceiptExtractor
from app.modules.payments.storage import ObjectStorage, create_object_storage


@dataclass(frozen=True, slots=True)
class PaymentRuntime:
    storage: ObjectStorage
    extractor: ReceiptExtractor


def create_payment_runtime(settings: Settings) -> PaymentRuntime:
    return PaymentRuntime(
        storage=create_object_storage(settings.payments.storage),
        extractor=GeminiReceiptExtractor(settings.payments.gemini),
    )

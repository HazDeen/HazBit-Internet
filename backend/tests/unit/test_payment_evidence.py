from __future__ import annotations

import io

import pytest
from app.core.config import PaymentSettings
from app.core.errors import ApplicationError
from app.modules.payments.evidence import normalize_evidence
from fastapi import UploadFile
from PIL import Image


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", (40, 30), (255, 255, 255, 128)).save(output, "PNG")
    return output.getvalue()


async def test_upload_is_decoded_and_reencoded_as_canonical_jpeg() -> None:
    evidence = await normalize_evidence(
        UploadFile(file=io.BytesIO(_png()), filename="receipt.png"),
        PaymentSettings(),
    )

    assert evidence.content_type == "image/jpeg"
    assert evidence.data.startswith(b"\xff\xd8")
    assert len(evidence.sha256) == 32


async def test_non_image_upload_is_rejected() -> None:
    with pytest.raises(ApplicationError, match="valid JPEG") as exc_info:
        await normalize_evidence(
            UploadFile(file=io.BytesIO(b"<script>not an image</script>"), filename="receipt.jpg"),
            PaymentSettings(),
        )

    assert exc_info.value.code == "payment_evidence_invalid_image"

from __future__ import annotations

import hashlib
import io
import warnings
from dataclasses import dataclass

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import PaymentSettings
from app.core.errors import ApplicationError


@dataclass(frozen=True, slots=True)
class NormalizedEvidence:
    data: bytes
    content_type: str
    sha256: bytes


async def normalize_evidence(
    upload: UploadFile,
    settings: PaymentSettings,
) -> NormalizedEvidence:
    raw = bytearray()
    while chunk := await upload.read(64 * 1024):
        raw.extend(chunk)
        if len(raw) > settings.max_upload_bytes:
            raise ApplicationError(
                "payment_evidence_too_large",
                "Payment evidence exceeds the upload size limit.",
                413,
            )
    if not raw:
        raise ApplicationError("payment_evidence_empty", "Payment evidence is empty.", 422)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                width, height = source.size
                if width <= 0 or height <= 0 or width * height > settings.max_image_pixels:
                    raise ApplicationError(
                        "payment_evidence_dimensions_invalid",
                        "Payment evidence image dimensions are not allowed.",
                        422,
                    )
                source.load()
                image = ImageOps.exif_transpose(source)
                if image.mode in {"RGBA", "LA"}:
                    background = Image.new("RGB", image.size, "white")
                    alpha = image.getchannel("A")
                    background.paste(image.convert("RGB"), mask=alpha)
                    image = background
                else:
                    image = image.convert("RGB")
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=95, optimize=True)
    except ApplicationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
    ) as exc:
        raise ApplicationError(
            "payment_evidence_invalid_image",
            "Payment evidence must be a valid JPEG, PNG, or WebP image.",
            422,
        ) from exc

    data = output.getvalue()
    return NormalizedEvidence(
        data=data,
        content_type="image/jpeg",
        sha256=hashlib.sha256(data).digest(),
    )

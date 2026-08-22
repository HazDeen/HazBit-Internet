from __future__ import annotations

import asyncio
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]

from app.core.config import PaymentStorageSettings


class ObjectStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...

    async def close(self) -> None: ...


def _validate_key(key: str) -> PurePosixPath:
    path = PurePosixPath(key)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("invalid object storage key")
    return path


class LocalObjectStorage:
    def __init__(self, settings: PaymentStorageSettings) -> None:
        self._root = settings.local_directory.resolve()

    def _path(self, key: str) -> Path:
        return self._root.joinpath(*_validate_key(key).parts)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        del content_type
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            await asyncio.to_thread(path.unlink)

    async def close(self) -> None:
        return None


class S3ObjectStorage:
    def __init__(self, settings: PaymentStorageSettings) -> None:
        self._bucket = settings.bucket
        secret = (
            settings.secret_access_key.get_secret_value()
            if settings.secret_access_key is not None
            else None
        )
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=str(settings.endpoint_url) if settings.endpoint_url else None,
            region_name=settings.region,
            aws_access_key_id=settings.access_key_id,
            aws_secret_access_key=secret,
            config=Config(s3={"addressing_style": "path"}),
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        object_key = str(_validate_key(key))
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=object_key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )

    async def get(self, key: str) -> bytes:
        object_key = str(_validate_key(key))
        response = await asyncio.to_thread(
            self._client.get_object,
            Bucket=self._bucket,
            Key=object_key,
        )
        return await asyncio.to_thread(response["Body"].read)

    async def delete(self, key: str) -> None:
        object_key = str(_validate_key(key))
        await asyncio.to_thread(
            self._client.delete_object,
            Bucket=self._bucket,
            Key=object_key,
        )

    async def close(self) -> None:
        self._client.close()


def create_object_storage(settings: PaymentStorageSettings) -> ObjectStorage:
    if settings.backend == "s3":
        return S3ObjectStorage(settings)
    return LocalObjectStorage(settings)

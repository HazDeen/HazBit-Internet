from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from pydantic import TypeAdapter, ValidationError

from remnawave_adapter.config import Settings
from remnawave_adapter.schemas import DeviceList, DeviceState, ProvisionUserRequest, UserState


@dataclass(slots=True)
class RemnawaveClientError(Exception):
    code: str
    detail: str
    status_code: int
    retryable: bool = False


class RemnawaveClient:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=str(settings.panel_base_url).rstrip("/"),
            headers={
                "Authorization": f"Bearer {settings.panel_token.get_secret_value()}",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(
                settings.read_timeout_seconds,
                connect=settings.connect_timeout_seconds,
            ),
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> None:
        await self._request("GET", "/api/system/health")

    async def create_user(self, request: ProvisionUserRequest) -> UserState:
        payload: dict[str, Any] = {
            "username": request.username,
            "expireAt": _iso(request.expire_at),
            "trafficLimitBytes": request.traffic_limit_bytes,
            "trafficLimitStrategy": "NO_RESET",
            "hwidDeviceLimit": request.device_limit,
            "activeInternalSquads": [str(value) for value in request.internal_squad_ids],
        }
        if request.email is not None:
            payload["email"] = str(request.email)
        if request.telegram_id is not None:
            payload["telegramId"] = request.telegram_id
        data = await self._request("POST", "/api/users", json=payload)
        return _user_state(data)

    async def get_user(self, user_id: int) -> UserState:
        return _user_state(await self._request("GET", f"/api/users/{user_id}"))

    async def get_user_by_username(self, username: str) -> UserState:
        return _user_state(await self._request("GET", f"/api/users/by-username/{username}"))

    async def update_user(self, user_id: int, **changes: Any) -> UserState:
        payload = {"id": user_id, **changes}
        return _user_state(await self._request("PATCH", "/api/users", json=payload))

    async def disable_user(self, user_id: int) -> UserState:
        return _user_state(await self._request("POST", f"/api/users/{user_id}/actions/disable"))

    async def enable_user(self, user_id: int) -> UserState:
        return _user_state(await self._request("POST", f"/api/users/{user_id}/actions/enable"))

    async def extend_user(self, user_id: int, days: int) -> UserState:
        return _user_state(
            await self._request(
                "POST",
                f"/api/users/{user_id}/actions/extend",
                json={"days": days},
            )
        )

    async def create_device(
        self,
        user_id: int,
        *,
        hwid: str,
        platform: str | None,
        os_version: str | None,
        device_model: str | None,
        user_agent: str | None,
        request_ip: str | None,
    ) -> DeviceState:
        payload = _drop_none(
            {
                "userId": user_id,
                "hwid": hwid,
                "platform": platform,
                "osVersion": os_version,
                "deviceModel": device_model,
                "userAgent": user_agent,
                "requestIp": request_ip,
            }
        )
        devices = _device_list(await self._request("POST", "/api/hwid/devices", json=payload))
        for device in devices.devices:
            if device.hwid == hwid:
                return device
        raise RemnawaveClientError(
            "panel_contract_mismatch",
            "Remnawave did not return the created HWID device.",
            502,
        )

    async def list_devices(self, user_id: int) -> DeviceList:
        return _device_list(await self._request("GET", f"/api/hwid/devices/{user_id}"))

    async def remove_device(self, user_id: int, hwid: str) -> DeviceList:
        return _device_list(
            await self._request(
                "POST",
                "/api/hwid/devices/delete",
                json={"userId": user_id, "hwid": hwid},
            )
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        attempts = self._settings.max_get_attempts if method == "GET" else 1
        for attempt in range(1, attempts + 1):
            try:
                response = await self._client.request(method, path, **kwargs)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == attempts:
                    raise RemnawaveClientError(
                        "panel_unavailable",
                        "Remnawave Panel is unavailable.",
                        503,
                        retryable=True,
                    ) from exc
                await asyncio.sleep(0.05 * 2 ** (attempt - 1))
                continue
            if response.status_code in {429, 502, 503, 504} and attempt < attempts:
                await asyncio.sleep(0.05 * 2 ** (attempt - 1))
                continue
            if response.is_error:
                raise _http_error(response)
            if response.status_code == 204:
                return {}
            try:
                value = response.json()
            except ValueError as exc:
                raise RemnawaveClientError(
                    "panel_invalid_response",
                    "Remnawave Panel returned invalid JSON.",
                    502,
                    retryable=False,
                ) from exc
            if not isinstance(value, dict):
                raise RemnawaveClientError(
                    "panel_invalid_response",
                    "Remnawave Panel returned an unexpected response.",
                    502,
                )
            return value
        raise RuntimeError("unreachable retry state")


def _user_state(data: dict[str, Any]) -> UserState:
    try:
        body = data["response"]
        return UserState(
            id=int(body["id"]),
            username=body["username"],
            status=body["status"],
            expire_at=body["expireAt"],
            traffic_limit_bytes=int(body["trafficLimitBytes"]),
            device_limit=body.get("hwidDeviceLimit"),
            subscription_url=body.get("subscriptionUrl"),
        )
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise RemnawaveClientError(
            "panel_contract_mismatch",
            "Remnawave user response does not match API v3.3.2.",
            502,
        ) from exc


def _device_list(data: dict[str, Any]) -> DeviceList:
    try:
        body = data["response"]
        adapter = TypeAdapter(list[DeviceState])
        devices = adapter.validate_python(
            [
                {
                    "hwid": item["hwid"],
                    "user_id": item["userId"],
                    "platform": item.get("platform"),
                    "os_version": item.get("osVersion"),
                    "device_model": item.get("deviceModel"),
                    "created_at": item["createdAt"],
                    "updated_at": item["updatedAt"],
                }
                for item in body["devices"]
            ]
        )
        return DeviceList(total=int(body["total"]), devices=devices)
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise RemnawaveClientError(
            "panel_contract_mismatch",
            "Remnawave device response does not match API v3.3.2.",
            502,
        ) from exc


def _http_error(response: httpx.Response) -> RemnawaveClientError:
    vendor_code: str | None = None
    try:
        body = response.json()
        if isinstance(body, dict) and isinstance(body.get("errorCode"), str):
            vendor_code = body["errorCode"]
    except ValueError:
        pass
    if response.status_code in {401, 403}:
        code = "panel_unauthorized"
    elif response.status_code == 404:
        code = "panel_not_found"
    elif response.status_code == 429:
        code = "panel_rate_limited"
    elif response.status_code >= 500:
        code = "panel_server_error"
    else:
        code = "panel_rejected_request"
    if vendor_code:
        code = f"{code}_{vendor_code.lower()}"
    return RemnawaveClientError(
        code=code,
        detail="Remnawave Panel rejected the operation.",
        status_code=502 if response.status_code >= 500 else response.status_code,
        retryable=response.status_code in {429, 502, 503, 504},
    )


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _drop_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}

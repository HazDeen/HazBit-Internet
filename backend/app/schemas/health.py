from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ComponentHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["up", "down"]
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "not_ready"]
    service: str
    version: str
    environment: str
    checks: dict[str, ComponentHealth] | None = None

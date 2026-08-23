from __future__ import annotations

from functools import lru_cache
from typing import Literal, Self

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="REMNAWAVE_ADAPTER_",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    panel_base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:3000")
    panel_token: SecretStr = SecretStr("local-panel-token")
    internal_token: SecretStr = SecretStr("local-internal-token-change-me")
    connect_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    read_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    max_get_attempts: int = Field(default=3, ge=1, le=5)

    @model_validator(mode="after")
    def validate_production(self) -> Self:
        if self.environment == "production":
            for name, value in {
                "panel": self.panel_token.get_secret_value(),
                "internal": self.internal_token.get_secret_value(),
            }.items():
                if len(value) < 32 or value.startswith("local-"):
                    raise ValueError(f"{name} token must be replaced for production")
            if self.panel_base_url.scheme != "https":
                raise ValueError("Remnawave panel must use HTTPS in production")
            if "example.com" in str(self.panel_base_url).casefold():
                raise ValueError("Remnawave panel placeholder must be replaced for production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

from datetime import time
from decimal import Decimal
from functools import lru_cache
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings read from environment variables (see .env.example).

    Fields are added here as the phase that needs them is built.
    """

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    log_level: str = "info"

    # Auth
    secret_key: SecretStr
    frontend_url: str = "http://localhost:5173"
    session_ttl_hours: int = 168
    cookie_secure: bool = False
    trust_proxy_headers: bool = False
    invite_ttl_hours: int = 72
    reset_ttl_hours: int = 24

    # Google OAuth (Google login is disabled while the client ID is empty)
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    google_redirect_uri: str = "http://localhost:5173/api/auth/google/callback"

    # Dates ("today", overdue, dashboard weeks) are computed in this time zone.
    app_timezone: str = "UTC"

    # Hours in a working day (planned totals above it are shown as a warning).
    workday_hours: Decimal = Field(Decimal(8), gt=0, le=24)
    # Next week's plan is due at this time on Friday (APP_TIMEZONE).
    plan_deadline_time: time = time(18, 30)

    # AI. Empty LLM_PROVIDER = AI features disabled (they return 503). When it is set,
    # the app refuses to start without a matching adapter, a model and an API key.
    llm_provider: str = ""
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    # OpenAI-compatible endpoint (gateway, Ollama, vLLM...). Empty = the vendor default.
    llm_base_url: str = ""
    llm_timeout_seconds: float = Field(120.0, gt=0)
    ai_daily_limit_per_user: int = Field(50, ge=0)
    # Characters of log text (remarks) sent with an AI team summary prompt.
    ai_summary_char_budget: int = Field(20000, ge=500)

    @field_validator("llm_provider")
    @classmethod
    def _normalise_provider(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("app_timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown APP_TIMEZONE {value!r}") from exc
        return value

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)

    @field_validator("frontend_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("secret_key")
    @classmethod
    def _secret_not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("SECRET_KEY must not be empty")
        return value

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]

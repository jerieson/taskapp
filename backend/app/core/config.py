from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings read from environment variables (see .env.example).

    Fields are added here as the phase that needs them is built.
    """

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    log_level: str = "info"


@lru_cache
def get_settings() -> Settings:
    return Settings()

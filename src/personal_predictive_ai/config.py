from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PPA_", extra="ignore")

    data_dir: Path = Path("data")
    raw_ttl_seconds: int = Field(default=900, ge=1)
    structured_retention_days: int = Field(default=30, ge=1)
    offline_mode: bool = True


def load_settings() -> Settings:
    return Settings()

from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Order-to-Audit Management System"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = "postgresql+psycopg://ota_admin:ota_dev_password@localhost:5432/ota_dev"
    TEST_DATABASE_URL: str = (
        "postgresql+psycopg://ota_admin:ota_dev_password@localhost:5432/ota_test"
    )

    JWT_SECRET_KEY: str = "dev_only_secret_key_change_in_production_32chars"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480

    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    ENABLE_DEV_SEED: bool = True

    @field_validator("DATABASE_URL", "TEST_DATABASE_URL", mode="before")
    @classmethod
    def normalize_postgres_driver(cls, value: str) -> str:
        """Normalize cloud postgres:// or postgresql:// URLs to Psycopg 3 driver syntax."""
        if isinstance(value, str):
            if value.startswith("postgres://"):
                return "postgresql+psycopg://" + value[len("postgres://") :]
            if value.startswith("postgresql://"):
                return "postgresql+psycopg://" + value[len("postgresql://") :]
        return value

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                import json

                return list(json.loads(stripped))
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            if "dev_only" in self.JWT_SECRET_KEY or len(self.JWT_SECRET_KEY) < 32:
                raise ValueError("Production requires a strong JWT_SECRET_KEY (>= 32 chars).")
            if self.ENABLE_DEV_SEED:
                raise ValueError("ENABLE_DEV_SEED must be False in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

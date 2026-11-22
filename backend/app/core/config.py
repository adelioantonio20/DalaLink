from datetime import datetime
from zoneinfo import ZoneInfo
from pydantic_settings import BaseSettings, SettingsConfigDict


LUANDA_TZ = ZoneInfo("Africa/Luanda")


def now_luanda() -> datetime:
    """Return current timezone-aware datetime in Africa/Luanda (WAT, UTC+1)."""
    return datetime.now(LUANDA_TZ)


class Settings(BaseSettings):
    APP_NAME: str = "DalaLink — Plataforma de Mobilidade Urbana de Luanda"
    APP_VERSION: str = "1.0.0-mvp"
    ENVIRONMENT: str = "development"
    TIMEZONE: str = "Africa/Luanda"
    CURRENCY: str = "AOA"

    # Supports PostgreSQL+PostGIS in production (e.g. postgresql+psycopg2://...)
    # Defaults to local SQLite for zero-config MVP dev/test without external costs.
    DATABASE_URL: str = "sqlite:///./dalalink.db"

    SECRET_KEY: str = "dalalink-luanda-dev-secret-change-in-production-2026"
    QR_SIGNING_SECRET: str = "dalalink-qr-credential-hmac-secret-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Operational parameters
    MATCHING_OFFER_TIMEOUT_SECONDS: int = 45
    PLATFORM_COMMISSION_RATE: float = 0.15  # 15%
    CORS_ORIGINS: str = "*"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

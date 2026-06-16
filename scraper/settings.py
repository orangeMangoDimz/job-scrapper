"""Central, env-derived runtime settings (12-Factor III: config in the environment)."""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # os.environ only (NO env_file — a stray .env must not change behavior).
    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "job_scraper"
    MONGO_COLLECTION_NAME: str = "scrape_runs"
    MONGO_SERVER_SELECTION_TIMEOUT_MS: int = 3000

    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    LOG_FILE: str = ""
    LOG_FILE_MAX_BYTES: int = 5 * 1024 * 1024
    LOG_FILE_BACKUP_COUNT: int = 3

    STATUS_FILE: str = "logs/status.json"

    SENTRY_ENABLED: bool = False
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "production"
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0
    SENTRY_RELEASE: str = ""

    @field_validator("LOG_LEVEL")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("LOG_FORMAT")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()

    @field_validator("LOG_FILE")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("SENTRY_ENABLED", mode="before")
    @classmethod
    def _empty_is_false(cls, v: object) -> object:
        # `${SENTRY_ENABLED:-}` from compose injects ""; pydantic raises on "".
        if isinstance(v, str) and not v.strip():
            return False
        return v

    @field_validator("SENTRY_TRACES_SAMPLE_RATE", mode="before")
    @classmethod
    def _empty_is_zero(cls, v: object) -> object:
        # same "" edge as the bool above — float("") would raise ValidationError.
        if isinstance(v, str) and not v.strip():
            return 0.0
        return v


_settings = Settings()

# Re-export each field as a module global so `settings.X` resolves AND
# importlib.reload(scraper.settings) re-reads os.environ (fresh Settings()).
MONGO_URI: str = _settings.MONGO_URI
MONGO_DB_NAME: str = _settings.MONGO_DB_NAME
MONGO_COLLECTION_NAME: str = _settings.MONGO_COLLECTION_NAME
MONGO_SERVER_SELECTION_TIMEOUT_MS: int = _settings.MONGO_SERVER_SELECTION_TIMEOUT_MS
LOG_LEVEL: str = _settings.LOG_LEVEL
LOG_FORMAT: str = _settings.LOG_FORMAT
LOG_FILE: str = _settings.LOG_FILE
LOG_FILE_MAX_BYTES: int = _settings.LOG_FILE_MAX_BYTES
LOG_FILE_BACKUP_COUNT: int = _settings.LOG_FILE_BACKUP_COUNT
STATUS_FILE: str = _settings.STATUS_FILE
SENTRY_ENABLED: bool = _settings.SENTRY_ENABLED
SENTRY_DSN: str = _settings.SENTRY_DSN
SENTRY_ENVIRONMENT: str = _settings.SENTRY_ENVIRONMENT
SENTRY_TRACES_SAMPLE_RATE: float = _settings.SENTRY_TRACES_SAMPLE_RATE
SENTRY_RELEASE: str = _settings.SENTRY_RELEASE

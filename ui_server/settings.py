from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SESSION_SECRET_LENGTH = 32
MIN_DEV_LOGIN_KEY_LENGTH = 16
LOCAL_HOSTS = ("localhost", "127.0.0.1")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UI_", frozen=True)

    env: Literal["dev", "prod"]
    host: str = "127.0.0.1"
    port: int = 8090
    mcp_url: str = "http://scraper-mcp:8080/mcp"
    runs_dir: Path = Path("output/ui-runs")
    log_path: Path = Path("logs/scraper.log")
    static_dir: Path = Path("ui/dist")
    password_hash: str = ""
    dev_login_key: str = ""
    session_secret: str = ""
    domain: str = ""
    keep_runs: int = 50

    @model_validator(mode="after")
    def require_prod_secrets(self) -> Self:
        if self.env != "prod":
            if not self.dev_login_key:
                raise ValueError("UI_DEV_LOGIN_KEY is required in dev")
            if len(self.dev_login_key) < MIN_DEV_LOGIN_KEY_LENGTH:
                raise ValueError(
                    f"UI_DEV_LOGIN_KEY must have at least {MIN_DEV_LOGIN_KEY_LENGTH} characters"
                )
            return self
        if not self.password_hash:
            raise ValueError("UI_PASSWORD_HASH is required in prod")
        if len(self.session_secret) < MIN_SESSION_SECRET_LENGTH:
            raise ValueError(
                f"UI_SESSION_SECRET must have at least {MIN_SESSION_SECRET_LENGTH} characters"
            )
        if not self.domain:
            raise ValueError("UI_DOMAIN is required in prod")
        return self

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        return (*LOCAL_HOSTS, self.domain) if self.domain else LOCAL_HOSTS

    @property
    def cookie_secure(self) -> bool:
        return self.env == "prod"

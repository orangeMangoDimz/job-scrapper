from __future__ import annotations

import pytest
from pydantic import ValidationError

from ui_server.settings import Settings

STRONG_SECRET = "s" * 32
DOMAIN = "ui.example.com"
FAKE_HASH = "hash"  # pragma: allowlist secret
SHORT_SECRET = "short"  # pragma: allowlist secret
DEV_LOGIN_KEY = "dev-login-key-for-tests"


def test_env_is_required(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("UI_ENV", raising=False)

    with pytest.raises(ValidationError, match="env"):
        Settings()


def test_host_defaults_to_loopback():
    assert Settings(env="dev", dev_login_key=DEV_LOGIN_KEY).host == "127.0.0.1"


def test_dev_allows_only_local_hosts():
    assert Settings(env="dev", dev_login_key=DEV_LOGIN_KEY).allowed_hosts == (
        "localhost",
        "127.0.0.1",
    )


def test_prod_allows_its_domain():
    settings = Settings(
        env="prod", password_hash=FAKE_HASH, session_secret=STRONG_SECRET, domain=DOMAIN
    )

    assert settings.allowed_hosts == ("localhost", "127.0.0.1", DOMAIN)


def test_prod_refuses_to_start_without_domain():
    with pytest.raises(ValidationError, match="UI_DOMAIN"):
        Settings(env="prod", password_hash=FAKE_HASH, session_secret=STRONG_SECRET)


def test_dev_needs_only_the_dev_login_key():
    settings = Settings(env="dev", dev_login_key=DEV_LOGIN_KEY)

    assert settings.dev_login_key == DEV_LOGIN_KEY
    assert settings.cookie_secure is False


def test_dev_refuses_to_start_without_dev_login_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("UI_DEV_LOGIN_KEY", raising=False)

    with pytest.raises(ValidationError, match="UI_DEV_LOGIN_KEY"):
        Settings(env="dev")


def test_dev_refuses_a_short_dev_login_key():
    with pytest.raises(ValidationError, match="UI_DEV_LOGIN_KEY must have at least 16"):
        Settings(env="dev", dev_login_key="k" * 15)


def test_prod_needs_no_dev_login_key():
    settings = Settings(
        env="prod", password_hash=FAKE_HASH, session_secret=STRONG_SECRET, domain=DOMAIN
    )

    assert settings.dev_login_key == ""


def test_prod_refuses_to_start_without_password_hash():
    with pytest.raises(ValidationError, match="UI_PASSWORD_HASH"):
        Settings(env="prod", session_secret=STRONG_SECRET, domain=DOMAIN)


def test_prod_refuses_short_session_secret():
    with pytest.raises(ValidationError, match="UI_SESSION_SECRET"):
        Settings(env="prod", password_hash=FAKE_HASH, session_secret=SHORT_SECRET, domain=DOMAIN)


def test_prod_turns_on_login():
    settings = Settings(
        env="prod", password_hash=FAKE_HASH, session_secret=STRONG_SECRET, domain=DOMAIN
    )

    assert settings.cookie_secure is True

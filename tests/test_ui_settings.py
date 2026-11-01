from __future__ import annotations

import pytest
from pydantic import ValidationError

from ui_server.settings import Settings

STRONG_SECRET = "s" * 32


def test_dev_needs_no_secrets():
    settings = Settings(env="dev")

    assert settings.auth_enabled is False
    assert settings.config_read_only is False
    assert settings.cookie_secure is False


def test_prod_refuses_to_start_without_password_hash():
    with pytest.raises(ValidationError, match="UI_PASSWORD_HASH"):
        Settings(env="prod", session_secret=STRONG_SECRET)


def test_prod_refuses_short_session_secret():
    with pytest.raises(ValidationError, match="UI_SESSION_SECRET"):
        Settings(env="prod", password_hash="hash", session_secret="short")


def test_prod_turns_on_login_and_read_only_config():
    settings = Settings(env="prod", password_hash="hash", session_secret=STRONG_SECRET)

    assert settings.auth_enabled is True
    assert settings.config_read_only is True
    assert settings.cookie_secure is True

from __future__ import annotations

import pytest
from argon2 import PasswordHasher

from ui_server.errors import InvalidPasswordError, TooManyAttemptsError
from ui_server.services.auth_service import MAX_FAILED_ATTEMPTS, AuthService, LoginLimiter
from ui_server.settings import Settings

PASSWORD = "correct horse battery"  # pragma: allowlist secret


def _service() -> AuthService:
    settings = Settings(
        env="prod",
        password_hash=PasswordHasher().hash(PASSWORD),
        session_secret="s" * 32,
        domain="ui.example.com",
    )
    return AuthService(settings)


def test_right_password_gives_valid_session():
    service = _service()

    token = service.login(PASSWORD, "1.1.1.1")

    assert service.is_signed_in(token) is True


def test_wrong_password_is_rejected():
    with pytest.raises(InvalidPasswordError):
        _service().login("wrong", "1.1.1.1")


def test_tampered_token_is_rejected():
    service = _service()

    assert service.is_signed_in(service.login(PASSWORD, "1.1.1.1") + "x") is False


def test_missing_token_is_rejected():
    assert _service().is_signed_in(None) is False


def test_too_many_failures_block_client():
    service = _service()
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(InvalidPasswordError):
            service.login("wrong", "1.1.1.1")

    with pytest.raises(TooManyAttemptsError):
        service.login(PASSWORD, "1.1.1.1")


def test_block_applies_to_one_client_only():
    service = _service()
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(InvalidPasswordError):
            service.login("wrong", "1.1.1.1")

    assert service.is_signed_in(service.login(PASSWORD, "2.2.2.2")) is True


def test_limiter_forgets_old_failures():
    now = [0.0]
    limiter = LoginLimiter(clock=lambda: now[0])
    for _ in range(MAX_FAILED_ATTEMPTS):
        limiter.record_failure("1.1.1.1")

    now[0] = 10_000.0

    limiter.check("1.1.1.1")

from __future__ import annotations

import hmac
import secrets
import time
from collections.abc import Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from itsdangerous import BadSignature, TimestampSigner

from ui_server.errors import InvalidPasswordError, TooManyAttemptsError
from ui_server.settings import Settings

SESSION_COOKIE = "scraper_ui_session"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
SESSION_SUBJECT = "owner"
SESSION_SALT = "scraper-ui-session"
MAX_FAILED_ATTEMPTS = 5
SESSION_SECRET_BYTES = 32
FAILURE_WINDOW_SECONDS = 15 * 60.0


class LoginLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._failures: dict[str, tuple[float, ...]] = {}

    def check(self, client: str) -> None:
        if len(self._recent(client)) >= MAX_FAILED_ATTEMPTS:
            raise TooManyAttemptsError()

    def record_failure(self, client: str) -> None:
        self._failures = {**self._failures, client: (*self._recent(client), self._clock())}

    def clear(self, client: str) -> None:
        self._failures = {key: value for key, value in self._failures.items() if key != client}

    def _recent(self, client: str) -> tuple[float, ...]:
        cutoff = self._clock() - FAILURE_WINDOW_SECONDS
        return tuple(moment for moment in self._failures.get(client, ()) if moment > cutoff)


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self._is_dev = settings.env == "dev"
        self._password_hash = settings.password_hash
        self._dev_login_key = settings.dev_login_key
        self._signer = TimestampSigner(
            settings.session_secret or secrets.token_urlsafe(SESSION_SECRET_BYTES),
            salt=SESSION_SALT,
        )
        self._hasher = PasswordHasher()
        self._limiter = LoginLimiter()

    def login(self, password: str, client: str) -> str:
        self._limiter.check(client)
        if not self._is_right_password(password):
            self._limiter.record_failure(client)
            raise InvalidPasswordError()
        self._limiter.clear(client)
        return self._signer.sign(SESSION_SUBJECT).decode()

    def is_signed_in(self, token: str | None) -> bool:
        if token is None:
            return False
        try:
            self._signer.unsign(token, max_age=SESSION_MAX_AGE_SECONDS)
        except BadSignature:
            return False
        return True

    def _is_right_password(self, password: str) -> bool:
        if self._is_dev:
            return bool(self._dev_login_key) and hmac.compare_digest(
                password.encode(), self._dev_login_key.encode()
            )
        try:
            return self._hasher.verify(self._password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

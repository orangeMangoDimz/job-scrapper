from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response

from ui_server.dependencies import ServicesDep
from ui_server.schema.auth import LoginRequest
from ui_server.schema.response import ok
from ui_server.services.auth_service import SESSION_COOKIE, SESSION_MAX_AGE_SECONDS

UNKNOWN_CLIENT = "unknown"

router = APIRouter(prefix="/api/auth")


@router.get("/session")
def read_session(request: Request, services: ServicesDep) -> dict[str, Any]:
    required = services.settings.auth_enabled
    signed_in = not required or services.auth.is_signed_in(request.cookies.get(SESSION_COOKIE))
    return ok({"auth_required": required, "signed_in": signed_in})


@router.post("/login")
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    services: ServicesDep,
) -> dict[str, Any]:
    client = request.client.host if request.client else UNKNOWN_CLIENT
    token = services.auth.login(body.password, client)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=services.settings.cookie_secure,
        samesite="strict",
    )
    return ok(None)


@router.post("/logout")
def logout(response: Response, services: ServicesDep) -> dict[str, Any]:
    response.delete_cookie(
        SESSION_COOKIE,
        httponly=True,
        secure=services.settings.cookie_secure,
        samesite="strict",
    )
    return ok(None)

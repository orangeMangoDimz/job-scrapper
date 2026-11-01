from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ui_server.schema.response import failure

LOG = logging.getLogger("scraper-ui")
UNEXPECTED_MESSAGE = "Something went wrong. Try again."


class AppError(Exception):
    status_code = 400
    default_message = "The request could not be completed."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class NotSignedInError(AppError):
    status_code = 401
    default_message = "You are not signed in."


class InvalidPasswordError(AppError):
    status_code = 401
    default_message = "Wrong password."


class CrossSiteRequestError(AppError):
    status_code = 403
    default_message = "Cross-site requests are not allowed."


class ConfigReadOnlyError(AppError):
    status_code = 403
    default_message = "Config is read-only here. Change it through git and deploy."


class RunNotFoundError(AppError):
    status_code = 404
    default_message = "Run not found."


class RunInProgressError(AppError):
    status_code = 409
    default_message = "A scrape is already running."


class ConfigInvalidError(AppError):
    status_code = 422
    default_message = "That config is not valid."


class TooManyAttemptsError(AppError):
    status_code = 429
    default_message = "Too many tries. Try again in a few minutes."


class McpUnavailableError(AppError):
    status_code = 503
    default_message = "The scraper service could not be reached."


def _field_errors(exc: RequestValidationError) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for item in exc.errors():
        name = ".".join(str(part) for part in item["loc"][1:]) or "body"
        fields = {**fields, name: [*fields.get(name, []), item["msg"]]}
    return fields


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=failure(exc.message))

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content=failure(_field_errors(exc)))

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        LOG.error("unhandled error on %s", request.url.path, exc_info=exc)
        return JSONResponse(status_code=500, content=failure(UNEXPECTED_MESSAGE))

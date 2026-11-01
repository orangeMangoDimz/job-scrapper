from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from ui_server.errors import RunInProgressError, install_error_handlers
from ui_server.schema.response import ok


class Body(BaseModel):
    limit: int


def _client() -> TestClient:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/busy")
    def busy() -> None:
        raise RunInProgressError()

    @app.get("/crash")
    def crash() -> None:
        raise RuntimeError("secret detail")

    @app.post("/validate")
    def validate(body: Body) -> dict:
        return ok(body.limit)

    return TestClient(app, raise_server_exceptions=False)


def test_ok_wraps_data():
    assert ok({"a": 1}) == {"success": True, "data": {"a": 1}, "error": None}


def test_ok_adds_meta_when_given():
    assert ok([], meta={"total": 0})["meta"] == {"total": 0}


def test_app_error_uses_error_envelope():
    response = _client().get("/busy")

    assert response.status_code == 409
    assert response.json() == {
        "success": False,
        "data": None,
        "error": "A scrape is already running.",
    }


def test_validation_error_lists_fields():
    response = _client().post("/validate", json={"limit": "x"})

    assert response.status_code == 422
    assert list(response.json()["error"]) == ["limit"]


def test_unexpected_error_hides_detail():
    response = _client().get("/crash")

    assert response.status_code == 500
    assert "secret detail" not in response.text

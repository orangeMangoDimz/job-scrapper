from __future__ import annotations

from typing import Any


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"success": True, "data": data, "error": None}
    return body if meta is None else {**body, "meta": meta}


def failure(error: Any) -> dict[str, Any]:
    return {"success": False, "data": None, "error": error}

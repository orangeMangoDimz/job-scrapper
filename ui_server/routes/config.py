from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ui_server.dependencies import ServicesDep, require_session
from ui_server.schema.config import ConfigUpdateRequest
from ui_server.schema.response import ok
from ui_server.services.log_tail import redact

router = APIRouter(prefix="/api/config", dependencies=[Depends(require_session)])


def _to_values(config: dict[str, Any]) -> dict[str, Any]:
    proxy = config.get("proxy")
    return {
        "keywords": config.get("keywords", []),
        "limit": config.get("limit"),
        "max_age_hours": config.get("max_age_hours"),
        "proxy_url": redact(proxy) if proxy else None,
        "sites": [
            {"name": name, "enabled": site.get("enabled", True), "limit": site.get("limit")}
            for name, site in (config.get("sites") or {}).items()
        ],
    }


@router.get("")
async def read_config(services: ServicesDep) -> dict[str, Any]:
    read = await services.scraper.read_config()
    return ok(
        {
            "values": _to_values(read.value),
            "read_only": services.settings.config_read_only,
            "locked": list(services.config_store.locked_paths()),
            "is_stale": read.is_stale,
        }
    )


@router.put("")
def update_config(body: ConfigUpdateRequest, services: ServicesDep) -> dict[str, Any]:
    services.config_store.update(body)
    return ok(None)

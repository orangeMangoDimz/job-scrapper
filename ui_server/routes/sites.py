from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ui_server.dependencies import ServicesDep, require_session
from ui_server.schema.response import ok

router = APIRouter(prefix="/api/sites", dependencies=[Depends(require_session)])


@router.get("")
async def read_sites(services: ServicesDep) -> dict[str, Any]:
    read = await services.scraper.read_sites()
    return ok(
        {
            "keywords": read.value.get("keywords", []),
            "sites": [
                {"name": site["name"], "enabled": site["enabled"]}
                for site in read.value.get("sites", [])
            ],
            "is_stale": read.is_stale,
        }
    )

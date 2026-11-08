from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, status

from ui_server.dependencies import ServicesDep, require_session
from ui_server.errors import ConfigInvalidError
from ui_server.schema.response import ok
from ui_server.schema.runs import StartRunRequest
from ui_server.services.run_store import build_payloads, flatten_result

router = APIRouter(prefix="/api/runs", dependencies=[Depends(require_session)])


@router.get("")
def list_runs(services: ServicesDep) -> dict[str, Any]:
    return ok([asdict(record) for record in services.run_store.list_recent()])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def start_run(body: StartRunRequest, services: ServicesDep) -> dict[str, Any]:
    services.run_service.ensure_idle()
    read = await services.scraper.read_sites()
    known = {site["name"] for site in read.value.get("sites", [])}
    unknown = sorted(set(body.sites) - known)
    if unknown:
        raise ConfigInvalidError(f"Unknown site: {', '.join(unknown)}")
    record = services.run_service.start(tuple(body.keywords), tuple(body.sites))
    return ok(asdict(record))


@router.get("/{run_id}")
def read_run(run_id: str, services: ServicesDep) -> dict[str, Any]:
    record = services.run_store.get(run_id)
    result = services.run_store.read_result(run_id)
    jobs, failures = flatten_result(result)
    payloads = build_payloads(result, record.keywords, record.sites)
    return ok({"record": asdict(record), "jobs": jobs, "failures": failures, "payloads": payloads})

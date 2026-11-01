from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ui_server.dependencies import ServicesDep, require_session
from ui_server.services.log_tail import follow_lines, redact

HEARTBEAT_EVENT = ": ping\n\n"

router = APIRouter(prefix="/api/logs", dependencies=[Depends(require_session)])


@router.get("/stream")
async def stream_logs(request: Request, services: ServicesDep) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        async for line in follow_lines(services.settings.log_path, request.is_disconnected):
            yield HEARTBEAT_EVENT if line is None else f"data: {redact(line)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

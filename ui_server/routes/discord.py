from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ui_server.dependencies import Services, ServicesDep, require_session
from ui_server.errors import ConfigInvalidError
from ui_server.schema.discord import (
    DiscordMessageRequest,
    DiscordSendRequest,
    DiscordSettingsRequest,
)
from ui_server.schema.response import ok
from ui_server.services.run_store import flatten_result

router = APIRouter(prefix="/api/discord", dependencies=[Depends(require_session)])


def _pick_jobs(services: Services, body: DiscordMessageRequest) -> list[dict[str, Any]] | None:
    if body.run_id is None or body.job_indexes is None:
        return None
    services.run_store.get(body.run_id)
    jobs, _ = flatten_result(services.run_store.read_result(body.run_id))
    if any(index >= len(jobs) for index in body.job_indexes):
        raise ConfigInvalidError("One of the selected jobs is not in this run.")
    return [jobs[index] for index in body.job_indexes]


@router.get("/settings")
async def read_settings(services: ServicesDep) -> dict[str, Any]:
    return ok(await services.scraper.read_discord_settings())


@router.put("/settings")
async def update_settings(body: DiscordSettingsRequest, services: ServicesDep) -> dict[str, Any]:
    return ok(await services.scraper.save_discord_settings(body.to_patch()))


@router.post("/test")
async def test_connection(services: ServicesDep) -> dict[str, Any]:
    return ok(await services.scraper.test_discord_connection())


@router.get("/channels")
async def read_channels(services: ServicesDep) -> dict[str, Any]:
    return ok({"channels": await services.scraper.list_discord_channels()})


@router.post("/preview")
async def preview_message(body: DiscordMessageRequest, services: ServicesDep) -> dict[str, Any]:
    jobs = _pick_jobs(services, body)
    messages = await services.scraper.preview_discord_message(body.mention, body.text, jobs)
    return ok({"messages": messages})


@router.post("/send")
async def send_message(body: DiscordSendRequest, services: ServicesDep) -> dict[str, Any]:
    jobs = _pick_jobs(services, body)
    result = await services.scraper.send_discord_message(
        body.channel_id, body.mention, body.text, jobs
    )
    return ok(result)

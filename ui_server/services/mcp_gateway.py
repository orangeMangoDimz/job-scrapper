from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from ui_server.errors import McpUnavailableError

LOG = logging.getLogger("scraper-ui")
READ_TIMEOUT_SECONDS = 5.0
SCRAPE_TIMEOUT_SECONDS = 1800.0
CONNECT_TIMEOUT_SECONDS = 5.0


class McpGateway(Protocol):
    async def call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class CachedRead:
    value: dict[str, Any]
    is_stale: bool


def read_structured(tool: str, result: Any) -> dict[str, Any]:
    if result.isError or not isinstance(result.structuredContent, dict):
        LOG.warning("mcp tool %s returned no usable result", tool)
        raise McpUnavailableError()
    content = result.structuredContent
    if "error" in content:
        raise McpUnavailableError(str(content["error"]))
    return content


class HttpMcpGateway:
    def __init__(self, url: str) -> None:
        self._url = url

    async def call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        try:
            async with asyncio.timeout(timeout_seconds):
                result = await self._open_session_and_call(tool, arguments, timeout_seconds)
        except Exception as exc:
            LOG.warning("mcp tool %s failed: %s", tool, exc)
            raise McpUnavailableError() from exc
        return read_structured(tool, result)

    async def _open_session_and_call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> Any:
        timeout = httpx.Timeout(timeout_seconds, connect=CONNECT_TIMEOUT_SECONDS)
        async with (
            httpx.AsyncClient(timeout=timeout) as http_client,
            streamable_http_client(self._url, http_client=http_client) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            return await session.call_tool(
                tool, arguments, read_timeout_seconds=timedelta(seconds=timeout_seconds)
            )


class ScraperClient:
    def __init__(self, gateway: McpGateway) -> None:
        self._gateway = gateway
        self._cache: dict[str, dict[str, Any]] = {}

    async def scrape_jobs(
        self, sites: tuple[str, ...], keywords: tuple[str, ...]
    ) -> dict[str, Any]:
        arguments = {"sites": list(sites), "keywords": list(keywords)}
        return await self._gateway.call("scrape_jobs", arguments, SCRAPE_TIMEOUT_SECONDS)

    async def read_sites(self) -> CachedRead:
        return await self._read("list_sites")

    async def read_config(self) -> CachedRead:
        return await self._read("get_config")

    async def _read(self, tool: str) -> CachedRead:
        try:
            value = await self._gateway.call(tool, {}, READ_TIMEOUT_SECONDS)
        except McpUnavailableError:
            if tool not in self._cache:
                raise
            return CachedRead(self._cache[tool], True)
        self._cache = {**self._cache, tool: value}
        return CachedRead(value, False)

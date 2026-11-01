from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from ui_server.errors import McpUnavailableError
from ui_server.services.mcp_gateway import ScraperClient, read_structured


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responses: list[dict[str, Any] | Exception] = []

    async def call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        self.calls.append((tool, arguments))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_read_structured_returns_content():
    result = SimpleNamespace(isError=False, structuredContent={"ok": True})

    assert read_structured("list_sites", result) == {"ok": True}


def test_read_structured_rejects_tool_error():
    result = SimpleNamespace(isError=True, structuredContent=None)

    with pytest.raises(McpUnavailableError):
        read_structured("list_sites", result)


def test_read_structured_passes_tool_error_message():
    result = SimpleNamespace(isError=False, structuredContent={"error": "bad config"})

    with pytest.raises(McpUnavailableError, match="bad config"):
        read_structured("list_sites", result)


def test_read_returns_fresh_value():
    gateway = FakeGateway()
    gateway.responses = [{"sites": []}]

    read = asyncio.run(ScraperClient(gateway).read_sites())

    assert read.value == {"sites": []}
    assert read.is_stale is False


def test_read_falls_back_to_last_value_when_mcp_is_busy():
    gateway = FakeGateway()
    gateway.responses = [{"sites": ["a"]}, McpUnavailableError()]
    client = ScraperClient(gateway)

    async def read_twice():
        await client.read_sites()
        return await client.read_sites()

    read = asyncio.run(read_twice())

    assert read.value == {"sites": ["a"]}
    assert read.is_stale is True


def test_read_raises_when_nothing_is_cached():
    gateway = FakeGateway()
    gateway.responses = [McpUnavailableError()]

    with pytest.raises(McpUnavailableError):
        asyncio.run(ScraperClient(gateway).read_config())


def test_scrape_jobs_sends_sites_and_keywords():
    gateway = FakeGateway()
    gateway.responses = [{"ok": True}]

    asyncio.run(ScraperClient(gateway).scrape_jobs(("upwork",), ("django",)))

    assert gateway.calls == [("scrape_jobs", {"sites": ["upwork"], "keywords": ["django"]})]

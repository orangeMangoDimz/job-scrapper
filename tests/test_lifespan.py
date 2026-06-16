# tests/test_lifespan.py
from __future__ import annotations

from unittest.mock import patch

from starlette.testclient import TestClient

import mcp_server.server as server


def test_app_lifespan_closes_mongo_on_shutdown():
    # Drive the REAL composed ASGI lifespan (startup + shutdown) via TestClient.
    # This proves mongo.close() actually fires at process shutdown. The earlier
    # test only called a helper directly and never exercised the FastMCP wiring,
    # which (for the streamable-http transport) does NOT invoke FastMCP(lifespan=)
    # at the process level.
    app = server._build_app()
    with patch.object(server.mongo, "close") as mock_close:
        with TestClient(app):
            pass  # __enter__ runs lifespan startup, __exit__ runs shutdown
        mock_close.assert_called_once()

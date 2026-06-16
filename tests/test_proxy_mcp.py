# tests/test_proxy_mcp.py
from __future__ import annotations

from unittest.mock import MagicMock, patch

from mcp_server.server import test_proxy_connection as probe_proxy_connection
from scraper.config import redact_proxy_url


def test_redact_proxy_url_hides_password():
    u = "http://user:secret@proxy.example.com:8080/path"  # pragma: allowlist secret
    r = redact_proxy_url(u)
    assert "secret" not in r
    assert "user:***" in r
    assert "proxy.example.com" in r


def test_test_proxy_connection_rejects_non_http_scheme():
    out = probe_proxy_connection(
        proxy_url="http://127.0.0.1:8080",
        url="ftp://example.com/",
    )
    assert out["ok"] is False
    assert "http(s)" in out["error"]


@patch("mcp_server.server._load_config")
def test_test_proxy_connection_errors_when_no_proxy_configured(mock_load_config):
    cfg = MagicMock()
    cfg.proxy = None
    mock_load_config.return_value = cfg

    out = probe_proxy_connection()

    assert out["ok"] is False
    assert "no proxy" in out["error"].lower()


@patch("curl_cffi.requests.get")
def test_test_proxy_connection_ok_with_explicit_proxy(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"ip":"203.0.113.1"}'
    mock_resp.headers = {"content-type": "application/json"}
    mock_get.return_value = mock_resp

    out = probe_proxy_connection(proxy_url="socks5://127.0.0.1:1080")

    assert out["ok"] is True
    assert out["http_status"] == 200
    assert out["egress_ip"] == "203.0.113.1"
    assert "source" not in out
    mock_get.assert_called_once()
    call_kw = mock_get.call_args.kwargs
    assert call_kw["proxies"] == {
        "http": "socks5://127.0.0.1:1080",
        "https": "socks5://127.0.0.1:1080",
    }


@patch("mcp_server.server._load_config")
@patch("curl_cffi.requests.get")
def test_test_proxy_connection_uses_config_proxy(mock_get, mock_load_config):
    cfg = MagicMock()
    proxy = MagicMock()
    proxy.url = "http://127.0.0.1:8888"
    cfg.proxy = proxy
    mock_load_config.return_value = cfg

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"
    mock_resp.headers = {}
    mock_get.return_value = mock_resp

    out = probe_proxy_connection()

    assert out["ok"] is False
    assert out["http_status"] == 403
    assert out["source"] == "config"

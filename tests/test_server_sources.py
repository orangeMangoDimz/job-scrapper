from __future__ import annotations

from mcp_server.server import _build_per_site_sources


def test_builds_one_entry_per_site_and_keyword():
    filtered = [
        {
            "keyword": "devops",
            "site": "jobstreet",
            "payload": {"source": "api", "fallback_reason": None},
        },
        {
            "keyword": "devops",
            "site": "glints",
            "payload": {"source": "html", "fallback_reason": "http_403"},
        },
        {"keyword": "devops", "site": "indeed", "payload": {"count": 0}},
        {"keyword": "devops", "site": "broken", "payload": "not a dict"},
    ]
    assert _build_per_site_sources(filtered) == [
        {"site": "jobstreet", "keyword": "devops", "source": "api", "fallback_reason": None},
        {"site": "glints", "keyword": "devops", "source": "html", "fallback_reason": "http_403"},
        {"site": "indeed", "keyword": "devops", "source": "html", "fallback_reason": None},
    ]

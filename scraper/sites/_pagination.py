from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def with_query_param(url: str, key: str, value: str) -> str:
    """Return ``url`` with query parameter ``key`` set to ``value`` (replacing any
    existing occurrence). Used by scrapers to build deeper pagination URLs."""
    parts = urlsplit(url)
    params = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != key]
    params.append((key, value))
    query = urlencode(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))

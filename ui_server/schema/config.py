from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_LIMIT = 200
MAX_AGE_HOURS = 720

Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
SiteName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]+$", max_length=40)]
ProxyUrl = Annotated[str, StringConstraints(pattern=r"^(socks5h?|https?)://\S+$", max_length=300)]


class SiteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    limit: int | None = Field(default=None, ge=1, le=MAX_LIMIT)


class ConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: list[Keyword] | None = Field(default=None, min_length=1)
    limit: int | None = Field(default=None, ge=1, le=MAX_LIMIT)
    max_age_hours: int | None = Field(default=None, ge=1, le=MAX_AGE_HOURS)
    proxy_url: ProxyUrl | None = None
    sites: dict[SiteName, SiteUpdate] = Field(default_factory=dict)

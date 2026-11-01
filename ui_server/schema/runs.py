from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ui_server.schema.config import Keyword, SiteName

MAX_KEYWORDS = 20
MAX_SITES = 20


class StartRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: list[Keyword] = Field(min_length=1, max_length=MAX_KEYWORDS)
    sites: list[SiteName] = Field(min_length=1, max_length=MAX_SITES)

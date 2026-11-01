from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_LIMIT = 200
MAX_AGE_HOURS = 720
MAX_LIST_ITEMS = 100
MAX_DELAY_SECONDS = 60

Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
SiteName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]+$", max_length=40)]
FieldName = Annotated[str, StringConstraints(pattern=r"^[a-z_]+$", max_length=40)]
TextItem = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
TextList = Annotated[list[TextItem], Field(max_length=MAX_LIST_ITEMS)]
FieldList = Annotated[list[FieldName], Field(max_length=MAX_LIST_ITEMS)]
Delay = Annotated[float, Field(ge=0, le=MAX_DELAY_SECONDS)]


class FilterSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: TextList = Field(default_factory=list)
    employment_type: TextList = Field(default_factory=list)
    work_type: TextList = Field(default_factory=list)


class ApiSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    locations: TextList
    country_wide: bool
    delay_seconds: tuple[Delay, Delay] | None = None


class SiteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    limit: int | None = Field(default=None, ge=1, le=MAX_LIMIT)
    max_age_hours: int | None = Field(default=None, ge=1, le=MAX_AGE_HOURS)
    filter: FilterSettings | None = None
    fields: FieldList | None = None
    api: ApiSettings | None = None


class ConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    keywords: list[Keyword] | None = Field(default=None, min_length=1, max_length=MAX_LIST_ITEMS)
    limit: int | None = Field(default=None, ge=1, le=MAX_LIMIT)
    max_age_hours: int | None = Field(default=None, ge=1, le=MAX_AGE_HOURS)
    filter: FilterSettings | None = None
    default_fields: FieldList | None = None
    sites: dict[SiteName, SiteUpdate] = Field(default_factory=dict)

    def to_patch(self) -> dict[str, Any]:
        # exclude_unset keeps explicit nulls, which remove a key from the settings
        return self.model_dump(mode="json", exclude_unset=True, exclude={"version"})


class ConfigRestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    expected_version: int = Field(ge=1)

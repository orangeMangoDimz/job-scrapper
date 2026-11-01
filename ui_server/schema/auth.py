from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

MAX_PASSWORD_LENGTH = 200


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)

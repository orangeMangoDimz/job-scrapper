from __future__ import annotations

from collections.abc import Callable

from .client import ApiClient
from .glints import GlintsApi
from .jobstreet import JobstreetApi
from .linkedin import LinkedinApi
from .source import ApiSource

API_SOURCES: dict[str, Callable[[ApiClient], ApiSource]] = {
    "jobstreet": JobstreetApi,
    "glints": GlintsApi,
    "linkedin": LinkedinApi,
}

from __future__ import annotations

import math
from datetime import UTC, datetime

_HOURS_PER_DAY = 24
_SECONDS_PER_HOUR = 3600


def days_window(max_age_hours: int | None) -> int | None:
    if max_age_hours is None:
        return None
    return max(1, math.ceil(max_age_hours / _HOURS_PER_DAY))


def seconds_window(max_age_hours: int | None) -> int | None:
    if max_age_hours is None:
        return None
    return max_age_hours * _SECONDS_PER_HOUR


def to_utc_iso(raw: str | None) -> str | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()

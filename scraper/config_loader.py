from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, urlparse

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from .config import FetchTuning
from .log import get_logger
from .types import CANONICAL_FIELDS, MANDATORY_FIELDS

DEFAULT_FIELDS: tuple[str, ...] = ("title", "company", "location", "url")

FILTERABLE_FIELDS: frozenset[str] = frozenset({"location", "employment_type", "work_type"})

ALLOWED_URL_HOSTS: frozenset[str] = frozenset(
    {
        "id.jobstreet.com",
        "jobstreet.com",
        "glints.com",
        "id.glints.com",
        "www.linkedin.com",
        "linkedin.com",
        "id.linkedin.com",
        "id.indeed.com",
        "indeed.com",
        "www.indeed.com",
    }
)


class ConfigError(ValueError):
    pass


class ProxyConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    url: str


class SiteConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    enabled: bool
    url_template: str
    fields: tuple[str, ...] | None = None
    max_age_hours: int | None = None
    filter: dict[str, list[str]] | None = None
    limit: int | None = None

    @field_validator("url_template")
    @classmethod
    def _check_host(cls, v: str, info: ValidationInfo) -> str:
        _validate_url_host(info.data.get("name", "?"), v)
        return v

    def effective_fields(self, default: tuple[str, ...]) -> tuple[str, ...]:
        return self.fields if self.fields is not None else default

    def url_for(self, keyword: str) -> str:
        return _resolve_url(self.name, self.url_template, _build_template_vars(keyword))


class AppConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    keywords: tuple[str, ...]
    limit: int
    concurrency: int
    default_fields: tuple[str, ...]
    max_age_hours: int | None
    filter: dict[str, list[str]]
    sites: tuple[SiteConfig, ...]
    proxy: ProxyConfig | None = None
    timeouts: FetchTuning = Field(default_factory=FetchTuning)

    @model_validator(mode="before")
    @classmethod
    def _from_raw(cls, raw: object) -> dict:
        if not isinstance(raw, dict):
            raise ConfigError(f"config root must be a mapping, got {type(raw).__name__}")
        keywords = _resolve_keywords(raw)
        sites_raw = raw.get("sites")
        if not isinstance(sites_raw, dict) or not sites_raw:
            raise ConfigError("config must define a non-empty 'sites' mapping")
        if "default_fields" in raw:
            default_fields = (
                _validate_fields(raw["default_fields"], "default_fields") or DEFAULT_FIELDS
            )
        else:
            default_fields = DEFAULT_FIELDS
        sites: list[dict] = []
        for name, cfg in sites_raw.items():
            if not isinstance(cfg, dict):
                raise ConfigError(f"site '{name}' must be a mapping")
            template = cfg.get("url_template")
            if not isinstance(template, str) or not template:
                raise ConfigError(f"site '{name}' must define non-empty 'url_template'")
            site_fields = (
                _validate_fields(cfg["fields"], f"sites.{name}.fields") if "fields" in cfg else None
            )
            site_max_age = _parse_max_age(cfg.get("max_age_hours"), f"sites.{name}.max_age_hours")
            site_filter = (
                _validate_filter(cfg["filter"], f"sites.{name}.filter") if "filter" in cfg else None
            )
            site_limit = None
            if "limit" in cfg and cfg["limit"] is not None:
                try:
                    site_limit = int(cfg["limit"])
                except (TypeError, ValueError) as exc:
                    raise ConfigError(
                        f"sites.{name}.limit must be an integer, got {cfg['limit']!r}"
                    ) from exc
                if site_limit < 1:
                    raise ConfigError(f"sites.{name}.limit must be >= 1, got {site_limit}")
            sites.append(
                {
                    "name": name,
                    "enabled": bool(cfg.get("enabled", True)),
                    "url_template": template,
                    "fields": site_fields,
                    "max_age_hours": site_max_age,
                    "filter": site_filter,
                    "limit": site_limit,
                }
            )
        try:
            limit = int(raw.get("limit", 2))
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"'limit' must be an integer, got {raw.get('limit')!r}") from exc
        if limit < 1:
            raise ConfigError(f"'limit' must be >= 1, got {limit}")
        try:
            concurrency = int(raw.get("concurrency", 2))
        except (TypeError, ValueError) as exc:
            raise ConfigError(
                f"'concurrency' must be an integer, got {raw.get('concurrency')!r}"
            ) from exc
        if concurrency < 1:
            raise ConfigError(f"'concurrency' must be >= 1, got {concurrency}")
        proxy_url = raw.get("proxy")
        proxy = (
            {"url": proxy_url.strip()} if isinstance(proxy_url, str) and proxy_url.strip() else None
        )
        return {
            "keywords": keywords,
            "limit": limit,
            "concurrency": concurrency,
            "default_fields": default_fields,
            "max_age_hours": _parse_max_age(raw.get("max_age_hours"), "max_age_hours"),
            "filter": _validate_filter(raw.get("filter"), "filter"),
            "sites": sites,
            "proxy": proxy,
            "timeouts": _parse_timeouts(raw.get("timeouts")),
        }

    @model_validator(mode="after")
    def _check_urls(self) -> AppConfig:
        if self.keywords:
            sample_vars = _build_template_vars(self.keywords[0])
            for site in self.sites:
                _resolve_url(site.name, site.url_template, sample_vars)
        return self

    @property
    def keyword(self) -> str:
        return self.keywords[0] if self.keywords else ""

    def site(self, name: str) -> SiteConfig | None:
        for site in self.sites:
            if site.name == name:
                return site
        return None

    def enabled_site_names(self) -> tuple[str, ...]:
        return tuple(site.name for site in self.sites if site.enabled)

    def fields_for(self, site_name: str) -> frozenset[str]:
        cfg = self.site(site_name)
        configured = (
            cfg.effective_fields(self.default_fields) if cfg is not None else self.default_fields
        )
        return MANDATORY_FIELDS | frozenset(configured)

    def max_age_for(self, site_name: str) -> int | None:
        cfg = self.site(site_name)
        if cfg is not None and cfg.max_age_hours is not None:
            return cfg.max_age_hours
        return self.max_age_hours

    def filter_for(self, site_name: str) -> dict[str, list[str]]:
        cfg = self.site(site_name)
        if cfg is not None and cfg.filter is not None:
            return cfg.filter
        return self.filter

    def limit_for(self, site_name: str) -> int:
        cfg = self.site(site_name)
        if cfg is not None and cfg.limit is not None:
            return cfg.limit
        return self.limit


def _slugify(keyword: str) -> str:
    safe = keyword.strip().replace("/", "-").replace("\\", "-")
    while ".." in safe:
        safe = safe.replace("..", ".")
    return safe.lower().replace(" ", "-")


def _validate_url_host(site_name: str, template: str) -> None:
    parsed = urlparse(template)
    if parsed.scheme not in ("http", "https"):
        raise ConfigError(
            f"site '{site_name}' url_template scheme must be http or https, got '{parsed.scheme}'"
        )
    host = (parsed.hostname or "").lower()
    if "{" in host or "}" in host:
        raise ConfigError(
            f"site '{site_name}' url_template hostname must be a fixed domain, not a placeholder"
        )
    if host not in ALLOWED_URL_HOSTS:
        raise ConfigError(
            f"site '{site_name}' url_template has disallowed host '{host}'; "
            f"allowed: {sorted(ALLOWED_URL_HOSTS)}"
        )


def _build_template_vars(keyword: str) -> dict[str, str]:
    stripped = keyword.strip()
    return {
        "keyword": quote(stripped),
        "keyword_slug": _slugify(stripped),
        "keyword_plus": stripped.replace(" ", "+"),
    }


def _resolve_url(site_name: str, template: str, vars_: dict[str, str]) -> str:
    try:
        return template.format(**vars_)
    except KeyError as exc:
        raise ConfigError(
            f"site '{site_name}' url_template uses unknown placeholder {exc}; "
            f"allowed: {sorted(vars_)}"
        ) from exc


def _parse_max_age(raw: object, source: str) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int | float | str):
        raise ConfigError(f"{source} must be a positive integer or null, got {raw!r}")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{source} must be a positive integer or null, got {raw!r}") from exc
    if value < 1:
        raise ConfigError(f"{source} must be >= 1, got {value}")
    return value


def _validate_fields(raw: object, source: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ConfigError(f"{source} must be a list of field names, got {type(raw).__name__}")

    cleaned: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            raise ConfigError(f"{source} entries must be strings, got {entry!r}")
        if entry not in CANONICAL_FIELDS:
            get_logger().warning(
                "[config] {} contains unknown field '{}'; ignored. allowed: {}",
                source,
                entry,
                sorted(CANONICAL_FIELDS),
            )
            continue
        cleaned.append(entry)
    return tuple(cleaned)


def _normalize_filter_value(raw: object, source: str) -> list[str]:
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        return [normalized] if normalized else []
    if isinstance(raw, list):
        cleaned: list[str] = []
        for entry in raw:
            if not isinstance(entry, str):
                raise ConfigError(f"{source} entries must be strings, got {entry!r}")
            normalized = entry.strip().lower()
            if normalized:
                cleaned.append(normalized)
        return cleaned
    raise ConfigError(f"{source} must be a string or list of strings, got {type(raw).__name__}")


def _validate_filter(raw: object, source: str) -> dict[str, list[str]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{source} must be a mapping, got {type(raw).__name__}")
    cleaned: dict[str, list[str]] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise ConfigError(f"{source} keys must be strings, got {key!r}")
        if key not in FILTERABLE_FIELDS:
            get_logger().warning(
                "[config] {} contains unknown filter field '{}'; ignored. allowed: {}",
                source,
                key,
                sorted(FILTERABLE_FIELDS),
            )
            continue
        if value is None or value == "":
            continue
        items = _normalize_filter_value(value, f"{source}.{key}")
        if items:
            cleaned[key] = items
    return cleaned


def _resolve_keywords(raw: dict) -> tuple[str, ...]:
    if "keywords" in raw:
        value = raw["keywords"]
        if not isinstance(value, list) or not value:
            raise ConfigError("'keywords' must be a non-empty list of strings")
        cleaned: list[str] = []
        seen: set[str] = set()
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                raise ConfigError(f"'keywords' entries must be non-empty strings, got {entry!r}")
            normalized = entry.strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
        return tuple(cleaned)

    keyword = raw.get("keyword")
    if isinstance(keyword, str) and keyword.strip():
        return (keyword.strip(),)

    raise ConfigError("config must define non-empty 'keywords' (list) or 'keyword' (string)")


_TIMEOUT_FIELDS: frozenset[str] = frozenset(
    {
        "http_seconds",
        "playwright_goto_ms",
        "playwright_networkidle_ms",
        "playwright_settle_seconds",
        "indeed_api_seconds",
    }
)


def _parse_timeouts(raw: object) -> FetchTuning:
    if raw is None:
        return FetchTuning()
    if not isinstance(raw, dict):
        raise ConfigError(f"'timeouts' must be a mapping, got {type(raw).__name__}")
    overrides: dict[str, int] = {}
    for key, value in raw.items():
        if key not in _TIMEOUT_FIELDS:
            get_logger().warning(
                "[config] timeouts.{} unknown; ignored. allowed: {}",
                key,
                sorted(_TIMEOUT_FIELDS),
            )
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ConfigError(f"timeouts.{key} must be a positive integer, got {value!r}")
        overrides[key] = value
    return FetchTuning(**overrides)


def _format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        original = err.get("ctx", {}).get("error")
        if isinstance(original, ConfigError):
            parts.append(str(original))  # exact original message (verified present in ctx.error)
        else:
            loc = ".".join(str(p) for p in err["loc"])
            parts.append(f"{loc}: {err['msg']}" if loc else err["msg"])
    return "; ".join(parts) or "invalid config"


def load(path: Path) -> AppConfig:
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"config root must be a mapping, got {type(raw).__name__}")
    try:
        return AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc)) from exc


def keyword_slug(keyword: str) -> str:
    return _slugify(keyword)

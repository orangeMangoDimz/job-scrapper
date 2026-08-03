from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse

import yaml

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


@dataclass(frozen=True)
class ProxyConfig:
    url: str


@dataclass(frozen=True)
class SiteConfig:
    name: str
    enabled: bool
    url_template: str
    fields: tuple[str, ...] | None = None
    max_age_hours: int | None = None
    filter: dict[str, list[str]] | None = None
    limit: int | None = None
    max_pages: int | None = None

    def effective_fields(self, default: tuple[str, ...]) -> tuple[str, ...]:
        return self.fields if self.fields is not None else default

    def url_for(self, keyword: str) -> str:
        return _resolve_url(self.name, self.url_template, _build_template_vars(keyword))


@dataclass(frozen=True)
class AppConfig:
    keywords: tuple[str, ...]
    limit: int
    concurrency: int
    output_dir: Path
    default_fields: tuple[str, ...]
    max_age_hours: int | None
    filter: dict[str, list[str]]
    sites: tuple[SiteConfig, ...]
    max_pages: int = 1
    api_max_pages: int = 1
    page_delay_sec: float = 0.0
    requirements_max_chars: int | None = None
    proxy: ProxyConfig | None = None

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

    def max_pages_for(self, site_name: str, api_backed: bool = False) -> int:
        """Page budget for a site. An explicit per-site ``max_pages`` always wins;
        otherwise API-backed sites (one cheap pooled request) use ``api_max_pages``
        while HTML sites (one rate-limited fetch per page) use ``max_pages``."""
        cfg = self.site(site_name)
        if cfg is not None and cfg.max_pages is not None:
            return cfg.max_pages
        return self.api_max_pages if api_backed else self.max_pages


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
            from .log import get_logger as _get_logger

            _get_logger().warning(
                "[config] %s contains unknown field '%s'; ignored. allowed: %s",
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
            from .log import get_logger as _get_logger

            _get_logger().warning(
                "[config] %s contains unknown filter field '%s'; ignored. allowed: %s",
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


def load(path: Path) -> AppConfig:
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")

    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"config root must be a mapping, got {type(raw).__name__}")

    keywords = _resolve_keywords(raw)

    sites_raw = raw.get("sites")
    if not isinstance(sites_raw, dict) or not sites_raw:
        raise ConfigError("config must define a non-empty 'sites' mapping")

    if "default_fields" in raw:
        default_fields = _validate_fields(raw["default_fields"], "default_fields")
        if not default_fields:
            default_fields = DEFAULT_FIELDS
    else:
        default_fields = DEFAULT_FIELDS

    sites: list[SiteConfig] = []
    sample_vars = _build_template_vars(keywords[0])
    for name, cfg in sites_raw.items():
        if not isinstance(cfg, dict):
            raise ConfigError(f"site '{name}' must be a mapping")
        template = cfg.get("url_template")
        if not isinstance(template, str) or not template:
            raise ConfigError(f"site '{name}' must define non-empty 'url_template'")
        _validate_url_host(name, template)
        _resolve_url(name, template, sample_vars)
        enabled = bool(cfg.get("enabled", True))

        site_fields: tuple[str, ...] | None = None
        if "fields" in cfg:
            site_fields = _validate_fields(cfg["fields"], f"sites.{name}.fields")

        site_max_age = _parse_max_age(cfg.get("max_age_hours"), f"sites.{name}.max_age_hours")

        site_filter: dict[str, list[str]] | None = None
        if "filter" in cfg:
            site_filter = _validate_filter(cfg["filter"], f"sites.{name}.filter")

        site_limit: int | None = None
        if "limit" in cfg and cfg["limit"] is not None:
            try:
                site_limit = int(cfg["limit"])
            except (TypeError, ValueError) as exc:
                raise ConfigError(
                    f"sites.{name}.limit must be an integer, got {cfg['limit']!r}"
                ) from exc
            if site_limit < 1:
                raise ConfigError(f"sites.{name}.limit must be >= 1, got {site_limit}")

        site_max_pages: int | None = None
        if "max_pages" in cfg and cfg["max_pages"] is not None:
            try:
                site_max_pages = int(cfg["max_pages"])
            except (TypeError, ValueError) as exc:
                raise ConfigError(
                    f"sites.{name}.max_pages must be an integer, got {cfg['max_pages']!r}"
                ) from exc
            if site_max_pages < 1:
                raise ConfigError(f"sites.{name}.max_pages must be >= 1, got {site_max_pages}")

        sites.append(
            SiteConfig(
                name=name,
                enabled=enabled,
                url_template=template,
                fields=site_fields,
                max_age_hours=site_max_age,
                filter=site_filter,
                limit=site_limit,
                max_pages=site_max_pages,
            )
        )

    limit_raw = raw.get("limit", 2)
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"'limit' must be an integer, got {limit_raw!r}") from exc
    if limit < 1:
        raise ConfigError(f"'limit' must be >= 1, got {limit}")

    concurrency_raw = raw.get("concurrency", 2)
    try:
        concurrency = int(concurrency_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"'concurrency' must be an integer, got {concurrency_raw!r}") from exc
    if concurrency < 1:
        raise ConfigError(f"'concurrency' must be >= 1, got {concurrency}")

    max_pages_raw = raw.get("max_pages", 1)
    try:
        max_pages = int(max_pages_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"'max_pages' must be an integer, got {max_pages_raw!r}") from exc
    if max_pages < 1:
        raise ConfigError(f"'max_pages' must be >= 1, got {max_pages}")

    # API-backed sites default to a deeper pool than HTML sites (see max_pages_for).
    api_max_pages_raw = raw.get("api_max_pages", max_pages)
    try:
        api_max_pages = int(api_max_pages_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"'api_max_pages' must be an integer, got {api_max_pages_raw!r}") from exc
    if api_max_pages < 1:
        raise ConfigError(f"'api_max_pages' must be >= 1, got {api_max_pages}")

    page_delay_raw = raw.get("page_delay_sec", 0.0)
    try:
        page_delay_sec = float(page_delay_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"'page_delay_sec' must be a number, got {page_delay_raw!r}"
        ) from exc
    if page_delay_sec < 0:
        raise ConfigError(f"'page_delay_sec' must be >= 0, got {page_delay_sec}")

    # Raw descriptions run to several thousand chars each and dominate the payload
    # handed to the bot, which only renders a few bullets from them. Cap server-side.
    requirements_max_chars: int | None = None
    req_max_raw = raw.get("requirements_max_chars")
    if req_max_raw is not None:
        try:
            requirements_max_chars = int(req_max_raw)
        except (TypeError, ValueError) as exc:
            raise ConfigError(
                f"'requirements_max_chars' must be a positive integer or null, got {req_max_raw!r}"
            ) from exc
        if requirements_max_chars < 1:
            raise ConfigError(
                f"'requirements_max_chars' must be >= 1, got {requirements_max_chars}"
            )

    output_dir = Path(str(raw.get("output_dir", "output")))

    max_age_hours = _parse_max_age(raw.get("max_age_hours"), "max_age_hours")

    global_filter = _validate_filter(raw.get("filter"), "filter")

    proxy: ProxyConfig | None = None
    proxy_url = raw.get("proxy")
    if isinstance(proxy_url, str) and proxy_url.strip():
        proxy = ProxyConfig(url=proxy_url.strip())

    return AppConfig(
        keywords=keywords,
        limit=limit,
        concurrency=concurrency,
        output_dir=output_dir,
        default_fields=default_fields,
        filter=global_filter,
        max_age_hours=max_age_hours,
        sites=tuple(sites),
        max_pages=max_pages,
        api_max_pages=api_max_pages,
        page_delay_sec=page_delay_sec,
        requirements_max_chars=requirements_max_chars,
        proxy=proxy,
    )


def keyword_slug(keyword: str) -> str:
    return _slugify(keyword)

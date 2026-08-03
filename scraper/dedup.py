from __future__ import annotations

import hashlib
from urllib.parse import urlsplit, urlunsplit

from .types import Job


def _normalize_url(url: str) -> str:
    """Canonicalize a URL for identity comparison: lowercase scheme+host, drop
    query/fragment, strip a trailing slash. Path case is preserved (some job
    slugs are case-sensitive). Falls back to the stripped input on parse error."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def dedup_key(job: Job) -> str:
    """Stable cross-run identifier for a scraped job.

    Preference order, matching what each site reliably exposes:
      1. ``{site}:{job_id}``  — LinkedIn/Indeed always; JobStreet/Glints on the
         __NEXT_DATA__ path.
      2. ``url:{normalized_url}`` — covers the JobStreet/Glints HTML-fallback
         path where job_id is absent but a listing URL is present.
      3. ``hash:{sha1(site|title|company|location)}`` — last resort when neither
         an id nor a URL could be extracted.
    """
    site = (job.get("site") or "").strip().lower()
    job_id = job.get("job_id")
    if job_id:
        return f"{site}:{job_id}"
    url = job.get("url")
    if url:
        return f"url:{_normalize_url(url)}"
    raw = "|".join(
        (
            site,
            (job.get("title") or "").strip().lower(),
            (job.get("company") or "").strip().lower(),
            (job.get("location") or "").strip().lower(),
        )
    )
    return "hash:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()

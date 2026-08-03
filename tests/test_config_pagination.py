from __future__ import annotations

from pathlib import Path

from scraper.config_loader import load

_CONFIG = """
keywords: [software engineer]
max_pages: 3
api_max_pages: 10
sites:
  linkedin:
    url_template: "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keyword}&start=0"
  jobstreet:
    url_template: "https://id.jobstreet.com/id/{keyword_slug}-jobs"
  glints:
    url_template: "https://glints.com/id/opportunities/jobs/explore?keyword={keyword}"
    max_pages: 2
"""


def _load(tmp_path: Path):
    p = tmp_path / "config.yaml"
    p.write_text(_CONFIG)
    return load(p)


def test_html_sites_use_max_pages(tmp_path: Path):
    cfg = _load(tmp_path)
    assert cfg.max_pages_for("linkedin", api_backed=False) == 3


def test_api_sites_use_api_max_pages(tmp_path: Path):
    cfg = _load(tmp_path)
    assert cfg.max_pages_for("jobstreet", api_backed=True) == 10


def test_per_site_override_beats_type_default(tmp_path: Path):
    cfg = _load(tmp_path)
    # glints has an explicit max_pages: 2 — wins over the api_max_pages default
    assert cfg.max_pages_for("glints", api_backed=True) == 2


def test_api_max_pages_defaults_to_max_pages_when_absent(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text(
        "keywords: [x]\nmax_pages: 4\n"
        'sites:\n  linkedin:\n    url_template: "https://www.linkedin.com/jobs?keywords={keyword}"\n'
    )
    cfg = load(p)
    assert cfg.max_pages == 4
    assert cfg.api_max_pages == 4  # falls back to max_pages when not specified

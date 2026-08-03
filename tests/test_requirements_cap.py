from __future__ import annotations

from pathlib import Path

from scraper.config_loader import load
from scraper.runner import _truncate_requirements

_CONFIG = """
keywords: [software engineer]
requirements_max_chars: 40
sites:
  glints:
    url_template: "https://glints.com/id/opportunities/jobs/explore?keyword={keyword}"
"""


def _load(tmp_path: Path, body: str = _CONFIG):
    p = tmp_path / "config.yaml"
    p.write_text(body)
    return load(p)


def test_cap_is_parsed(tmp_path: Path):
    assert _load(tmp_path).requirements_max_chars == 40


def test_cap_defaults_to_none(tmp_path: Path):
    body = _CONFIG.replace("requirements_max_chars: 40\n", "")
    assert _load(tmp_path, body).requirements_max_chars is None


def test_short_text_is_untouched():
    assert _truncate_requirements("short", 40) == "short"


def test_long_text_is_truncated_with_ellipsis():
    out = _truncate_requirements("x" * 100, 40)
    assert out is not None
    assert out.endswith("…")
    assert len(out) == 41  # 40 chars + the ellipsis


def test_window_anchors_on_qualification_heading():
    # boilerplate long enough that a head-only cut would lose the heading entirely
    text = "About ACME. " * 40 + "Requirements: Python, 3 years experience." + " tail" * 50
    out = _truncate_requirements(text, 60)
    assert out is not None
    assert out.startswith("…Requirements:")
    assert "Python" in out


def test_window_falls_back_to_head_when_no_heading():
    text = "About ACME. " * 40
    out = _truncate_requirements(text, 60)
    assert out is not None
    assert not out.startswith("…")
    assert out.startswith("About ACME.")


def test_indonesian_heading_is_recognized():
    text = "Tentang perusahaan. " * 30 + "Kualifikasi: S1 Teknik Informatika." + " x" * 60
    out = _truncate_requirements(text, 60)
    assert out is not None
    assert out.startswith("…Kualifikasi:")


def test_no_cap_means_no_truncation():
    assert _truncate_requirements("x" * 5000, None) == "x" * 5000


def test_non_string_becomes_none():
    assert _truncate_requirements(None, 40) is None
    assert _truncate_requirements(123, 40) is None

from __future__ import annotations

from scraper.api.window import days_window, seconds_window, to_utc_iso


def test_days_window_rounds_up_and_floors_at_one():
    assert days_window(72) == 3
    assert days_window(73) == 4
    assert days_window(1) == 1


def test_windows_are_none_without_max_age():
    assert days_window(None) is None
    assert seconds_window(None) is None


def test_seconds_window():
    assert seconds_window(72) == 259200


def test_to_utc_iso_normalizes_z_suffix():
    assert to_utc_iso("2026-10-26T07:34:52Z") == "2026-10-26T07:34:52+00:00"


def test_to_utc_iso_rejects_garbage():
    assert to_utc_iso("6h ago") is None
    assert to_utc_iso(None) is None

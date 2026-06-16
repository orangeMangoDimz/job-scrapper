# tests/test_fetch_tuning.py
from __future__ import annotations

from scraper.config import FetchTuning
from scraper.fetchers import CloudscraperFetcher, CurlCffiFetcher, PlaywrightFetcher
from scraper.runner import default_fetch_chain


def test_fetchers_store_tuning():
    t = FetchTuning(http_seconds=7)
    assert CurlCffiFetcher(tuning=t)._tuning.http_seconds == 7
    assert CloudscraperFetcher(tuning=t)._tuning.http_seconds == 7
    assert PlaywrightFetcher(tuning=t)._tuning.http_seconds == 7


def test_fetchers_default_tuning_when_omitted():
    assert CurlCffiFetcher()._tuning == FetchTuning()


def test_default_fetch_chain_passes_tuning():
    t = FetchTuning(http_seconds=9)
    chain = default_fetch_chain(proxy=None, tuning=t)
    assert all(f._tuning.http_seconds == 9 for f in chain._fetchers)  # type: ignore[attr-defined]

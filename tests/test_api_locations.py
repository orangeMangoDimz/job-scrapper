from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scraper.api.locations import LOCATION_OPTIONS, location_options_payload

SEED_PATH = Path(__file__).resolve().parents[1] / "seeds" / "job_settings.yaml"
SITES_WITH_LIST = ("jobstreet", "glints", "linkedin")


def test_only_sites_with_a_city_list_are_present():
    assert set(LOCATION_OPTIONS) == set(SITES_WITH_LIST)


@pytest.mark.parametrize("site", SITES_WITH_LIST)
def test_site_list_is_not_empty(site: str):
    assert len(LOCATION_OPTIONS[site]) >= 5


@pytest.mark.parametrize("site", SITES_WITH_LIST)
def test_labels_and_values_are_unique_per_site(site: str):
    options = LOCATION_OPTIONS[site]

    assert len({option.label for option in options}) == len(options)
    assert len({option.value for option in options}) == len(options)


def test_every_label_exists_on_the_fullest_list_in_the_same_order():
    full = [option.label for option in LOCATION_OPTIONS["jobstreet"]]

    for site in SITES_WITH_LIST:
        labels = [option.label for option in LOCATION_OPTIONS[site]]
        assert labels == [label for label in full if label in labels]
        assert set(labels) <= set(full)


def test_jakarta_comes_first():
    assert all(LOCATION_OPTIONS[site][0].label == "Jakarta" for site in SITES_WITH_LIST)


def test_every_seed_location_is_in_the_list():
    seed = yaml.safe_load(SEED_PATH.read_text())

    for site in SITES_WITH_LIST:
        values = {option.value for option in LOCATION_OPTIONS[site]}
        assert set(seed["sites"][site]["api"]["locations"]) <= values


def test_payload_has_label_and_value_dicts_per_site():
    payload = location_options_payload()

    assert set(payload) == set(SITES_WITH_LIST)
    assert payload["jobstreet"][0] == {"label": "Jakarta", "value": "Jakarta Raya"}
    assert payload["linkedin"][0] == {"label": "Jakarta", "value": "Jakarta, Indonesia"}
    assert payload["glints"][0]["value"] == "78d63064-78a1-4577-8516-036a6c5e903e"


def test_options_are_immutable():
    assert isinstance(LOCATION_OPTIONS["jobstreet"], tuple)
    with pytest.raises(AttributeError):
        LOCATION_OPTIONS["jobstreet"][0].label = "x"  # type: ignore[misc]

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LocationOption:
    """One city in the Config page picker: `label` is shown, `value` is what the site accepts."""

    label: str
    value: str


def _options(*pairs: tuple[str, str]) -> tuple[LocationOption, ...]:
    return tuple(LocationOption(label, value) for label, value in pairs)


# Same label order on every site (a site may skip cities it cannot filter); Jakarta metro first.
# Upwork (remote, worldwide) and HTML-only sites like indeed have no list.
JOBSTREET = _options(
    ("Jakarta", "Jakarta Raya"),
    ("Bandung", "Bandung Jawa Barat"),
    ("Bekasi", "Bekasi Jawa Barat"),
    ("Tangerang", "Tangerang Banten"),
    ("Tangerang Selatan", "Tangerang Selatan Banten"),
    ("Depok", "Depok Jawa Barat"),
    ("Bogor", "Bogor Jawa Barat"),
    ("Surabaya", "Surabaya Jawa Timur"),
    ("Semarang", "Semarang Jawa Tengah"),
    ("Yogyakarta", "Yogyakarta DI Yogyakarta"),
    ("Medan", "Medan Sumatera Utara"),
    ("Bali", "Bali"),
    ("Makassar", "Makassar Sulawesi Selatan"),
    ("Batam", "Batam Kepulauan Riau"),
    ("Malang", "Malang Jawa Timur"),
    ("Palembang", "Palembang Sumatera Selatan"),
    ("Balikpapan", "Balikpapan Kalimantan Timur"),
    ("Solo", "Surakarta Jawa Tengah"),
    ("Pekanbaru", "Pekanbaru Riau"),
)

GLINTS = _options(
    ("Jakarta", "78d63064-78a1-4577-8516-036a6c5e903e"),
    ("Bandung", "86a3dc56-1bd7-4cd3-8225-d3e4b976e552"),
    ("Bekasi", "87c39cfb-0e3c-4edb-a7a0-754fb70cc587"),
    ("Tangerang", "ae3c458e-5947-4833-8f1b-e001ce2fad1d"),
    ("Tangerang Selatan", "337f8da8-70d8-4916-9733-1cee8e4902e9"),
    ("Depok", "f5817918-7ce1-436d-9478-c438b3466adb"),
    ("Bogor", "262b7d3c-2c51-4854-a7e8-6635e0657338"),
    ("Surabaya", "0822446a-8784-4af4-bc88-9f9294fca382"),
    ("Semarang", "a9ff8f92-f835-47a5-b74b-4425bda9e092"),
    ("Yogyakarta", "dadb256b-8716-4fae-b7bf-f85d922d0df3"),  # DI Yogyakarta province
    ("Medan", "a6f7a20f-7172-4436-a418-afc91020ba0f"),
    ("Bali", "c7aaf839-7091-4a64-95a9-a25642d02aba"),  # Bali province
    ("Makassar", "7677c41c-126d-44f6-b249-106f430c0fbc"),
    ("Batam", "654dbd43-0da6-44a1-8fa6-3f2879b8fbdf"),
    ("Malang", "6ec28332-761a-4ee9-b0d8-52171a170edf"),
    ("Palembang", "8ddc89b0-78c1-4be9-a9c0-07733d38c3ae"),
    ("Balikpapan", "513f150c-4fba-415a-9a68-75b755b4f506"),
    ("Solo", "17c26ccc-5329-494c-b6ad-4b37a0c12fde"),  # listed as Surakarta
    ("Pekanbaru", "79c660ef-ab9a-44e5-9f9d-623a766e5b72"),
)

# Only cities whose value was checked against the guest API (results came back for that city).
# Bekasi, Tangerang, Tangerang Selatan and Bogor resolve to the Jakarta metro area there, so
# Jakarta covers them. Depok resolves to the wrong region. Other cities were not verified
# (LinkedIn rate-limited the probe), so they are left out until checked.
LINKEDIN = _options(
    ("Jakarta", "Jakarta, Indonesia"),
    ("Bandung", "Bandung, Indonesia"),
    ("Surabaya", "Surabaya, Indonesia"),
    ("Semarang", "Semarang, Indonesia"),
    ("Yogyakarta", "Yogyakarta, Indonesia"),
    ("Medan", "Medan, Indonesia"),
)

LOCATION_OPTIONS: dict[str, tuple[LocationOption, ...]] = {
    "jobstreet": JOBSTREET,
    "glints": GLINTS,
    "linkedin": LINKEDIN,
}


def location_options_payload() -> dict[str, list[dict[str, str]]]:
    """JSON-ready shape served by get_config and GET /api/config."""
    return {
        site: [{"label": option.label, "value": option.value} for option in options]
        for site, options in LOCATION_OPTIONS.items()
    }

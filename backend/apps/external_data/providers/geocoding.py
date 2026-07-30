from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx


@dataclass(frozen=True)
class AdministrativeAddress:
    province: str
    city: str
    district: str
    country: str


class ReverseGeocodingProvider(Protocol):
    def reverse(
        self, *, latitude: float, longitude: float, language: str
    ) -> AdministrativeAddress: ...


class NominatimReverseGeocodingProvider:
    """Replaceable reverse-geocoding provider for explicitly authorized coordinates."""

    name = "nominatim"
    url = "https://nominatim.openstreetmap.org/reverse"

    def __init__(self, *, client: httpx.Client | None = None, timeout_seconds: float = 12) -> None:
        self._client = client
        self.timeout_seconds = timeout_seconds

    def reverse(self, *, latitude: float, longitude: float, language: str) -> AdministrativeAddress:
        params = {
            "format": "jsonv2",
            "lat": latitude,
            "lon": longitude,
            "zoom": 10,
            "addressdetails": 1,
            "accept-language": language,
        }
        if self._client is not None:
            response = self._client.get(self.url, params=params)
        else:
            with httpx.Client(
                timeout=self.timeout_seconds,
                headers={"User-Agent": "TimeAgent/0.1 reverse-geocoding"},
                follow_redirects=True,
            ) as client:
                response = client.get(self.url, params=params)
        response.raise_for_status()
        payload = response.json()
        address = payload.get("address", {}) if isinstance(payload, dict) else {}
        if not isinstance(address, dict):
            raise LookupError("Reverse geocoding returned no administrative address")

        province = _first(address, "state", "province", "region")
        city = _first(address, "city", "municipality", "prefecture", "state_district")
        district = _first(address, "city_district", "district", "county", "suburb")
        country = _first(address, "country")
        if not (province and city and district):
            raise LookupError("Reverse geocoding did not resolve province, city, and district")
        return AdministrativeAddress(
            province=province,
            city=city,
            district=district,
            country=country,
        )


def _first(address: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = address.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""

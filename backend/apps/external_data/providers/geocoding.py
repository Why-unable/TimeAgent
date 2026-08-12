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
    adcode: str = ""


class ReverseGeocodingProvider(Protocol):
    name: str

    def reverse(
        self, *, latitude: float, longitude: float, language: str
    ) -> AdministrativeAddress: ...


class AmapReverseGeocodingProvider:
    """AMap Web Service adapter for GPS coordinate conversion and reverse geocoding."""

    name = "amap"
    coordinate_conversion_url = "https://restapi.amap.com/v3/assistant/coordinate/convert"
    reverse_geocoding_url = "https://restapi.amap.com/v3/geocode/regeo"
    direct_municipalities = frozenset({"北京市", "上海市", "天津市", "重庆市"})

    def __init__(
        self,
        *,
        api_key: str,
        client: httpx.Client | None = None,
        timeout_seconds: float = 5,
    ) -> None:
        if not api_key.strip():
            raise ValueError("AMap Web Service key is required")
        self.api_key = api_key.strip()
        self._client = client
        self.timeout_seconds = timeout_seconds

    def reverse(self, *, latitude: float, longitude: float, language: str) -> AdministrativeAddress:
        del language
        if self._client is not None:
            return self._reverse_with_client(
                self._client,
                latitude=latitude,
                longitude=longitude,
            )
        with httpx.Client(
            timeout=self.timeout_seconds,
            headers={"User-Agent": "TimeAgent/0.1 reverse-geocoding"},
            follow_redirects=True,
        ) as client:
            return self._reverse_with_client(client, latitude=latitude, longitude=longitude)

    def _reverse_with_client(
        self,
        client: httpx.Client,
        *,
        latitude: float,
        longitude: float,
    ) -> AdministrativeAddress:
        coordinate_response = client.get(
            self.coordinate_conversion_url,
            params={
                "key": self.api_key,
                "locations": f"{longitude:.6f},{latitude:.6f}",
                "coordsys": "gps",
                "output": "JSON",
            },
        )
        coordinate_response.raise_for_status()
        coordinate_payload = _amap_payload(coordinate_response)
        converted_location = _text(coordinate_payload.get("locations")).split(";", 1)[0]
        if len(converted_location.split(",")) != 2:
            raise LookupError("AMap coordinate conversion returned no location")

        address_response = client.get(
            self.reverse_geocoding_url,
            params={
                "key": self.api_key,
                "location": converted_location,
                "extensions": "base",
                "output": "JSON",
            },
        )
        address_response.raise_for_status()
        address_payload = _amap_payload(address_response)
        regeocode = address_payload.get("regeocode")
        if not isinstance(regeocode, dict):
            raise LookupError("AMap reverse geocoding returned no address")
        component = regeocode.get("addressComponent")
        if not isinstance(component, dict):
            raise LookupError("AMap reverse geocoding returned no address component")

        province = _text(component.get("province"))
        city = _text(component.get("city"))
        district = _text(component.get("district"))
        country = _text(component.get("country")) or "中国"
        if not city and province in self.direct_municipalities:
            city = province
        if not (province and city and district):
            raise LookupError("AMap did not resolve province, city, and district")
        return AdministrativeAddress(
            province=province,
            city=city,
            district=district,
            country=country,
            adcode=_text(component.get("adcode")),
        )


class NominatimReverseGeocodingProvider:
    """Replaceable reverse-geocoding provider for explicitly authorized coordinates."""

    name = "nominatim"
    url = "https://nominatim.openstreetmap.org/reverse"

    def __init__(self, *, client: httpx.Client | None = None, timeout_seconds: float = 5) -> None:
        self._client = client
        self.timeout_seconds = timeout_seconds

    def reverse(self, *, latitude: float, longitude: float, language: str) -> AdministrativeAddress:
        params: dict[str, str | int | float] = {
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


def _amap_payload(response: httpx.Response) -> dict[str, Any]:
    payload = response.json()
    if not isinstance(payload, dict):
        raise LookupError("AMap returned an invalid response")
    if str(payload.get("status", "")) != "1":
        info = _text(payload.get("info")) or "unknown error"
        info_code = _text(payload.get("infocode"))
        suffix = f" ({info_code})" if info_code else ""
        raise LookupError(f"AMap request failed: {info}{suffix}")
    return payload


def _text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return next((item.strip() for item in value if isinstance(item, str) and item.strip()), "")
    return ""

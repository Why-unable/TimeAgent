from __future__ import annotations

from typing import Any, Literal, TypedDict, cast

from django.core.exceptions import ValidationError


class StoredWeatherCoordinates(TypedDict, total=False):
    provider: str
    provider_location_id: str
    coordinate_role: Literal["administrative_center", "device_gps"]
    latitude: float
    longitude: float
    label: str
    accuracy_meters: float


class StoredWeatherLocationData(TypedDict, total=False):
    schema_version: Literal[2]
    provider: str
    provider_location_id: str
    adcode: str
    name: str
    admin1: str
    country: str
    timezone: str
    label: str
    province: str
    city: str
    district: str
    administrative_coordinates: StoredWeatherCoordinates
    current_coordinates: StoredWeatherCoordinates


def validate_weather_location_data(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValidationError({"weather_location_data": "Must be an object"})
    if not value:
        return
    if value.get("schema_version") == 2:
        _validate_v2(value)
        return
    _validate_legacy(value)


def normalized_weather_location_data(value: Any) -> StoredWeatherLocationData:
    if not isinstance(value, dict) or not value:
        return {}
    if value.get("schema_version") == 2:
        return cast(StoredWeatherLocationData, value)

    provider = _text(value.get("provider"))
    latitude = value.get("latitude")
    longitude = value.get("longitude")
    if not _is_coordinate_pair(latitude, longitude):
        return {}
    coordinate_role: Literal["administrative_center", "device_gps"] = (
        "device_gps" if provider == "device_geolocation" else "administrative_center"
    )
    latitude_value = cast(int | float, latitude)
    longitude_value = cast(int | float, longitude)
    coordinates: StoredWeatherCoordinates = {
        "provider": provider or "open_meteo",
        "provider_location_id": _text(value.get("provider_location_id")),
        "coordinate_role": coordinate_role,
        "latitude": float(latitude_value),
        "longitude": float(longitude_value),
        "label": _text(value.get("label")),
    }
    normalized: StoredWeatherLocationData = {
        "schema_version": 2,
        "provider": provider,
        "provider_location_id": _text(value.get("provider_location_id")),
        "adcode": _adcode(value.get("adcode") or value.get("provider_location_id")),
        "name": _text(value.get("name")),
        "admin1": _text(value.get("admin1")),
        "country": _text(value.get("country")),
        "timezone": _text(value.get("timezone")),
        "label": _text(value.get("label")),
        "province": _text(value.get("province")),
        "city": _text(value.get("city")),
        "district": _text(value.get("district")),
    }
    normalized[
        "current_coordinates" if coordinate_role == "device_gps" else "administrative_coordinates"
    ] = coordinates
    return normalized


def _validate_v2(value: dict[str, Any]) -> None:
    required_text = ("timezone", "label")
    if any(not _text(value.get(field)) for field in required_text):
        raise ValidationError({"weather_location_data": "Selected location is incomplete"})
    administrative = value.get("administrative_coordinates")
    current = value.get("current_coordinates")
    if administrative is None and current is None:
        raise ValidationError(
            {"weather_location_data": "At least one coordinate source is required"}
        )
    if administrative is not None:
        if any(not _text(value.get(field)) for field in ("province", "city", "district")):
            raise ValidationError(
                {"weather_location_data": "Administrative location is incomplete"}
            )
        _validate_coordinates(administrative, expected_role="administrative_center")
    if current is not None:
        _validate_coordinates(current, expected_role="device_gps")
    adcode = _text(value.get("adcode"))
    if adcode and (len(adcode) != 6 or not adcode.isdigit()):
        raise ValidationError({"weather_location_data": "adcode must be six digits"})


def _validate_legacy(value: dict[str, Any]) -> None:
    required_text = ("provider", "name", "timezone", "label")
    if any(not _text(value.get(field)) for field in required_text):
        raise ValidationError({"weather_location_data": "Selected location is incomplete"})
    _validate_coordinate_values(value.get("latitude"), value.get("longitude"))


def _validate_coordinates(value: Any, *, expected_role: str) -> None:
    if not isinstance(value, dict):
        raise ValidationError({"weather_location_data": "Coordinates must be an object"})
    if not _text(value.get("provider")):
        raise ValidationError({"weather_location_data": "Coordinate provider is required"})
    if value.get("coordinate_role") != expected_role:
        raise ValidationError({"weather_location_data": "Coordinate role is invalid"})
    _validate_coordinate_values(value.get("latitude"), value.get("longitude"))
    accuracy = value.get("accuracy_meters")
    if accuracy is not None and (
        not isinstance(accuracy, (int, float)) or isinstance(accuracy, bool) or float(accuracy) < 0
    ):
        raise ValidationError({"weather_location_data": "GPS accuracy must be non-negative"})


def _validate_coordinate_values(latitude: Any, longitude: Any) -> None:
    if not _is_coordinate_pair(latitude, longitude):
        raise ValidationError({"weather_location_data": "Coordinates must be numbers"})
    if not -90 <= float(latitude) <= 90 or not -180 <= float(longitude) <= 180:
        raise ValidationError({"weather_location_data": "Coordinates are out of range"})


def _is_coordinate_pair(latitude: Any, longitude: Any) -> bool:
    return all(
        isinstance(item, (int, float)) and not isinstance(item, bool)
        for item in (latitude, longitude)
    )


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _adcode(value: Any) -> str:
    text = _text(value)
    return text if len(text) == 6 and text.isdigit() else ""

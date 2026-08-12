from django.db import migrations


def migrate_weather_locations_forward(apps, schema_editor):
    del schema_editor
    UserPreference = apps.get_model("preferences", "UserPreference")
    for preference in UserPreference.objects.exclude(weather_location_data={}):
        value = preference.weather_location_data
        if not isinstance(value, dict) or value.get("schema_version") == 2:
            continue
        latitude = value.get("latitude")
        longitude = value.get("longitude")
        if not isinstance(latitude, (int, float)) or isinstance(latitude, bool):
            continue
        if not isinstance(longitude, (int, float)) or isinstance(longitude, bool):
            continue
        provider = str(value.get("provider", "")).strip()
        provider_location_id = str(value.get("provider_location_id", "")).strip()
        coordinate_role = (
            "device_gps" if provider == "device_geolocation" else "administrative_center"
        )
        coordinates = {
            "provider": provider or "open_meteo",
            "provider_location_id": provider_location_id,
            "coordinate_role": coordinate_role,
            "latitude": float(latitude),
            "longitude": float(longitude),
            "label": str(value.get("label", "")).strip(),
        }
        migrated = {
            "schema_version": 2,
            "provider": provider,
            "provider_location_id": provider_location_id,
            "adcode": (
                provider_location_id
                if len(provider_location_id) == 6 and provider_location_id.isdigit()
                else ""
            ),
            "name": str(value.get("name", "")).strip(),
            "admin1": str(value.get("admin1", "")).strip(),
            "country": str(value.get("country", "")).strip(),
            "timezone": str(value.get("timezone", "")).strip(),
            "label": str(value.get("label", "")).strip(),
            "province": str(value.get("province", "")).strip(),
            "city": str(value.get("city", "")).strip(),
            "district": str(value.get("district", "")).strip(),
            (
                "current_coordinates"
                if coordinate_role == "device_gps"
                else "administrative_coordinates"
            ): coordinates,
        }
        preference.weather_location_data = migrated
        preference.save(update_fields=["weather_location_data"])


def migrate_weather_locations_backward(apps, schema_editor):
    del schema_editor
    UserPreference = apps.get_model("preferences", "UserPreference")
    for preference in UserPreference.objects.exclude(weather_location_data={}):
        value = preference.weather_location_data
        if not isinstance(value, dict) or value.get("schema_version") != 2:
            continue
        coordinates = value.get("administrative_coordinates") or value.get(
            "current_coordinates"
        )
        if not isinstance(coordinates, dict):
            continue
        preference.weather_location_data = {
            "provider": str(coordinates.get("provider", value.get("provider", ""))),
            "provider_location_id": str(
                coordinates.get(
                    "provider_location_id",
                    value.get("provider_location_id", ""),
                )
            ),
            "name": str(value.get("name", "")),
            "admin1": str(value.get("admin1", "")),
            "country": str(value.get("country", "")),
            "timezone": str(value.get("timezone", "")),
            "label": str(value.get("label", "")),
            "latitude": coordinates.get("latitude"),
            "longitude": coordinates.get("longitude"),
            "province": str(value.get("province", "")),
            "city": str(value.get("city", "")),
            "district": str(value.get("district", "")),
        }
        preference.save(update_fields=["weather_location_data"])


class Migration(migrations.Migration):
    dependencies = [
        ("preferences", "0007_time_memory_controls")
    ]

    operations = [
        migrations.RunPython(
            migrate_weather_locations_forward,
            migrate_weather_locations_backward,
        )
    ]

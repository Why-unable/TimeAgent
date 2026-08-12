from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _area_lists() -> dict[str, dict[str, str]]:
    path = Path(__file__).with_name("data") / "china_administrative_areas.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Administrative area catalog must be an object")
    return {
        level: {str(code): str(name) for code, name in values.items()}
        for level, values in payload.items()
        if isinstance(values, dict)
    }


def administrative_area_options(
    *, province_code: str = "", city_code: str = ""
) -> list[dict[str, str]]:
    areas = _area_lists()
    if city_code:
        source = areas["county_list"]
        prefix = city_code[:4]
    elif province_code:
        source = areas["city_list"]
        prefix = province_code[:2]
    else:
        source = areas["province_list"]
        prefix = ""
    return [
        {"code": code, "name": name}
        for code, name in sorted(source.items())
        if not prefix or code.startswith(prefix)
    ]


def administrative_area_code(*, province: str, city: str, district: str) -> str:
    areas = _area_lists()
    province_code = _find_code(areas["province_list"], province)
    if not province_code:
        return ""
    city_code = _find_code(
        areas["city_list"],
        city,
        prefix=province_code[:2],
    )
    if not city_code:
        return ""
    return _find_code(
        areas["county_list"],
        district,
        prefix=city_code[:4],
    )


def _find_code(values: dict[str, str], name: str, *, prefix: str = "") -> str:
    normalized = name.strip()
    return next(
        (
            code
            for code, candidate in values.items()
            if candidate == normalized and (not prefix or code.startswith(prefix))
        ),
        "",
    )

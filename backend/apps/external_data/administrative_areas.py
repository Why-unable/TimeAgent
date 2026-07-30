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

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


REGION_DATA_PATH = Path(__file__).resolve().parents[1] / "shared_data" / "china_weather_regions.json"


@lru_cache(maxsize=1)
def weather_regions() -> list[dict[str, Any]]:
    with REGION_DATA_PATH.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    return payload if isinstance(payload, list) else []


def _province_option(region: dict[str, Any]) -> dict[str, Any]:
    name = str(region.get("name") or "").strip()
    return {
        "id": f"province:{name}",
        "name": name,
        "path": f"{name},中国",
        "country": "CN",
        "level": "province",
        "province": name,
        "direct": bool(region.get("direct")),
    }


def _city_option(province: str, city: str) -> dict[str, Any]:
    return {
        "id": f"city:{province}:{city}",
        "name": city,
        "path": f"{city},{province},中国",
        "country": "CN",
        "level": "city",
        "province": province,
        "direct": False,
    }


def region_catalog() -> dict[str, Any]:
    return {
        "items": [
            {
                **_province_option(region),
                "cities": [
                    _city_option(str(region.get("name") or ""), str(city))
                    for city in region.get("cities", [])
                    if str(city).strip()
                ],
            }
            for region in weather_regions()
            if str(region.get("name") or "").strip()
        ]
    }


def search_region_options(query: str) -> dict[str, Any]:
    text = query.strip()
    if not text:
        return {"items": []}

    regions = weather_regions()
    province_matches = [
        _province_option(region)
        for region in regions
        if text in str(region.get("name") or "")
    ]
    if province_matches:
        return {"items": province_matches}

    city_matches: list[dict[str, Any]] = []
    for region in regions:
        province = str(region.get("name") or "").strip()
        for city in region.get("cities", []):
            city_name = str(city).strip()
            if city_name and text in city_name:
                city_matches.append(_city_option(province, city_name))
    return {"items": city_matches[:20]}

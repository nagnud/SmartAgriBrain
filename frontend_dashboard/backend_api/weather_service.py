from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx
from fastapi import HTTPException


SENIVERSE_BASE_URL = "https://api.seniverse.com/v3"
DEFAULT_CITY = "无锡"
DEFAULT_LANGUAGE = "zh-Hans"
DEFAULT_UNIT = "c"

_bundle_cache: Dict[str, Tuple[int, Dict[str, Any]]] = {}
_current_cache: Dict[str, Tuple[int, Dict[str, Any]]] = {}


def now_ms() -> int:
    return int(time.time() * 1000)


def weather_api_key() -> str:
    return os.getenv("SENIVERSE_KEY", "").strip()


def default_city() -> str:
    return os.getenv("WEATHER_CITY", DEFAULT_CITY).strip() or DEFAULT_CITY


def weather_language() -> str:
    return os.getenv("WEATHER_LANGUAGE", DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE


def weather_unit() -> str:
    return os.getenv("WEATHER_UNIT", DEFAULT_UNIT).strip() or DEFAULT_UNIT


def cache_seconds() -> int:
    try:
        return max(0, int(os.getenv("WEATHER_CACHE_SECONDS", "600")))
    except ValueError:
        return 600


def timeout_seconds() -> float:
    try:
        return max(1.0, float(os.getenv("WEATHER_TIMEOUT_SECONDS", "10")))
    except ValueError:
        return 10.0


def normalize_city(city: Optional[str]) -> str:
    value = (city or default_city()).strip()
    return value or DEFAULT_CITY


def require_api_key() -> str:
    api_key = weather_api_key()
    placeholders = {"your_seniverse_key", "your_seniverse_key_here", "你的心知天气KEY"}
    if not api_key or api_key in placeholders:
        raise HTTPException(status_code=503, detail="天气 API 未配置：请在 backend_api/.env 设置 SENIVERSE_KEY。")
    return api_key


def cache_get(cache: Dict[str, Tuple[int, Dict[str, Any]]], key: str) -> Optional[Dict[str, Any]]:
    ttl = cache_seconds()
    if ttl <= 0:
        return None
    cached = cache.get(key)
    if not cached:
        return None
    created_at, value = cached
    if now_ms() - created_at > ttl * 1000:
        cache.pop(key, None)
        return None
    return value


def cache_set(cache: Dict[str, Tuple[int, Dict[str, Any]]], key: str, value: Dict[str, Any]) -> Dict[str, Any]:
    cache[key] = (now_ms(), value)
    return value


def seniverse_get(path: str, city: Optional[str] = None, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "key": require_api_key(),
        "location": normalize_city(city),
        "language": weather_language(),
        "unit": weather_unit(),
    }
    if extra:
        params.update(extra)
    with httpx.Client(timeout=timeout_seconds()) as client:
        response = client.get(f"{SENIVERSE_BASE_URL}{path}", params=params)
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
    return response.json()


def module_error(error: Exception) -> Dict[str, Any]:
    return {
        "available": False,
        "reason": str(error)[:300],
        "updated_at": now_ms(),
    }


def safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> Optional[int]:
    number = safe_float(value)
    return int(number) if number is not None else None


def first_result(body: Dict[str, Any]) -> Dict[str, Any]:
    results = body.get("results")
    if isinstance(results, list) and results and isinstance(results[0], dict):
        return results[0]
    return {}


def location_text(location: Dict[str, Any], fallback: str) -> str:
    name = str(location.get("name") or fallback)
    path = str(location.get("path") or "")
    raw_parts = [part.strip() for part in (path or name).split(",") if part.strip()]
    parts: List[str] = []
    for part in raw_parts:
        if part in {"中国", "CN"} or part in parts:
            continue
        parts.append(part)
    if len(parts) >= 2:
        return " · ".join(parts[:2])
    return parts[0] if parts else name


def wind_level_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "--"
    return text if text.endswith("级") else f"{text} 级"


def parse_current(body: Dict[str, Any], city: str) -> Dict[str, Any]:
    result = first_result(body)
    location = result.get("location") if isinstance(result.get("location"), dict) else {}
    now = result.get("now") if isinstance(result.get("now"), dict) else {}
    wind_direction = str(now.get("wind_direction") or now.get("wind_direction_degree") or "--")
    humidity = safe_float(now.get("humidity"))
    return {
        "available": True,
        "location": location_text(location, city),
        "city": city,
        "condition": str(now.get("text") or "--"),
        "code": str(now.get("code") or ""),
        "temperature": safe_float(now.get("temperature")) or 0,
        "feels_like": safe_float(now.get("feels_like")),
        "humidity": humidity,
        "wind_direction": wind_direction,
        "wind_direction_degree": safe_float(now.get("wind_direction_degree")),
        "wind_speed": safe_float(now.get("wind_speed")),
        "wind_scale": safe_int(now.get("wind_scale")),
        "wind_level": wind_level_text(now.get("wind_scale")),
        "pressure": safe_float(now.get("pressure")),
        "visibility": safe_float(now.get("visibility")),
        "clouds": safe_float(now.get("clouds")),
        "dew_point": safe_float(now.get("dew_point")),
        "last_update": str(result.get("last_update") or ""),
        "updated_at": now_ms(),
        "raw": now,
    }


def weather_current(city: Optional[str] = None) -> Dict[str, Any]:
    normalized_city = normalize_city(city)
    cache_key = f"current:{normalized_city}:{weather_language()}:{weather_unit()}"
    cached = cache_get(_current_cache, cache_key)
    if cached:
        return cached
    try:
        current = parse_current(seniverse_get("/weather/now.json", normalized_city), normalized_city)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"天气实况获取失败：{error}") from error
    return cache_set(_current_cache, cache_key, current)


def current_payload(city: Optional[str] = None) -> Dict[str, Any]:
    current = weather_current(city)
    return {
        "location": current.get("location") or normalize_city(city),
        "condition": current.get("condition") or "--",
        "temperature": current.get("temperature") or 0,
        "humidity": current.get("humidity"),
        "wind_direction": current.get("wind_direction") or "--",
        "wind_level": current.get("wind_level") or "--",
        "updated_at": current.get("updated_at") or now_ms(),
    }


def parse_daily(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = first_result(body)
    daily = result.get("daily") if isinstance(result.get("daily"), list) else []
    items: List[Dict[str, Any]] = []
    for item in daily:
        if not isinstance(item, dict):
            continue
        items.append({
            "date": item.get("date"),
            "condition_day": item.get("text_day"),
            "condition_night": item.get("text_night"),
            "high": safe_float(item.get("high")),
            "low": safe_float(item.get("low")),
            "rainfall": safe_float(item.get("rainfall")),
            "precip": safe_float(item.get("precip")),
            "humidity": safe_float(item.get("humidity")),
            "wind_direction": item.get("wind_direction"),
            "wind_speed": safe_float(item.get("wind_speed")),
            "wind_scale": safe_int(item.get("wind_scale")),
        })
    return items


def parse_hourly(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = first_result(body)
    hourly = result.get("hourly") if isinstance(result.get("hourly"), list) else []
    items: List[Dict[str, Any]] = []
    for item in hourly:
        if not isinstance(item, dict):
            continue
        items.append({
            "time": item.get("time"),
            "condition": item.get("text"),
            "temperature": safe_float(item.get("temperature")),
            "humidity": safe_float(item.get("humidity")),
            "rainfall": safe_float(item.get("rainfall")),
            "precip": safe_float(item.get("precip")),
            "wind_direction": item.get("wind_direction"),
            "wind_speed": safe_float(item.get("wind_speed")),
            "wind_scale": safe_int(item.get("wind_scale")),
        })
    return items


def parse_air(body: Dict[str, Any]) -> Dict[str, Any]:
    result = first_result(body)
    air = result.get("air") if isinstance(result.get("air"), dict) else {}
    city = air.get("city") if isinstance(air.get("city"), dict) else air
    return {
        "aqi": safe_int(city.get("aqi")),
        "quality": city.get("quality"),
        "pm25": safe_float(city.get("pm25")),
        "pm10": safe_float(city.get("pm10")),
        "o3": safe_float(city.get("o3")),
        "no2": safe_float(city.get("no2")),
        "so2": safe_float(city.get("so2")),
        "co": safe_float(city.get("co")),
    }


def parse_life(body: Dict[str, Any]) -> Dict[str, Any]:
    result = first_result(body)
    suggestion = result.get("suggestion") if isinstance(result.get("suggestion"), dict) else {}
    parsed: Dict[str, Any] = {}
    for key, value in suggestion.items():
        if isinstance(value, dict):
            parsed[key] = {
                "brief": value.get("brief"),
                "details": value.get("details"),
            }
    return parsed


def parse_alarms(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = first_result(body)
    alarms = result.get("alarms") if isinstance(result.get("alarms"), list) else []
    items: List[Dict[str, Any]] = []
    for item in alarms:
        if not isinstance(item, dict):
            continue
        items.append({
            "title": item.get("title"),
            "type": item.get("type"),
            "level": item.get("level"),
            "status": item.get("status"),
            "description": item.get("description"),
            "pub_date": item.get("pub_date"),
        })
    return items


def weather_module(
    name: str,
    path: str,
    city: str,
    parser: Callable[[Dict[str, Any]], Any],
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        data = parser(seniverse_get(path, city, extra))
        return {
            "available": True,
            "name": name,
            "data": data,
            "updated_at": now_ms(),
        }
    except Exception as error:
        unavailable = module_error(error)
        unavailable["name"] = name
        return unavailable


def weather_bundle(city: Optional[str] = None) -> Dict[str, Any]:
    normalized_city = normalize_city(city)
    cache_key = f"bundle:{normalized_city}:{weather_language()}:{weather_unit()}"
    cached = cache_get(_bundle_cache, cache_key)
    if cached:
        return cached

    current = weather_module("实况天气", "/weather/now.json", normalized_city, lambda body: parse_current(body, normalized_city))
    bundle = {
        "city": normalized_city,
        "updated_at": now_ms(),
        "current": current,
        "daily": weather_module("逐日预报", "/weather/daily.json", normalized_city, parse_daily, {"days": 5}),
        "hourly": weather_module("逐小时预报", "/weather/hourly.json", normalized_city, parse_hourly, {"hours": 24}),
        "air": weather_module("空气质量", "/air/now.json", normalized_city, parse_air),
        "life": weather_module("生活指数", "/life/suggestion.json", normalized_city, parse_life),
        "alarms": weather_module("天气预警", "/weather/alarm.json", normalized_city, parse_alarms),
        "registered_capabilities": [
            {"key": "agriculture", "name": "农业气象", "available": False, "reason": "已预留能力入口；账号支持对应心知天气产品后可接入。"},
            {"key": "grid", "name": "网格天气", "available": False, "reason": "已预留能力入口；账号支持对应心知天气产品后可接入。"},
            {"key": "map_layer", "name": "气象图层", "available": False, "reason": "已预留能力入口；账号支持对应心知天气产品后可接入。"},
            {"key": "marine", "name": "海洋天气", "available": False, "reason": "已预留能力入口；账号支持对应心知天气产品后可接入。"},
        ],
    }
    return cache_set(_bundle_cache, cache_key, bundle)


def search_cities(query: str) -> Dict[str, Any]:
    text = query.strip()
    if not text:
        return {"items": []}
    params = {
        "key": require_api_key(),
        "q": text,
        "language": weather_language(),
        "limit": 10,
    }
    try:
        with httpx.Client(timeout=timeout_seconds()) as client:
            response = client.get(f"{SENIVERSE_BASE_URL}/location/search.json", params=params)
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
        body = response.json()
        results = body.get("results") if isinstance(body.get("results"), list) else []
        items = []
        for item in results:
            if not isinstance(item, dict):
                continue
            items.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "path": item.get("path"),
                "country": item.get("country"),
                "timezone": item.get("timezone"),
                "timezone_offset": item.get("timezone_offset"),
            })
        return {"items": items}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"城市搜索失败：{error}") from error

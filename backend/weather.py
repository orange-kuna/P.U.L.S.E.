"""Open-Meteo forecasts. Fail explicitly; never substitute weather on failure."""

import math
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx

from backend.atmosphere import R_AIR

SITES = [
    {"id": "cape", "name": "Cape Canaveral", "region": "Florida, United States", "latitude": 28.4889, "longitude": -80.5778},
    {"id": "vandenberg", "name": "Vandenberg", "region": "California, United States", "latitude": 34.742, "longitude": -120.5724},
    {"id": "sriharikota", "name": "Sriharikota", "region": "Andhra Pradesh, India", "latitude": 13.7199, "longitude": 80.2304},
    {"id": "mahia", "name": "Māhia Peninsula", "region": "New Zealand", "latitude": -39.261, "longitude": 177.865},
]
LEVELS = [1000, 925, 850, 700, 500, 400, 300, 250, 200, 150, 100, 70, 50, 30]
_cache = {}
_lock = threading.Lock()


class WeatherUnavailable(Exception):
    pass


def get_site(site_id):
    return next(s for s in SITES if s["id"] == site_id)


def get_forecast(site):
    with _lock:
        cached = _cache.get(site["id"])
        if cached and time.monotonic() - cached[0] < 600:
            return cached[1]
    hourly = ["temperature_2m", "relative_humidity_2m", "precipitation", "cloud_cover",
              "wind_speed_10m", "wind_direction_10m", "surface_pressure"]
    for level in LEVELS:
        hourly.extend(f"{v}_{level}hPa" for v in
                      ["temperature", "wind_speed", "wind_direction", "geopotential_height"])
    try:
        response = httpx.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": site["latitude"], "longitude": site["longitude"],
            "hourly": ",".join(hourly), "wind_speed_unit": "ms",
            "timezone": "UTC", "forecast_days": 7,
        }, timeout=20)
        response.raise_for_status()
        data = response.json()["hourly"]
        if not data.get("time"):
            raise ValueError("Forecast has no hourly records.")
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise WeatherUnavailable("Open-Meteo forecast is unavailable. Retry later or explicitly select Standard atmosphere.") from exc
    with _lock:
        _cache[site["id"]] = (time.monotonic(), data)
    return data


def hour_index(data, launch_time=None):
    target = launch_time or datetime.now(timezone.utc)
    times = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in data["time"]]
    index = min(range(len(times)), key=lambda i: abs((times[i] - target).total_seconds()))
    if abs((times[index] - target).total_seconds()) > 3600:
        raise WeatherUnavailable("The requested launch time is outside the available forecast.")
    return index


def _value(data, key, index):
    try:
        value = float(data[key][index])
        if not math.isfinite(value):
            raise ValueError
        return value
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise WeatherUnavailable(f"Forecast is missing required data: {key}.") from exc


def wind_components(speed, direction):
    # Meteorological direction is where wind comes FROM.
    angle = math.radians(direction)
    return -speed * math.sin(angle), -speed * math.cos(angle)


def weather_at(site, launch_time=None, data=None):
    data = data if data is not None else get_forecast(site)
    i = hour_index(data, launch_time)
    temp = _value(data, "temperature_2m", i)
    pressure = _value(data, "surface_pressure", i) * 100
    speed = _value(data, "wind_speed_10m", i)
    east, north = wind_components(speed, _value(data, "wind_direction_10m", i))
    layers = [{
        "altitude_m": 0, "temperature_c": temp, "pressure_pa": pressure,
        "density_kg_m3": pressure / (R_AIR * (temp + 273.15)),
        "wind_east_ms": east, "wind_north_ms": north, "wind_ms": speed,
    }]
    for level in LEVELS:
        height = _value(data, f"geopotential_height_{level}hPa", i)
        if height <= layers[-1]["altitude_m"]:
            continue
        t = _value(data, f"temperature_{level}hPa", i)
        v = _value(data, f"wind_speed_{level}hPa", i)
        e, n = wind_components(v, _value(data, f"wind_direction_{level}hPa", i))
        layers.append({
            "altitude_m": height, "temperature_c": t, "pressure_pa": level * 100,
            "density_kg_m3": level * 100 / (R_AIR * (t + 273.15)),
            "wind_east_ms": e, "wind_north_ms": n, "wind_ms": v,
        })
    return {
        "source": "open-meteo", "label": "Open-Meteo · hourly forecast",
        "valid_at": data["time"][i] + "+00:00",
        "surface": {
            "temperature_c": temp, "wind_ms": speed,
            "precipitation_mm": _value(data, "precipitation", i),
            "cloud_cover_pct": _value(data, "cloud_cover", i),
            "humidity_pct": _value(data, "relative_humidity_2m", i),
        },
        "layers": layers,
        "note": "Open-Meteo hourly forecast, nearest forecast hour (UTC), not a radiosonde observation. Heights are above sea level; sites approximated at sea level. Above the highest forecast pressure level, density blends to reference atmosphere and wind tapers to zero over 10 km. CC BY 4.0 attribution: Open-Meteo.com. Free endpoint is for non-commercial use.",
    }


def rank_windows(site, wind_limit):
    data = get_forecast(site)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    windows = []
    for hours in range(0, 36, 3):
        weather = weather_at(site, now + timedelta(hours=hours), data)
        surface = weather["surface"]
        max_wind = max(l["wind_ms"] for l in weather["layers"])
        rain = surface["precipitation_mm"]
        cloud = surface["cloud_cover_pct"]
        # A transparent relative index, NOT launch-success probability.
        penalty = 45 * min(max_wind / wind_limit, 2) + 35 * min(rain / 2, 1) + 20 * cloud / 100
        score = round(max(0, 100 - penalty))
        reasons = []
        if max_wind > wind_limit:
            reasons.append("Forecast profile wind exceeds selected wind limit")
        if rain >= 1:
            reasons.append("Precipitation at or above 1 mm/h")
        if cloud >= 80:
            reasons.append("High cloud cover; lightning not assessed")
        status = "exceeded" if max_wind > wind_limit or rain >= 2 else "caution" if score < 65 or reasons else "nominal"
        windows.append({
            "launch_time": weather["valid_at"], "wind_ms": round(max_wind, 2),
            "precipitation_mm": rain, "cloud_cover_pct": cloud, "score": score,
            "status": status, "reasons": reasons or ["Lowest relative weather penalty; not a launch clearance"],
        })
    return {
        "source": "Open-Meteo hourly forecast", "site": site,
        "method": "Score = max(0, 100 − 45·min(profile wind / wind limit, 2) − 35·min(rain / 2, 1) − 20·cloud fraction). A relative index, not a probability. No AI model is used.",
        "windows": windows, "recommended": max(windows, key=lambda w: w["score"]),
        "note": "Best among 12 sampled hours over 36 hours. Does not assess lightning, range safety, vehicle loads, orbital alignment or mission constraints. An exceeded window is never a launch recommendation.",
    }

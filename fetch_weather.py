#!/usr/bin/env python3
"""Fetch 3-year daily weather for Myanmar cities from Open-Meteo Archive API.

No API key required. Writes a single CSV with derived flags.
Reusable: just run `python3 fetch_weather.py`.
"""

import csv
import json
import os
import time
import urllib.parse
import urllib.request

START_DATE = "2023-06-24"
END_DATE = "2026-06-23"
TIMEZONE = "Asia/Yangon"
API = "https://archive-api.open-meteo.com/v1/archive"

OUTPUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data", "external", "weather_daily.csv",
)

CITIES = [
    ("Yangon", 16.8409, 96.1735),
    ("Mandalay", 21.9588, 96.0891),
    ("Naypyidaw", 19.7633, 96.0785),
    ("Bago", 17.3350, 96.4815),
    ("Pyay", 18.8249, 95.2086),
    ("Taunggyi", 20.7892, 97.0378),
]

DAILY_VARS = [
    "precipitation_sum",
    "rain_sum",
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "relative_humidity_2m_mean",
    "windspeed_10m_max",
    "weathercode",
]

COLUMNS = [
    "date", "city", "lat", "lon",
    "precip_mm", "rain_mm", "tmax_c", "tmin_c", "tmean_c",
    "humidity_pct", "wind_kmh", "weathercode",
    "is_rainy", "is_heavy_rain", "is_hot",
]


def fetch_city(name, lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "timezone": TIMEZONE,
        "daily": ",".join(DAILY_VARS),
    }
    url = API + "?" + urllib.parse.urlencode(params)
    last_err = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "weather-fetch/1.0"})
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last_err = e
            wait = 5 * (attempt + 1)
            print(f"  [{name}] attempt {attempt + 1} failed: {e} -> retry in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Failed to fetch {name}: {last_err}")


def num(v):
    """Return value as-is for CSV (blank if None)."""
    return "" if v is None else v


def flag_gt(v, threshold):
    if v is None:
        return ""
    return 1 if v > threshold else 0


def build_rows(name, lat, lon, payload):
    daily = payload.get("daily", {})
    times = daily.get("time", [])
    rows = []
    for i, d in enumerate(times):
        def g(key):
            arr = daily.get(key, [])
            return arr[i] if i < len(arr) else None
        precip = g("precipitation_sum")
        rain = g("rain_sum")
        tmax = g("temperature_2m_max")
        tmin = g("temperature_2m_min")
        tmean = g("temperature_2m_mean")
        hum = g("relative_humidity_2m_mean")
        wind = g("windspeed_10m_max")
        wcode = g("weathercode")
        rows.append({
            "date": d,
            "city": name,
            "lat": lat,
            "lon": lon,
            "precip_mm": num(precip),
            "rain_mm": num(rain),
            "tmax_c": num(tmax),
            "tmin_c": num(tmin),
            "tmean_c": num(tmean),
            "humidity_pct": num(hum),
            "wind_kmh": num(wind),
            "weathercode": num(wcode),
            "is_rainy": flag_gt(rain, 1),
            "is_heavy_rain": flag_gt(rain, 20),
            "is_hot": flag_gt(tmax, 35),
        })
    return rows


def main():
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    all_rows = []
    for name, lat, lon in CITIES:
        print(f"Fetching {name} ({lat}, {lon}) ...")
        payload = fetch_city(name, lat, lon)
        rows = build_rows(name, lat, lon, payload)
        print(f"  -> {len(rows)} rows")
        all_rows.extend(rows)
        time.sleep(1)  # be polite to the free API

    with open(OUTPUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(all_rows)

    print(f"\nWrote {len(all_rows)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()

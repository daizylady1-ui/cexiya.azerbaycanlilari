"""Прогноз на текущую неделю пн…вс (Open-Meteo, бесплатно, без ключа)."""
from datetime import datetime, timedelta

import requests

from .util import log


def week_forecast(cities: list[dict], tz: str, now: datetime) -> list[dict]:
    monday = (now - timedelta(days=now.weekday())).date()
    sunday = monday + timedelta(days=6)
    result = []
    for c in cities:
        try:
            r = requests.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": c["lat"], "longitude": c["lon"], "timezone": tz,
                "start_date": monday.isoformat(), "end_date": sunday.isoformat(),
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            }, timeout=20)
            r.raise_for_status()
            d = r.json()["daily"]
            days = [{
                "code": int(d["weather_code"][i] or 0),
                "max": round(d["temperature_2m_max"][i]),
                "min": round(d["temperature_2m_min"][i]),
                "rain": int(d["precipitation_probability_max"][i] or 0),
            } for i in range(7)]
            result.append({"name": c["name"], "days": days})
        except (requests.RequestException, KeyError, IndexError, TypeError) as e:
            log.warning("Погода %s: %s", c["name"], e)
            if not result:          # без Праги сторис не собрать
                return []
    return result

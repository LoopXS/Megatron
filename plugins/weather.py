"""
Weather plugin for UserBot.

Features
--------
Commands
    .weather <city>
    .air <city>

Inline
    @bot weather <city>

Current weather
    Temperature
    Feels like
    Humidity
    Wind
    Gusts
    Precipitation
    Clouds
    Pressure
    Visibility
    UV index
    Sunrise / Sunset
    Timezone

Forecast
    Hourly
    7-day daily

Air quality
    European AQI
    US AQI
    PM2.5
    PM10
    NO2
    O3
    SO2
    CO

Units
    Celsius
    Fahrenheit

Caching
-------
Geocoding, weather and air-quality requests use separate in-memory
TTL caches.

Architecture
------------
The command and inline layers are intentionally separated.

COMMAND LAYER
    heartless_cmd
        ↓
    command_*()
        ↓
    WeatherService

INLINE LAYER
    in_pattern
        ↓
    inline_*()
        ↓
    callback()
        ↓
    WeatherService

No command handler invokes the inline query system.
No inline callback invokes a command handler.

Provider
--------
Open-Meteo
https://open-meteo.com/

No API key is required.
"""

from __future__ import annotations

import asyncio
import html
import math
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote
from zoneinfo import ZoneInfo

import aiohttp
from telethon import Button

from . import (
    Button as ProjectButton,
    asst,
    callback,
    in_pattern,
    heartless_cmd,
)


# ============================================================================
# CONFIGURATION
# ============================================================================

OPEN_METEO_FORECAST = (
    "https://api.open-meteo.com/v1/forecast"
)

OPEN_METEO_GEOCODING = (
    "https://geocoding-api.open-meteo.com/v1/search"
)

OPEN_METEO_AIR = (
    "https://air-quality-api.open-meteo.com/v1/air-quality"
)

USER_AGENT = (
    "CythonX-Weather/2.0 "
    "(Open-Meteo; Heartless)"
)

REQUEST_TIMEOUT = 15

GEOCODE_CACHE_TTL = 60 * 60 * 12
WEATHER_CACHE_TTL = 60 * 5
AIR_CACHE_TTL = 60 * 10

MAX_INLINE_RESULTS = 8

# Separate caches.
# They are deliberately NOT used as command/inline state.
_GEOCODE_CACHE: Dict[str, Tuple[float, List[dict]]] = {}
_WEATHER_CACHE: Dict[str, Tuple[float, dict]] = {}
_AIR_CACHE: Dict[str, Tuple[float, dict]] = {}


# ============================================================================
# WEATHER CODES
# ============================================================================

WEATHER_CODES = {
    0: ("☀️", "Clear sky"),
    1: ("🌤️", "Mainly clear"),
    2: ("⛅", "Partly cloudy"),
    3: ("☁️", "Overcast"),
    45: ("🌫️", "Fog"),
    48: ("🌫️", "Depositing rime fog"),
    51: ("🌦️", "Light drizzle"),
    53: ("🌦️", "Moderate drizzle"),
    55: ("🌧️", "Dense drizzle"),
    56: ("🌧️", "Light freezing drizzle"),
    57: ("🌧️", "Dense freezing drizzle"),
    61: ("🌦️", "Slight rain"),
    63: ("🌧️", "Moderate rain"),
    65: ("🌧️", "Heavy rain"),
    66: ("🌧️", "Light freezing rain"),
    67: ("🌧️", "Heavy freezing rain"),
    71: ("🌨️", "Slight snow fall"),
    73: ("🌨️", "Moderate snow fall"),
    75: ("❄️", "Heavy snow fall"),
    77: ("🌨️", "Snow grains"),
    80: ("🌦️", "Slight rain showers"),
    81: ("🌧️", "Moderate rain showers"),
    82: ("⛈️", "Violent rain showers"),
    85: ("🌨️", "Slight snow showers"),
    86: ("❄️", "Heavy snow showers"),
    95: ("⛈️", "Thunderstorm"),
    96: ("⛈️", "Thunderstorm with slight hail"),
    99: ("⛈️", "Thunderstorm with heavy hail"),
}


# ============================================================================
# AIR QUALITY
# ============================================================================

def aqi_label(aqi: Optional[float]) -> str:
    if aqi is None:
        return "Unknown"

    if aqi <= 20:
        return "🟢 Good"

    if aqi <= 40:
        return "🟢 Fair"

    if aqi <= 60:
        return "🟡 Moderate"

    if aqi <= 80:
        return "🟠 Poor"

    if aqi <= 100:
        return "🔴 Very Poor"

    return "🟣 Extremely Poor"


def us_aqi_label(aqi: Optional[float]) -> str:
    """Return the standard US AQI category for the supplied index."""
    if aqi is None:
        return "Unknown"

    if aqi <= 50:
        return "🟢 Good"

    if aqi <= 100:
        return "🟡 Moderate"

    if aqi <= 150:
        return "🟠 Unhealthy for Sensitive Groups"

    if aqi <= 200:
        return "🔴 Unhealthy"

    if aqi <= 300:
        return "🟣 Very Unhealthy"

    return "⚫ Hazardous"


# ============================================================================
# UTILITIES
# ============================================================================

def clean_text(
    value: Any,
    limit: int = 300,
) -> str:
    if value is None:
        return "—"

    value = str(value)

    value = value.replace(
        "\n",
        " ",
    )

    value = value.replace(
        "\r",
        " ",
    )

    if len(value) > limit:
        return value[: limit - 1] + "…"

    return value


def html_escape(
    value: Any,
    limit: int = 300,
) -> str:
    """
    Return a safely escaped, single-line string for Telegram markup.

    ``limit`` is applied before escaping so callers can safely bound the
    original text without changing the public behaviour of ``clean_text``.
    """
    return html.escape(
        clean_text(
            value,
            limit,
        )
    )


def safe_float(
    value: Any,
) -> Optional[float]:
    try:
        if value is None:
            return None

        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return None


def fmt_num(
    value: Any,
    digits: int = 1,
) -> str:
    number = safe_float(
        value
    )

    if number is None:
        return "—"

    if digits == 0:
        return str(
            int(
                round(number)
            )
        )

    return f"{number:.{digits}f}"


def wind_direction(
    degrees: Any,
) -> str:
    value = safe_float(
        degrees
    )

    if value is None:
        return "—"

    directions = [
        "N",
        "NE",
        "E",
        "SE",
        "S",
        "SW",
        "W",
        "NW",
    ]

    index = int(
        round(
            value / 45
        )
    ) % 8

    return directions[index]


def weather_description(
    code: Any,
) -> Tuple[str, str]:
    try:
        code = int(code)

    except (
        TypeError,
        ValueError,
    ):
        return "🌡️", "Unknown"

    return WEATHER_CODES.get(
        code,
        (
            "🌡️",
            "Unknown",
        ),
    )


def temperature(
    value: Any,
    unit: str = "C",
) -> str:
    number = safe_float(
        value
    )

    if number is None:
        return "—"

    if unit.upper() == "F":
        number = (
            number * 9 / 5
        ) + 32

    return (
        f"{number:.1f}°"
        f"{unit.upper()}"
    )


def convert_temperature(
    value: Any,
    unit: str,
) -> Optional[float]:
    number = safe_float(
        value
    )

    if number is None:
        return None

    if unit.upper() == "F":
        return (
            number * 9 / 5
        ) + 32

    return number


def local_time(
    iso_time: Optional[str],
) -> str:
    if not iso_time:
        return "—"

    try:
        dt = datetime.fromisoformat(
            iso_time
        )

        return dt.strftime(
            "%H:%M"
        )

    except Exception:
        return clean_text(
            iso_time,
            50,
        )


def local_date(
    iso_time: Optional[str],
) -> str:
    if not iso_time:
        return "—"

    try:
        dt = datetime.fromisoformat(
            iso_time
        )

        return dt.strftime(
            "%a, %d %b"
        )

    except Exception:
        return clean_text(
            iso_time,
            50,
        )


def unix_to_local(
    timestamp: Any,
    offset: int,
) -> str:
    try:
        timestamp = int(
            timestamp
        )

        dt = datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc,
        )

        from datetime import timedelta

        dt += timedelta(
            seconds=offset
        )

        return dt.strftime(
            "%Y-%m-%d %H:%M"
        )

    except Exception:
        return "—"


# ============================================================================
# HTTP CLIENT
# ============================================================================

async def http_json(
    url: str,
    params: Optional[dict] = None,
    *,
    timeout: int = REQUEST_TIMEOUT,
) -> dict:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }

    client_timeout = aiohttp.ClientTimeout(
        total=timeout,
        connect=7,
        sock_read=timeout,
    )

    last_error = None

    for attempt in range(2):

        try:
            async with aiohttp.ClientSession(
                timeout=client_timeout,
                headers=headers,
            ) as session:

                async with session.get(
                    url,
                    params=params,
                    allow_redirects=True,
                ) as response:

                    if response.status != 200:

                        body = await response.text(
                            errors="replace"
                        )

                        raise RuntimeError(
                            "HTTP "
                            f"{response.status}: "
                            f"{clean_text(body, 180)}"
                        )

                    data = await response.json(
                        content_type=None
                    )

                    if not isinstance(
                        data,
                        dict,
                    ):
                        raise RuntimeError(
                            "Invalid JSON response."
                        )

                    return data

        except Exception as exc:

            last_error = exc

            if attempt == 0:
                await asyncio.sleep(
                    0.35
                )

    raise RuntimeError(
        clean_text(
            last_error,
            300,
        )
    )


# ============================================================================
# GEOCODING SERVICE
# ============================================================================

async def geocode(
    query: str,
) -> List[dict]:

    query = clean_text(
        query,
        120,
    ).strip()

    if not query:
        return []

    cache_key = query.casefold()

    cached = _GEOCODE_CACHE.get(
        cache_key
    )

    if cached:

        created, data = cached

        if (
            time.time() - created
            < GEOCODE_CACHE_TTL
        ):
            return data

    params = {
        "name": query,
        "count": 8,
        "language": "en",
        "format": "json",
    }

    data = await http_json(
        OPEN_METEO_GEOCODING,
        params,
    )

    results = data.get(
        "results"
    )

    if not isinstance(
        results,
        list,
    ):
        results = []

    _GEOCODE_CACHE[
        cache_key
    ] = (
        time.time(),
        results,
    )

    return results


def location_title(
    location: dict,
) -> str:

    name = location.get(
        "name"
    )

    admin = location.get(
        "admin1"
    )

    country = location.get(
        "country"
    )

    parts = [
        clean_text(
            name,
            80,
        )
    ]

    if admin and admin != name:
        parts.append(
            clean_text(
                admin,
                80,
            )
        )

    if country:
        parts.append(
            clean_text(
                country,
                80,
            )
        )

    return ", ".join(
        part
        for part in parts
        if part
    )


# ============================================================================
# FORECAST SERVICE
# ============================================================================

async def fetch_weather(
    location: dict,
) -> dict:

    latitude = safe_float(
        location.get(
            "latitude"
        )
    )

    longitude = safe_float(
        location.get(
            "longitude"
        )
    )

    if (
        latitude is None
        or longitude is None
    ):
        raise ValueError(
            "Invalid location coordinates."
        )

    cache_key = (
        f"{latitude:.4f}:"
        f"{longitude:.4f}"
    )

    cached = _WEATHER_CACHE.get(
        cache_key
    )

    if cached:

        created, data = cached

        if (
            time.time() - created
            < WEATHER_CACHE_TTL
        ):
            return data

    params = {
        "latitude": latitude,
        "longitude": longitude,

        "current": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "is_day",
                "precipitation",
                "rain",
                "showers",
                "snowfall",
                "weather_code",
                "cloud_cover",
                "pressure_msl",
                "surface_pressure",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
                "visibility",
                "uv_index",
            ]
        ),

        "hourly": ",".join(
            [
                "temperature_2m",
                "apparent_temperature",
                "precipitation_probability",
                "precipitation",
                "weather_code",
                "cloud_cover",
                "wind_speed_10m",
                "wind_direction_10m",
                "uv_index",
            ]
        ),

        "daily": ",".join(
            [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "apparent_temperature_max",
                "apparent_temperature_min",
                "sunrise",
                "sunset",
                "precipitation_sum",
                "rain_sum",
                "showers_sum",
                "snowfall_sum",
                "precipitation_probability_max",
                "wind_speed_10m_max",
                "wind_gusts_10m_max",
                "wind_direction_10m_dominant",
                "uv_index_max",
            ]
        ),

        "timezone": "auto",

        "forecast_days": 7,

        "temperature_unit": "celsius",

        "wind_speed_unit": "kmh",

        "precipitation_unit": "mm",
    }

    data = await http_json(
        OPEN_METEO_FORECAST,
        params,
    )

    if "current" not in data:
        raise RuntimeError(
            "Weather provider returned "
            "no current weather data."
        )

    _WEATHER_CACHE[
        cache_key
    ] = (
        time.time(),
        data,
    )

    return data


# ============================================================================
# AIR QUALITY SERVICE
# ============================================================================

async def fetch_air_quality(
    location: dict,
) -> dict:

    latitude = safe_float(
        location.get(
            "latitude"
        )
    )

    longitude = safe_float(
        location.get(
            "longitude"
        )
    )

    if (
        latitude is None
        or longitude is None
    ):
        raise ValueError(
            "Invalid location coordinates."
        )

    cache_key = (
        f"{latitude:.4f}:"
        f"{longitude:.4f}"
    )

    cached = _AIR_CACHE.get(
        cache_key
    )

    if cached:

        created, data = cached

        if (
            time.time() - created
            < AIR_CACHE_TTL
        ):
            return data

    params = {
        "latitude": latitude,
        "longitude": longitude,

        "current": ",".join(
            [
                "european_aqi",
                "us_aqi",
                "pm10",
                "pm2_5",
                "carbon_monoxide",
                "nitrogen_dioxide",
                "sulphur_dioxide",
                "ozone",
            ]
        ),

        "timezone": "auto",
    }

    data = await http_json(
        OPEN_METEO_AIR,
        params,
    )

    _AIR_CACHE[
        cache_key
    ] = (
        time.time(),
        data,
    )

    return data


# ============================================================================
# FORMATTERS
# ============================================================================

def format_current(
    location: dict,
    weather: dict,
    unit: str = "C",
) -> str:

    current = weather.get(
        "current",
        {}
    )

    name = location_title(
        location
    )

    code = current.get(
        "weather_code"
    )

    icon, description = weather_description(
        code
    )

    temp = temperature(
        current.get(
            "temperature_2m"
        ),
        unit,
    )

    feels = temperature(
        current.get(
            "apparent_temperature"
        ),
        unit,
    )

    humidity = fmt_num(
        current.get(
            "relative_humidity_2m"
        ),
        0,
    )

    wind = fmt_num(
        current.get(
            "wind_speed_10m"
        ),
        0,
    )

    wind_dir = wind_direction(
        current.get(
            "wind_direction_10m"
        )
    )

    gust = fmt_num(
        current.get(
            "wind_gusts_10m"
        ),
        0,
    )

    pressure = fmt_num(
        current.get(
            "pressure_msl"
        ),
        0,
    )

    visibility = safe_float(
        current.get(
            "visibility"
        )
    )

    if visibility is not None:
        visibility_text = (
            f"{visibility / 1000:.1f} km"
        )

    else:
        visibility_text = "—"

    precip = fmt_num(
        current.get(
            "precipitation"
        )
    )

    clouds = fmt_num(
        current.get(
            "cloud_cover"
        ),
        0,
    )

    uv = fmt_num(
        current.get(
            "uv_index"
        )
    )

    timezone_name = weather.get(
        "timezone",
        "—",
    )

    sunrise = "—"
    sunset = "—"

    daily = weather.get(
        "daily",
        {}
    )

    if daily.get(
        "sunrise"
    ):
        sunrise = local_time(
            daily["sunrise"][0]
        )

    if daily.get(
        "sunset"
    ):
        sunset = local_time(
            daily["sunset"][0]
        )

    is_day = current.get(
        "is_day"
    )

    day_state = (
        "Daylight"
        if is_day
        else "Night"
    )

    return (
        f"{icon} **{html_escape(name)}**\n"
        f"**{description}** · {day_state}\n\n"

        f"🌡 **Temperature:** "
        f"`{temp}`\n"

        f"🤍 **Feels like:** "
        f"`{feels}`\n\n"

        f"💧 **Humidity:** "
        f"`{humidity}%`\n"

        f"💨 **Wind:** "
        f"`{wind} km/h {wind_dir}`\n"

        f"🌬 **Gusts:** "
        f"`{gust} km/h`\n"

        f"🌧 **Precipitation:** "
        f"`{precip} mm`\n"

        f"☁️ **Clouds:** "
        f"`{clouds}%`\n"

        f"📊 **Pressure:** "
        f"`{pressure} hPa`\n"

        f"👁 **Visibility:** "
        f"`{visibility_text}`\n"

        f"☀️ **UV Index:** "
        f"`{uv}`\n\n"

        f"🌅 **Sunrise:** `{sunrise}`\n"
        f"🌇 **Sunset:** `{sunset}`\n"

        f"🕐 **Timezone:** "
        f"`{html_escape(timezone_name, 80)}`"
    )


def format_hourly(
    weather: dict,
    unit: str = "C",
    day_offset: int = 0,
) -> str:

    hourly = weather.get(
        "hourly",
        {}
    )

    times = hourly.get(
        "time",
        []
    )

    temps = hourly.get(
        "temperature_2m",
        []
    )

    codes = hourly.get(
        "weather_code",
        []
    )

    precipitation = hourly.get(
        "precipitation_probability",
        []
    )

    wind = hourly.get(
        "wind_speed_10m",
        []
    )

    wind_dirs = hourly.get(
        "wind_direction_10m",
        []
    )

    if not times:
        return (
            "🕐 **Hourly Forecast**\n\n"
            "No hourly forecast is available."
        )

    now_index = 0

    # Open-Meteo returns local timestamps when ``timezone=auto`` is used.
    # Compare them against the location timezone rather than the host timezone.
    current_time = datetime.now()

    timezone_name = weather.get(
        "timezone"
    )

    if timezone_name:
        try:
            current_time = datetime.now(
                ZoneInfo(
                    str(timezone_name)
                )
            ).replace(
                tzinfo=None
            )

        except Exception:
            pass

    for index, value in enumerate(
        times
    ):

        try:
            dt = datetime.fromisoformat(
                value
            ).replace(
                tzinfo=None
            )

            if dt >= current_time:
                now_index = index
                break

        except Exception:
            continue

    start = now_index

    if day_offset:
        start = min(
            len(times) - 1,
            now_index
            + (
                day_offset * 24
            ),
        )

    end = min(
        len(times),
        start + 12,
    )

    lines = [
        "🕐 **Hourly Forecast**",
        "",
    ]

    for index in range(
        start,
        end,
    ):

        icon, _ = weather_description(
            codes[index]
            if index < len(codes)
            else None
        )

        temp = temperature(
            temps[index]
            if index < len(temps)
            else None,
            unit,
        )

        rain = (
            precipitation[index]
            if index < len(precipitation)
            else None
        )

        wind_speed = fmt_num(
            wind[index]
            if index < len(wind)
            else None,
            0,
        )

        direction = wind_direction(
            wind_dirs[index]
            if index < len(wind_dirs)
            else None
        )

        lines.append(
            f"`{local_time(times[index]):>5}` "
            f"{icon} "
            f"`{temp:>6}` "
            f"🌧 `{fmt_num(rain, 0)}%` "
            f"💨 `{wind_speed} {direction}`"
        )

    return "\n".join(
        lines
    )


def format_daily(
    weather: dict,
    unit: str = "C",
) -> str:

    daily = weather.get(
        "daily",
        {}
    )

    times = daily.get(
        "time",
        []
    )

    codes = daily.get(
        "weather_code",
        []
    )

    highs = daily.get(
        "temperature_2m_max",
        []
    )

    lows = daily.get(
        "temperature_2m_min",
        []
    )

    precipitation = daily.get(
        "precipitation_probability_max",
        []
    )

    precipitation_sum = daily.get(
        "precipitation_sum",
        []
    )

    wind = daily.get(
        "wind_speed_10m_max",
        []
    )

    if not times:
        return (
            "📅 **Forecast**\n\n"
            "No daily forecast is available."
        )

    lines = [
        "📅 **7-Day Forecast**",
        "",
    ]

    for index, date in enumerate(
        times[:7]
    ):

        icon, description = weather_description(
            codes[index]
            if index < len(codes)
            else None
        )

        high = temperature(
            highs[index]
            if index < len(highs)
            else None,
            unit,
        )

        low = temperature(
            lows[index]
            if index < len(lows)
            else None,
            unit,
        )

        rain = (
            precipitation[index]
            if index < len(precipitation)
            else None
        )

        rain_sum = (
            precipitation_sum[index]
            if index < len(precipitation_sum)
            else None
        )

        max_wind = (
            wind[index]
            if index < len(wind)
            else None
        )

        lines.append(
            f"**{local_date(date)}**\n"
            f"{icon} {description}\n"
            f"🌡 `{high} / {low}`  "
            f"🌧 `{fmt_num(rain, 0)}%`  "
            f"💧 `{fmt_num(rain_sum)} mm`  "
            f"💨 `{fmt_num(max_wind, 0)} km/h`"
        )

        if index != len(
            times[:7]
        ) - 1:
            lines.append("")

    return "\n".join(
        lines
    )


def format_air(
    location: dict,
    data: dict,
) -> str:

    current = data.get(
        "current",
        {}
    )

    name = location_title(
        location
    )

    eu_aqi = safe_float(
        current.get(
            "european_aqi"
        )
    )

    us_aqi = safe_float(
        current.get(
            "us_aqi"
        )
    )

    return (
        f"🌫️ **Air Quality — "
        f"{html_escape(name)}**\n\n"

        f"🇪🇺 **European AQI:** "
        f"`{fmt_num(eu_aqi, 0)}` "
        f"{aqi_label(eu_aqi)}\n"

        f"🇺🇸 **US AQI:** "
        f"`{fmt_num(us_aqi, 0)}` "
        f"{us_aqi_label(us_aqi)}\n\n"

        f"🟤 **PM2.5:** "
        f"`{fmt_num(current.get('pm2_5'))} μg/m³`\n"

        f"⚫ **PM10:** "
        f"`{fmt_num(current.get('pm10'))} μg/m³`\n"

        f"🟠 **NO₂:** "
        f"`{fmt_num(current.get('nitrogen_dioxide'))} μg/m³`\n"

        f"🔵 **O₃:** "
        f"`{fmt_num(current.get('ozone'))} μg/m³`\n"

        f"🟡 **SO₂:** "
        f"`{fmt_num(current.get('sulphur_dioxide'))} μg/m³`\n"

        f"⚫ **CO:** "
        f"`{fmt_num(current.get('carbon_monoxide'))} μg/m³`"
    )



def parse_callback_unit(payload: str) -> str:
    """Extract C/F from callback payload like '0:C' or '12p34_-56p78:F'."""
    if not payload:
        return "C"
    unit = payload.rsplit(":", 1)[-1].strip().upper()
    return unit if unit in {"C", "F"} else "C"

# ============================================================================
# BUTTON BUILDERS
# ============================================================================

def current_buttons(
    location_id: str,
    unit: str,
    owner_id: int,
):

    return [
        [
            Button.inline(
                "🕐 Hourly",
                data=(
                    f"wth:h:{owner_id}:"
                    f"{location_id}:{unit}"
                ),
            ),
            Button.inline(
                "📅 Forecast",
                data=(
                    f"wth:d:{owner_id}:"
                    f"{location_id}:{unit}"
                ),
            ),
        ],
        [
            Button.inline(
                "🌫 Air Quality",
                data=(
                    f"wth:a:{owner_id}:"
                    f"{location_id}:{unit}"
                ),
            ),
        ],
        [
            Button.inline(
                ("🌡 °C ✅" if str(unit).upper() == "C" else "🌡 °C"),
                data=(
                    f"wth:u:{owner_id}:"
                    f"{location_id}:C"
                ),
            ),
            Button.inline(
                ("°F ✅" if str(unit).upper() == "F" else "°F"),
                data=(
                    f"wth:u:{owner_id}:"
                    f"{location_id}:F"
                ),
            ),
            Button.inline(
                "🔄 Refresh",
                data=(
                    f"wth:r:{owner_id}:"
                    f"{location_id}:{unit}"
                ),
            ),
        ],
        [
            Button.switch_inline(
                "📍 Change Location",
                query="weather ",
                same_peer=True,
            ),
        ],
    ]


def subpage_buttons(
    location_id: str,
    unit: str,
    owner_id: int,
    page: str,
):

    return [
        [
            Button.inline(
                "🌤 Current",
                data=(
                    f"wth:c:{owner_id}:"
                    f"{location_id}:{unit}"
                ),
            ),
            Button.inline(
                "🕐 Hourly",
                data=(
                    f"wth:h:{owner_id}:"
                    f"{location_id}:{unit}"
                ),
            ),
            Button.inline(
                "📅 Daily",
                data=(
                    f"wth:d:{owner_id}:"
                    f"{location_id}:{unit}"
                ),
            ),
        ],
        [
            Button.inline(
                "🌫 Air Quality",
                data=(
                    f"wth:a:{owner_id}:"
                    f"{location_id}:{unit}"
                ),
            ),
            Button.inline(
                "🔄 Refresh",
                data=(
                    f"wth:r:{owner_id}:"
                    f"{location_id}:{unit}"
                ),
            ),
        ],
        [
            Button.switch_inline(
                "📍 Change Location",
                query="weather ",
                same_peer=True,
            ),
        ],
    ]


def search_buttons(
    results: List[dict],
    owner_id: int,
):

    buttons = []

    for index, location in enumerate(
        results[:6]
    ):

        title = location_title(
            location
        )

        buttons.append(
            [
                Button.inline(
                    f"📍 {clean_text(title, 45)}",
                    data=(
                        f"wth:s:{owner_id}:"
                        f"{index}"
                    ),
                )
            ]
        )

    buttons.append(
        [
            Button.switch_inline(
                "🔎 New Search",
                query="weather ",
                same_peer=True,
            )
        ]
    )

    return buttons


# ============================================================================
# INLINE HELP
# ============================================================================

INLINE_HELP = (
    "🌤 **Weather**\n\n"
    "Search for a city to get weather information.\n\n"
    "Examples:\n"
    "`weather Paris`\n"
    "`weather Tehran`\n"
    "`weather London`\n"
    "`weather New York`\n\n"
    "You can then open:\n"
    "• Current weather\n"
    "• Hourly forecast\n"
    "• 7-day forecast\n"
    "• Air quality\n"
    "• Celsius / Fahrenheit"
)


# ============================================================================
# INLINE SESSION DATA
# ============================================================================

# IMPORTANT:
# This data belongs ONLY to inline queries.
#
# Commands never read or modify this structure.
#
# Key:
#     user_id
#
# Value:
#     {
#         "results": [...]
#     }
#
# A small TTL prevents stale sessions from living forever.

_INLINE_SESSIONS: Dict[
    int,
    Tuple[float, List[dict]]
] = {}

INLINE_SESSION_TTL = 15 * 60


def save_inline_session(
    user_id: int,
    results: List[dict],
) -> None:

    _INLINE_SESSIONS[
        user_id
    ] = (
        time.time(),
        results,
    )


def get_inline_session(
    user_id: int,
) -> List[dict]:

    session = _INLINE_SESSIONS.get(
        user_id
    )

    if not session:
        return []

    created, results = session

    if (
        time.time() - created
        > INLINE_SESSION_TTL
    ):

        _INLINE_SESSIONS.pop(
            user_id,
            None,
        )

        return []

    return results


# ============================================================================
# INLINE QUERY
# ============================================================================

@in_pattern(
    r"(?i)^weather(?:\s+(.+))?$",
)
async def weather_inline(
    event,
):

    user_id = event.sender_id

    query = ""

    try:
        query = (
            event.pattern_match.group(1)
            or ""
        ).strip()

    except Exception:
        query = ""

    if not query:

        article = event.builder.article(
            "🌤 Weather",
            text=INLINE_HELP,
        )

        return await event.answer(
            [article],
            cache_time=3,
        )

    try:

        results = await geocode(
            query
        )

    except Exception as exc:

        article = event.builder.article(
            "❌ Weather",
            text=(
                "❌ **Unable to search "
                "for this location.**\n\n"
                f"`{clean_text(exc, 220)}`"
            ),
        )

        return await event.answer(
            [article],
            cache_time=0,
        )

    if not results:

        article = event.builder.article(
            "🔎 No location found",
            text=(
                "🔎 **No location was found.**\n\n"
                f"Search: `{html_escape(query, 100)}`\n\n"
                "Try a more specific city name."
            ),
        )

        return await event.answer(
            [article],
            cache_time=5,
        )

    save_inline_session(
        user_id,
        results,
    )

    articles = []

    for index, location in enumerate(
        results[:MAX_INLINE_RESULTS]
    ):

        title = location_title(
            location
        )

        country_code = (
            location.get(
                "country_code"
            )
            or ""
        ).upper()

        latitude = fmt_num(
            location.get(
                "latitude"
            ),
            4,
        )

        longitude = fmt_num(
            location.get(
                "longitude"
            ),
            4,
        )

        description = (
            f"{country_code} • "
            f"{latitude}, {longitude}"
        )

        articles.append(
            event.builder.article(
                f"📍 {title}",
                text=(
                    "📍 **Location selected**\n\n"
                    f"**{html_escape(title)}**\n\n"
                    f"Coordinates: "
                    f"`{latitude}, {longitude}`\n\n"
                    "Tap **Get Weather** below."
                ),
                buttons=[
                    [
                        Button.inline(
                            "🌤 Get Weather",
                            data=(
                                f"wth:s:"
                                f"{user_id}:"
                                f"{index}"
                            ),
                        )
                    ]
                ],
                description=description,
            )
        )

    return await event.answer(
        articles,
        cache_time=5,
        gallery=False,
    )


# ============================================================================
# INLINE CALLBACK ROUTER
# ============================================================================

@callback(
    re.compile(
        rb"^wth:"
        rb"(s|c|h|d|a|u|r):"
        rb"(\d+):"
        rb"(.+)$"
    )
)
async def weather_callback(
    event,
):

    try:

        action = (
            event.data_match.group(1)
            .decode()
        )

        owner_id = int(
            event.data_match.group(2)
        )

        payload = (
            event.data_match.group(3)
            .decode()
        )

    except Exception:

        return await event.answer(
            "Invalid weather request.",
            alert=True,
        )

    # ------------------------------------------------------------------------
    # SECURITY
    # ------------------------------------------------------------------------

    if event.sender_id != owner_id:

        return await event.answer(
            "This weather panel belongs to another user.",
            alert=True,
        )

    # ------------------------------------------------------------------------
    # LOCATION SELECTION
    # ------------------------------------------------------------------------

    if action == "s":

        try:
            index = int(
                payload
            )

        except ValueError:

            return await event.answer(
                "Invalid location.",
                alert=True,
            )

        results = get_inline_session(
            owner_id
        )

        if (
            not results
            or index < 0
            or index >= len(results)
        ):

            return await event.answer(
                "This search has expired. Please search again.",
                alert=True,
            )

        location = results[index]

        try:

            weather = await fetch_weather(
                location
            )

        except Exception as exc:

            return await event.edit(
                (
                    "❌ **Unable to retrieve weather.**\n\n"
                    f"`{clean_text(exc, 250)}`"
                ),
                buttons=[
                    [
                        Button.switch_inline(
                            "🔎 Search Again",
                            query="weather ",
                            same_peer=True,
                        )
                    ]
                ],
            )

        unit = "C"

        # Use coordinates as an encoded location ID.
        location_id = (
            f"{safe_float(location.get('latitude')):.4f},"
            f"{safe_float(location.get('longitude')):.4f}"
        )

        # Telegram callback data is byte-limited.
        # Coordinates are intentionally compact.
        location_id = (
            location_id
            .replace(
                ".",
                "p"
            )
            .replace(
                ",",
                "_"
            )
        )

        # Reconstructable coordinate payload.
        # Save actual location in the user's inline session.
        save_inline_session(
            owner_id,
            [location],
        )

        text = format_current(
            location,
            weather,
            unit,
        )

        return await event.edit(
            text,
            buttons=current_buttons(
                "0",
                unit,
                owner_id,
            ),
            link_preview=False,
        )

    # ------------------------------------------------------------------------
    # OTHER ACTIONS
    # ------------------------------------------------------------------------

    # Current selected location is kept in the inline session.
    locations = get_inline_session(
        owner_id
    )

    if not locations:

        return await event.answer(
            "This weather panel has expired.",
            alert=True,
        )

    # After a location has been selected,
    # the first entry is always the active location.
    location = locations[0]

    # ------------------------------------------------------------------------
    # UNIT
    # ------------------------------------------------------------------------

    if action == "u":

        unit = parse_callback_unit(payload)

        try:

            weather = await fetch_weather(
                location
            )

        except Exception as exc:

            return await event.answer(
                clean_text(
                    exc,
                    220,
                ),
                alert=True,
            )

        text = format_current(
            location,
            weather,
            unit,
        )

        return await event.edit(
            text,
            buttons=current_buttons(
                "0",
                unit,
                owner_id,
            ),
            link_preview=False,
        )

    # ------------------------------------------------------------------------
    # REFRESH
    # ------------------------------------------------------------------------

    if action == "r":

        # Force-refresh only this coordinate.
        latitude = safe_float(
            location.get(
                "latitude"
            )
        )

        longitude = safe_float(
            location.get(
                "longitude"
            )
        )

        cache_key = (
            f"{latitude:.4f}:"
            f"{longitude:.4f}"
        )

        _WEATHER_CACHE.pop(
            cache_key,
            None,
        )

        try:

            weather = await fetch_weather(
                location
            )

        except Exception as exc:

            return await event.answer(
                clean_text(
                    exc,
                    220,
                ),
                alert=True,
            )

        unit = parse_callback_unit(payload)

        text = format_current(
            location,
            weather,
            unit,
        )

        await event.edit(
            text,
            buttons=current_buttons(
                "0",
                unit,
                owner_id,
            ),
            link_preview=False,
        )

        return await event.answer(
            "Weather updated.",
            alert=False,
        )

    # ------------------------------------------------------------------------
    # FETCH WEATHER
    # ------------------------------------------------------------------------

    try:

        weather = await fetch_weather(
            location
        )

    except Exception as exc:

        return await event.answer(
            clean_text(
                exc,
                220,
            ),
            alert=True,
        )

    # ------------------------------------------------------------------------
    # CURRENT
    # ------------------------------------------------------------------------

    if action == "c":

        unit = parse_callback_unit(payload)

        return await event.edit(
            format_current(
                location,
                weather,
                unit,
            ),
            buttons=current_buttons(
                "0",
                unit,
                owner_id,
            ),
            link_preview=False,
        )

    # ------------------------------------------------------------------------
    # HOURLY
    # ------------------------------------------------------------------------

    if action == "h":

        unit = parse_callback_unit(payload)

        return await event.edit(
            format_hourly(
                weather,
                unit,
            ),
            buttons=subpage_buttons(
                "0",
                unit,
                owner_id,
                "h",
            ),
            link_preview=False,
        )

    # ------------------------------------------------------------------------
    # DAILY
    # ------------------------------------------------------------------------

    if action == "d":

        unit = parse_callback_unit(payload)

        return await event.edit(
            format_daily(
                weather,
                unit,
            ),
            buttons=subpage_buttons(
                "0",
                unit,
                owner_id,
                "d",
            ),
            link_preview=False,
        )

    # ------------------------------------------------------------------------
    # AIR QUALITY
    # ------------------------------------------------------------------------

    if action == "a":

        unit = parse_callback_unit(payload)

        try:

            air = await fetch_air_quality(
                location
            )

        except Exception as exc:

            return await event.edit(
                (
                    "🌫️ **Air Quality**\n\n"
                    "Unable to retrieve air quality data.\n\n"
                    f"`{clean_text(exc, 220)}`"
                ),
                buttons=subpage_buttons(
                    "0",
                    unit,
                    owner_id,
                    "a",
                ),
            )

        return await event.edit(
            format_air(
                location,
                air,
            ),
            buttons=subpage_buttons(
                "0",
                unit,
                owner_id,
                "a",
            ),
            link_preview=False,
        )

    return await event.answer(
        "Unknown weather action.",
        alert=True,
    )


# ============================================================================
# COMMAND LAYER
# ============================================================================
#
# IMPORTANT:
# This section does NOT call:
#
#     asst.inline_query(...)
#
# and does NOT use:
#
#     _INLINE_SESSIONS
#
# Therefore the command implementation is completely independent
# from the inline implementation.
# ============================================================================


def command_usage() -> str:

    return (
        "🌤 **Weather**\n\n"
        "**Usage:**\n"
        "`.weather <city>`\n\n"
        "**Examples:**\n"
        "`.weather Paris`\n"
        "`.weather Tehran`\n"
        "`.weather London`\n\n"
        "For air quality:\n"
        "`.air <city>`"
    )


@heartless_cmd(
    pattern=r"weather ?(.*)"
)
async def weather_command(
    event,
):

    if event.fwd_from:
        return

    query = ""

    try:

        query = (
            event.pattern_match.group(1)
            or ""
        ).strip()

    except Exception:
        query = ""

    if not query:

        return await event.eor(
            command_usage(),
            time=8,
        )

    msg = await event.eor(
        "🌤 `Searching location...`"
    )

    try:

        locations = await geocode(
            query
        )

        if not locations:

            return await msg.edit(
                (
                    "❌ **Location not found.**\n\n"
                    f"Search: `{html_escape(query, 100)}`"
                )
            )

        location = locations[0]

        weather = await fetch_weather(
            location
        )

        text = format_current(
            location,
            weather,
            "C",
        )

        text += (
            "\n\n"
            "💡 **More:** "
            "`.air <city>` for air quality."
        )

        return await msg.edit(
            text,
            link_preview=False,
        )

    except Exception as exc:

        return await msg.edit(
            (
                "❌ **Weather request failed.**\n\n"
                f"`{clean_text(exc, 300)}`"
            )
        )


# ============================================================================
# AIR COMMAND
# ============================================================================
#
# Kept for compatibility with the old plugin:
#
#     .air <city>
#
# This is a completely independent command handler.
# ============================================================================


@heartless_cmd(
    pattern=r"air ?(.*)"
)
async def air_command(
    event,
):

    if event.fwd_from:
        return

    query = ""

    try:

        query = (
            event.pattern_match.group(1)
            or ""
        ).strip()

    except Exception:
        query = ""

    if not query:

        return await event.eor(
            (
                "🌫️ **Air Quality**\n\n"
                "Usage:\n"
                "`.air <city>`\n\n"
                "Example:\n"
                "`.air Paris`"
            ),
            time=8,
        )

    msg = await event.eor(
        "🌫️ `Searching air quality...`"
    )

    try:

        locations = await geocode(
            query
        )

        if not locations:

            return await msg.edit(
                (
                    "❌ **Location not found.**\n\n"
                    f"Search: `{html_escape(query, 100)}`"
                )
            )

        location = locations[0]

        air = await fetch_air_quality(
            location
        )

        return await msg.edit(
            format_air(
                location,
                air,
            ),
            link_preview=False,
        )

    except Exception as exc:

        return await msg.edit(
            (
                "❌ **Air quality request failed.**\n\n"
                f"`{clean_text(exc, 300)}`"
            )
        )


# ============================================================================
# CLEANUP
# ============================================================================

def cleanup_weather_caches() -> None:
    """
    Optional lightweight cleanup.

    The plugin doesn't start a permanent background task because
    the project loader may reload plugins dynamically.

    This function can be called by a future global cleanup mechanism.
    """

    now = time.time()

    for cache, ttl in (
        (
            _GEOCODE_CACHE,
            GEOCODE_CACHE_TTL,
        ),
        (
            _WEATHER_CACHE,
            WEATHER_CACHE_TTL * 2,
        ),
        (
            _AIR_CACHE,
            AIR_CACHE_TTL * 2,
        ),
    ):

        expired = [
            key
            for key, value in cache.items()
            if now - value[0] > ttl
        ]

        for key in expired:

            cache.pop(
                key,
                None,
            )

    expired_sessions = [
        key
        for key, value in _INLINE_SESSIONS.items()
        if now - value[0] > INLINE_SESSION_TTL
    ]

    for key in expired_sessions:

        _INLINE_SESSIONS.pop(
            key,
            None,
)

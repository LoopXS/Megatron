"""
🌍 Time — Global Timezone Inline Plugin
=======================================

Inline usage
------------

@AssisXBot time Tehran
@AssisXBot time Iran
@AssisXBot time Chicago
@AssisXBot time New York
@AssisXBot time Tehran vs Chicago
@AssisXBot time Tehran | Tokyo

Features
--------

• Global city / country lookup.
• IANA timezone support (e.g. Europe/Tehran, America/Chicago).
• Exact local time with DST-aware UTC offset.
• Time difference between two locations.
• "Search Again" inline button under every result.
• "Compare" button for quick two-location comparison.
• Short-lived in-memory caches to reduce API traffic.
• No API key required.
• Uses the project's existing `async_searcher` and `in_pattern`
  infrastructure; it does not create a second Telegram inline client.

The geocoding provider is Open-Meteo. Its public geocoding API returns
IANA timezone names for locations and is suitable for non-commercial use
without an API key.
"""

from __future__ import annotations

import html
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote
from zoneinfo import ZoneInfo

from telethon import Button

from . import LOGS, async_searcher
from CythonX._misc._assistant import in_pattern


# ============================================================================
# CONSTANTS
# ============================================================================

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# Used only for country-name queries, so we can resolve a country to its
# capital instead of accidentally selecting an unrelated city with the same
# name. No API key is required.
COUNTRY_URL = "https://restcountries.com/v3.1/name/{name}"

CACHE_TTL = 600
MAX_QUERY_LENGTH = 100
MAX_RESULTS = 5

_GEOCODE_CACHE: Dict[str, Tuple[float, List[dict]]] = {}
_COUNTRY_CACHE: Dict[str, Tuple[float, List[dict]]] = {}


# ============================================================================
# SMALL, SAFE HELPERS
# ============================================================================

def _clean(value: object, limit: int = 160) -> str:
    """Return a bounded, single-line Telegram-safe string."""
    if value is None:
        return ""

    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)

    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"

    return text


def _esc(value: object, limit: int = 160) -> str:
    """Escape text for Telegram HTML parse mode."""
    return html.escape(_clean(value, limit), quote=False)


def _fmt_offset(seconds: int) -> str:
    """Format a UTC offset as UTC±HH:MM."""
    sign = "+" if seconds >= 0 else "-"
    seconds = abs(int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def _ordinal_offset(seconds: int) -> str:
    """Human-readable offset used in comparison output."""
    if seconds == 0:
        return "same time"

    minutes = abs(seconds) // 60
    hours, minutes = divmod(minutes, 60)

    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")

    return " ".join(parts)


def _timezone_display_name(
    zone_name: str,
    abbreviation: str,
    country: str,
) -> str:
    """
    Produce a readable timezone name.

    Python's zoneinfo exposes the timezone abbreviation rather than a
    localized long name. Common abbreviations are expanded here; other
    zones use the country name as a stable fallback.
    """
    names = {
        "EST": "Eastern Standard Time",
        "EDT": "Eastern Daylight Time",
        "CST": "Central Standard Time",
        "CDT": "Central Daylight Time",
        "MST": "Mountain Standard Time",
        "MDT": "Mountain Daylight Time",
        "PST": "Pacific Standard Time",
        "PDT": "Pacific Daylight Time",
        "AKST": "Alaska Standard Time",
        "AKDT": "Alaska Daylight Time",
        "HST": "Hawaii Standard Time",
        "GMT": "Greenwich Mean Time",
        "BST": "British Summer Time",
        "CET": "Central European Time",
        "CEST": "Central European Summer Time",
        "EET": "Eastern European Time",
        "EEST": "Eastern European Summer Time",
        "WET": "Western European Time",
        "WEST": "Western European Summer Time",
        "IST": (
            "India Standard Time"
            if country.casefold() == "india"
            else "Irish Standard Time"
        ),
        "JST": "Japan Standard Time",
        "KST": "Korea Standard Time",
        "AEST": "Australian Eastern Standard Time",
        "AEDT": "Australian Eastern Daylight Time",
        "ACST": "Australian Central Standard Time",
        "ACDT": "Australian Central Daylight Time",
        "AWST": "Australian Western Standard Time",
        "NZST": "New Zealand Standard Time",
        "NZDT": "New Zealand Daylight Time",
    }

    if abbreviation in names:
        return names[abbreviation]

    if country:
        return f"{_clean(country, 60)} Time"

    leaf = zone_name.rsplit("/", 1)[-1].replace("_", " ")
    return f"{leaf} Time"


def _location_label(location: dict) -> str:
    """Build 'City, Admin, Country' without duplicated fields."""
    parts: List[str] = []

    for key in ("name", "admin1", "country"):
        value = _clean(location.get(key), 70)
        if value and value not in parts:
            parts.append(value)

    return ", ".join(parts)


def _location_title(location: dict) -> str:
    """Build a compact city/country title."""
    city = _clean(location.get("name"), 60)
    country = _clean(
        location.get("_queried_country") or location.get("country"),
        60,
    )

    if city and country:
        return f"{country} ({city})"

    return city or country or "Unknown Location"


def _is_expired(
    entry: Optional[Tuple[float, object]],
    ttl: int,
) -> bool:
    return not entry or (time.time() - entry[0] >= ttl)


# ============================================================================
# LOCATION LOOKUP
# ============================================================================

async def _geocode(query: str) -> List[dict]:
    """
    Resolve a city/place to an Open-Meteo location.

    Open-Meteo returns an IANA timezone directly, so no fragile longitude
    or manually calculated UTC-offset logic is required.
    """
    query = _clean(query, MAX_QUERY_LENGTH).strip()
    if not query:
        return []

    # Open-Meteo accepts comma-qualified names. Normalize natural input such
    # as "Chicago (United States)" / "United States (Chicago)" first.
    paren = re.fullmatch(r"(.+?)\s*\(([^()]+)\)", query)
    if paren:
        left = paren.group(1).strip()
        right = paren.group(2).strip()
        if left and right:
            query = f"{left}, {right}"

    key = query.casefold()
    cached = _GEOCODE_CACHE.get(key)

    if not _is_expired(cached, CACHE_TTL):
        return cached[1]

    data = await async_searcher(
        GEOCODING_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "Megatron-Time-Plugin/1.0",
        },
        re_json=True,
        params={
            "name": query,
            "count": MAX_RESULTS,
            "language": "en",
            "format": "json",
        },
    )

    results = data.get("results") if isinstance(data, dict) else []

    if not isinstance(results, list):
        results = []

    results = [
        item
        for item in results
        if isinstance(item, dict)
        and item.get("timezone")
        and item.get("name")
    ]

    _GEOCODE_CACHE[key] = (time.time(), results)
    return results


async def _country_capital(country_query: str) -> List[dict]:
    """
    Resolve a country name to its capital.

    Country lookup is a second-stage resolver. Normal city searches remain
    entirely handled by Open-Meteo.
    """
    query = _clean(country_query, MAX_QUERY_LENGTH).strip()
    if not query:
        return []

    key = query.casefold()
    cached = _COUNTRY_CACHE.get(key)

    if not _is_expired(cached, CACHE_TTL):
        return cached[1]

    url = COUNTRY_URL.format(name=quote(query, safe=""))

    try:
        data = await async_searcher(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Megatron-Time-Plugin/1.0",
            },
            re_json=True,
        )
    except Exception:
        _COUNTRY_CACHE[key] = (time.time(), [])
        return []

    if not isinstance(data, list):
        data = []

    candidates: List[dict] = []

    for country in data[:5]:
        if not isinstance(country, dict):
            continue

        capitals = country.get("capital")
        if not isinstance(capitals, list):
            continue

        country_name = country.get("name") or {}
        if not isinstance(country_name, dict):
            country_name = {}

        for capital in capitals[:2]:
            capital = _clean(capital, 80)

            if not capital:
                continue

            candidates.append(
                {
                    "capital": capital,
                    "country": _clean(
                        country_name.get("common"),
                        80,
                    ),
                }
            )

    _COUNTRY_CACHE[key] = (time.time(), candidates)
    return candidates


async def resolve_locations(query: str) -> List[dict]:
    """
    Resolve a user query.

    Priority:
      1. Direct IANA timezone.
      2. Country -> capital.
      3. Normal global geocoding.
    """
    query = _clean(query, MAX_QUERY_LENGTH).strip()

    if not query:
        return []

    # Advanced users can enter an IANA timezone directly.
    #
    # Important: zoneinfo contains legacy aliases such as ``Iran`` and
    # ``US/Eastern``. A bare country name must therefore be allowed to reach
    # the country resolver first. Slash-based IANA names are unambiguous.
    is_explicit_timezone = (
        "/" in query
        or query.upper() in {"UTC", "GMT", "UCT", "GMT0"}
    )

    if is_explicit_timezone:
        try:
            ZoneInfo(query)

            return [
                {
                    "name": query.rsplit("/", 1)[-1].replace("_", " "),
                    "admin1": "",
                    "country": "",
                    "timezone": query,
                    "country_code": "",
                    "latitude": None,
                    "longitude": None,
                    "_direct_timezone": True,
                }
            ]
        except Exception:
            pass

    country_candidates = await _country_capital(query)

    if country_candidates:
        resolved: List[dict] = []

        for item in country_candidates[:3]:
            locations = await _geocode(item["capital"])

            for location in locations:
                location = dict(location)

                if item["country"]:
                    location["_queried_country"] = item["country"]

                resolved.append(location)
                break

        if resolved:
            return resolved

    return await _geocode(query)


# ============================================================================
# TIME CALCULATION
# ============================================================================

def _now_for_location(location: dict) -> Tuple[datetime, str, str]:
    """
    Return local datetime, timezone abbreviation and long display name.

    ZoneInfo handles DST transitions and current UTC offsets using the
    operating system's IANA tzdata.
    """
    zone_name = _clean(location.get("timezone"), 100)

    if not zone_name:
        raise ValueError("Location has no timezone.")

    zone = ZoneInfo(zone_name)
    now = datetime.now(zone)

    country = _clean(
        location.get("_queried_country") or location.get("country"),
        80,
    )

    abbreviation = now.tzname() or zone_name

    long_name = _timezone_display_name(
        zone_name,
        abbreviation,
        country,
    )

    return now, abbreviation, long_name


def _format_single(location: dict) -> str:
    now, abbreviation, long_name = _now_for_location(location)

    title = _location_title(location)
    label = _location_label(location)
    zone_name = _clean(location.get("timezone"), 100)

    offset = now.utcoffset()
    offset_seconds = int(offset.total_seconds()) if offset else 0

    country = _clean(
        location.get("_queried_country") or location.get("country"),
        80,
    )

    if location.get("_direct_timezone"):
        label = zone_name
        title = zone_name

    # datetime.strftime("%-d") is Linux-specific.  This project is deployed
    # on Linux, but using day as an integer keeps the formatter portable too.
    date_text = (
        f"{now.strftime('%A, %B')} "
        f"{now.day}, {now.year}"
    )

    return (
        f"🌍 <b>{_esc(title)} Time</b> 🌎\n\n"
        f"🕓 <b>{now.strftime('%I:%M:%S %p')}</b> "
        f"<i>{_esc(long_name)}</i>\n"
        f"📆 <b>{_esc(date_text)}</b>\n\n"
        f"🗺️ <b>Timezone:</b> <code>{_esc(zone_name, 100)}</code>\n"
        f"⏱️ <b>Zone:</b> <code>{_esc(abbreviation, 30)}</code> · "
        f"<code>{_fmt_offset(offset_seconds)}</code>\n"
        f"📍 <b>Location:</b> {_esc(label or title, 150)}"
        + (
            f"\n🏳️ <b>Country:</b> {_esc(country, 80)}"
            if country
            else ""
        )
    )


def _format_comparison(first: dict, second: dict) -> str:
    first_now, first_abbr, first_long = _now_for_location(first)
    second_now, second_abbr, second_long = _now_for_location(second)

    first_title = _location_title(first)
    second_title = _location_title(second)

    first_zone = _clean(first.get("timezone"), 100)
    second_zone = _clean(second.get("timezone"), 100)

    first_delta = first_now.utcoffset()
    second_delta = second_now.utcoffset()

    first_offset = int(first_delta.total_seconds()) if first_delta is not None else 0
    second_offset = int(second_delta.total_seconds()) if second_delta is not None else 0

    difference = second_offset - first_offset

    if difference > 0:
        relation = (
            f"{_esc(second_title)} is "
            f"<b>{_ordinal_offset(difference)}</b> ahead of "
            f"{_esc(first_title)}."
        )
    elif difference < 0:
        relation = (
            f"{_esc(second_title)} is "
            f"<b>{_ordinal_offset(difference)}</b> behind "
            f"{_esc(first_title)}."
        )
    else:
        relation = "Both locations are in the <b>same current UTC offset</b>."

    return (
        "🌐 <b>Time Zone Comparison</b>\n\n"
        f"📍 <b>{_esc(first_title)}</b>\n"
        f"🕓 <code>{first_now.strftime('%I:%M:%S %p')}</code> · "
        f"<i>{_esc(first_long)}</i>\n"
        f"🗺️ <code>{_esc(first_zone)}</code> · "
        f"<code>{_esc(first_abbr)}</code> · "
        f"<code>{_fmt_offset(first_offset)}</code>\n\n"
        f"📍 <b>{_esc(second_title)}</b>\n"
        f"🕓 <code>{second_now.strftime('%I:%M:%S %p')}</code> · "
        f"<i>{_esc(second_long)}</i>\n"
        f"🗺️ <code>{_esc(second_zone)}</code> · "
        f"<code>{_esc(second_abbr)}</code> · "
        f"<code>{_fmt_offset(second_offset)}</code>\n\n"
        f"↔️ {relation}\n"
        f"⏱️ <b>Difference:</b> <code>{_ordinal_offset(difference)}</code>"
    )


# ============================================================================
# QUERY PARSING
# ============================================================================

def _parse_query(query: str) -> Tuple[str, Optional[str]]:
    """
    Supported comparison syntax:

      time Tehran vs Chicago
      time Tehran | Chicago
      time Tehran <> Chicago
      time Tehran -> Chicago
      time diff Tehran | Chicago
      time compare London and Dubai
    """
    query = _clean(query, MAX_QUERY_LENGTH).strip()

    if not query:
        return "", None

    query = re.sub(
        r"^(?:diff|difference|compare)\s+",
        "",
        query,
        flags=re.IGNORECASE,
    ).strip()

    separators = (
        r"\s+(?:vs\.?|versus|to|and)\s+",
        r"\s*(?:\||<>|->|—|–)\s*",
    )

    for separator in separators:
        parts = re.split(
            separator,
            query,
            maxsplit=1,
            flags=re.IGNORECASE,
        )

        if len(parts) == 2:
            first = parts[0].strip()
            second = parts[1].strip()

            if first and second:
                return first, second

    return query, None


# ============================================================================
# INLINE UI
# ============================================================================

async def _help_result(event):
    return await event.builder.article(
        title="🌍 Global Time",
        description="Search the current local time anywhere in the world.",
        text=(
            "🌍 <b>Global Time</b>\n\n"
            "Search a city, country or IANA timezone.\n\n"
            "<b>Examples:</b>\n"
            "• <code>time Tehran</code>\n"
            "• <code>time Iran</code>\n"
            "• <code>time Chicago</code>\n"
            "• <code>time New York</code>\n"
            "• <code>time Asia/Tehran</code>\n\n"
            "<b>Compare two locations:</b>\n"
            "• <code>time Tehran vs Chicago</code>\n"
            "• <code>time Tehran | Tokyo</code>\n"
            "• <code>time diff London and Dubai</code>\n\n"
            "The result is calculated with the IANA timezone database and "
            "is DST-aware."
        ),
        parse_mode="html",
        buttons=[
            [
                Button.switch_inline(
                    "🔎 Search Again",
                    query="time ",
                    same_peer=True,
                ),
                Button.switch_inline(
                    "↔️ Compare",
                    query="time diff ",
                    same_peer=True,
                ),
            ]
        ],
    )


async def _error_result(event, query: str, message: str):
    return await event.builder.article(
        title="❌ Time Search",
        description=message,
        text=(
            "❌ <b>Time lookup failed</b>\n\n"
            f"🔎 <b>Search:</b> <code>{_esc(query, 100)}</code>\n\n"
            f"{_esc(message, 300)}\n\n"
            "Try a city, country, or IANA timezone such as "
            "<code>Europe/London</code>."
        ),
        parse_mode="html",
        buttons=[
            [
                Button.switch_inline(
                    "🔎 Search Again",
                    query="time ",
                    same_peer=True,
                )
            ]
        ],
    )


def _single_buttons(location: dict):
    title = _location_title(location)

    return [
        [
            Button.switch_inline(
                "🔎 Search Again",
                query="time ",
                same_peer=True,
            ),
            Button.switch_inline(
                "↔️ Compare",
                query=f"time diff {title} | ",
                same_peer=True,
            ),
        ],
        [
            Button.switch_inline(
                "📍 Search This Place",
                query=f"time {title}",
                same_peer=True,
            ),
        ],
    ]


def _compare_buttons(first: str, second: str):
    return [
        [
            Button.switch_inline(
                "🔎 New Search",
                query="time ",
                same_peer=True,
            ),
            Button.switch_inline(
                "↔️ Compare Again",
                query="time diff ",
                same_peer=True,
            ),
        ],
        [
            Button.switch_inline(
                "🔁 Reverse",
                query=f"time diff {second} | {first}",
                same_peer=True,
            ),
        ],
    ]


async def _candidate_results(event, locations: List[dict]):
    results = []

    for location in locations[:MAX_RESULTS]:
        try:
            now, abbreviation, _ = _now_for_location(location)

            title = _location_title(location)

            offset = now.utcoffset()
            seconds = int(offset.total_seconds()) if offset else 0

            results.append(
                await event.builder.article(
                    title=f"🌍 {title}",
                    description=(
                        f"{now.strftime('%I:%M:%S %p')} · "
                        f"{abbreviation} · {_fmt_offset(seconds)}"
                    ),
                    text=_format_single(location),
                    parse_mode="html",
                    buttons=_single_buttons(location),
                )
            )
        except Exception:
            continue

    return results


# ============================================================================
# INLINE HANDLER
# ============================================================================

@in_pattern(
    r"(?i)^time(?:\s+(.+))?$",
)
async def time_inline(event):
    """
    Main inline entry point.

    No callback session or mutable per-user Telegram state is used.
    Each inline result is self-contained.
    """
    try:
        raw = event.text or ""

        match = re.match(
            r"(?i)^time(?:\s+(.+))?$",
            raw.strip(),
        )

        query = (
            match.group(1).strip()
            if match and match.group(1)
            else ""
        )

        if not query:
            return await event.answer(
                [await _help_result(event)],
                cache_time=5,
            )

        first_query, second_query = _parse_query(query)

        # ------------------------------------------------------------------
        # TWO-LOCATION COMPARISON
        # ------------------------------------------------------------------

        if second_query:
            first_locations = await resolve_locations(first_query)
            second_locations = await resolve_locations(second_query)

            if not first_locations:
                return await event.answer(
                    [
                        await _error_result(
                            event,
                            first_query,
                            "The first location could not be found.",
                        )
                    ],
                    cache_time=5,
                )

            if not second_locations:
                return await event.answer(
                    [
                        await _error_result(
                            event,
                            second_query,
                            "The second location could not be found.",
                        )
                    ],
                    cache_time=5,
                )

            first = first_locations[0]
            second = second_locations[0]

            result = await event.builder.article(
                title=(
                    f"↔️ {_location_title(first)} "
                    f"↔ {_location_title(second)}"
                ),
                description=(
                    "Compare current local times and UTC offsets."
                ),
                text=_format_comparison(first, second),
                parse_mode="html",
                buttons=_compare_buttons(
                    first_query,
                    second_query,
                ),
            )

            return await event.answer(
                [result],
                cache_time=10,
            )

        # ------------------------------------------------------------------
        # SINGLE LOCATION
        # ------------------------------------------------------------------

        locations = await resolve_locations(first_query)

        if not locations:
            return await event.answer(
                [
                    await _error_result(
                        event,
                        first_query,
                        "No matching city, country or timezone was found.",
                    )
                ],
                cache_time=10,
            )

        results = await _candidate_results(
            event,
            locations,
        )

        if not results:
            return await event.answer(
                [
                    await _error_result(
                        event,
                        first_query,
                        "The returned locations did not contain a valid timezone.",
                    )
                ],
                cache_time=10,
            )

        return await event.answer(
            results,
            cache_time=10,
        )

    except Exception as exc:
        LOGS.exception(
            "time inline plugin failed: %s",
            exc,
        )

        try:
            return await event.answer(
                [
                    await _error_result(
                        event,
                        getattr(event, "text", "time"),
                        "The time service is temporarily unavailable.",
                    )
                ],
                cache_time=5,
            )
        except Exception:
            # The inline query may already have expired.
            return None


# ============================================================================
# CACHE MAINTENANCE
# ============================================================================

def cleanup_time_caches() -> None:
    """Optional cleanup hook for future global plugin maintenance."""
    now = time.time()

    for cache in (_GEOCODE_CACHE, _COUNTRY_CACHE):
        expired = [
            key
            for key, value in cache.items()
            if now - value[0] >= CACHE_TTL
        ]

        for key in expired:
            cache.pop(key, None)

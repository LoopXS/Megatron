"""
🌍 Time — Global Timezone Inline Plugin
=======================================

Inline usage
------------

@AssisXBot time Tehran
@AssisXBot time Iran
@AssisXBot time Chicago
@AssisXBot time New York
@AssisXBot time Asia/Tehran
@AssisXBot time US/Eastern
@AssisXBot time Tehran vs Chicago
@AssisXBot time Tehran | Tokyo
@AssisXBot time compare London and Dubai

Features
--------

• Global city / country lookup.
• IANA timezone support (e.g. Asia/Tehran, America/Chicago),
  including common legacy aliases such as US/Eastern.
• Exact local time with DST-aware UTC offset.
• Time difference between two locations.
• "Search Again" inline button under every result.
• "Compare" button for quick two-location comparison.
• Bounded TTL/LRU caches to reduce API traffic.
• No API key required.
• Uses the project's existing `async_searcher` and `in_pattern`
  infrastructure; it does not create a second Telegram inline client.

The geocoding provider is Open-Meteo. Its public geocoding API returns
IANA timezone names for locations and is suitable for non-commercial use
without an API key. Country names are resolved against the static,
keyless ISO 3166 dataset published as mledoze/countries on GitHub,
which maps every country to its capital(s).
"""

from __future__ import annotations

import html
import re
import time
from collections import OrderedDict
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from . import LOGS, Button, async_searcher, in_pattern


# ============================================================================
# CONSTANTS
# ============================================================================

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# Static country dataset (ISO 3166 names, capitals and alternative
# spellings) used to resolve a country query to its capital. No API
# key is required and the data changes rarely, so it is only fetched
# once a day.
COUNTRIES_DATA_URL = (
    "https://raw.githubusercontent.com/mledoze/countries/master/countries.json"
)
COUNTRY_DATA_TTL = 86400

CACHE_TTL = 600  # successful lookups are cached for 10 minutes
NEGATIVE_TTL = 60  # failed lookups are retried after 1 minute
CACHE_MAX_SIZE = 256  # hard bound on cached entries per cache
MAX_QUERY_LENGTH = 100
MAX_RESULTS = 5
MAX_TITLE_LENGTH = 255  # Telegram inline result title limit
BUTTON_QUERY_LIMIT = 48  # keep switch_inline queries comfortably short


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


# ============================================================================
# TIMEZONE NAMING
# ============================================================================

# Abbreviations that are unambiguous across regions.
_UNAMBIGUOUS_ZONES = {
    "ACDT": "Australian Central Daylight Time",
    "ACST": "Australian Central Standard Time",
    "AEDT": "Australian Eastern Daylight Time",
    "AEST": "Australian Eastern Standard Time",
    "AKDT": "Alaska Daylight Time",
    "AKST": "Alaska Standard Time",
    "ART": "Argentina Standard Time",
    "AWST": "Australian Western Standard Time",
    "AZT": "Azerbaijan Time",
    "BRT": "Brasilia Standard Time",
    "CAT": "Central Africa Time",
    "CEST": "Central European Summer Time",
    "CET": "Central European Time",
    "CLST": "Chile Summer Time",
    "CLT": "Chile Standard Time",
    "CVT": "Cape Verde Time",
    "EAT": "East Africa Time",
    "EDT": "Eastern Daylight Time",
    "EEST": "Eastern European Summer Time",
    "EET": "Eastern European Time",
    "EST": "Eastern Standard Time",
    "GET": "Georgia Standard Time",
    "GMT": "Greenwich Mean Time",
    "GST": "Gulf Standard Time",
    "HKT": "Hong Kong Time",
    "HST": "Hawaii Standard Time",
    "ICT": "Indochina Time",
    "IDT": "Israel Daylight Time",
    "IRST": "Iran Standard Time",
    "JST": "Japan Standard Time",
    "KST": "Korea Standard Time",
    "MDT": "Mountain Daylight Time",
    "MSK": "Moscow Standard Time",
    "MST": "Mountain Standard Time",
    "MYT": "Malaysia Time",
    "NPT": "Nepal Time",
    "NST": "Newfoundland Standard Time",
    "NZDT": "New Zealand Daylight Time",
    "NZST": "New Zealand Standard Time",
    "PDT": "Pacific Daylight Time",
    "PHT": "Philippine Time",
    "PKT": "Pakistan Standard Time",
    "PST": "Pacific Standard Time",
    "SAST": "South Africa Standard Time",
    "SGT": "Singapore Time",
    "UZT": "Uzbekistan Time",
    "WEST": "Western European Summer Time",
    "WET": "Western European Time",
    "WIT": "Western Indonesian Time",
}

# Country/zone hints that identify the Arabian (UTC+3) "AST" zones as
# opposed to the Canadian/Greenlandian Atlantic "AST" zones.
_ARABIA_HINTS = ("saudi", "yemen", "kuwait", "bahrain", "qatar", "iraq", "arabia")

# POSIX-style tznames such as "+0330" are offsets, not abbreviations.
_POSIX_TZNAME = re.compile(r"^[+-]\d{2,4}$")


def _disambiguate(
    abbreviation: str,
    zone_name: str,
    country: str,
) -> Optional[str]:
    """
    Several regions share these abbreviations; pick the right one
    using the country name and the IANA zone as hints.
    """
    country_l = (country or "").casefold()
    zone_l = (zone_name or "").lower()

    if abbreviation == "IST":
        if "india" in country_l or zone_l in {"asia/kolkata", "asia/calcutta"}:
            return "India Standard Time"
        if "israel" in country_l or "jerusalem" in zone_l:
            return "Israel Standard Time"
        return "Irish Standard Time"

    if abbreviation == "BST":
        if "bangladesh" in country_l or "dhaka" in zone_l:
            return "Bangladesh Standard Time"
        if "bhutan" in country_l or "thimphu" in zone_l:
            return "Bhutan Standard Time"
        return "British Summer Time"

    if abbreviation == "CST":
        if "china" in country_l or "shanghai" in zone_l:
            return "China Standard Time"
        if "cuba" in country_l or "havana" in zone_l:
            return "Cuba Standard Time"
        return "Central Standard Time"

    if abbreviation == "CDT":
        if "cuba" in country_l or "havana" in zone_l:
            return "Cuba Daylight Time"
        return "Central Daylight Time"

    if abbreviation == "AST":
        if any(hint in country_l for hint in _ARABIA_HINTS):
            return "Arabia Standard Time"
        return "Atlantic Standard Time"

    if abbreviation == "ADT":
        return "Atlantic Daylight Time"

    if abbreviation == "AMT":
        if "armenia" in country_l or "yerevan" in zone_l:
            return "Armenia Standard Time"
        if "brazil" in country_l or "manaus" in zone_l:
            return "Amazon Time"
        return "Armenia Standard Time"

    return None


def _timezone_display_name(
    zone_name: str,
    abbreviation: Optional[str],
    country: str,
) -> str:
    """
    Produce a readable timezone name.

    Python's zoneinfo exposes the timezone abbreviation rather than a
    localized long name. Common abbreviations are expanded here; other
    zones use the country name as a stable fallback.
    """
    if abbreviation:
        name = _disambiguate(abbreviation, zone_name, country)
        if name:
            return name
        name = _UNAMBIGUOUS_ZONES.get(abbreviation)
        if name:
            return name

    if country:
        return f"{_clean(country, 60)} Time"

    leaf = (zone_name or "").rsplit("/", 1)[-1].replace("_", " ")
    return f"{leaf} Time" if leaf else "Local Time"


def _zone_abbreviation(now: datetime) -> Optional[str]:
    """
    Return the timezone abbreviation, or None when the host's tzdata
    only provides a POSIX-style offset string such as "+0330".
    """
    abbreviation = now.tzname()
    if not abbreviation or _POSIX_TZNAME.match(abbreviation):
        return None
    return abbreviation


def _zone_line(zone_name: str, abbreviation: Optional[str], offset_seconds: int) -> str:
    """Render the timezone/abbreviation/offset block shared by both layouts."""
    if abbreviation:
        return (
            f"🗺️ <code>{_esc(zone_name, 100)}</code> · "
            f"<code>{_esc(abbreviation, 30)}</code> · "
            f"<code>{_fmt_offset(offset_seconds)}</code>"
        )
    return f"🗺️ <code>{_esc(zone_name, 100)}</code> · <code>{_fmt_offset(offset_seconds)}</code>"


def _location_label(location: dict) -> str:
    """Build 'City, Admin, Country' (or the IANA zone) without duplicates."""
    if location.get("_direct_timezone"):
        return _clean(location.get("timezone"), 100)

    parts: list[str] = []

    for key in ("name", "admin1", "country"):
        value = _clean(location.get(key), 70)
        if value and value not in parts:
            parts.append(value)

    return ", ".join(parts)


def _location_title(location: dict) -> str:
    """Build a compact city/country title (or the IANA zone)."""
    if location.get("_direct_timezone"):
        return _clean(location.get("timezone"), 60)

    city = _clean(location.get("name"), 60)
    country = _clean(
        location.get("_queried_country") or location.get("country"),
        60,
    )

    if city and country:
        return f"{country} ({city})"

    return city or country or "Unknown Location"


# ============================================================================
# BOUNDED TTL/LRU CACHE
# ============================================================================


class _TTLCache:
    """
    Bounded TTL cache with LRU eviction.

    The bot runs on a single asyncio loop, so plain dicts are safe
    here; the bound keeps long-running deployments from growing
    without limit as distinct queries accumulate.
    """

    def __init__(self, ttl: int, maxsize: int = CACHE_MAX_SIZE) -> None:
        self._ttl = ttl
        self._maxsize = maxsize
        self._data: OrderedDict[str, tuple[float, object]] = OrderedDict()

    def get(self, key: str) -> Optional[object]:
        entry = self._data.get(key)
        if entry is None:
            return None

        expires_at, value = entry
        if time.time() >= expires_at:
            self._data.pop(key, None)
            return None

        self._data.move_to_end(key)
        return value

    def set(self, key: str, value: object, ttl: Optional[int] = None) -> None:
        self._data[key] = (time.time() + (ttl if ttl is not None else self._ttl), value)
        self._data.move_to_end(key)

        while len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def evict_expired(self) -> None:
        now = time.time()
        expired = [
            key for key, (expires_at, _) in self._data.items() if now >= expires_at
        ]
        for key in expired:
            self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()


_GEOCODE_CACHE = _TTLCache(CACHE_TTL)
_COUNTRY_CACHE = _TTLCache(CACHE_TTL)
_COUNTRY_DATA_CACHE = _TTLCache(COUNTRY_DATA_TTL)


# ============================================================================
# LOCATION LOOKUP
# ============================================================================

# Legacy IANA aliases that may be missing from reduced system tzdata
# (slim Docker images, Termux, ...). Only consulted for explicit
# slash-based or UTC-like queries, so bare country names such as
# "Iran" still reach the country resolver first.
_LEGACY_ZONE_ALIASES = {
    "uct": "UTC",
    "gmt0": "Etc/GMT",
    "us/eastern": "America/New_York",
    "us/central": "America/Chicago",
    "us/mountain": "America/Denver",
    "us/pacific": "America/Los_Angeles",
    "us/alaska": "America/Anchorage",
    "us/hawaii": "Pacific/Honolulu",
    "us/arizona": "America/Phoenix",
    "us/michigan": "America/Detroit",
    "us/indiana": "America/Indiana/Indianapolis",
}


def _looks_like_timezone(query: str) -> bool:
    """Heuristic for queries that are meant as IANA timezones."""
    return "/" in query or query.upper() in {"UTC", "GMT", "UCT", "GMT0"}


async def _geocode(query: str) -> list[dict]:
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

    if cached is not None:
        return cached  # type: ignore[return-value]

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

    _GEOCODE_CACHE.set(key, results)
    return results


async def _load_country_dataset() -> list[dict]:
    """
    Fetch the static country dataset (at most once a day).

    The dataset is a plain JSON list of ISO 3166 entries with
    common/official names, alternative spellings and capitals.
    """
    cached = _COUNTRY_DATA_CACHE.get("dataset")

    if cached is not None:
        return cached  # type: ignore[return-value]

    try:
        data = await async_searcher(
            COUNTRIES_DATA_URL,
            headers={
                "Accept": "application/json",
                "User-Agent": "Megatron-Time-Plugin/1.0",
            },
            re_json=True,
            retries=2,
        )
    except Exception:
        # A transient outage must not block country resolution
        # for the whole TTL, so failures are retried after a
        # minute and the plain geocoder takes over meanwhile.
        _COUNTRY_DATA_CACHE.set("dataset", [], ttl=NEGATIVE_TTL)
        return []

    if not isinstance(data, list):
        _COUNTRY_DATA_CACHE.set("dataset", [], ttl=NEGATIVE_TTL)
        return []

    _COUNTRY_DATA_CACHE.set("dataset", data)
    return data


def _match_countries(dataset: list[dict], query: str) -> list[dict]:
    """
    Match a country query against the static dataset.

    Priority: exact common name, alternative spelling
    (e.g. "USA", "UK"), official name, then fuzzy matches.
    """
    if not dataset:
        return []

    exact: list[dict] = []
    alt: list[dict] = []
    official: list[dict] = []
    fuzzy: list[dict] = []

    for entry in dataset:
        if not isinstance(entry, dict):
            continue

        name = entry.get("name")
        if not isinstance(name, dict):
            continue

        common = _clean(name.get("common"), 80)

        if not common:
            continue

        common_l = common.casefold()

        if common_l == query:
            exact.append(entry)
            continue

        alt_spellings = entry.get("altSpellings")

        if isinstance(alt_spellings, list) and any(
            _clean(spelling, 80).casefold() == query
            for spelling in alt_spellings
        ):
            alt.append(entry)
            continue

        if _clean(name.get("official"), 120).casefold() == query:
            official.append(entry)
            continue

        if query in common_l or common_l.startswith(query):
            fuzzy.append(entry)

    matches = (exact or alt or official or fuzzy)[:3]

    candidates: list[dict] = []

    for entry in matches:
        capitals = entry.get("capital")

        if not isinstance(capitals, list) or not capitals:
            continue

        country_name = _clean(
            (entry.get("name") or {}).get("common"),
            80,
        )

        for capital in capitals[:2]:
            capital = _clean(capital, 80)

            if not capital:
                continue

            candidates.append(
                {
                    "capital": capital,
                    "country": country_name,
                }
            )

    return candidates


async def _country_candidates(country_query: str) -> list[dict]:
    """
    Resolve a country name to its capital(s).

    Country lookup is a second-stage resolver. Normal city
    searches remain entirely handled by Open-Meteo.
    """
    query = _clean(country_query, MAX_QUERY_LENGTH).strip()

    if not query:
        return []

    key = query.casefold()
    cached = _COUNTRY_CACHE.get(key)

    if cached is not None:
        return cached  # type: ignore[return-value]

    dataset = await _load_country_dataset()
    candidates = _match_countries(dataset, key)

    _COUNTRY_CACHE.set(key, candidates)
    return candidates


async def resolve_locations(query: str) -> list[dict]:
    """
    Resolve a user query.

    Priority:
      1. Explicit IANA timezone (or common legacy alias).
      2. Country -> capital.
      3. Normal global geocoding.
    """
    query = _clean(query, MAX_QUERY_LENGTH).strip()

    if not query:
        return []

    # Advanced users can enter an IANA timezone directly.
    #
    # Important: zoneinfo contains legacy aliases such as ``Iran`` and
    # ``US/Eastern``. A bare country name must therefore be allowed to
    # reach the country resolver first. Slash-based IANA names and the
    # UTC family are unambiguous.
    if _looks_like_timezone(query):
        zone_name = _LEGACY_ZONE_ALIASES.get(query.casefold(), query)

        try:
            ZoneInfo(zone_name)
        except Exception:
            pass
        else:
            return [
                {
                    "name": zone_name.rsplit("/", 1)[-1].replace("_", " "),
                    "admin1": "",
                    "country": "",
                    "timezone": zone_name,
                    "country_code": "",
                    "latitude": None,
                    "longitude": None,
                    "_direct_timezone": True,
                }
            ]

    country_candidates = await _country_candidates(query)

    if country_candidates:
        resolved: list[dict] = []

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


def _now_for_location(location: dict) -> tuple[datetime, Optional[str], str]:
    """
    Return local datetime, timezone abbreviation and long display name.

    ZoneInfo handles DST transitions and current UTC offsets using the
    operating system's IANA tzdata (with the tzdata package as a
    fallback on hosts with reduced system data).
    """
    zone_name = _clean(location.get("timezone"), 100)

    if not zone_name:
        raise ValueError("Location has no timezone.")

    try:
        zone = ZoneInfo(zone_name)
    except Exception as exc:
        raise ValueError(f"Unknown timezone: {zone_name}") from exc

    now = datetime.now(zone)

    country = _clean(
        location.get("_queried_country") or location.get("country"),
        80,
    )

    abbreviation = _zone_abbreviation(now)

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

    # datetime.strftime("%-d") is Linux-specific.  Using the day as an
    # integer keeps the formatter portable across platforms.
    date_text = (
        f"{now.strftime('%A, %B')} "
        f"{now.day}, {now.year}"
    )

    if abbreviation:
        zone_block = (
            f"🗺️ <b>Timezone:</b> <code>{_esc(zone_name, 100)}</code>\n"
            f"⏱️ <b>Zone:</b> <code>{_esc(abbreviation, 30)}</code> · "
            f"<code>{_fmt_offset(offset_seconds)}</code>"
        )
    else:
        # The host's tzdata only provides a POSIX-style offset
        # string (e.g. "+0330"), which is not a real abbreviation.
        zone_block = (
            f"🗺️ <b>Timezone:</b> <code>{_esc(zone_name, 100)}</code>\n"
            f"⏱️ <b>UTC Offset:</b> <code>{_fmt_offset(offset_seconds)}</code>"
        )

    return (
        f"🌍 <b>{_esc(title)} Time</b> 🌎\n\n"
        f"🕓 <b>{now.strftime('%I:%M:%S %p')}</b> "
        f"<i>{_esc(long_name)}</i>\n"
        f"📆 <b>{_esc(date_text)}</b>\n\n"
        f"{zone_block}\n"
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
        f"{_zone_line(first_zone, first_abbr, first_offset)}\n\n"
        f"📍 <b>{_esc(second_title)}</b>\n"
        f"🕓 <code>{second_now.strftime('%I:%M:%S %p')}</code> · "
        f"<i>{_esc(second_long)}</i>\n"
        f"{_zone_line(second_zone, second_abbr, second_offset)}\n\n"
        f"↔️ {relation}\n"
        f"⏱️ <b>Difference:</b> <code>{_ordinal_offset(difference)}</code>"
    )


# ============================================================================
# QUERY PARSING
# ============================================================================

_COMPARISON_PREFIX = re.compile(
    r"^(?:diff|difference|compare)(?:\s+between)?\s+",
    re.IGNORECASE,
)

_UNIVERSAL_SEPARATORS = (
    r"\s+(?:vs\.?|versus|to)\s+",
    r"\s*(?:\||<>|->|—|–)\s*",
)

_AND_SEPARATOR = r"\s+and\s+"


def _parse_query(query: str) -> tuple[str, Optional[str]]:
    """
    Split a query into (first, second) for comparison.

    Supported comparison syntax:

      time Tehran vs Chicago
      time Tehran | Tokyo
      time Tehran <> Chicago
      time Tehran -> Chicago
      time Tehran to Chicago
      time diff Tehran | Chicago
      time compare London and Dubai

    "and" only separates when an explicit compare/diff keyword was used,
    so that single places whose names contain " and " (e.g. Wallis and
    Futuna) keep working as one location.
    """
    query = _clean(query, MAX_QUERY_LENGTH).strip()

    if not query:
        return "", None

    prefix = _COMPARISON_PREFIX.match(query)
    explicit_compare = prefix is not None

    if explicit_compare:
        query = query[prefix.end() :].strip()

    separators = list(_UNIVERSAL_SEPARATORS)
    if explicit_compare:
        separators.append(_AND_SEPARATOR)

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


def _not_found_message(query: str, role: Optional[str] = None) -> str:
    """Pick a helpful error message for a query that resolved to nothing."""
    if _looks_like_timezone(query):
        detail = f"unknown timezone: {_clean(query, 60)}"
    else:
        detail = "no matching city, country or timezone was found"

    if role:
        return f"The {role} location could not be found: {detail}."

    return detail[0].upper() + detail[1:] + "."


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
            "• <code>time Asia/Tehran</code>\n"
            "• <code>time US/Eastern</code>\n\n"
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
        description=_clean(message, 200),
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


def _button_seed(location: dict) -> str:
    """Short seed used for the per-result switch_inline queries."""
    if location.get("_direct_timezone"):
        seed = _clean(location.get("timezone"), BUTTON_QUERY_LIMIT)
    else:
        seed = _clean(_location_title(location), BUTTON_QUERY_LIMIT)

    return seed or "time"


def _single_buttons(location: dict):
    seed = _button_seed(location)

    return [
        [
            Button.switch_inline(
                "🔎 Search Again",
                query="time ",
                same_peer=True,
            ),
            Button.switch_inline(
                "↔️ Compare",
                query=f"time diff {seed} | ",
                same_peer=True,
            ),
        ],
        [
            Button.switch_inline(
                "📍 Search This Place",
                query=f"time {seed}",
                same_peer=True,
            ),
        ],
    ]


def _compare_buttons(first: str, second: str):
    first = _clean(first, BUTTON_QUERY_LIMIT)
    second = _clean(second, BUTTON_QUERY_LIMIT)

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


def _comparison_title(first: dict, second: dict) -> str:
    """Telegram caps inline result titles at 255 characters."""
    title = f"↔️ {_location_title(first)} ↔ {_location_title(second)}"
    return _clean(title, MAX_TITLE_LENGTH)


async def _candidate_results(event, locations: list[dict]):
    results = []

    for location in locations[:MAX_RESULTS]:
        try:
            now, abbreviation, _ = _now_for_location(location)

            title = _location_title(location)

            offset = now.utcoffset()
            seconds = int(offset.total_seconds()) if offset else 0

            description = (
                f"{now.strftime('%I:%M:%S %p')} · "
                f"{abbreviation or _timezone_display_name(location.get('timezone', ''), None, '')} · "
                f"{_fmt_offset(seconds)}"
            )

            results.append(
                await event.builder.article(
                    title=f"🌍 {_clean(title, 200)}",
                    description=_clean(description, 200),
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
    r"(?i)^time(?:\s+(.*))?$",
)
async def time_inline(event):
    """
    Main inline entry point.

    No callback session or mutable per-user Telegram state is used.
    Each inline result is self-contained.
    """
    try:
        raw = (event.text or "").strip()

        # Telethon already matched the decorator pattern; keep a manual
        # fallback so the query extraction never depends on event internals.
        match = event.pattern_match or re.match(
            r"(?i)^time(?:\s+(.*))?$",
            raw,
        )

        query = (
            (match.group(1) or "").strip()
            if match
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
                            _not_found_message(first_query, role="first"),
                        )
                    ],
                    cache_time=10,
                )

            if not second_locations:
                return await event.answer(
                    [
                        await _error_result(
                            event,
                            second_query,
                            _not_found_message(second_query, role="second"),
                        )
                    ],
                    cache_time=10,
                )

            first = first_locations[0]
            second = second_locations[0]

            result = await event.builder.article(
                title=_comparison_title(first, second),
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
                        _not_found_message(first_query),
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
                        getattr(event, "text", "") or "time",
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
    """Drop expired entries from the plugin's lookup caches."""
    _GEOCODE_CACHE.evict_expired()
    _COUNTRY_CACHE.evict_expired()

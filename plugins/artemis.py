"""
✘ Commands Available -

• `{i}gentoken SESSION`
   Generate MRKT token from session.

• `{i}buytoken YOUR_TOKEN`
   Set token / restart monitors.

• `{i}b`
   Show MRKT hard balance (TON).

• `{i}nfts`
   Show your listed MRKT NFTs + model floors.

• `{i}add <id|@username>`
   Allow a user for assistant `/gift` `/gift c` `/p` `/order` `/ordertop`
   and inline `g` / `ch`.

• `{i}rm <id|@username>`
   Remove a user from that allow-list.

• `{i}buy Collection, Model, Backdrop, MIN-MAX`
   Auto buy (owner) — without transfer lock only.

• `{i}buys` | `{i}buycancel N` | `{i}buycancel all`
   List / cancel auto-buy monitors.

• `{i}gift Collection`
   Transferable floors via Gift Satellite miniapp (all markets).

• `{i}gift Collection, Model`
   Floors + quick sells + up to 5 MRKT cheapest listings + monochromes.

• `{i}gift Collection, Model, Backdrop`
   Floors + quick sells + listings + latest sales (all markets).

• `{i}gift https://t.me/nft/Name-123`
   Resolve NFT attrs → full floors / listings / sales.

• `{i}gift c Collection, Model, Backdrop`
   Compact floors + matching quick sell only.

• `{i}gift c https://t.me/nft/Name-123`
   Compact floors for that NFT's collection + model + backdrop.

• Inline: `@AssisXBot g Collection[, Model][, Backdrop]`
• Inline: `@AssisXBot g https://t.me/nft/Name-123`
   Hub: Floor Price 📉 / Gift Chart 📊 / NFT Sales 🧾 → market filters.

• `{i}ch Collection[, Model]`
   Send GiftCharts baseline chart in chat.

• `{i}p usdt` | `{i}p ton` | `{i}p stars`
   Convert 1 unit (+ Tomans & USDT).

• `{i}p 5 usdt` | `{i}p 5 ton` | `{i}p 50 stars`
   Convert an amount (+ Tomans & USDT).

• `{i}p 50 ton stars` | `{i}p 1000 stars ton`
   Explicit conversion direction.

• `{i}p 1000000 t ton` | `{i}p 1000000 t usdt` | `{i}p 1000000 t stars`
   Convert Tomans (`t`) → TON / USDT / Stars (no Tomans line in output).

• `{i}order Collection`
   Offer count + highest + top 5 ranges.

• `{i}order Collection, Model`
   Orders for a specific model.

• `{i}order Collection, Model, Backdrop`
   Orders for model + backdrop.

• `{i}ordertop Collection`
   Top 10 highest orders across all models.

• `{i}orders`
   List your active orders.

• `{i}ordernew Collection, Model, Backdrop, QTY, MIN-MAX`
   Create a new order (qty + price range).

• `{i}ordernew Collection, Model, Backdrop, MIN-MAX`
   Create a new order (price range).

• `{i}ordernew Collection, Model, MIN-MAX`
   Create a new order for model only.

• `{i}ordernew` (reply to / paste `.orders` list)
   Bulk recreate: for each numbered order, skip if that UUID is already
   live; otherwise create from Collection, Model, Backdrop + 💰 MIN-MAX.

• `{i}orderup N`
   Retarget order N to competitor top+0.01 (raise or lower).

• `{i}orderupall`
   Retarget every order to competitor top+0.01 (raise or lower).

• `{i}autotop on` | `{i}autotop on 20` | `{i}autotop off`
   Auto orderupall every N seconds (default 30).
   Active orders are stored in DB and recreated if missing.
   Turns itself off when no active orders remain.

• `{i}orderdel N` | `{i}orderdel 1, 2, 3`
   Delete one or multiple orders by `.orders` index.

• `{i}orderdelall`
   Delete all orders.

Auto: missing/expired token regenerates from DB `SESSIONMRKT`.
"""

import os
import html
import requests
import asyncio
import contextlib
import secrets
import time
import re
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import aiohttp
from TelegramGifts import TelegramGifts
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from telethon.utils import get_display_name

from artemis import MRKTClient
from artemis.exceptions import TradingError, RequestError, AuthError
from artemis.utils import ton_to_nano, nano_to_ton

from telethon import Button

from . import (
    heartless_cmd,
    asst_cmd,
    LOGS,
    heartless_bot,
    asst,
    udB,
    HNDLR,
    OWNER_ID,
    in_pattern,
    callback,
)
from . import _satellite_tma as sat
from . import _giftcharts as gc  # charts callbacks register via this import
from CythonX._misc import owner_and_sudos


# ============================================================
# CONFIG
# ============================================================

LOG_CHAT_ID = -1001275576295
POLL_SECONDS = 1.0
BUY_ONE = True

ARTEMIS_TOKEN = udB.get_key("ARTEMIS_TOKEN") or None
if ARTEMIS_TOKEN:
    ARTEMIS_TOKEN = str(ARTEMIS_TOKEN).strip() or None
MRKT_API_ID = udB.get_key("api_id")
MRKT_API_HASH = udB.get_key("api_hash")

BUY_MONITORS = {}
MONITOR_COUNTER = 0
BUY_LOCK = asyncio.Lock()
TOKEN_LOCK = asyncio.Lock()
ORDER_CACHE = []

AUTOTOP_DEFAULT_INTERVAL = 30.0
AUTOTOP_MIN_INTERVAL = 5.0
AUTOTOP_MAX_INTERVAL = 3600.0
AUTOTOP_INTERVAL = AUTOTOP_DEFAULT_INTERVAL
AUTOTOP_DB_KEY = "ARTEMIS_AUTOTOP"
AUTOTOP_INTERVAL_DB_KEY = "ARTEMIS_AUTOTOP_INTERVAL"
AUTOTOP_ORDERS_DB_KEY = "ARTEMIS_AUTOTOP_ORDERS"
ORDERUP_LOCK = asyncio.Lock()
AUTOTOP_TASK = None
AUTOTOP_ENABLED = False
AUTOTOP_STATS = {
    "started_at": None,
    "last_run_at": None,
    "last_updated": 0,
    "last_skipped": 0,
    "last_errors": 0,
    "last_recreated": 0,
    "cycles": 0,
}

TELEGRAM_GIFTS = TelegramGifts(
    cache_mode="http",
    asset_mode="lazy",
    ttl_seconds=600,
)

# Gift Changes API — gift/model metadata/rarity (not stickers)
# thanks to @GiftChanges for this API (api.changes.tg)
CHANGES_API = "https://api.changes.tg"
GIFT_CHANGES_CREDIT = "thanks to @GiftChanges for this API"

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

# Gift Satellite miniapp markets (display labels; floors+sales via sat TMA)
SATELLITE_MARKETS = tuple(
    (search, label) for search, label, _hist in sat.SAT_MARKETS
)

# Fragment-style Stars USD reference (override with DB key STAR_USD).
DEFAULT_STAR_USD = Decimal("0.015")
_RATE_CACHE = {"at": 0.0, "ton_usd": None, "usdt_toman": None}
_RATE_CACHE_TTL = 60.0


def _h(*parts):
    """Command usage with the active Heartless handler."""
    return f"{HNDLR}{''.join(str(p) for p in parts)}"


def _get_nftids():
    """NFTIDS DB key as a list of int user IDs."""
    raw = udB.get_key("NFTIDS")
    if raw is None:
        return []
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, tuple):
        values = list(raw)
    elif isinstance(raw, (int, float)):
        values = [raw]
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                import ast
                parsed = ast.literal_eval(text)
                values = parsed if isinstance(parsed, list) else [parsed]
            except Exception:
                values = re.split(r"[\s,;]+", text)
        else:
            values = re.split(r"[\s,;]+", text)
    else:
        return []
    out = []
    for item in values:
        try:
            uid = int(str(item).strip())
        except Exception:
            continue
        if uid not in out:
            out.append(uid)
    return out


def _set_nftids(ids):
    clean = []
    for item in ids or []:
        try:
            uid = int(item)
        except Exception:
            continue
        if uid not in clean:
            clean.append(uid)
    udB.set_key("NFTIDS", clean)
    return clean


def _add_nftid(user_id):
    uid = int(user_id)
    ids = _get_nftids()
    if uid not in ids:
        ids.append(uid)
        _set_nftids(ids)
    return ids


def _rm_nftid(user_id):
    uid = int(user_id)
    ids = _get_nftids()
    if uid in ids:
        ids = [x for x in ids if x != uid]
        _set_nftids(ids)
        return ids, True
    return ids, False


def _nft_user_allowed(user_id):
    try:
        uid = int(user_id)
    except Exception:
        return False
    if uid in set(owner_and_sudos() or []):
        return True
    if OWNER_ID and uid == int(OWNER_ID):
        return True
    return uid in _get_nftids()


def _asst_nft_ok(event):
    """Assistant NFT cmds: private chat + allow-list (or owner)."""
    if getattr(event, "is_group", False) or not getattr(event, "is_private", True):
        return False
    return _nft_user_allowed(getattr(event, "sender_id", None))


# Back-compat alias used by /gift and /p handlers.
_asst_gift_p_ok = _asst_nft_ok


def _user_profile_link(entity):
    name = html.escape(get_display_name(entity) or str(entity.id))
    return f'<a href="tg://user?id={entity.id}">{name}</a>'


async def _resolve_tg_user(event, raw):
    """Resolve user by numeric ID or @username. Returns entity."""
    text = str(raw or "").strip()
    if not text:
        raise ValueError("User ID or username is required.")
    text = text.lstrip("@")
    if re.fullmatch(r"-?\d{5,}", text):
        target = int(text)
    else:
        target = text
    try:
        return await event.client.get_entity(target)
    except Exception as e:
        raise ValueError(f"Could not resolve user: {e}") from e



# ============================================================
# HELPERS
# ============================================================

def _next_monitor_id():
    global MONITOR_COUNTER
    MONITOR_COUNTER += 1
    return MONITOR_COUNTER


def _parse_ton(value):
    value = value.strip().replace(",", ".")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError(f"Invalid TON value: {value}")
    if result < 0:
        raise ValueError("TON price cannot be negative.")
    return result


def _parse_price_range(value):
    value = value.strip()
    if "-" not in value:
        raise ValueError("Price range must be in this format: 0.5-4.6")
    minimum, maximum = value.split("-", 1)
    min_ton = _parse_ton(minimum)
    max_ton = _parse_ton(maximum)
    if min_ton > max_ton:
        raise ValueError(
            "Minimum price cannot be greater than maximum price."
        )
    return min_ton, max_ton


def _parse_buy_command(raw):
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 4:
        raise ValueError(
            "Invalid format.\n\n"
            "Correct format:\n"
            f"{_h('buy')} Collection, Model, Backdrop, MIN-MAX\n\n"
            "Example:\n"
            f"{_h('buy')} Liberty Bell, Fire Opal, Cyberpunk, 0.5-4.6"
        )
    collection, model, backdrop, price_range = parts
    if not collection:
        raise ValueError("Collection cannot be empty.")
    if not model:
        raise ValueError("Model cannot be empty.")
    if backdrop.lower() in ("none", "null", "*", "-"):
        backdrop = None
    min_ton, max_ton = _parse_price_range(price_range)
    return collection, model, backdrop, min_ton, max_ton


def _format_ton(value):
    try:
        value = Decimal(str(value))
        return format(value.normalize(), "f")
    except Exception:
        return str(value)


def _format_uptime(created_at):
    seconds = max(0, int(time.time() - created_at))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    return f"{hours // 24}d"


def _ton2(value):
    if value is None or value == "":
        return "—"
    d = Decimal(str(value)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    text = f"{d:.2f}"
    # 867.00 → 867 (only exact .00 cents)
    if text.endswith(".00"):
        return text[:-3]
    return text


def _rarity_pct(per_mille):
    if per_mille is None or per_mille == "":
        return "?"
    text = str(per_mille).strip()
    if text.endswith("%"):
        return text
    try:
        value = Decimal(text) / Decimal(10)
    except Exception:
        return "?"
    return (
        f"{value:.1f}".rstrip("0").rstrip(".") + "%"
    )


def _pct_to_permille(value):
    """Convert '1.5%' / 1.5 / '1.5' into per-mille (15)."""
    if value is None or value == "":
        return None
    text = str(value).strip().replace(",", ".")
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        return int(
            (
                Decimal(text) * Decimal(10)
            ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    except Exception:
        return None


def _rarity_from_label(label):
    """Extract per-mille from labels like 'Cyberpunk (1.5%)'."""
    match = re.search(
        r"\(([\d.,]+)\s*%\)",
        str(label or ""),
    )
    if not match:
        return None
    return _pct_to_permille(match.group(1))


def _mrkt_link(gift_id):
    return f"https://t.me/mrkt/app?startapp={gift_id}"


def _nft_link(gift_name):
    return f"https://t.me/nft/{gift_name}"


def _get_raw(gift):
    raw = getattr(gift, "raw", None)
    return raw if isinstance(raw, dict) else {}


def _norm_name(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _name_key(value):
    return _norm_name(value).replace(" ", "_")


def _loose_key(value):
    """Case/space/punctuation-insensitive key: 'EasterEgg' == 'easter egg'."""
    return re.sub(r"[^a-z0-9]", "", _norm_name(value))


def _strip_rarity(value):
    text = str(value or "")
    return re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()


def _title_from_compact(value):
    """EasterEgg / easter_egg / libertyfigure -> title-ish form."""
    text = str(value or "").strip()
    if not text:
        return text
    if " " in text:
        return " ".join(part.capitalize() for part in text.split())
    text = text.replace("-", "_")
    if "_" in text:
        return " ".join(
            part.capitalize() for part in text.split("_") if part
        )
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    return " ".join(part.capitalize() for part in spaced.split() if part)


def _name_variants(*values):
    """
    All useful spellings of a gift collection/model name.

    libertyfigure / LibertyFigure / liberty figure / Liberty Figure
    fireopal / FireOpal / fire opal / Fire Opal
    """
    out = []

    def _add(item):
        item = str(item or "").strip()
        if item and item not in out:
            out.append(item)

    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        spaced = " ".join(
            raw.replace("_", " ").replace("-", " ").split()
        )
        titled = _title_from_compact(raw)
        spaced_title = " ".join(
            part.capitalize() for part in spaced.split()
        )
        # Compact forms: LibertyFigure / libertyfigure
        compact = re.sub(r"[^a-zA-Z0-9]", "", raw)
        pascal = "".join(part.capitalize() for part in spaced_title.split())
        lower_compact = compact.lower()

        for item in (
            raw,
            titled,
            spaced,
            spaced_title,
            spaced.lower(),
            spaced.upper(),
            compact,
            pascal,
            lower_compact,
            pascal.lower(),
            _norm_name(raw),
            " ".join(part.capitalize() for part in _norm_name(raw).split()),
        ):
            _add(item)
    return out


async def _resolve_gift_names(client, collection, model=None, backdrop=None):
    """Canonicalize then refine collection/model/backdrop for any command."""
    collection, model, backdrop, _ = await asyncio.to_thread(
        _canonicalize_gift_query,
        collection,
        model,
        backdrop,
    )
    return await _refine_gift_names(client, collection, model, backdrop)

def _match_known_name(target, known_names):
    """Pick canonical name from a known list via loose key / fuzzy match."""
    if not target:
        return target
    target_loose = _loose_key(target)
    fuzzy = None
    for name in known_names or []:
        if not name:
            continue
        if _loose_key(name) == target_loose:
            return name
        if fuzzy is None and _match_attr(name, target):
            fuzzy = name
    return fuzzy or target


def _floor_ton(value):
    """Always `x.xx TON` or `— TON` when floor is missing."""
    amount = _as_floor(value)
    if amount is None:
        return "— TON"
    return f"{_ton2(amount)} TON"


def _gift_full_name(gift):
    if isinstance(gift, dict):
        return (
            gift.get("full_name")
            or gift.get("name")
            or gift.get("title")
        )
    if gift is None:
        return None
    for attr in ("full_name", "name", "title"):
        val = getattr(gift, attr, None)
        if val:
            return str(val)
    return None


def _canonicalize_collection(name):
    """
    Resolve user collection input to the canonical MRKT/TG display name.
    'libertyfigure' / 'LibertyFigure' / 'liberty figure' -> 'Liberty Figure'
    """
    raw = str(name or "").strip()
    if not raw:
        return raw, {}

    candidates = _name_variants(raw)

    for candidate in candidates:
        try:
            gift = TELEGRAM_GIFTS.get_gift(candidate)
        except Exception:
            gift = None
        if isinstance(gift, dict) and gift:
            full = _gift_full_name(gift) or candidate
            return full, gift

    # Scan upgraded catalog by loose key.
    target = _loose_key(raw)
    try:
        upgraded = TELEGRAM_GIFTS.get_upgraded_gifts() or []
    except Exception:
        upgraded = []
    for item in upgraded:
        if isinstance(item, dict):
            full = item.get("full_name") or item.get("name")
            short = item.get("short_name")
        else:
            full = getattr(item, "full_name", None) or getattr(item, "name", None)
            short = getattr(item, "short_name", None)
        if full and _loose_key(full) == target:
            try:
                gift = TELEGRAM_GIFTS.get_gift(full) or {}
            except Exception:
                gift = {}
            return str(full), gift if isinstance(gift, dict) else {}
        if short and _loose_key(short) == target:
            try:
                gift = (
                    TELEGRAM_GIFTS.get_gift(short)
                    or TELEGRAM_GIFTS.get_gift(full)
                    or {}
                )
            except Exception:
                gift = {}
            return str(full or short), gift if isinstance(gift, dict) else {}

    return _title_from_compact(raw) or raw, {}


def _canonicalize_attr(prices_map, target_name):
    """Resolve model/backdrop name against a TelegramGifts attribute map."""
    if not target_name:
        return target_name
    target = _loose_key(_strip_rarity(target_name))
    if isinstance(prices_map, dict):
        for key in prices_map:
            clean = _strip_rarity(key)
            if _loose_key(clean) == target:
                return clean
            if _match_attr(clean, target_name):
                return clean
        # Also try compact variants against map keys.
        for variant in _name_variants(target_name):
            vkey = _loose_key(_strip_rarity(variant))
            for key in prices_map:
                clean = _strip_rarity(key)
                if _loose_key(clean) == vkey:
                    return clean
    return _title_from_compact(target_name) or target_name


def _canonicalize_gift_query(collection, model=None, backdrop=None):
    """Normalize collection/model/backdrop for case-insensitive .gift input."""
    canon_collection, gift = _canonicalize_collection(collection)

    model_prices = {}
    backdrop_prices = {}
    if gift or canon_collection:
        try:
            model_prices = TELEGRAM_GIFTS.get_attribute_price(
                canon_collection, "models"
            ) or {}
        except Exception:
            model_prices = {}
        try:
            backdrop_prices = TELEGRAM_GIFTS.get_attribute_price(
                canon_collection, "backdrops"
            ) or {}
        except Exception:
            backdrop_prices = {}

    canon_model = _canonicalize_attr(model_prices, model) if model else None
    canon_backdrop = (
        _canonicalize_attr(backdrop_prices, backdrop) if backdrop else None
    )
    return canon_collection, canon_model, canon_backdrop, gift


def _mrkt_floor_lookup(floors_obj, collection):
    """Case/space-insensitive MRKT collection floor lookup."""
    if floors_obj is None:
        return None
    direct = _as_floor(floors_obj.floor(collection))
    if direct is not None:
        return direct
    values = getattr(floors_obj, "values", None) or {}
    target = _loose_key(collection)
    for key, value in values.items():
        if _loose_key(key) == target:
            return _as_floor(value)
    return None


def _mrkt_collection_name(floors_obj, collection):
    """Resolve canonical collection spelling from MRKT floor map."""
    if not collection:
        return collection
    values = getattr(floors_obj, "values", None) or {}
    target = _loose_key(collection)
    for key in values:
        if _loose_key(key) == target:
            return key
    # Some SDK floors expose floor() only — try direct hit.
    if _as_floor(floors_obj.floor(collection)) is not None:
        return collection
    return collection


async def _refine_gift_names(client, collection, model=None, backdrop=None):
    """
    Align collection/model/backdrop spelling with MRKT catalog names.
    Fixes libertyfigure / LibertyFigure / liberty figure / FireOpal / fire opal.
    """
    try:
        floors = await client.market.collection_floors()
        known = list(getattr(floors, "values", None) or {})
        resolved = None
        for candidate in _name_variants(collection):
            for key in known:
                if _loose_key(key) == _loose_key(candidate):
                    resolved = key
                    break
            if resolved:
                break
        collection = resolved or _mrkt_collection_name(floors, collection)
    except Exception as e:
        LOGS.warning("MRKT collection name refine failed: %s", e)
        collection = _title_from_compact(collection) or collection

    if model:
        row = {}
        try:
            models = await client.request(
                "POST", "/gifts/models", json={"collections": [collection]},
            )
            for variant in _name_variants(model):
                row = _find_named_row(models, ("modelName", "name"), variant)
                if row:
                    break
            name = row.get("modelName") or row.get("name")
            if name:
                model = _strip_rarity(name)
            else:
                model = _title_from_compact(model) or model
        except Exception as e:
            LOGS.warning("MRKT model name refine failed: %s", e)
            model = _title_from_compact(model) or model

    if backdrop:
        row = {}
        try:
            backdrops = await client.request(
                "POST",
                "/gifts/backdrops",
                json={"collections": [collection]},
            )
            for variant in _name_variants(backdrop):
                row = _find_named_row(
                    backdrops, ("backdropName", "name"), variant,
                )
                if row:
                    break
            name = row.get("backdropName") or row.get("name")
            if name:
                backdrop = _strip_rarity(name)
            else:
                backdrop = _title_from_compact(backdrop) or backdrop
        except Exception as e:
            LOGS.warning("MRKT backdrop name refine failed: %s", e)
            backdrop = _title_from_compact(backdrop) or backdrop

    return collection, model, backdrop


def _match_attr(candidate, target):
    if not target:
        return True
    c = _name_key(_strip_rarity(candidate))
    t = _name_key(target)
    if _loose_key(c) == _loose_key(t):
        return True
    return (
        c == t
        or c.startswith(t + "_")
        or t.startswith(c + "_")
        or c.startswith(t)
        or t.startswith(c)
    )


def _find_named_row(rows, name_keys, target):
    """Find a dict row by name fields — exact match first, then fuzzy."""
    fuzzy = None
    target_key = _name_key(target)
    target_loose = _loose_key(target)
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for key in name_keys:
            value = row.get(key)
            if not value:
                continue
            clean = _strip_rarity(value)
            if _name_key(clean) == target_key or _loose_key(clean) == target_loose:
                return row
            if fuzzy is None and _match_attr(value, target):
                fuzzy = row
    return fuzzy or {}


def _as_floor(value):
    """Normalize floor values; treat missing/zero as None."""
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value))
    except Exception:
        return None
    if amount <= 0:
        return None
    return amount


_NFT_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?t\.me/nft/"
    r"([A-Za-z0-9_]+)-(\d+)",
    re.I,
)


def _slug_name_candidates(slug):
    """Turn NFT slug fragment (LibertyFigure) into lookup candidates."""
    slug = str(slug or "").strip()
    if not slug:
        return []
    snake = re.sub(
        r"([a-z0-9])([A-Z])",
        r"\1_\2",
        slug,
    ).lower()
    spaced = snake.replace("_", " ")
    titled = " ".join(
        part.capitalize() for part in snake.split("_") if part
    )
    out = []
    for item in (
        slug,
        slug.lower(),
        snake,
        spaced,
        titled,
        snake.replace("_", ""),
    ):
        if item and item not in out:
            out.append(item)
    return out


def _parse_nft_link(value):
    """
    Parse `.gift https://t.me/nft/LibertyFigure-214445`
    → (slug, short_slug, number)
    """
    text = str(value or "").strip()
    match = _NFT_LINK_RE.search(text)
    if not match:
        # bare slug: LibertyFigure-214445
        bare = re.fullmatch(
            r"([A-Za-z0-9_]+)-(\d+)",
            text,
        )
        if not bare:
            return None
        short, number = bare.group(1), bare.group(2)
        return f"{short}-{number}", short, int(number)
    short, number = match.group(1), match.group(2)
    return f"{short}-{number}", short, int(number)


def _resolve_collection_from_slug(short_slug):
    for candidate in _slug_name_candidates(short_slug):
        try:
            gift = TELEGRAM_GIFTS.get_gift(candidate)
        except Exception:
            gift = None
        if isinstance(gift, dict) and gift:
            return (
                gift.get("name")
                or gift.get("full_name")
                or gift.get("title")
                or candidate,
                gift.get("short_name") or candidate,
                gift,
            )
    # last resort: title-case spaced camel
    snake = re.sub(
        r"([a-z0-9])([A-Z])",
        r"\1_\2",
        short_slug,
    ).lower()
    titled = " ".join(
        part.capitalize() for part in snake.split("_") if part
    )
    return titled or short_slug, snake or short_slug.lower(), {}


def _parse_telegram_nft_html(html):
    """
    Extract model/backdrop (+ rarity %) from a t.me/nft page.
    """
    if not html:
        return None, None, None, None

    model = backdrop = None
    model_rarity = backdrop_rarity = None

    # Modern attribute cards
    for block in re.finditer(
        r'(?is)(?:tgme_gift_attribute|gift_attribute)[^>]*>'
        r'(.*?)</div>\s*</div>',
        html,
    ):
        chunk = re.sub(r"<[^>]+>", " ", block.group(1))
        chunk = re.sub(r"\s+", " ", chunk).strip()
        low = chunk.lower()
        pct = re.search(r"([\d.,]+)\s*%", chunk)
        permille = _pct_to_permille(pct.group(1)) if pct else None
        if low.startswith("model"):
            model = re.sub(
                r"(?i)^model\s*", "", chunk
            )
            model = re.sub(r"\s*[\d.,]+\s*%\s*$", "", model).strip()
            model_rarity = permille
        elif low.startswith("backdrop"):
            backdrop = re.sub(
                r"(?i)^backdrop\s*", "", chunk
            )
            backdrop = re.sub(
                r"\s*[\d.,]+\s*%\s*$", "", backdrop
            ).strip()
            backdrop_rarity = permille

    # Table rows: Model | Fire Opal | 1.5%
    if model is None or backdrop is None:
        for label, name, pct in re.findall(
            r"(?is)(Model|Backdrop)\s*</t[hd]>\s*"
            r"<t[hd][^>]*>\s*(?:<[^>]+>)*\s*([^<]+?)\s*"
            r"(?:</[^>]+>\s*)*</t[hd]>\s*"
            r"<t[hd][^>]*>\s*([\d.,]+\s*%)",
            html,
        ):
            permille = _pct_to_permille(pct)
            name = name.strip()
            if label.lower() == "model" and not model:
                model, model_rarity = name, permille
            elif label.lower() == "backdrop" and not backdrop:
                backdrop, backdrop_rarity = name, permille

    # Plain text fallbacks
    if model is None:
        m = re.search(
            r"(?i)Model\s*[:\|]\s*([^\n<%]+?)(?:\s*([\d.,]+)\s*%)?",
            html,
        )
        if m:
            model = m.group(1).strip(" |-")
            if m.group(2):
                model_rarity = _pct_to_permille(m.group(2))
    if backdrop is None:
        m = re.search(
            r"(?i)Backdrop\s*[:\|]\s*([^\n<%]+?)(?:\s*([\d.,]+)\s*%)?",
            html,
        )
        if m:
            backdrop = m.group(1).strip(" |-")
            if m.group(2):
                backdrop_rarity = _pct_to_permille(m.group(2))

    return model or None, backdrop or None, model_rarity, backdrop_rarity


async def _fetch_telegram_nft_attrs(slug):
    """Fetch model/backdrop from https://t.me/nft/<slug> (HTML fallback)."""
    url = f"https://t.me/nft/{slug}"
    try:
        timeout = aiohttp.ClientTimeout(total=25)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml",
                },
            ) as resp:
                if resp.status != 200:
                    LOGS.warning(
                        "NFT page HTTP %s for %s",
                        resp.status,
                        url,
                    )
                    return None, None, None, None, None
                html = await resp.text()
        model, backdrop, model_rarity, backdrop_rarity = (
            _parse_telegram_nft_html(html)
        )
        return model, backdrop, model_rarity, backdrop_rarity, None
    except Exception as e:
        LOGS.warning(
            "NFT page fetch failed for %s: %s: %r",
            url,
            type(e).__name__,
            e,
        )
        return None, None, None, None, None


def _attr_rarity_permille(attr):
    rarity = getattr(attr, "rarity", None)
    if rarity is None:
        return None
    return getattr(rarity, "permille", None)


async def _fetch_unique_star_gift_attrs(tg_client, slug):
    """
    Resolve NFT attributes via MTProto payments.getUniqueStarGift.
    This works even when t.me HTML scraping is blocked.
    """
    if tg_client is None:
        return None, None, None, None, None

    try:
        from telethon.tl.functions.payments import (
            GetUniqueStarGiftRequest,
        )
        from telethon.tl.types import (
            StarGiftAttributeBackdrop,
            StarGiftAttributeModel,
            StarGiftUnique,
        )
    except Exception as e:
        LOGS.warning("Telethon gift imports failed: %s", e)
        return None, None, None, None, None

    try:
        result = await tg_client(
            GetUniqueStarGiftRequest(slug=slug)
        )
    except Exception as e:
        LOGS.warning(
            "GetUniqueStarGift failed for %s: %s: %r",
            slug,
            type(e).__name__,
            e,
        )
        return None, None, None, None, None

    gift = getattr(result, "gift", None)
    if not isinstance(gift, StarGiftUnique):
        LOGS.warning(
            "Unexpected unique gift type for %s: %r",
            slug,
            type(gift),
        )
        return None, None, None, None, None

    model = backdrop = None
    model_rarity = backdrop_rarity = None
    for attr in getattr(gift, "attributes", None) or []:
        if isinstance(attr, StarGiftAttributeModel):
            model = getattr(attr, "name", None) or model
            model_rarity = _attr_rarity_permille(attr)
        elif isinstance(attr, StarGiftAttributeBackdrop):
            backdrop = getattr(attr, "name", None) or backdrop
            backdrop_rarity = _attr_rarity_permille(attr)

    collection = getattr(gift, "title", None)
    return model, backdrop, model_rarity, backdrop_rarity, collection


async def _resolve_nft_gift(client, raw, tg_client=None):
    """
    Resolve an NFT link / slug into
    (collection, model, backdrop, extras).
    extras may include pre-known rarity values + nft_url.
    """
    parsed = _parse_nft_link(raw)
    if not parsed:
        raise ValueError("Invalid NFT link.")

    slug, short_slug, number = parsed
    nft_url = f"https://t.me/nft/{slug}"
    collection, _, _ = _resolve_collection_from_slug(short_slug)

    model = backdrop = None
    model_rarity = backdrop_rarity = None

    # GetUniqueStarGift is user-only — never call it with the assistant bot.
    tg_clients = []
    for candidate in (heartless_bot, tg_client):
        if candidate is None or candidate in tg_clients:
            continue
        if candidate is asst:
            continue
        me = getattr(candidate, "me", None)
        if me is not None and getattr(me, "bot", False):
            continue
        tg_clients.append(candidate)

    # 1) MTProto unique gift lookup (preferred — no Cloudflare/HTML)
    title = None
    for tg in tg_clients:
        (
            model,
            backdrop,
            model_rarity,
            backdrop_rarity,
            title,
        ) = await _fetch_unique_star_gift_attrs(tg, slug)
        if model:
            break
    if title:
        collection = title

    # 2) Telegram NFT page HTML fallback
    if not model or not backdrop:
        (
            html_model,
            html_backdrop,
            html_model_rarity,
            html_backdrop_rarity,
            _,
        ) = await _fetch_telegram_nft_attrs(slug)
        model = model or html_model
        backdrop = backdrop or html_backdrop
        if model_rarity is None:
            model_rarity = html_model_rarity
        if backdrop_rarity is None:
            backdrop_rarity = html_backdrop_rarity

    # 3) MRKT search by gift number / slug
    items = []
    if not model or not backdrop or model_rarity is None or backdrop_rarity is None:
        try:
            page = await client.market.search(
                collection_names=[collection],
                number=number,
                ordering="None",
                low_to_high=True,
                count=5,
            )
            items = list(page.items or [])
        except Exception as e:
            LOGS.warning(
                "MRKT number search failed for %s #%s: %s: %r",
                collection,
                number,
                type(e).__name__,
                e,
            )
            items = []

        if not items:
            try:
                page = await client.market.search(
                    query=slug,
                    ordering="None",
                    low_to_high=True,
                    count=5,
                )
                items = [
                    g for g in (page.items or [])
                    if str(getattr(g, "number", "") or "") == str(number)
                    or str(getattr(g, "name", "") or "").endswith(
                        f"-{number}"
                    )
                ]
            except Exception as e:
                LOGS.warning(
                    "MRKT query search failed for %s: %s: %r",
                    slug,
                    type(e).__name__,
                    e,
                )
                items = []

    if items:
        gift = items[0]
        raw_gift = _get_raw(gift)
        model = (
            model
            or getattr(gift, "model_name", None)
            or raw_gift.get("modelName")
        )
        backdrop = (
            backdrop
            or getattr(gift, "backdrop_name", None)
            or raw_gift.get("backdropName")
        )
        if model_rarity is None:
            model_rarity = raw_gift.get("modelRarityPerMille")
        if backdrop_rarity is None:
            backdrop_rarity = raw_gift.get(
                "backdropRarityPerMille"
            )
        collection = (
            getattr(gift, "collection_name", None)
            or raw_gift.get("collectionName")
            or collection
        )

    if not model:
        raise ValueError(
            f"Could not resolve model for NFT {slug}."
        )

    return collection, model, backdrop, {
        "slug": slug,
        "number": number,
        "nft_url": nft_url,
        "model_rarity": model_rarity,
        "backdrop_rarity": backdrop_rarity,
    }


def _min_price(values):
    nums = []
    for value in values:
        if value is None or value == "":
            continue
        try:
            nums.append(Decimal(str(value)))
        except Exception:
            continue
    return min(nums) if nums else None


async def _send_purchase_log(client, gift, monitor_id):
    collection = getattr(gift, "collection_name", "Unknown")
    model = getattr(gift, "model_name", "Unknown")
    backdrop = getattr(gift, "backdrop_name", "Unknown")
    price = getattr(gift, "price_ton", "Unknown")
    gift_id = getattr(gift, "id", "Unknown")
    text = (
        "🎁 <b>Gift Purchased Successfully</b>\n\n"
        f"🆔 <b>Gift ID:</b> <code>{gift_id}</code>\n"
        f"💰 <b>Price:</b> <code>{_format_ton(price)} TON</code>\n"
        f"📦 <b>Collection:</b> <code>{collection}</code>\n"
        f"🧬 <b>Model:</b> <code>{model}</code>\n"
        f"🎨 <b>Backdrop:</b> <code>{backdrop}</code>\n"
        f"🤖 <b>Monitor:</b> <code>#{monitor_id}</code>\n"
        f"📡 <b>Log:</b> <code>{LOG_CHAT_ID}</code>"
    )
    try:
        await heartless_bot.send_message(
            LOG_CHAT_ID, text, parse_mode="html",
        )
    except Exception:
        LOGS.exception("Failed to send Artemis purchase log")


# ============================================================
# ORDERS HELPERS / COMMANDS
# ============================================================

def _order_range(order):
    lo = _ton2(nano_to_ton(order.get("priceMinNanoTONs") or 0))
    hi = _ton2(nano_to_ton(order.get("priceMaxNanoTONs") or 0))
    return f"{lo}-{hi}"


_FINISHED_STATUS_TOKENS = {
    "finished",
    "completed",
    "cancelled",
    "canceled",
    "closed",
    "expired",
    "done",
    "inactive",
    "fulfilled",
    "failed",
    "rejected",
}


def _parse_order_ts(value):
    """
    Parse order timestamps (ISO / unix sec / unix ms).

    MRKT often returns fractional seconds with 5 digits
    (e.g. 03.83569Z). Older Python fromisoformat rejects
    that, so finished orders were never filtered.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        return ts
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return _parse_order_ts(int(text))

    text = text.replace("Z", "+00:00")
    match = re.match(
        r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})"
        r"(?:\.(\d+))?(.*)$",
        text,
    )
    if match:
        base, frac, rest = match.groups()
        if frac is not None:
            frac = (frac + "000000")[:6]
            text = f"{base}.{frac}{rest or '+00:00'}"
        else:
            text = f"{base}{rest or '+00:00'}"
        if " " in base and "T" not in text[:19]:
            text = text.replace(" ", "T", 1)

    try:
        from datetime import datetime
        return datetime.fromisoformat(text).timestamp()
    except Exception:
        return None


def _order_status_text(order):
    for key in (
        "status",
        "orderStatus",
        "state",
        "orderState",
        "finishStatus",
        "executionStatus",
    ):
        val = order.get(key)
        if val is None or val == "":
            continue
        return str(val).strip().lower().replace(" ", "_")
    return ""


def _order_finished(order):
    """True when the order should not appear in `.orders`.

    Be conservative: MRKT still returns live bids that have an ``endAt``
    (scheduled lifetime). Treating past ``endAt`` as finished made orders
    vanish from ``.orders`` / autotop after a few hours even though they
    were still open on MRKT. Only definitive completion signals count.
    """
    if not isinstance(order, dict):
        return True

    for key in (
        "isFinished",
        "isCompleted",
        "isClosed",
        "isCancelled",
        "isCanceled",
        "isExpired",
        "finished",
        "completed",
        "closed",
        "cancelled",
        "canceled",
    ):
        if order.get(key) is True:
            return True

    for key in ("isActive", "active", "isOpen"):
        if key in order and order.get(key) is False:
            return True

    status = _order_status_text(order)
    if status:
        # Exact token only — substring checks like "finish" in "unfinished"
        # falsely hide active orders.
        normalized = status.replace("-", "_")
        if normalized in _FINISHED_STATUS_TOKENS:
            return True
        parts = {p for p in normalized.split("_") if p}
        if parts & _FINISHED_STATUS_TOKENS:
            return True

    total = int(
        order.get("totalQuantity")
        or order.get("quantity")
        or 0
    )
    done = int(order.get("completedQuantity") or 0)
    if total and done >= total:
        return True

    remaining = order.get("remainingQuantity")
    if remaining is not None:
        try:
            if int(remaining) <= 0 and (total > 0 or done > 0):
                return True
        except Exception:
            pass

    # Do NOT use endAt here: it is a lifetime hint, not a completion stamp.
    # An order returned by get-my-orders with remaining qty is still open
    # until MRKT sets a real finished/cancelled timestamp or flag.
    now = time.time()
    for key in (
        "finishedAt",
        "closedAt",
        "completedAt",
        "cancelledAt",
        "canceledAt",
        "expiredAt",
    ):
        ts = _parse_order_ts(order.get(key))
        if ts is not None and ts <= now:
            return True

    return False


def _order_max_nano(order_or_top):
    if not order_or_top:
        return 0
    try:
        return int(order_or_top.get("priceMaxNanoTONs") or 0)
    except Exception:
        return 0


def _order_is_highest(order, top):
    """
    True when this order's max bid is at/above the market top
    (or the top order is this same order).
    """
    my_max = _order_max_nano(order)
    if not top:
        return True
    if (
        order.get("id")
        and top.get("id")
        and str(order["id"]) == str(top["id"])
    ):
        return True
    return my_max >= _order_max_nano(top)


ORDER_TOP_STEP = Decimal("0.01")


def _ton_q2(value):
    """Quantize a TON amount to 0.01 for order price comparisons."""
    return Decimal(str(value or 0)).quantize(
        ORDER_TOP_STEP, rounding=ROUND_HALF_UP,
    )


def _order_ideal_max(competitor_top_ton, price_min_ton):
    """
    Target max = competitor top + 0.01, never below our min.
    competitor_top_ton may be None when there is no other bid.
    """
    if competitor_top_ton is None:
        ideal = _ton_q2(price_min_ton)
    else:
        ideal = _ton_q2(competitor_top_ton) + ORDER_TOP_STEP
    min_q = _ton_q2(price_min_ton)
    if ideal < min_q:
        return min_q
    return ideal


async def _competitor_top_ton(client, order, top=None):
    """
    Highest competing max bid for this order's filter (excludes this order).
    Returns Decimal TON or None if nobody else is bidding.
    """
    if top is None:
        top = await _top_order(client, order)
    my_id = str(order.get("id") or "")
    if top and _order_max_nano(top) > 0:
        top_id = str(top.get("id") or "")
        if not my_id or top_id != my_id:
            return nano_to_ton(top.get("priceMaxNanoTONs") or 0)

    # /orders/top is us (or empty) — walk the book for the next bid.
    collection = order.get("collectionName") or order.get("collectionTitle")
    if not collection:
        return None
    try:
        data = await _fetch_filter_orders_page(
            client,
            collection,
            model=order.get("modelName") or None,
            backdrop=order.get("backdropName") or None,
            count=20,
            low_to_high=False,
        )
    except Exception as e:
        LOGS.warning("Competitor order book failed: %s", e)
        return None
    orders, _, _ = _orders_list_payload(data)
    best = None
    for row in orders or []:
        if my_id and str(row.get("id") or "") == my_id:
            continue
        amount = _as_floor(nano_to_ton(row.get("priceMaxNanoTONs") or 0))
        if amount is None:
            continue
        if best is None or amount > best:
            best = amount
    return best


def _order_label(order):
    parts = [
        order.get("collectionTitle") or order.get("collectionName") or "?",
        order.get("modelName") or None,
        order.get("backdropName") or None,
    ]
    return ", ".join(p for p in parts if p)


def _require_order_uuid(value):
    value = str(value or "").strip()
    try:
        return str(UUID(value))
    except Exception as exc:
        raise ValueError(
            f"Invalid order id {value!r} (expected UUID, not list index)"
        ) from exc


async def _fetch_my_orders(client):
    """Fetch all of the account's orders, then keep only open ones.

    Paginates with a larger page size and dedupes by id so a flaky cursor
    cannot silently drop live bids from ``.orders`` / autotop.
    """
    orders = []
    seen_ids = set()
    cursor = ""
    page_size = 50
    max_pages = 40  # hard cap against a broken cursor loop
    for _ in range(max_pages):
        data = await client.request(
            "POST",
            "/orders/get-my-orders",
            json={
                "collectionNames": [],
                "modelNames": [],
                "backdropNames": [],
                "symbolNames": [],
                "minPrice": None,
                "maxPrice": None,
                "availableForStaking": None,
                "ordering": "PublicationTime",
                "lowToHigh": False,
                "query": None,
                "cursor": cursor,
                "count": page_size,
            },
        )
        batch = (data or {}).get("orders") or []
        if not batch:
            break
        new_in_page = 0
        for order in batch:
            if not isinstance(order, dict):
                continue
            oid = order.get("id")
            key = str(oid) if oid is not None else None
            if key:
                if key in seen_ids:
                    continue
                seen_ids.add(key)
            orders.append(order)
            new_in_page += 1
        next_cursor = (data or {}).get("cursor") or ""
        # Stop when API says done, page undersized, or cursor made no progress.
        if (
            not next_cursor
            or next_cursor == cursor
            or len(batch) < page_size
            or new_in_page == 0
        ):
            break
        cursor = next_cursor

    active = [order for order in orders if not _order_finished(order)]
    return active


def _store_artemis_token(token):
    """Persist token in memory + Heartless DB."""
    global ARTEMIS_TOKEN
    token = str(token or "").strip()
    if not token:
        raise ValueError("Token cannot be empty.")
    ARTEMIS_TOKEN = token
    with contextlib.suppress(Exception):
        udB.set_key("ARTEMIS_TOKEN", token)
    return token


async def _generate_token_from_session(session):
    global MRKT_API_ID, MRKT_API_HASH
    session = str(session or "").strip()
    if not session:
        raise ValueError("SESSIONMRKT is empty.")
    # Always re-read DB creds — module-level cache can be stale after setdb.
    MRKT_API_ID = udB.get_key("api_id") or MRKT_API_ID
    MRKT_API_HASH = udB.get_key("api_hash") or MRKT_API_HASH
    if not MRKT_API_ID or not MRKT_API_HASH:
        raise ValueError(
            "api_id / api_hash are missing from Heartless DB."
        )
    async with MRKTClient() as client:
        token = await client.auth.login(
            api_id=int(MRKT_API_ID),
            api_hash=str(MRKT_API_HASH),
            session="mrkt",
            session_string=session,
            bot_username="mrkt",
            platform="android",
        )
    return _store_artemis_token(token)


def _is_token_expired_error(exc):
    """True when MRKT rejects the stored Artemis token (needs SESSIONMRKT regen)."""
    if isinstance(exc, AuthError):
        return True
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(exc, "status", None)
    try:
        status = int(status) if status is not None else None
    except Exception:
        status = None
    if status in (401, 403):
        return True
    msg = str(exc or "").lower()
    if any(
        s in msg
        for s in (
            "401",
            "403",
            "unauthorized",
            "forbidden",
            "unauthenticated",
        )
    ):
        return True
    if "token" in msg and any(
        s in msg
        for s in ("expired", "invalid", "missing", "revoke", "jwt")
    ):
        return True
    if "re-authenticate" in msg or "reauthenticate" in msg:
        return True
    if "session" in msg and ("expired" in msg or "invalid" in msg):
        return True
    return False


def _sessionmrkt():
    raw = udB.get_key("SESSIONMRKT")
    text = str(raw).strip() if raw else ""
    return text or None


async def _force_refresh_token(event=None, status=None):
    """Drop expired token and mint a new one from SESSIONMRKT."""
    global ARTEMIS_TOKEN, MRKT_API_ID, MRKT_API_HASH
    async with TOKEN_LOCK:
        ARTEMIS_TOKEN = None
        with contextlib.suppress(Exception):
            udB.del_key("ARTEMIS_TOKEN")

        # Refresh api creds in case DB was updated after plugin load.
        MRKT_API_ID = udB.get_key("api_id")
        MRKT_API_HASH = udB.get_key("api_hash")

        session = _sessionmrkt()
        if not session:
            raise ValueError(
                "Artemis token expired and "
                "<code>SESSIONMRKT</code> is not set.\n\n"
                f"Use <code>{_h('buytoken')} YOUR_TOKEN</code> "
                f"or <code>{_h('gentoken')} SESSION</code>."
            )

        if event is not None:
            if status is not None:
                with contextlib.suppress(Exception):
                    status = await status.edit(
                        "<b>Token expired — regenerating from SESSIONMRKT…</b>",
                        parse_mode="html",
                    )
            else:
                with contextlib.suppress(Exception):
                    status = await event.eor(
                        "<b>Token expired — regenerating from SESSIONMRKT…</b>",
                        parse_mode="html",
                    )

        token = await _generate_token_from_session(session)
        LOGS.info("Artemis token regenerated from SESSIONMRKT after expiry")
        return token, status


async def _ensure_artemis_token(event=None, status=None):
    """
    Ensure ARTEMIS_TOKEN is available.

    Order:
      1. In-memory token
      2. udB ARTEMIS_TOKEN
      3. Generate from udB SESSIONMRKT

    Returns (token, status_message_or_None).
    """
    global ARTEMIS_TOKEN, MRKT_API_ID, MRKT_API_HASH

    async with TOKEN_LOCK:
        if ARTEMIS_TOKEN:
            return ARTEMIS_TOKEN, status

        stored = udB.get_key("ARTEMIS_TOKEN")
        if stored and str(stored).strip():
            ARTEMIS_TOKEN = str(stored).strip()
            return ARTEMIS_TOKEN, status

        MRKT_API_ID = udB.get_key("api_id")
        MRKT_API_HASH = udB.get_key("api_hash")

        session = _sessionmrkt()
        if not session:
            raise ValueError(
                "Artemis token is not configured.\n\n"
                f"Use <code>{_h('buytoken')} YOUR_TOKEN</code>\n"
                "or set DB key <code>SESSIONMRKT</code> "
                f"(and optionally run <code>{_h('gentoken')}</code>)."
            )

        if event is not None:
            if status is not None:
                status = await status.edit(
                    "<b>Generating Token from SESSIONMRKT…</b>",
                    parse_mode="html",
                )
            else:
                status = await event.eor(
                    "<b>Generating Token from SESSIONMRKT…</b>",
                    parse_mode="html",
                )

        token = await _generate_token_from_session(session)
        LOGS.info("Artemis token auto-generated from SESSIONMRKT")
        return token, status


async def _mrkt_call(event, status, runner):
    """
    Ensure token, run `runner()`, and on 401/expired regenerate from
    SESSIONMRKT once then retry.
    `runner` is an async callable with no args.
    """
    _, status = await _ensure_artemis_token(event, status)
    try:
        return await runner(), status
    except Exception as e:
        if not _is_token_expired_error(e):
            raise
        LOGS.warning("Artemis auth failed (%s); refreshing from SESSIONMRKT", e)
        _, status = await _force_refresh_token(event, status)
        try:
            return await runner(), status
        except Exception as e2:
            if _is_token_expired_error(e2):
                LOGS.error(
                    "Artemis still unauthorized after SESSIONMRKT regen: %s", e2,
                )
            raise


async def _with_mrkt(event, status, work):
    """
    Run `await work(client)` with auto token refresh on expiry.
    Always re-reads the current ARTEMIS_TOKEN after a refresh.
    Returns (result, status).
    """
    async def runner():
        token = ARTEMIS_TOKEN
        if not token:
            raise AuthError("ARTEMIS_TOKEN is empty after ensure/refresh.")
        async with MRKTClient(token=token) as client:
            return await work(client)

    return await _mrkt_call(event, status, runner)


def _star_usd_rate():
    raw = udB.get_key("STAR_USD")
    if raw is None or str(raw).strip() == "":
        return DEFAULT_STAR_USD
    try:
        amount = Decimal(str(raw))
    except Exception:
        return DEFAULT_STAR_USD
    return amount if amount > 0 else DEFAULT_STAR_USD


async def _live_ton_usdt_toman():
    """
    Live TON/USD (tonapi) + USDT/Toman (tetherland).
    Cached briefly to keep `{i}p` snappy.
    """
    now = time.monotonic()
    if (
        _RATE_CACHE["ton_usd"] is not None
        and _RATE_CACHE["usdt_toman"] is not None
        and now - _RATE_CACHE["at"] < _RATE_CACHE_TTL
    ):
        return _RATE_CACHE["ton_usd"], _RATE_CACHE["usdt_toman"]

    ton_usd = None
    usdt_toman = None
    timeout = aiohttp.ClientTimeout(total=15, connect=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(
                "https://tonapi.io/v2/rates",
                params={"tokens": "ton", "currencies": "usd"},
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    ton_usd = Decimal(
                        str(data["rates"]["TON"]["prices"]["USD"])
                    )
        except Exception as e:
            LOGS.warning("TON/USD rate fetch failed: %s", e)

        try:
            async with session.get(
                "https://api.tetherland.com/currencies",
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    usdt_toman = Decimal(
                        str(
                            data["data"]["currencies"]["USDT"]["price"]
                        )
                    )
        except Exception as e:
            LOGS.warning("USDT/Toman rate fetch failed: %s", e)

    if ton_usd is None or usdt_toman is None:
        raise ValueError("Could not fetch live TON / Toman rates.")

    _RATE_CACHE["at"] = now
    _RATE_CACHE["ton_usd"] = ton_usd
    _RATE_CACHE["usdt_toman"] = usdt_toman
    return ton_usd, usdt_toman


def _fmt_toman(amount):
    try:
        n = int(Decimal(str(amount)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        return "—"
    return f"{n:,}"


def _fmt_amount(amount, places="0.01"):
    try:
        d = Decimal(str(amount)).quantize(
            Decimal(places), rounding=ROUND_HALF_UP,
        )
    except Exception:
        return "—"
    text = f"{d:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _fmt_usdt(amount):
    return _fmt_amount(amount, "0.01")


def _fmt_stars(amount):
    """Whole stars only (no decimals)."""
    try:
        n = int(
            Decimal(str(amount)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    except Exception:
        return "—"
    return f"{n}"


async def _price_convert_message(amount, src, dst=None):
    """
    Convert / price amount in ton, stars, usdt, or tomans (`t`).

    - src can be ton, stars, usdt, or toman.
    - dst is None (`.p ton`, `.p 50 stars`, `.p 1 usdt`): IRT + USDT only
    - dst set (`.p 50 ton stars`, `.p 1000 stars usdt`, `.p 5 usdt ton`):
      conversion line + IRT + USDT
    - toman source (`.p 1000000 t ton|usdt|stars`): conversion only —
      no Tomans equivalent line in the output.
    Stars are rounded to whole numbers when shown as converted output.
    """
    src = src.lower()
    show_convert = dst is not None
    if dst:
        dst = dst.lower()
    else:
        dst = "stars" if src == "ton" else ("ton" if src == "stars" else "usdt")

    ton_usd, usdt_toman = await _live_ton_usdt_toman()
    star_usd = _star_usd_rate()
    ton_toman = ton_usd * usdt_toman

    def _value_block(irt, usdt, show_usdt=True):
        if show_usdt:
            return (
                f"🇮🇷 <b>IRT:</b> <code>{_fmt_toman(irt)}</code> Tomans\n"
                f"💲 <b>USDT:</b> <code>{_fmt_usdt(usdt)}</code> $"
            )
        return (
            f"🇮🇷 <b>IRT:</b> <code>{_fmt_toman(irt)}</code> Tomans"
        )

    if src == "toman":
        if not show_convert or dst not in ("ton", "usdt", "stars"):
            raise ValueError("Supported: t→ton/usdt/stars only.")
        usdt = amount / usdt_toman
        if dst == "usdt":
            return (
                "💱 <b>Price Convert</b>\n\n"
                f"🇮🇷 <b>{_fmt_toman(amount)} Tomans</b> → "
                f"💲 <b>{_fmt_usdt(usdt)} USDT</b>"
            )
        if dst == "ton":
            tons = usdt / ton_usd
            return (
                "💱 <b>Price Convert</b>\n\n"
                f"🇮🇷 <b>{_fmt_toman(amount)} Tomans</b> → "
                f"💎 <b>{_fmt_amount(tons)} TON</b>"
            )
        stars = usdt / star_usd
        stars_i = Decimal(
            stars.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        return (
            "💱 <b>Price Convert</b>\n\n"
            f"🇮🇷 <b>{_fmt_toman(amount)} Tomans</b> → "
            f"⭐ <b>{_fmt_stars(stars_i)} Stars</b>"
        )

    if src == "ton":
        irt = amount * ton_toman
        usdt = amount * ton_usd
        if not show_convert:
            return (
                "💱 <b>Price Convert</b>\n\n"
                f"💎 <b>{_fmt_amount(amount)} TON</b>\n\n"
                f"{_value_block(irt, usdt)}"
            )
        if dst == "usdt":
            return (
                "💱 <b>Price Convert</b>\n\n"
                f"💎 <b>{_fmt_amount(amount)} TON</b> → "
                f"💲 <b>{_fmt_usdt(usdt)} USDT</b>\n\n"
                f"{_value_block(irt, usdt)}"
            )
        stars = (amount * ton_usd) / star_usd
        stars_i = Decimal(
            stars.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        return (
            "💱 <b>Price Convert</b>\n\n"
            f"💎 <b>{_fmt_amount(amount)} TON</b> → "
            f"⭐ <b>{_fmt_stars(stars_i)} Stars</b>\n\n"
            f"{_value_block(irt, usdt)}"
        )

    if src == "stars":
        stars_i = Decimal(
            Decimal(str(amount)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        irt = stars_i * star_usd * usdt_toman
        usdt = stars_i * star_usd
        if not show_convert:
            return (
                "💱 <b>Price Convert</b>\n\n"
                f"⭐ <b>{_fmt_stars(stars_i)} Stars</b>\n\n"
                f"{_value_block(irt, usdt)}"
            )
        if dst == "usdt":
            return (
                "💱 <b>Price Convert</b>\n\n"
                f"⭐ <b>{_fmt_stars(stars_i)} Stars</b> → "
                f"💲 <b>{_fmt_usdt(usdt)} USDT</b>\n\n"
                f"{_value_block(irt, usdt)}"
            )
        tons = (stars_i * star_usd) / ton_usd
        return (
            "💱 <b>Price Convert</b>\n\n"
            f"⭐ <b>{_fmt_stars(stars_i)} Stars</b> → "
            f"💎 <b>{_fmt_amount(tons)} TON</b>\n\n"
            f"{_value_block(irt, usdt)}"
        )

    if src == "usdt":
        irt = amount * usdt_toman
        usdt = amount
        tons = amount / ton_usd
        stars = amount / star_usd
        stars_i = Decimal(
            stars.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        if not show_convert:
            return (
                "💱 <b>Price Convert</b>\n\n"
                f"💲 <b>{_fmt_usdt(amount)} USDT</b>\n\n"
                f"{_value_block(irt, usdt, show_usdt=False)}"
            )
        if dst == "ton":
            return (
                "💱 <b>Price Convert</b>\n\n"
                f"💲 <b>{_fmt_usdt(amount)} USDT</b> → "
                f"💎 <b>{_fmt_amount(tons)} TON</b>\n\n"
                f"{_value_block(irt, usdt, show_usdt=False)}"
            )
        if dst == "stars":
            return (
                "💱 <b>Price Convert</b>\n\n"
                f"💲 <b>{_fmt_usdt(amount)} USDT</b> → "
                f"⭐ <b>{_fmt_stars(stars_i)} Stars</b>\n\n"
                f"{_value_block(irt, usdt, show_usdt=False)}"
            )
        raise ValueError("Supported: usdt→ton/stars only.")

    raise ValueError("Supported: ton↔stars↔usdt↔t only.")


def _parse_price_query(raw):
    """
    Parse:
      ton / stars / usdt
      5 ton / 50 stars / 5 usdt
      50 ton stars / 1000 stars ton / 5 usdt ton
      1000000 t ton / 1000000 t usdt / 1000000 t stars
    Returns (amount: Decimal, src, dst|None).
    """
    parts = [p for p in str(raw or "").strip().split() if p]
    if not parts:
        raise ValueError("empty")

    def _unit(word):
        w = word.lower()
        if w in ("ton", "tons"):
            return "ton"
        if w in ("stars", "star"):
            return "stars"
        if w in ("usdt", "usdts", "tether"):
            return "usdt"
        if w in ("t", "toman", "tomans", "irt"):
            return "toman"
        return None

    # ton / stars / usdt  → amount 1  (tomans alone not supported)
    if len(parts) == 1:
        unit = _unit(parts[0])
        if not unit or unit == "toman":
            raise ValueError("bad")
        return Decimal("1"), unit, None

    # 5 ton / 50 stars / 5 usdt  (not `5 t` — destination required)
    if len(parts) == 2:
        u0, u1 = _unit(parts[0]), _unit(parts[1])
        if u0 == "toman" or u1 == "toman":
            raise ValueError("bad")
        if u0 and not u1:
            try:
                amount = Decimal(str(parts[1]).replace(",", ""))
            except Exception as e:
                raise ValueError("bad") from e
            return amount, u0, None
        if not u0 and u1:
            try:
                amount = Decimal(str(parts[0]).replace(",", ""))
            except Exception as e:
                raise ValueError("bad") from e
            return amount, u1, None
        raise ValueError("bad")

    # 50 ton stars / 1000 stars ton / 5 usdt ton / 1000000 t ton
    if len(parts) == 3:
        u1, u2 = _unit(parts[1]), _unit(parts[2])
        if not u1 or not u2 or u1 == u2:
            raise ValueError("bad")
        # Tomans may only be the source: `AMOUNT t ton|usdt|stars`
        if u2 == "toman":
            raise ValueError("bad")
        if u1 == "toman" and u2 not in ("ton", "usdt", "stars"):
            raise ValueError("bad")
        try:
            amount = Decimal(str(parts[0]).replace(",", ""))
        except Exception as e:
            raise ValueError("bad") from e
        return amount, u1, u2

    raise ValueError("bad")


async def _top_order(client, order_or_filter):
    """
    POST /orders/top for a filter.

    MRKT returns HTTP 400 for some filter shapes (expired attrs, empty
    model/backdrop combos). Treat those as \"no top\" instead of aborting
    orderup mid-flight — callers must not cancel when this returns None
    due to a hard failure they did not already handle.
    """
    body = {
        "collectionName": order_or_filter.get("collectionName") or None,
        "modelName": order_or_filter.get("modelName") or None,
        "backdropName": order_or_filter.get("backdropName") or None,
        "symbolName": order_or_filter.get("symbolName") or None,
    }
    try:
        return await client.request("POST", "/orders/top", json=body)
    except RequestError as e:
        status = getattr(e, "status", None) or getattr(e, "status_code", None)
        msg = str(e)
        if status == 400 or "HTTP 400" in msg or "400" in msg[:40]:
            LOGS.warning(
                "orders/top HTTP 400 for %s / %s / %s — treating as no top",
                body.get("collectionName"),
                body.get("modelName"),
                body.get("backdropName"),
            )
            return None
        raise


def _parse_order_filter(raw):
    """Parse `.order Collection[, Model[, Backdrop]]`."""
    parts = [part.strip() for part in str(raw or "").split(",")]
    parts = [p for p in parts if p]
    if len(parts) == 1:
        return parts[0], None, None
    if len(parts) == 2:
        return parts[0], parts[1], None
    if len(parts) == 3:
        collection, model, backdrop = parts
        if backdrop.lower() in ("any", "none", "null", "*", "-"):
            backdrop = None
        return collection, model, backdrop
    raise ValueError(
        "Usage:\n"
        f"{_h('order')} Collection\n"
        f"{_h('order')} Collection, Model\n"
        f"{_h('order')} Collection, Model, Backdrop"
    )


def _orders_list_payload(data):
    """Normalize POST /orders response into (orders, cursor, total_hint)."""
    if data is None:
        return [], "", None
    if isinstance(data, list):
        return data, "", len(data)
    if not isinstance(data, dict):
        return [], "", None
    orders = data.get("orders")
    if orders is None:
        orders = data.get("items") or data.get("data") or []
    if not isinstance(orders, list):
        orders = []
    cursor = data.get("cursor") or ""
    total_hint = None
    for key in ("totalCount", "total", "totalOrders", "ordersCount"):
        if key in data and data.get(key) is not None:
            try:
                total_hint = int(data.get(key))
                break
            except Exception:
                pass
    return orders, cursor, total_hint


async def _fetch_filter_orders_page(
    client,
    collection,
    model=None,
    backdrop=None,
    *,
    count=20,
    cursor="",
    low_to_high=False,
):
    """
    Public buy-order book for a filter.

    Artemis SDK has no orders.list — use MRKT POST /orders directly
    (same route as tgmrkts Orders.list).
    """
    body = {
        "collectionNames": [collection] if collection else [],
        "modelNames": [model] if model else [],
        "backdropNames": [backdrop] if backdrop else [],
        "symbolNames": [],
        "availableForStaking": None,
        "minPrice": None,
        "maxPrice": None,
        "ordering": "Price",
        "lowToHigh": bool(low_to_high),
        "query": None,
        "cursor": cursor or "",
        "count": int(count),
    }
    return await client.request("POST", "/orders", json=body)


async def _fetch_filter_order_book(
    client,
    collection,
    model=None,
    backdrop=None,
    *,
    top_n=5,
):
    """
    Return (total_count, top_order, top_n_orders) for a gift filter.

    Highest first via ordering=Price, lowToHigh=False.
    """
    filt = {
        "collectionName": collection,
        "modelName": model,
        "backdropName": backdrop,
        "symbolName": None,
    }
    top_task = asyncio.create_task(_top_order(client, filt))
    first_task = asyncio.create_task(
        _fetch_filter_orders_page(
            client,
            collection,
            model=model,
            backdrop=backdrop,
            count=max(int(top_n), 5),
            cursor="",
            low_to_high=False,
        )
    )
    top, first = await asyncio.gather(top_task, first_task)
    orders, cursor, total_hint = _orders_list_payload(first)
    top_orders = list(orders[:top_n])

    if total_hint is not None and (
        not cursor or total_hint <= len(orders)
    ):
        return total_hint, top, top_orders

    total = len(orders)
    # Paginate remaining pages for an accurate offer count.
    while cursor:
        page = await _fetch_filter_orders_page(
            client,
            collection,
            model=model,
            backdrop=backdrop,
            count=20,
            cursor=cursor,
            low_to_high=False,
        )
        batch, cursor, page_total = _orders_list_payload(page)
        if page_total is not None and page_total >= total:
            return page_total, top, top_orders
        total += len(batch)
        if not cursor or len(batch) < 20:
            break
    if total_hint is not None and total_hint > total:
        total = total_hint
    return total, top, top_orders


def _format_order_book_message(
    collection,
    model,
    backdrop,
    total,
    top,
    top_orders,
):
    label_parts = [collection]
    if model:
        label_parts.append(model)
    if backdrop:
        label_parts.append(backdrop)
    label = ", ".join(label_parts)
    highest = _order_range(top) if top else "—"
    lines = [
        f"📊 <b>Order book</b>",
        f"📦 <code>{html.escape(label)}</code>",
        "",
        f"🔢 <b>Total orders:</b> <code>{total}</code>",
        f"🏆 <b>Highest:</b> <code>{highest} TON</code>",
        "",
        "🔝 <b>Top 5</b>",
    ]
    if not top_orders:
        lines.append("   —")
    else:
        for i, order in enumerate(top_orders[:5], 1):
            qty = (
                order.get("remainingQuantity")
                if order.get("remainingQuantity") is not None
                else (
                    order.get("quantity")
                    or order.get("totalQuantity")
                )
            )
            qty_bit = (
                f" · qty {qty}" if qty not in (None, "") else ""
            )
            lines.append(
                f"   {i}. <code>{_order_range(order)} TON</code>"
                f"{qty_bit}"
            )
    return "\n".join(lines)


def _order_model_backdrop_label(order):
    """Model + backdrop for collection-wide top lists."""
    if not isinstance(order, dict):
        return "?, ?"
    model = order.get("modelName") or order.get("modelTitle") or "ANY"
    backdrop = (
        order.get("backdropName")
        or order.get("backdropTitle")
        or "ANY"
    )
    return f"{model}, {backdrop}"


async def _list_collection_model_names(client, collection):
    """All model names for a collection from MRKT /gifts/models."""
    try:
        data = await client.request(
            "POST",
            "/gifts/models",
            json={"collections": [collection]},
        )
    except Exception as e:
        LOGS.warning("ordertop models fetch failed: %s", e)
        return []
    names = []
    seen = set()
    for row in data or []:
        if not isinstance(row, dict):
            continue
        name = row.get("modelName") or row.get("name")
        if not name:
            continue
        key = _loose_key(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _order_is_active_open(order):
    """True when the order is still open (not finished / fully filled)."""
    if not isinstance(order, dict) or not order:
        return False
    if _order_finished(order):
        return False
    if _order_max_nano(order) <= 0:
        return False
    remaining = order.get("remainingQuantity")
    if remaining is not None:
        try:
            if int(remaining) <= 0:
                return False
        except Exception:
            pass
    return True


# Throttle ordertop fan-out so MRKT does not 429 the whole scan.
_ORDERTOP_LOCK = asyncio.Lock()
_ORDERTOP_NEXT_AT = 0.0
_ORDERTOP_MIN_INTERVAL = 0.45  # ~2 req/s
_ORDERTOP_CONCURRENCY = 2
_ORDERTOP_RETRIES = 5


def _is_rate_limited(exc):
    if getattr(exc, "status_code", None) == 429:
        return True
    text = str(exc or "").lower()
    return "429" in text or "too many requests" in text


async def _ordertop_acquire_slot():
    """Serialize ordertop API calls with a minimum spacing."""
    global _ORDERTOP_NEXT_AT
    async with _ORDERTOP_LOCK:
        now = time.monotonic()
        wait = _ORDERTOP_NEXT_AT - now
        if wait > 0:
            await asyncio.sleep(wait)
        _ORDERTOP_NEXT_AT = time.monotonic() + _ORDERTOP_MIN_INTERVAL


async def _ordertop_request(factory):
    """
    Run one ordertop MRKT call with slotting + 429 backoff.
    factory: zero-arg async callable that performs the request.
    """
    last = None
    for attempt in range(_ORDERTOP_RETRIES):
        await _ordertop_acquire_slot()
        try:
            return await factory()
        except Exception as e:
            last = e
            if not _is_rate_limited(e) or attempt >= _ORDERTOP_RETRIES - 1:
                raise
            delay = min(8.0, (2 ** attempt) * 0.6)
            await asyncio.sleep(delay)
    raise last


async def _highest_active_order_for_model(client, collection, model):
    """
    Highest active buy order for collection + model (any backdrop).
    Uses POST /orders (model filter) so model/backdrop/qty are present —
    collection-only /orders returns wildcard ANY/ANY bids.
    """
    async def _list():
        return await _fetch_filter_orders_page(
            client,
            collection,
            model=model,
            backdrop=None,
            count=10,
            cursor="",
            low_to_high=False,
        )

    data = await _ordertop_request(_list)
    orders, _, _ = _orders_list_payload(data)
    for order in orders:
        if not _order_is_active_open(order):
            continue
        oname = order.get("modelName") or order.get("modelTitle")
        # Skip collection-wide wildcards that ignore the model filter.
        if not oname:
            order = dict(order)
            order["modelName"] = model
        elif not _match_attr(oname, model):
            continue
        return order

    async def _top():
        return await _top_order(
            client,
            {
                "collectionName": collection,
                "modelName": model,
                "backdropName": None,
                "symbolName": None,
            },
        )

    top = await _ordertop_request(_top)
    if not _order_is_active_open(top):
        return None
    if not (top.get("modelName") or top.get("modelTitle")):
        top = dict(top)
        top["modelName"] = model
    return top


async def _fetch_collection_top_orders(client, collection, *, top_n=10):
    """
    Top N highest active offers across all models of a collection.

    For each model, take its highest open order, then rank those globally.
    Rate-limited to avoid MRKT HTTP 429 storms.
    """
    models = await _list_collection_model_names(client, collection)
    if not models:
        return []

    sem = asyncio.Semaphore(_ORDERTOP_CONCURRENCY)
    skipped_429 = 0
    skipped_other = 0

    async def _one(model):
        nonlocal skipped_429, skipped_other
        async with sem:
            try:
                return await _highest_active_order_for_model(
                    client, collection, model,
                )
            except Exception as e:
                if _is_rate_limited(e):
                    skipped_429 += 1
                else:
                    skipped_other += 1
                    LOGS.debug(
                        "ordertop highest for %s / %s failed: %s",
                        collection, model, e,
                    )
                return None

    results = await asyncio.gather(*[_one(m) for m in models])
    #if skipped_429 or skipped_other:
        #LOGS.info(
            #"ordertop %s: scanned %s models, skipped 429=%s other=%s",
            #collection,
            #len(models),
            #skipped_429,
            #skipped_other,
        #)

    best = []
    seen = set()
    for order in results:
        if not order:
            continue
        oid = order.get("id")
        if oid:
            key = ("id", str(oid))
        else:
            key = (
                "mb",
                _loose_key(order.get("modelName") or ""),
                _loose_key(order.get("backdropName") or ""),
                _order_max_nano(order),
            )
        if key in seen:
            continue
        seen.add(key)
        best.append(order)

    best.sort(key=_order_max_nano, reverse=True)
    return best[:top_n]


def _order_qty_text(order):
    """Human qty for public order rows (remaining/total when known)."""
    if not isinstance(order, dict):
        return "—"
    total = int(
        order.get("totalQuantity")
        or order.get("quantity")
        or 0
    )
    done = int(order.get("completedQuantity") or 0)
    remaining = order.get("remainingQuantity")
    if remaining is not None:
        try:
            rem = int(remaining)
        except Exception:
            rem = None
    else:
        rem = max(total - done, 0) if total else None
    if total and rem is not None:
        return f"{rem}/{total}"
    if rem is not None:
        return str(rem)
    if total:
        return str(total)
    return "—"


def _format_ordertop_message(collection, orders):
    lines = [
        "🏆 <b>Top 10 orders</b>",
        "",
        f"📦 <b>Collection:</b> {html.escape(collection)}",
        "",
    ]
    if not orders:
        lines.append("   —")
        return "\n".join(lines)
    for i, order in enumerate(orders[:10], 1):
        combo = html.escape(_order_model_backdrop_label(order))
        price = _order_range(order)
        qty = _order_qty_text(order)
        lines.append(
            f"<b>{i}.</b> <code>{combo}</code>\n"
            f"    💰 <code>{price} TON</code>\n"
            f"    🔢 Qty: <code>{qty}</code>"
        )
    return "\n".join(lines)


async def _create_order(
    client, *, collection, model, backdrop, price_min_ton, price_max_ton,
    quantity=1, symbol=None,
):
    """Create MRKT order — omit null optional filters (ASP.NET 400 otherwise)."""
    body = {
        "collectionName": collection,
        "priceMinNanoTONs": int(ton_to_nano(price_min_ton)),
        "priceMaxNanoTONs": int(ton_to_nano(price_max_ton)),
        "quantity": max(int(quantity), 1),
        "isTransferable": True,
    }
    if model:
        body["modelName"] = model
    if backdrop:
        body["backdropName"] = backdrop
    if symbol:
        body["symbolName"] = symbol
    return await client.request("POST", "/orders/create", json=body)


async def _cancel_order(client, order_id):
    oid = _require_order_uuid(order_id)
    return await client.request(
        "POST",
        f"/orders/cancel/{oid}",
        headers={"Content-Type": "application/json"},
    )


def _parse_ordernew(value):
    parts = [part.strip() for part in value.split(",")]
    if len(parts) == 5:
        collection, model, backdrop, qty_raw, price = parts
        if not qty_raw.isdigit() or int(qty_raw) < 1:
            raise ValueError("Quantity must be a positive integer.")
        quantity = int(qty_raw)
    elif len(parts) == 4:
        collection, model, backdrop, price = parts
        quantity = 1
    elif len(parts) == 3:
        collection, model, price = parts
        backdrop = None
        quantity = 1
    else:
        raise ValueError(
            "Usage:\n"
            f"{_h('ordernew')} Collection, Model, Backdrop, QTY, MIN-MAX\n"
            f"{_h('ordernew')} Collection, Model, Backdrop, MIN-MAX\n"
            f"{_h('ordernew')} Collection, Model, MIN-MAX\n"
            f"{_h('ordernew')}  (reply to / paste an .orders list)"
        )
    if not collection or not model:
        raise ValueError("Collection and Model cannot be empty.")
    if not backdrop or backdrop.lower() in ("any", "none", "null", "*", "-"):
        backdrop = None
    if "-" not in price:
        raise ValueError("Price must be MIN-MAX, e.g. 0.5-4.6")
    lo, hi = [part.strip() for part in price.split("-", 1)]
    min_ton = _parse_ton(lo)
    max_ton = _parse_ton(hi)
    if min_ton > max_ton:
        raise ValueError("Minimum price cannot be greater than maximum price.")
    return collection, model, backdrop, quantity, min_ton, max_ton


def _looks_like_orders_list(text: str) -> bool:
    """True when text looks like a pasted `.orders` dump."""
    raw = _normalize_orders_list_text(text)
    if not raw.strip():
        return False
    if re.search(r"(?im)^\s*\d+\.\s+.+,", raw) and (
        "💰" in raw
        or re.search(r"(?i)\b\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\s*TON\b", raw)
    ):
        return True
    if re.search(r"(?i)active\s+orders", raw) and (
        "💰" in raw or re.search(r"(?i)\d+\s*-\s*\d+.*TON", raw)
    ):
        return True
    return False


def _normalize_orders_list_text(text: str) -> str:
    """Flatten HTML / entities from a replied `.orders` message."""
    raw = str(text or "")
    raw = re.sub(r"(?is)^\s*(?:\.|/)?ordernew\b", "", raw).strip()
    raw = re.sub(r"(?is)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?is)</(?:p|div|h\d|li|tr)>", "\n", raw)
    raw = re.sub(r"(?is)<[^>]+>", "", raw)
    raw = (
        raw.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
        .replace("&nbsp;", " ")
        .replace("\xa0", " ")
        .replace("\u200b", "")
    )
    # Collapse fancy spaces but keep newlines.
    raw = re.sub(r"[^\S\n]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def _parse_orders_list_bulk(text: str) -> list[dict]:
    """
    Parse a pasted `.orders` message into create-specs.

    Expects blocks like::

        1. Lucky Locket, Beauty Beast, Fire Engine
           💰 0.50-39.10 TON ✅
           📊 Max: 0.50-39.09 TON
           🔢 Qty: 0/1
           🆔 0ae3d6ba-...
    """
    raw = _normalize_orders_list_text(text)

    # Split into numbered entries.
    parts = re.split(r"(?m)(?=^\s*\d+\.\s+)", raw)
    out = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.match(
            r"(?ms)^\s*(\d+)\.\s*(.+?)\s*$",
            part.split("\n", 1)[0],
        )
        if not m:
            continue
        idx = int(m.group(1))
        label = m.group(2).strip()
        # Drop trailing status marks from the title line.
        label = re.sub(r"\s*[✅❌✔️]?\s*$", "", label).strip()
        label_parts = [p.strip() for p in label.split(",") if p.strip()]
        if len(label_parts) < 2:
            continue
        collection = label_parts[0]
        model = label_parts[1]
        backdrop = label_parts[2] if len(label_parts) >= 3 else None
        if backdrop and backdrop.lower() in ("any", "none", "null", "*", "-"):
            backdrop = None

        price_m = re.search(
            r"💰\s*([\d.,]+)\s*-\s*([\d.,]+)\s*TON",
            part,
            flags=re.I,
        )
        if not price_m:
            price_m = re.search(
                r"(?i)(?:^|\n)\s*([\d.,]+)\s*-\s*([\d.,]+)\s*TON",
                part,
            )
        if not price_m:
            continue
        try:
            lo = _parse_ton(price_m.group(1).replace(",", ""))
            hi = _parse_ton(price_m.group(2).replace(",", ""))
        except Exception:
            continue
        if lo > hi:
            lo, hi = hi, lo

        qty = 1
        qty_m = re.search(r"🔢\s*Qty:\s*(\d+)\s*/\s*(\d+)", part, flags=re.I)
        if not qty_m:
            qty_m = re.search(r"(?i)Qty:\s*(\d+)\s*/\s*(\d+)", part)
        if qty_m:
            done = int(qty_m.group(1))
            total = int(qty_m.group(2))
            qty = max(total - done, 1)

        oid = None
        oid_m = re.search(
            r"🆔\s*(?:<code>)?([0-9a-fA-F-]{36})",
            part,
        )
        if not oid_m:
            oid_m = re.search(
                r"(?i)\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                r"[0-9a-f]{4}-[0-9a-f]{12})\b",
                part,
            )
        if oid_m:
            oid = oid_m.group(1)

        out.append(
            {
                "index": idx,
                "collection": collection,
                "model": model,
                "backdrop": backdrop,
                "quantity": qty,
                "price_min": float(lo),
                "price_max": float(hi),
                "id": oid,
                "label": ", ".join(
                    p for p in (collection, model, backdrop) if p
                ),
            }
        )
    if not out:
        raise ValueError(
            "Could not parse any orders from that text.\n"
            "Paste or reply to an `.orders` list."
        )
    # Keep original numbering order.
    out.sort(key=lambda r: r["index"])
    return out


def _live_order_ids(orders) -> set[str]:
    ids = set()
    for order in orders or []:
        if not isinstance(order, dict):
            continue
        oid = order.get("id")
        if oid:
            ids.add(str(oid).lower())
    return ids


def _live_order_keys(orders) -> set[str]:
    keys = set()
    for order in orders or []:
        if not isinstance(order, dict):
            continue
        try:
            keys.add(_order_snapshot(order)["key"])
        except Exception:
            continue
    return keys


async def _get_cached_order(idx):
    global ORDER_CACHE
    if not ORDER_CACHE:
        async with MRKTClient(token=ARTEMIS_TOKEN) as client:
            ORDER_CACHE = await _fetch_my_orders(client)
    if idx < 1 or idx > len(ORDER_CACHE):
        return None
    order = ORDER_CACHE[idx - 1]
    if not order.get("id"):
        raise ValueError(
            f"Order #{idx} has no id field: keys={list(order.keys())}"
        )
    return order


def _parse_order_indices(raw):
    """
    Parse `.orderdel 1` / `.orderdel 1, 2, 3` into unique 1-based indexes.
    Preserves first-seen order.
    """
    text = str(raw or "").strip()
    if not text:
        raise ValueError("empty")
    parts = [p.strip() for p in re.split(r"[\s,]+", text) if p.strip()]
    if not parts:
        raise ValueError("empty")
    indexes = []
    seen = set()
    for part in parts:
        if not part.isdigit():
            raise ValueError(part)
        idx = int(part)
        if idx < 1:
            raise ValueError(part)
        if idx in seen:
            continue
        seen.add(idx)
        indexes.append(idx)
    return indexes


def _chunk_html(text, limit=3500):
    """Split long Telegram HTML into chunks under the 4096-char cap."""
    text = str(text or "").rstrip()
    if not text:
        return [""]
    if len(text) <= limit:
        return [text]

    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        cut = text.rfind("\n\n", 0, limit)
        if cut < limit // 3:
            cut = text.rfind("\n", 0, limit)
        if cut < limit // 3:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    return chunks or [""]


async def _edit_chunks(status, event, text, parse_mode="html"):
    """Edit status with the first chunk; send any overflow as follow-ups."""
    chunks = _chunk_html(text)
    await status.edit(chunks[0], parse_mode=parse_mode)
    for chunk in chunks[1:]:
        await event.respond(chunk, parse_mode=parse_mode, link_preview=False)
    return status


async def _artemis_ordertop_handler(event):
    """Top 10 highest buy offers across all models of a collection."""
    raw = (event.pattern_match.group(1) or "").strip()
    if not raw:
        return await event.eor(
            "Usage:\n"
            f"<code>{_h('ordertop')} Collection</code>\n\n"
            "Example:\n"
            f"<code>{_h('ordertop')} Liberty Figure</code>",
            parse_mode="html",
        )
    # Collection only — ignore accidental commas.
    collection = raw.split(",")[0].strip()
    if not collection:
        return await event.eor(
            f"❌ Collection name is required.\n"
            f"Usage: <code>{_h('ordertop')} Collection</code>",
            parse_mode="html",
        )

    status = None
    try:
        status = await event.eor(
            "<b>Fetching top orders...</b>",
            parse_mode="html",
        )

        async def work(client):
            coll, _, _ = await _resolve_gift_names(
                client, collection, None, None,
            )
            if not coll:
                raise ValueError(
                    "Could not resolve collection name on MRKT."
                )
            orders = await _fetch_collection_top_orders(
                client, coll, top_n=10,
            )
            return _format_ordertop_message(coll, orders)

        message, status = await _with_mrkt(event, status, work)
        return await _edit_chunks(status, event, message)
    except ValueError as e:
        if status:
            return await status.edit(
                f"❌ <b>{html.escape(str(e))}</b>",
                parse_mode="html",
            )
        return await event.eor(
            f"❌ <b>{html.escape(str(e))}</b>",
            parse_mode="html",
        )
    except (TradingError, RequestError, AuthError) as e:
        LOGS.warning("Artemis .ordertop request error: %s", e)
        if status:
            return await status.edit(
                f"❌ <b>Artemis request failed.</b>\n\n<code>{e}</code>",
                parse_mode="html",
            )
        return await event.eor(
            f"❌ <b>Artemis request failed.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )
    except Exception as e:
        LOGS.exception("Artemis .ordertop failed: %s", e)
        if status:
            return await status.edit(
                f"❌ <b>Failed to fetch top orders.</b>\n\n<code>{e}</code>",
                parse_mode="html",
            )
        return await event.eor(
            f"❌ <b>Failed to fetch top orders.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )


async def _artemis_order_book_handler(event):
    """Public MRKT order book for a collection / model / backdrop filter."""
    raw = event.pattern_match.group(1)
    if not raw:
        return await event.eor(
            "Usage:\n"
            f"<code>{_h('order')} Collection</code>\n"
            f"<code>{_h('order')} Collection, Model</code>\n"
            f"<code>{_h('order')} Collection, Model, Backdrop</code>",
            parse_mode="html",
        )
    try:
        collection, model, backdrop = _parse_order_filter(raw.strip())
    except ValueError as e:
        return await event.eor(
            f"❌ <code>{html.escape(str(e))}</code>",
            parse_mode="html",
        )

    status = None
    try:
        status = await event.eor(
            "<b>Fetching order book...</b>",
            parse_mode="html",
        )

        async def work(client):
            coll, mod, back = await _resolve_gift_names(
                client, collection, model, backdrop,
            )
            if not coll:
                raise ValueError("Could not resolve collection name on MRKT.")
            if model and not mod:
                raise ValueError("Could not resolve model name on MRKT.")
            total, top, top_orders = await _fetch_filter_order_book(
                client, coll, model=mod, backdrop=back, top_n=5,
            )
            return _format_order_book_message(
                coll, mod, back, total, top, top_orders,
            )

        message, status = await _with_mrkt(event, status, work)
        return await _edit_chunks(status, event, message)
    except ValueError as e:
        if status:
            return await status.edit(
                f"❌ <b>{html.escape(str(e))}</b>",
                parse_mode="html",
            )
        return await event.eor(
            f"❌ <b>{html.escape(str(e))}</b>",
            parse_mode="html",
        )
    except (TradingError, RequestError, AuthError) as e:
        LOGS.warning("Artemis .order request error: %s", e)
        if status:
            return await status.edit(
                f"❌ <b>Artemis request failed.</b>\n\n<code>{e}</code>",
                parse_mode="html",
            )
        return await event.eor(
            f"❌ <b>Artemis request failed.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )
    except Exception as e:
        LOGS.exception("Artemis .order failed: %s", e)
        if status:
            return await status.edit(
                f"❌ <b>Failed to fetch order book.</b>\n\n<code>{e}</code>",
                parse_mode="html",
            )
        return await event.eor(
            f"❌ <b>Failed to fetch order book.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )


@heartless_cmd(owner_only=True, pattern=r"ordertop(?:\s+(.+))?$")
async def artemis_ordertop(event):
    await _artemis_ordertop_handler(event)


@heartless_cmd(owner_only=True, pattern=r"order(?:\s+(.+))?$")
async def artemis_order_book(event):
    await _artemis_order_book_handler(event)


@heartless_cmd(owner_only=True, pattern=r"orders$")
async def artemis_orders(event):
    global ORDER_CACHE
    status = None
    try:
        status = await event.eor("<b>Processing...</b>", parse_mode="html")

        async def work(client):
            global ORDER_CACHE
            orders = await _fetch_my_orders(client)
            ORDER_CACHE = orders
            _autotop_orders_sync_live(orders, trusted=bool(orders))
            if not orders:
                return None
            lines = [
                f"📋 <b>Active Orders</b> ({len(orders)})",
                "",
            ]
            for i, order in enumerate(orders, 1):
                top = await _top_order(client, order)
                my_range = _order_range(order)
                max_range = _order_range(top) if top else "—"
                highest = _order_is_highest(order, top)
                mark = " ✅" if highest else ""
                oid = order.get("id", "?")
                total_qty = int(
                    order.get("totalQuantity")
                    or order.get("quantity")
                    or 0
                )
                done_qty = int(order.get("completedQuantity") or 0)
                if total_qty:
                    qty_text = f"{done_qty}/{total_qty}"
                else:
                    qty_text = "—"
                lines.append(
                    f"<b>{i}. {_order_label(order)}</b>\n"
                    f"   💰 {my_range} TON{mark}\n"
                    f"   📊 Max: {max_range} TON\n"
                    f"   🔢 Qty: {qty_text}\n"
                    f"   🆔 <code>{oid}</code>"
                )
                lines.append("")
            return "\n".join(lines).rstrip()

        message, status = await _with_mrkt(event, status, work)
        if message is None:
            return await status.edit(
                "📭 <b>No active orders.</b>", parse_mode="html",
            )
        return await _edit_chunks(status, event, message)
    except ValueError as e:
        return await event.eor(f"❌ {e}", parse_mode="html")
    except (TradingError, RequestError, AuthError) as e:
        LOGS.warning("Artemis .orders request error: %s", e)
        if status:
            return await status.edit(
                f"❌ <b>Artemis request failed.</b>\n\n<code>{e}</code>",
                parse_mode="html",
            )
        return await event.eor(
            f"❌ <b>Artemis request failed.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )
    except Exception as e:
        LOGS.exception("Artemis .orders failed: %s", e)
        if status:
            return await status.edit(
                f"❌ <b>Failed to fetch orders.</b>\n\n<code>{e}</code>",
                parse_mode="html",
            )
        return await event.eor(
            f"❌ <b>Failed to fetch orders.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )


def _extract_created_order_id(resp):
    if not isinstance(resp, dict):
        return None
    oid = resp.get("id")
    if oid:
        return str(oid)
    for key in ("order", "data", "result"):
        nested = resp.get(key)
        if isinstance(nested, dict) and nested.get("id"):
            return str(nested["id"])
    return None


def _order_track_key_from_parts(
    collection, model, backdrop, symbol, price_min,
):
    return "|".join(
        [
            str(collection or "").strip().lower(),
            str(model or "").strip().lower(),
            str(backdrop or "").strip().lower(),
            str(symbol or "").strip().lower(),
            str(_ton_q2(price_min)),
        ]
    )


def _order_snapshot(order, *, pending_recreate=False):
    """Serializable snapshot used to restore a bid if MRKT drops it."""
    collection = order.get("collectionName") or order.get("collectionTitle") or ""
    model = order.get("modelName") or None
    backdrop = order.get("backdropName") or None
    symbol = order.get("symbolName") or None
    price_min = float(nano_to_ton(order.get("priceMinNanoTONs") or 0))
    price_max = float(nano_to_ton(order.get("priceMaxNanoTONs") or 0))
    total_quantity = int(
        order.get("totalQuantity") or order.get("quantity") or 1
    )
    completed_quantity = int(order.get("completedQuantity") or 0)
    remaining_quantity = max(total_quantity - completed_quantity, 1)
    oid = order.get("id")
    return {
        "key": _order_track_key_from_parts(
            collection, model, backdrop, symbol, price_min,
        ),
        "id": str(oid) if oid else None,
        "collection": collection,
        "model": model,
        "backdrop": backdrop,
        "symbol": symbol,
        "price_min": price_min,
        "price_max": price_max,
        "quantity": int(remaining_quantity),
        "label": _order_label(order),
        "pending_recreate": bool(pending_recreate),
        "updated_at": time.time(),
    }


def _snapshot_from_parts(
    *,
    collection,
    model,
    backdrop,
    symbol,
    price_min,
    price_max,
    quantity,
    oid=None,
    label=None,
    pending_recreate=False,
):
    return {
        "key": _order_track_key_from_parts(
            collection, model, backdrop, symbol, price_min,
        ),
        "id": str(oid) if oid else None,
        "collection": collection,
        "model": model or None,
        "backdrop": backdrop or None,
        "symbol": symbol or None,
        "price_min": float(price_min),
        "price_max": float(price_max),
        "quantity": max(int(quantity or 1), 1),
        "label": label
        or ", ".join(
            p
            for p in (collection, model or None, backdrop or None)
            if p
        ),
        "pending_recreate": bool(pending_recreate),
        "updated_at": time.time(),
    }


def _autotop_orders_load():
    raw = udB.get_key(AUTOTOP_ORDERS_DB_KEY)
    if not isinstance(raw, list):
        return []
    out = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        if not row.get("collection"):
            continue
        out.append(row)
    return out


def _autotop_orders_save(rows):
    clean = []
    for row in rows or []:
        if not isinstance(row, dict) or not row.get("collection"):
            continue
        clean.append(dict(row))
    with contextlib.suppress(Exception):
        udB.set_key(AUTOTOP_ORDERS_DB_KEY, clean)
    return clean


def _autotop_orders_upsert(snapshot):
    if not isinstance(snapshot, dict) or not snapshot.get("key"):
        return
    rows = _autotop_orders_load()
    key = snapshot["key"]
    out = [row for row in rows if row.get("key") != key]
    out.append(dict(snapshot))
    _autotop_orders_save(out)


def _autotop_orders_remove_order(order):
    """Hard-drop a tracked order after intentional delete."""
    try:
        snap = _order_snapshot(order)
        key = snap.get("key")
    except Exception:
        key = None
    oid = str(order.get("id") or "")
    rows = []
    for row in _autotop_orders_load():
        if key and row.get("key") == key:
            continue
        if oid and str(row.get("id") or "") == oid:
            continue
        rows.append(row)
    _autotop_orders_save(rows)


def _autotop_orders_clear():
    _autotop_orders_save([])


def _autotop_orders_sync_live(orders, *, trusted=True):
    """
    Persist current live bids.

    Missing tracked bids are never hard-deleted here — they are marked
    ``pending_recreate`` so a flaky/partial MRKT fetch (or orderup cancel
    that failed mid-flight) cannot shrink 13 tracked orders down to 4.

    An untrusted empty fetch (``trusted=False``) does not wipe the tracker.
    """
    live_snaps = []
    live_keys = set()
    live_ids = set()
    for order in orders or []:
        if not isinstance(order, dict):
            continue
        snap = _order_snapshot(order, pending_recreate=False)
        live_snaps.append(snap)
        live_keys.add(snap["key"])
        if snap.get("id"):
            live_ids.add(str(snap["id"]))
    if not live_snaps and not trusted:
        return _autotop_orders_load()

    prev = _autotop_orders_load()
    merged = {snap["key"]: dict(snap) for snap in live_snaps}
    for row in prev:
        if not isinstance(row, dict):
            continue
        key = row.get("key")
        if not key:
            continue
        oid = str(row.get("id") or "")
        present = key in live_keys or (oid and oid in live_ids)
        if present:
            # Live row already in merged; keep any fresher qty/price from live.
            continue
        # Gone from live fetch — queue restore instead of dropping.
        kept = dict(row)
        kept["pending_recreate"] = True
        kept["updated_at"] = time.time()
        merged[key] = kept

    out = list(merged.values())
    _autotop_orders_save(out)
    return live_snaps


async def _orderup_try_create(
    client,
    *,
    collection,
    model,
    backdrop,
    symbol,
    price_min_ton,
    price_max_ton,
    quantity,
    attempts=3,
    label="",
):
    """Create an order with retries. Returns (ok, last_error, response)."""
    last_err = None
    for attempt in range(max(int(attempts), 1)):
        try:
            resp = await _create_order(
                client,
                collection=collection,
                model=model,
                backdrop=backdrop,
                symbol=symbol,
                price_min_ton=price_min_ton,
                price_max_ton=price_max_ton,
                quantity=quantity,
            )
            return True, None, resp
        except Exception as e:
            last_err = e
            LOGS.warning(
                "orderup create attempt %s failed for %s @ %s-%s: %s",
                attempt + 1,
                label or collection,
                price_min_ton,
                price_max_ton,
                e,
            )
            await asyncio.sleep(0.7 * (attempt + 1))
    return False, last_err, None


async def _recreate_snapshot(client, snap):
    """Recreate one tracked bid from a DB snapshot."""
    collection = snap.get("collection")
    if not collection:
        return False, "missing collection", None
    ok, err, resp = await _orderup_try_create(
        client,
        collection=collection,
        model=snap.get("model"),
        backdrop=snap.get("backdrop"),
        symbol=snap.get("symbol"),
        price_min_ton=snap.get("price_min") or 0,
        price_max_ton=snap.get("price_max") or snap.get("price_min") or 0,
        quantity=snap.get("quantity") or 1,
        attempts=5,
        label=f"{snap.get('label') or collection} [db-restore]",
    )
    if not ok:
        snap = dict(snap)
        snap["pending_recreate"] = True
        snap["updated_at"] = time.time()
        _autotop_orders_upsert(snap)
        return False, err, None

    new_id = _extract_created_order_id(resp)
    snap = dict(snap)
    snap["id"] = new_id or snap.get("id")
    snap["pending_recreate"] = False
    snap["updated_at"] = time.time()
    _autotop_orders_upsert(snap)
    return True, None, snap


async def _ensure_tracked_orders(client, live_orders=None):
    """
    Recreate only DB snapshots marked ``pending_recreate`` that are still
    missing live (cancel/create race, crash, or failed restore).

    Filled / manually cancelled bids are not recreated.
    """
    if live_orders is None:
        live_orders = await _fetch_my_orders(client)
    live_keys = set()
    live_ids = set()
    for order in live_orders or []:
        snap = _order_snapshot(order)
        live_keys.add(snap["key"])
        if snap.get("id"):
            live_ids.add(str(snap["id"]))

    restored = []
    for row in list(_autotop_orders_load()):
        if not row.get("pending_recreate"):
            continue
        key = row.get("key")
        oid = str(row.get("id") or "")
        present = (key in live_keys) or (oid and oid in live_ids)
        if present:
            row = dict(row)
            row["pending_recreate"] = False
            row["updated_at"] = time.time()
            _autotop_orders_upsert(row)
            continue
        ok, err, snap = await _recreate_snapshot(client, row)
        if ok:
            restored.append(snap or row)
            LOGS.info(
                "Autotop DB-restored missing order: %s",
                (snap or row).get("label") or key,
            )
        else:
            LOGS.warning(
                "Autotop DB-restore failed for %s: %s",
                row.get("label") or key,
                err,
            )
    return restored


async def _orderup_one(client, order):
    """
    Retarget one order to competitor top + 0.01.

    Raises when below, lowers when there is a gap above the second-highest,
    skips when already exactly at competitor top + 0.01.

    CRITICAL: cancel runs before create. Snapshot is written to DB with
    ``pending_recreate`` before cancel so autotop can restore after
    recreate failures / restarts. Immediate restore is still attempted.
    """
    label = _order_label(order)
    oid = None
    try:
        oid = _require_order_uuid(order.get("id"))
    except Exception as e:
        return {
            "status": "error",
            "label": label,
            "error": str(e),
        }

    collection = order.get("collectionName") or order.get("collectionTitle")
    model = order.get("modelName") or None
    backdrop = order.get("backdropName") or None
    symbol = order.get("symbolName") or None
    old_min = nano_to_ton(order.get("priceMinNanoTONs") or 0)
    old_max = nano_to_ton(order.get("priceMaxNanoTONs") or 0)
    total_quantity = int(
        order.get("totalQuantity") or order.get("quantity") or 1
    )
    completed_quantity = int(order.get("completedQuantity") or 0)
    remaining_quantity = max(total_quantity - completed_quantity, 1)

    if not collection:
        return {
            "status": "error",
            "label": label,
            "oid": oid,
            "error": "Order has no collectionName/collectionTitle.",
        }

    filt = {
        "collectionName": collection,
        "modelName": model,
        "backdropName": backdrop,
        "symbolName": symbol,
    }

    cancelled = False
    try:
        # Never cancel when top lookup hard-fails — HTTP 400 used to wipe bids.
        try:
            top = await _top_order(client, filt)
        except Exception as top_err:
            LOGS.warning(
                "orderup top lookup failed for %s (skip, keep live): %s",
                oid,
                top_err,
            )
            _autotop_orders_upsert(
                _order_snapshot(order, pending_recreate=False)
            )
            return {
                "status": "error",
                "label": label,
                "oid": oid,
                "old_min": old_min,
                "old_max": old_max,
                "error": f"top lookup failed: {top_err}",
            }
        # Soft 400 → None: still try competitor book; if nobody else, skip.
        competitor = await _competitor_top_ton(client, order, top=top)
        if competitor is None:
            top_max = old_max
            ideal_max = _ton_q2(old_max)
        else:
            top_max = competitor
            ideal_max = _order_ideal_max(competitor, old_min)

        _autotop_orders_upsert(_order_snapshot(order, pending_recreate=False))

        if _ton_q2(old_max) == _ton_q2(ideal_max):
            return {
                "status": "skipped",
                "label": label,
                "oid": oid,
                "old_min": old_min,
                "old_max": old_max,
                "top_max": top_max,
            }

        pending_snap = _order_snapshot(order, pending_recreate=True)
        _autotop_orders_upsert(pending_snap)

        await _cancel_order(client, oid)
        cancelled = True
        try:
            top = await _top_order(client, filt)
        except Exception as top_err:
            LOGS.warning(
                "orderup post-cancel top failed for %s: %s", oid, top_err,
            )
            top = None
        if top and top.get("priceMaxNanoTONs") is not None:
            top_max = nano_to_ton(top.get("priceMaxNanoTONs"))
        else:
            top_max = competitor if competitor is not None else old_min
        new_max = _order_ideal_max(top_max, old_min)

        ok, create_err, create_resp = await _orderup_try_create(
            client,
            collection=collection,
            model=model,
            backdrop=backdrop,
            symbol=symbol,
            price_min_ton=old_min,
            price_max_ton=new_max,
            quantity=remaining_quantity,
            attempts=4,
            label=label,
        )
        if ok:
            new_id = _extract_created_order_id(create_resp)
            _autotop_orders_upsert(
                _snapshot_from_parts(
                    collection=collection,
                    model=model,
                    backdrop=backdrop,
                    symbol=symbol,
                    price_min=old_min,
                    price_max=new_max,
                    quantity=remaining_quantity,
                    oid=new_id,
                    label=label,
                    pending_recreate=False,
                )
            )
            return {
                "status": "updated",
                "label": label,
                "oid": new_id or oid,
                "old_min": old_min,
                "old_max": old_max,
                "top_max": top_max,
                "new_max": new_max,
                "qty": remaining_quantity,
            }

        LOGS.error(
            "orderup recreate failed for %s (%s); restoring %s-%s TON: %s",
            label, oid, old_min, old_max, create_err,
        )
        restored, restore_err, restore_resp = await _orderup_try_create(
            client,
            collection=collection,
            model=model,
            backdrop=backdrop,
            symbol=symbol,
            price_min_ton=old_min,
            price_max_ton=old_max,
            quantity=remaining_quantity,
            attempts=5,
            label=f"{label} [restore]",
        )
        if restored:
            new_id = _extract_created_order_id(restore_resp)
            _autotop_orders_upsert(
                _snapshot_from_parts(
                    collection=collection,
                    model=model,
                    backdrop=backdrop,
                    symbol=symbol,
                    price_min=old_min,
                    price_max=old_max,
                    quantity=remaining_quantity,
                    oid=new_id,
                    label=label,
                    pending_recreate=False,
                )
            )
            return {
                "status": "restored",
                "label": label,
                "oid": new_id or oid,
                "old_min": old_min,
                "old_max": old_max,
                "top_max": top_max,
                "new_max": new_max,
                "qty": remaining_quantity,
                "error": (
                    f"Recreate at {_ton2(new_max)} failed "
                    f"({create_err}); restored previous "
                    f"{_ton2(old_min)}-{_ton2(old_max)} TON."
                ),
            }
        _autotop_orders_upsert(pending_snap)
        return {
            "status": "lost",
            "label": label,
            "oid": oid,
            "old_min": old_min,
            "old_max": old_max,
            "top_max": top_max,
            "new_max": new_max,
            "qty": remaining_quantity,
            "error": (
                f"Cancelled, recreate failed ({create_err}), "
                f"restore failed ({restore_err}). "
                f"DB snapshot kept for autotop recreate. "
                f"Manual: {_h('ordernew')} "
                f"{collection}, {model or ''}, {backdrop or ''}, "
                f"{_ton2(old_min)}-{_ton2(old_max)}"
            ),
        }
    except Exception as e:
        LOGS.exception("orderup failed for %s: %s", oid, e)
        if cancelled and collection:
            restored, restore_err, restore_resp = await _orderup_try_create(
                client,
                collection=collection,
                model=model,
                backdrop=backdrop,
                symbol=symbol,
                price_min_ton=old_min,
                price_max_ton=old_max,
                quantity=remaining_quantity,
                attempts=5,
                label=f"{label} [emergency-restore]",
            )
            if restored:
                new_id = _extract_created_order_id(restore_resp)
                _autotop_orders_upsert(
                    _snapshot_from_parts(
                        collection=collection,
                        model=model,
                        backdrop=backdrop,
                        symbol=symbol,
                        price_min=old_min,
                        price_max=old_max,
                        quantity=remaining_quantity,
                        oid=new_id,
                        label=label,
                        pending_recreate=False,
                    )
                )
                return {
                    "status": "restored",
                    "label": label,
                    "oid": new_id or oid,
                    "old_min": old_min,
                    "old_max": old_max,
                    "error": (
                        f"orderup crashed after cancel ({e}); "
                        f"restored previous price."
                    ),
                }
            _autotop_orders_upsert(
                _snapshot_from_parts(
                    collection=collection,
                    model=model,
                    backdrop=backdrop,
                    symbol=symbol,
                    price_min=old_min,
                    price_max=old_max,
                    quantity=remaining_quantity,
                    oid=oid,
                    label=label,
                    pending_recreate=True,
                )
            )
            return {
                "status": "lost",
                "label": label,
                "oid": oid,
                "old_min": old_min,
                "old_max": old_max,
                "error": (
                    f"orderup crashed after cancel ({e}); "
                    f"restore failed ({restore_err}). "
                    f"DB snapshot kept for autotop recreate."
                ),
            }
        return {
            "status": "error",
            "label": label,
            "oid": oid,
            "error": str(e),
        }


async def _run_orderup_all(client):
    """
    Retarget every active order to competitor top+0.01.

    Syncs active bids into DB first, recreates any missing tracked bids,
    then orderups. Updates ORDER_CACHE.
    """
    global ORDER_CACHE
    orders = await _fetch_my_orders(client)
    _autotop_orders_sync_live(orders, trusted=bool(orders))
    recreated = await _ensure_tracked_orders(client, live_orders=orders)
    if recreated:
        orders = await _fetch_my_orders(client)
        _autotop_orders_sync_live(orders, trusted=bool(orders))
    ORDER_CACHE = orders
    updated = []
    restored = []
    lost = []
    skipped = 0
    errors = []
    for order in orders:
        result = await _orderup_one(client, order)
        status = result.get("status")
        if status == "updated":
            updated.append(result)
        elif status == "skipped":
            skipped += 1
        elif status == "restored":
            restored.append(result)
        elif status == "lost":
            lost.append(result)
        else:
            errors.append(result)
    ORDER_CACHE = await _fetch_my_orders(client)
    _autotop_orders_sync_live(ORDER_CACHE, trusted=bool(ORDER_CACHE))
    extra = await _ensure_tracked_orders(client, live_orders=ORDER_CACHE)
    if extra:
        recreated.extend(extra)
        ORDER_CACHE = await _fetch_my_orders(client)
        _autotop_orders_sync_live(ORDER_CACHE, trusted=bool(ORDER_CACHE))
    return {
        "orders": ORDER_CACHE,
        "updated": updated,
        "skipped": skipped,
        "restored": restored,
        "lost": lost,
        "errors": errors,
        "recreated": recreated,
    }


def _orderup_all_message(result):
    updated = result["updated"]
    skipped = result["skipped"]
    restored = result.get("restored") or []
    lost = result.get("lost") or []
    recreated = result.get("recreated") or []
    errors = result["errors"]
    lines = [
        "🚀 <b>Orderup All</b>",
        "",
        f"✅ Updated: <code>{len(updated)}</code>",
        f"⏭ Already at top+0.01: <code>{skipped}</code>",
        f"💾 DB-recreated missing: <code>{len(recreated)}</code>",
        f"♻️ Restored after failed recreate: <code>{len(restored)}</code>",
        f"🚨 Lost (cancel+recreate+restore failed): <code>{len(lost)}</code>",
        f"❌ Errors: <code>{len(errors)}</code>",
        "",
    ]
    if updated:
        lines.append("<b>Updated orders</b>")
        lines.append("")
        for i, row in enumerate(updated, 1):
            lines.append(
                f"<b>{i}. {row['label']}</b>\n"
                f"   💰 {_ton2(row['old_min'])}-{_ton2(row['old_max'])} TON"
                f" → {_ton2(row['old_min'])}-{_ton2(row['new_max'])} TON\n"
                f"   📊 Competitor top: {_ton2(row['top_max'])} TON\n"
                f"   🔢 Qty: {row['qty']}\n"
                f"   🆔 <code>{row['oid']}</code>"
            )
            lines.append("")
    elif not errors and not restored and not lost:
        if not result.get("orders"):
            lines.append("📭 <b>No active orders.</b>")
        else:
            lines.append(
                "✅ <b>All active orders were already at competitor top+0.01.</b>"
            )
        lines.append("")

    if restored:
        lines.append("<b>Restored (kept previous price)</b>")
        lines.append("")
        for i, row in enumerate(restored[:10], 1):
            lines.append(
                f"{i}. {row.get('label') or '?'}\n"
                f"   <code>{row.get('error') or 'restored'}</code>"
            )
            lines.append("")

    if lost:
        lines.append("<b>🚨 Lost orders — recreate manually</b>")
        lines.append("")
        for i, row in enumerate(lost[:10], 1):
            lines.append(
                f"{i}. {row.get('label') or '?'}\n"
                f"   <code>{row.get('error') or 'lost'}</code>"
            )
            lines.append("")

    if errors:
        lines.append("<b>Errors</b>")
        lines.append("")
        for i, row in enumerate(errors[:10], 1):
            err = row.get("error") or "?"
            lines.append(
                f"{i}. {row.get('label') or '?'}\n"
                f"   <code>{err}</code>"
            )
            lines.append("")
    return "\n".join(lines).rstrip()


def _clamp_autotop_interval(value):
    try:
        seconds = float(value)
    except Exception:
        seconds = AUTOTOP_DEFAULT_INTERVAL
    if seconds < AUTOTOP_MIN_INTERVAL:
        seconds = AUTOTOP_MIN_INTERVAL
    if seconds > AUTOTOP_MAX_INTERVAL:
        seconds = AUTOTOP_MAX_INTERVAL
    return float(seconds)


def _autotop_db_enabled():
    raw = udB.get_key(AUTOTOP_DB_KEY)
    if isinstance(raw, dict):
        raw = raw.get("enabled")
    if raw is True or raw == 1:
        return True
    if isinstance(raw, str) and raw.strip().lower() in ("1", "true", "on", "yes"):
        return True
    return False


def _autotop_set_db(enabled):
    udB.set_key(AUTOTOP_DB_KEY, bool(enabled))


def _autotop_get_interval():
    raw = udB.get_key(AUTOTOP_INTERVAL_DB_KEY)
    if raw is None:
        cfg = udB.get_key(AUTOTOP_DB_KEY)
        if isinstance(cfg, dict) and cfg.get("interval") is not None:
            raw = cfg.get("interval")
    if raw is None:
        return float(AUTOTOP_DEFAULT_INTERVAL)
    return _clamp_autotop_interval(raw)


def _autotop_set_interval(seconds):
    global AUTOTOP_INTERVAL
    AUTOTOP_INTERVAL = _clamp_autotop_interval(seconds)
    with contextlib.suppress(Exception):
        udB.set_key(AUTOTOP_INTERVAL_DB_KEY, float(AUTOTOP_INTERVAL))
    return AUTOTOP_INTERVAL


def _autotop_status_message():
    running = bool(
        AUTOTOP_ENABLED
        and AUTOTOP_TASK is not None
        and not AUTOTOP_TASK.done()
    )
    state = "ON" if running else "OFF"
    tracked = _autotop_orders_load()
    pending = sum(1 for row in tracked if row.get("pending_recreate"))
    lines = [
        f"⏱ <b>Autotop:</b> <code>{state}</code>",
        f"🔁 Interval: <code>{int(AUTOTOP_INTERVAL)}s</code>",
        f"💾 Tracked orders: <code>{len(tracked)}</code>"
        + (f" (pending recreate: <code>{pending}</code>)" if pending else ""),
    ]
    if AUTOTOP_STATS.get("started_at"):
        lines.append(
            f"▶️ Started: <code>{_format_tehran(AUTOTOP_STATS['started_at'])}</code>"
        )
    if AUTOTOP_STATS.get("last_run_at"):
        lines.append(
            f"🕒 Last check: <code>{_format_tehran(AUTOTOP_STATS['last_run_at'])}</code>"
        )
        lines.append(
            f"📊 Last cycle — updated "
            f"<code>{AUTOTOP_STATS.get('last_updated', 0)}</code>, "
            f"skipped <code>{AUTOTOP_STATS.get('last_skipped', 0)}</code>, "
            f"db-recreated <code>{AUTOTOP_STATS.get('last_recreated', 0)}</code>, "
            f"errors <code>{AUTOTOP_STATS.get('last_errors', 0)}</code>"
        )
    lines.append(f"🔢 Cycles: <code>{AUTOTOP_STATS.get('cycles', 0)}</code>")
    return "\n".join(lines)


async def _autotop_notify_disabled(reason: str):
    """Best-effort owner notice when autotop turns itself off."""
    try:
        owner = OWNER_ID or (owner_and_sudos() or [None])[0]
        if not owner or not heartless_bot:
            return
        await heartless_bot.send_message(
            int(owner),
            "⏹ <b>Autotop disabled</b>\n"
            f"{reason}\n\n"
            f"Use <code>{_h('autotop')} on</code> to enable again.",
            parse_mode="html",
        )
    except Exception:
        LOGS.debug("Autotop disable notify failed", exc_info=True)


async def _autotop_notify_problems(result: dict):
    """Alert owner when autotop loses/restores orders or hits errors."""
    lost = result.get("lost") or []
    restored = result.get("restored") or []
    recreated = result.get("recreated") or []
    errors = result.get("errors") or []
    if not lost and not restored and not recreated and not errors:
        return
    try:
        owner = OWNER_ID or (owner_and_sudos() or [None])[0]
        if not owner or not heartless_bot:
            return
        lines = ["⚠️ <b>Autotop orderup warning</b>", ""]
        if recreated:
            lines.append(
                f"💾 <b>DB-recreated missing:</b> <code>{len(recreated)}</code>"
            )
            for row in recreated[:8]:
                lines.append(
                    f"• {html.escape(str(row.get('label') or '?'))}"
                )
            lines.append("")
        if lost:
            lines.append(f"🚨 <b>Lost bids:</b> <code>{len(lost)}</code>")
            for row in lost[:8]:
                lines.append(
                    f"• {html.escape(str(row.get('label') or '?'))}\n"
                    f"  <code>{html.escape(str(row.get('error') or ''))}</code>"
                )
            lines.append("")
        if restored:
            lines.append(
                f"♻️ <b>Restored at old price:</b> <code>{len(restored)}</code>"
            )
            for row in restored[:8]:
                lines.append(
                    f"• {html.escape(str(row.get('label') or '?'))}"
                )
            lines.append("")
        if errors:
            lines.append(f"❌ <b>Errors:</b> <code>{len(errors)}</code>")
            for row in errors[:5]:
                lines.append(
                    f"• {html.escape(str(row.get('label') or '?'))}\n"
                    f"  <code>{html.escape(str(row.get('error') or ''))}</code>"
                )
        await heartless_bot.send_message(
            int(owner),
            "\n".join(lines).rstrip(),
            parse_mode="html",
        )
    except Exception:
        LOGS.debug("Autotop problem notify failed", exc_info=True)


async def _autotop_cycle_once():
    """One silent orderup-all pass used by the autotop worker."""
    global AUTOTOP_STATS
    await _ensure_artemis_token()
    async with ORDERUP_LOCK:
        async with MRKTClient(token=ARTEMIS_TOKEN) as client:
            result = await _run_orderup_all(client)
    AUTOTOP_STATS["last_run_at"] = time.time()
    AUTOTOP_STATS["last_updated"] = len(result["updated"])
    AUTOTOP_STATS["last_skipped"] = result["skipped"]
    AUTOTOP_STATS["last_recreated"] = len(result.get("recreated") or [])
    AUTOTOP_STATS["last_errors"] = (
        len(result["errors"])
        + len(result.get("lost") or [])
        + len(result.get("restored") or [])
    )
    AUTOTOP_STATS["cycles"] = int(AUTOTOP_STATS.get("cycles") or 0) + 1
    await _autotop_notify_problems(result)
    return result


async def _autotop_worker():
    global AUTOTOP_TASK, AUTOTOP_ENABLED, AUTOTOP_INTERVAL
    AUTOTOP_INTERVAL = _autotop_get_interval()
    LOGS.info("Artemis autotop worker started (every %ss)", AUTOTOP_INTERVAL)
    # Give startup / token refresh a moment before the first cancel+recreate
    # pass — restart races were canceling bids while the API was still settling.
    await asyncio.sleep(8)
    empty_streak = 0
    try:
        while AUTOTOP_ENABLED:
            try:
                AUTOTOP_INTERVAL = _autotop_get_interval()
                result = await _autotop_cycle_once()
                live_empty = not result.get("orders")
                pending = [
                    row
                    for row in _autotop_orders_load()
                    if row.get("pending_recreate")
                ]
                # Keep running while DB still needs to restore a cancelled bid.
                if live_empty and not pending:
                    empty_streak += 1
                else:
                    empty_streak = 0
                if empty_streak >= 2:
                    LOGS.info(
                        "Autotop: no live orders for %s cycles — disabling",
                        empty_streak,
                    )
                    _autotop_orders_clear()
                    AUTOTOP_ENABLED = False
                    _autotop_set_db(False)
                    await _autotop_notify_disabled(
                        "📭 No active orders remaining."
                    )
                    break
            except asyncio.CancelledError:
                raise
            except Exception as e:
                empty_streak = 0
                AUTOTOP_STATS["last_run_at"] = time.time()
                AUTOTOP_STATS["cycles"] = int(AUTOTOP_STATS.get("cycles") or 0) + 1
                if _is_token_expired_error(e):
                    try:
                        await _force_refresh_token()
                        LOGS.info("Autotop refreshed expired Artemis token")
                    except Exception as refresh_err:
                        LOGS.warning(
                            "Autotop token refresh failed: %s", refresh_err,
                        )
                LOGS.warning("Autotop cycle failed: %s", e)
            if not AUTOTOP_ENABLED:
                break
            await asyncio.sleep(_autotop_get_interval())
    except asyncio.CancelledError:
        LOGS.info("Artemis autotop worker cancelled")
        raise
    finally:
        if AUTOTOP_TASK is asyncio.current_task():
            AUTOTOP_TASK = None
        LOGS.info("Artemis autotop worker stopped")


def _autotop_start(interval=None):
    """Enable + start the background worker (idempotent)."""
    global AUTOTOP_TASK, AUTOTOP_ENABLED, AUTOTOP_STATS, AUTOTOP_INTERVAL
    if interval is not None:
        _autotop_set_interval(interval)
    else:
        AUTOTOP_INTERVAL = _autotop_get_interval()
    AUTOTOP_ENABLED = True
    _autotop_set_db(True)
    if AUTOTOP_TASK is not None and not AUTOTOP_TASK.done():
        return False
    AUTOTOP_STATS = {
        "started_at": time.time(),
        "last_run_at": None,
        "last_updated": 0,
        "last_skipped": 0,
        "last_recreated": 0,
        "last_errors": 0,
        "cycles": 0,
    }
    AUTOTOP_TASK = asyncio.create_task(_autotop_worker())
    return True


async def _autotop_stop():
    """Disable + stop the background worker."""
    global AUTOTOP_TASK, AUTOTOP_ENABLED
    AUTOTOP_ENABLED = False
    _autotop_set_db(False)
    task = AUTOTOP_TASK
    AUTOTOP_TASK = None
    if task and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
    return True


def _autotop_bootstrap():
    """Resume autotop after plugin reload when DB flag is on."""
    global AUTOTOP_INTERVAL
    AUTOTOP_INTERVAL = _autotop_get_interval()
    if not _autotop_db_enabled():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            from CythonX.startup.aio import ensure_event_loop

            loop = ensure_event_loop()
        except Exception:
            return
    try:
        loop.call_soon(_autotop_start)
    except Exception:
        with contextlib.suppress(Exception):
            loop.create_task(_autotop_delayed_start())


async def _autotop_delayed_start():
    await asyncio.sleep(1)
    if _autotop_db_enabled():
        _autotop_start()


@heartless_cmd(owner_only=True, pattern=r"orderupall$")
async def artemis_orderupall(event):
    try:
        _, status = await _ensure_artemis_token(event)
    except ValueError as e:
        return await event.eor(f"❌ {e}", parse_mode="html")
    if status is None:
        status = await event.eor("<b>Processing...</b>", parse_mode="html")
    else:
        status = await status.edit("<b>Processing...</b>", parse_mode="html")
    try:
        async with ORDERUP_LOCK:
            async with MRKTClient(token=ARTEMIS_TOKEN) as client:
                result = await _run_orderup_all(client)
        if not result["orders"]:
            return await status.edit(
                "📭 <b>No active orders.</b>",
                parse_mode="html",
            )
        return await _edit_chunks(
            status, event, _orderup_all_message(result),
        )
    except (TradingError, RequestError) as e:
        return await status.edit(
            f"❌ <b>Orderup all failed.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )
    except Exception as e:
        LOGS.exception("Artemis .orderupall failed: %s", e)
        return await status.edit(
            f"❌ <b>Failed to orderup all.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )


@heartless_cmd(owner_only=True, pattern=r"autotop(?:\s+(.+))?$")
async def artemis_autotop(event):
    raw = (event.pattern_match.group(1) or "").strip().lower()
    if not raw:
        return await event.eor(_autotop_status_message(), parse_mode="html")

    on_match = re.match(
        r"^(on|start|enable|1|true)(?:\s+(\d+(?:\.\d+)?)\s*s?)?$",
        raw,
    )
    if on_match:
        try:
            await _ensure_artemis_token(event)
        except ValueError as e:
            return await event.eor(f"❌ {e}", parse_mode="html")
        interval = (
            float(on_match.group(2))
            if on_match.group(2)
            else AUTOTOP_DEFAULT_INTERVAL
        )
        interval = _autotop_set_interval(interval)
        # Seed DB tracker from current live orders before the worker runs.
        try:
            async with ORDERUP_LOCK:
                async with MRKTClient(token=ARTEMIS_TOKEN) as client:
                    live = await _fetch_my_orders(client)
                    _autotop_orders_sync_live(live)
        except Exception as e:
            LOGS.warning("Autotop seed sync failed: %s", e)
        started = _autotop_start(interval)
        if started:
            msg = (
                "🟢 <b>Autotop enabled.</b>\n\n"
                f"🔁 Checking every <code>{int(interval)}s</code>.\n"
                f"💾 Active orders are tracked in DB and recreated if missing.\n"
                f"Use <code>{_h('autotop')} off</code> to disable."
            )
        else:
            msg = (
                "🟢 <b>Autotop is already running.</b>\n\n"
                f"🔁 Interval updated to <code>{int(interval)}s</code>."
            )
        return await event.eor(
            msg + "\n\n" + _autotop_status_message(),
            parse_mode="html",
        )

    if raw in ("off", "stop", "disable", "0", "false"):
        await _autotop_stop()
        return await event.eor(
            "🔴 <b>Autotop disabled.</b>\n\n"
            f"Use <code>{_h('autotop')} on</code> to enable again.",
            parse_mode="html",
        )

    return await event.eor(
        "❌ <b>Usage:</b>\n"
        f"<code>{_h('autotop')}</code>\n"
        f"<code>{_h('autotop')} on</code> — default 30s\n"
        f"<code>{_h('autotop')} on 20</code> — custom interval\n"
        f"<code>{_h('autotop')} off</code>",
        parse_mode="html",
    )


@heartless_cmd(owner_only=True, pattern=r"orderup(?:\s+(.+))?$")
async def artemis_orderup(event):
    global ORDER_CACHE
    try:
        _, status = await _ensure_artemis_token(event)
    except ValueError as e:
        return await event.eor(f"❌ {e}", parse_mode="html")
    raw_idx = event.pattern_match.group(1)
    if not raw_idx or not raw_idx.strip().isdigit():
        return await event.eor(f"Usage: <code>{_h('orderup')} N</code>", parse_mode="html")
    idx = int(raw_idx.strip())
    if status is None:
        status = await event.eor("<b>Processing...</b>", parse_mode="html")
    else:
        status = await status.edit("<b>Processing...</b>", parse_mode="html")
    try:
        order = await _get_cached_order(idx)
        if not order:
            return await status.edit(
                f"❌ Invalid index. Run <code>{_h('orders')}</code> first.",
                parse_mode="html",
            )
        async with ORDERUP_LOCK:
            async with MRKTClient(token=ARTEMIS_TOKEN) as client:
                result = await _orderup_one(client, order)
                ORDER_CACHE = await _fetch_my_orders(client)
                _autotop_orders_sync_live(
                    ORDER_CACHE, trusted=bool(ORDER_CACHE),
                )
                await _ensure_tracked_orders(client, live_orders=ORDER_CACHE)

        if result["status"] == "skipped":
            return await status.edit(
                "✅ <b>Your order is already at competitor top+0.01.</b>\n\n"
                f"📦 <b>Order:</b> {result['label']}\n"
                f"🆔 <code>{result['oid']}</code>\n"
                f"💰 <b>Yours:</b> "
                f"<code>{_ton2(result['old_min'])}-{_ton2(result['old_max'])} TON</code>\n"
                f"📊 <b>Competitor top:</b> "
                f"<code>{_ton2(result['top_max'])} TON</code>",
                parse_mode="html",
            )
        if result["status"] == "restored":
            return await status.edit(
                "♻️ <b>Recreate failed — previous bid restored.</b>\n\n"
                f"📦 <b>Order:</b> {result['label']}\n"
                f"🆔 <code>{result.get('oid')}</code>\n"
                f"💰 <code>{_ton2(result['old_min'])}-{_ton2(result['old_max'])} TON</code>\n"
                f"<code>{html.escape(str(result.get('error') or ''))}</code>",
                parse_mode="html",
            )
        if result["status"] == "lost":
            return await status.edit(
                "🚨 <b>Order lost after cancel — restore failed.</b>\n\n"
                f"📦 <b>Order:</b> {result['label']}\n"
                f"🆔 <code>{result.get('oid')}</code>\n"
                f"<code>{html.escape(str(result.get('error') or ''))}</code>",
                parse_mode="html",
            )
        if result["status"] == "error":
            return await status.edit(
                f"❌ <b>Order update failed.</b>\n\n"
                f"<code>{html.escape(str(result.get('error') or ''))}</code>",
                parse_mode="html",
            )
        return await status.edit(
            "✅ <b>Order updated successfully.</b>\n\n"
            f"📦 <b>Order:</b> {result['label']}\n"
            f"🆔 <b>Old ID:</b> <code>{result['oid']}</code>\n"
            f"💰 <b>Old:</b> "
            f"<code>{_ton2(result['old_min'])}-{_ton2(result['old_max'])} TON</code>\n"
            f"📊 <b>Competitor top:</b> "
            f"<code>{_ton2(result['top_max'])} TON</code>\n"
            f"🚀 <b>New:</b> "
            f"<code>{_ton2(result['old_min'])}-{_ton2(result['new_max'])} TON</code>\n"
            f"🔢 <b>Qty:</b> <code>{result['qty']}</code>\n"
            "🔓 <b>Without transfer lock</b>",
            parse_mode="html",
        )
    except (TradingError, RequestError) as e:
        return await status.edit(
            f"❌ <b>Order update failed.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )
    except Exception as e:
        LOGS.exception("Artemis .orderup failed: %s", e)
        return await status.edit(
            f"❌ <b>Failed to update order.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )


@heartless_cmd(owner_only=True, pattern=r"orderdelall$")
async def artemis_orderdelall(event):
    global ORDER_CACHE
    try:
        _, status = await _ensure_artemis_token(event)
    except ValueError as e:
        return await event.eor(f"❌ {e}", parse_mode="html")
    if status is None:
        status = await event.eor("<b>Processing...</b>", parse_mode="html")
    else:
        status = await status.edit("<b>Processing...</b>", parse_mode="html")
    try:
        async with ORDERUP_LOCK:
            async with MRKTClient(token=ARTEMIS_TOKEN) as client:
                orders = await _fetch_my_orders(client)
                if not orders:
                    ORDER_CACHE = []
                    # Also wipe stale autotop tracker rows.
                    _autotop_orders_clear()
                    return await status.edit(
                        "📭 <b>No active orders.</b>", parse_mode="html",
                    )
                deleted = 0
                errors = []
                for order in orders:
                    try:
                        await _cancel_order(client, order["id"])
                        deleted += 1
                    except Exception as e:
                        errors.append(f"{order.get('id')}: {e}")
                ORDER_CACHE = await _fetch_my_orders(client)
                # orderdelall always clears DB tracker; re-seed only leftovers.
                _autotop_orders_clear()
                if ORDER_CACHE:
                    _autotop_orders_sync_live(ORDER_CACHE, trusted=True)
        msg = (
            "🗑 <b>Bulk delete finished.</b>\n\n"
            f"Deleted: <code>{deleted}/{len(orders)}</code>"
        )
        if errors:
            msg += "\n\n⚠️ Errors:\n" + "\n".join(
                f"<code>{e}</code>" for e in errors[:5]
            )
        return await status.edit(msg, parse_mode="html")
    except (TradingError, RequestError) as e:
        return await status.edit(
            f"❌ <b>Bulk deletion failed.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )
    except Exception as e:
        LOGS.exception("Artemis .orderdelall failed: %s", e)
        return await status.edit(
            f"❌ <b>Failed to delete all orders.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )


@heartless_cmd(owner_only=True, pattern=r"orderdel(?:\s+(.+))?$")
async def artemis_orderdel(event):
    global ORDER_CACHE
    try:
        _, status = await _ensure_artemis_token(event)
    except ValueError as e:
        return await event.eor(f"❌ {e}", parse_mode="html")
    raw_idx = event.pattern_match.group(1)
    usage = (
        "Usage:\n"
        f"<code>{_h('orderdel')} N</code>\n"
        f"<code>{_h('orderdel')} 1, 2, 3</code>"
    )
    try:
        indexes = _parse_order_indices(raw_idx)
    except ValueError:
        return await event.eor(usage, parse_mode="html")

    if status is None:
        status = await event.eor("<b>Processing...</b>", parse_mode="html")
    else:
        status = await status.edit("<b>Processing...</b>", parse_mode="html")
    try:
        # Resolve all targets from the same snapshot so indexes stay stable.
        if not ORDER_CACHE:
            async with MRKTClient(token=ARTEMIS_TOKEN) as client:
                ORDER_CACHE = await _fetch_my_orders(client)
        if not ORDER_CACHE:
            return await status.edit(
                "📭 <b>No active orders.</b>",
                parse_mode="html",
            )

        invalid = [i for i in indexes if i < 1 or i > len(ORDER_CACHE)]
        if invalid:
            bad = ", ".join(str(i) for i in invalid)
            return await status.edit(
                f"❌ Invalid index: <code>{bad}</code>\n"
                f"Run <code>{_h('orders')}</code> first "
                f"(1-{len(ORDER_CACHE)}).",
                parse_mode="html",
            )

        targets = []
        for idx in indexes:
            order = ORDER_CACHE[idx - 1]
            oid = _require_order_uuid(order.get("id"))
            targets.append((idx, order, oid))

        deleted = []
        errors = []
        async with ORDERUP_LOCK:
            async with MRKTClient(token=ARTEMIS_TOKEN) as client:
                for idx, order, oid in targets:
                    try:
                        await _cancel_order(client, oid)
                        _autotop_orders_remove_order(order)
                        deleted.append((idx, order, oid))
                    except Exception as e:
                        errors.append((idx, order, oid, e))
                ORDER_CACHE = await _fetch_my_orders(client)
                if not ORDER_CACHE:
                    _autotop_orders_clear()
                else:
                    _autotop_orders_sync_live(ORDER_CACHE, trusted=True)

        if len(targets) == 1 and len(deleted) == 1 and not errors:
            idx, order, oid = deleted[0]
            return await status.edit(
                "🗑 <b>Order deleted.</b>\n\n"
                f"📦 {_order_label(order)}\n"
                f"🆔 <code>{oid}</code>",
                parse_mode="html",
            )

        lines = [
            "🗑 <b>Orders deleted.</b>",
            "",
            f"✅ Deleted: <code>{len(deleted)}/{len(targets)}</code>",
            "",
        ]
        for idx, order, oid in deleted:
            lines.append(
                f"<b>#{idx}. {_order_label(order)}</b>\n"
                f"   🆔 <code>{oid}</code>"
            )
            lines.append("")
        if errors:
            lines.append("<b>Errors</b>")
            lines.append("")
            for idx, order, oid, err in errors[:10]:
                lines.append(
                    f"#{idx}. {_order_label(order)}\n"
                    f"   🆔 <code>{oid}</code>\n"
                    f"   <code>{err}</code>"
                )
                lines.append("")
        return await status.edit(
            "\n".join(lines).rstrip(),
            parse_mode="html",
        )
    except (TradingError, RequestError) as e:
        return await status.edit(
            f"❌ <b>Order deletion failed.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )
    except Exception as e:
        LOGS.exception("Artemis .orderdel failed: %s", e)
        return await status.edit(
            f"❌ <b>Failed to delete order.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )


async def _ordernew_bulk(event, raw_text: str):
    """Create missing orders from a pasted / replied `.orders` list."""
    global ORDER_CACHE
    try:
        specs = _parse_orders_list_bulk(raw_text)
    except Exception as e:
        return await event.eor(f"❌ <code>{e}</code>", parse_mode="html")

    status = await event.eor(
        f"<b>Bulk ordernew:</b> parsing {len(specs)} entr"
        f"{'y' if len(specs) == 1 else 'ies'}…",
        parse_mode="html",
    )
    try:
        async def work(client):
            global ORDER_CACHE
            live = await _fetch_my_orders(client)
            live_ids = _live_order_ids(live)
            live_keys = _live_order_keys(live)
            created = []
            skipped = []
            failed = []

            for spec in specs:
                label = spec["label"]
                oid = (spec.get("id") or "").lower() or None
                track_key = _order_track_key_from_parts(
                    spec["collection"],
                    spec["model"],
                    spec.get("backdrop"),
                    None,
                    spec["price_min"],
                )
                # Skip when UUID is still live, or same filter+min already live.
                if oid and oid in live_ids:
                    skipped.append((label, "already live (same id)"))
                    continue
                if track_key in live_keys:
                    skipped.append((label, "already live (same filter/min)"))
                    continue

                try:
                    coll, mod, back = await _resolve_gift_names(
                        client,
                        spec["collection"],
                        spec["model"],
                        spec.get("backdrop"),
                    )
                    if not mod:
                        failed.append((label, "could not resolve model"))
                        continue
                    resp = await _create_order(
                        client,
                        collection=coll,
                        model=mod,
                        backdrop=back,
                        price_min_ton=spec["price_min"],
                        price_max_ton=spec["price_max"],
                        quantity=spec.get("quantity") or 1,
                    )
                    new_id = _extract_created_order_id(resp)
                    snap = _snapshot_from_parts(
                        collection=coll,
                        model=mod,
                        backdrop=back,
                        symbol=None,
                        price_min=spec["price_min"],
                        price_max=spec["price_max"],
                        quantity=spec.get("quantity") or 1,
                        oid=new_id,
                        label=label,
                        pending_recreate=False,
                    )
                    _autotop_orders_upsert(snap)
                    live_keys.add(snap["key"])
                    if new_id:
                        live_ids.add(str(new_id).lower())
                    created.append(
                        (
                            label,
                            spec["price_min"],
                            spec["price_max"],
                            spec.get("quantity") or 1,
                            new_id,
                        )
                    )
                except Exception as e:
                    LOGS.warning("bulk ordernew failed for %s: %s", label, e)
                    failed.append((label, str(e)))

            ORDER_CACHE = await _fetch_my_orders(client)
            _autotop_orders_sync_live(
                ORDER_CACHE, trusted=bool(ORDER_CACHE),
            )
            return {
                "created": created,
                "skipped": skipped,
                "failed": failed,
                "live": len(ORDER_CACHE),
            }

        result, status = await _with_mrkt(event, status, work)
        lines = [
            "📦 <b>Bulk ordernew</b>",
            "",
            f"✅ Created: <code>{len(result['created'])}</code>",
            f"⏭️ Skipped: <code>{len(result['skipped'])}</code>",
            f"❌ Failed: <code>{len(result['failed'])}</code>",
            f"📋 Live now: <code>{result['live']}</code>",
            "",
        ]
        if result["created"]:
            lines.append("<b>Created</b>")
            for label, lo, hi, qty, oid in result["created"][:20]:
                oid_txt = f" · <code>{oid}</code>" if oid else ""
                lines.append(
                    f"• {label} — "
                    f"<code>{_ton2(lo)}-{_ton2(hi)}</code> "
                    f"×{qty}{oid_txt}"
                )
            if len(result["created"]) > 20:
                lines.append(f"… +{len(result['created']) - 20} more")
            lines.append("")
        if result["skipped"]:
            lines.append("<b>Skipped</b>")
            for label, why in result["skipped"][:15]:
                lines.append(f"• {label} — <i>{why}</i>")
            if len(result["skipped"]) > 15:
                lines.append(f"… +{len(result['skipped']) - 15} more")
            lines.append("")
        if result["failed"]:
            lines.append("<b>Failed</b>")
            for label, why in result["failed"][:15]:
                lines.append(f"• {label} — <code>{why}</code>")
            if len(result["failed"]) > 15:
                lines.append(f"… +{len(result['failed']) - 15} more")
        return await _edit_chunks(status, event, "\n".join(lines).rstrip())
    except ValueError as e:
        return await event.eor(f"❌ {e}", parse_mode="html")
    except (TradingError, RequestError, AuthError) as e:
        LOGS.warning("Artemis bulk ordernew request error: %s", e)
        return await status.edit(
            f"❌ <b>Bulk ordernew failed.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )
    except Exception as e:
        LOGS.exception("Artemis bulk ordernew failed: %s", e)
        return await status.edit(
            f"❌ <b>Bulk ordernew failed.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )


@heartless_cmd(owner_only=True, pattern=r"ordernew(?:\s+([\s\S]+))?$")
async def artemis_ordernew(event):
    global ORDER_CACHE
    raw = event.pattern_match.group(1)
    raw = (raw or "").strip()

    # Reply-to `.orders` dump, or a multi-line paste → bulk mode.
    bulk_text = None
    if raw and _looks_like_orders_list(raw):
        bulk_text = raw
    elif not raw and (event.is_reply or getattr(event, "reply_to_msg_id", None)):
        reply = await event.get_reply_message()
        reply_text = ""
        if reply is not None:
            reply_text = (
                getattr(reply, "raw_text", None)
                or getattr(reply, "text", None)
                or getattr(reply, "message", None)
                or ""
            )
            # HTML parse_mode messages: prefer message body before entities strip.
            if not _looks_like_orders_list(reply_text) and getattr(reply, "message", None):
                reply_text = reply.message
        if _looks_like_orders_list(reply_text):
            bulk_text = reply_text
    if bulk_text:
        return await _ordernew_bulk(event, bulk_text)

    if not raw:
        return await event.eor(
            "Usage:\n"
            f"<code>{_h('ordernew')} Collection, Model, Backdrop, QTY, MIN-MAX</code>\n"
            f"<code>{_h('ordernew')} Collection, Model, Backdrop, MIN-MAX</code>\n"
            f"<code>{_h('ordernew')} Collection, Model, MIN-MAX</code>\n\n"
            f"Bulk: reply to an <code>{_h('orders')}</code> list with "
            f"<code>{_h('ordernew')}</code>, or paste the list after the command.",
            parse_mode="html",
        )
    try:
        collection, model, backdrop, quantity, lo, hi = _parse_ordernew(raw)
    except Exception as e:
        return await event.eor(f"❌ <code>{e}</code>", parse_mode="html")

    status = None
    try:
        status = await event.eor("<b>Processing...</b>", parse_mode="html")

        async def work(client):
            global ORDER_CACHE
            coll, mod, back = await _resolve_gift_names(
                client, collection, model, backdrop,
            )
            if not mod:
                return None
            await _create_order(
                client,
                collection=coll,
                model=mod,
                backdrop=back,
                price_min_ton=lo,
                price_max_ton=hi,
                quantity=quantity,
            )
            ORDER_CACHE = await _fetch_my_orders(client)
            _autotop_orders_sync_live(ORDER_CACHE)
            return coll, mod, back

        resolved, status = await _with_mrkt(event, status, work)
        if resolved is None:
            return await status.edit(
                "❌ <b>Could not resolve model name on MRKT.</b>",
                parse_mode="html",
            )
        coll, mod, back = resolved
        return await status.edit(
            "✅ <b>Order created.</b>\n\n"
            f"📦 {coll}, {mod}, {back or 'ANY'}\n"
            f"🔢 Qty: <code>{quantity}</code>\n"
            f"💰 <code>{_ton2(lo)}-{_ton2(hi)} TON</code>\n"
            "🔓 <b>Without transfer lock</b>",
            parse_mode="html",
        )
    except ValueError as e:
        return await event.eor(f"❌ {e}", parse_mode="html")
    except (TradingError, RequestError, AuthError) as e:
        if status:
            return await status.edit(
                f"❌ <b>Order creation failed.</b>\n\n<code>{e}</code>",
                parse_mode="html",
            )
        return await event.eor(
            f"❌ <b>Order creation failed.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )
    except Exception as e:
        LOGS.exception("Artemis .ordernew failed: %s", e)
        if status:
            return await status.edit(
                f"❌ <b>Failed to create order.</b>\n\n<code>{e}</code>",
                parse_mode="html",
            )
        return await event.eor(
            f"❌ <b>Failed to create order.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )


@heartless_cmd(owner_only=True, pattern=r"gentoken(?:\s+(.+))?$")
async def artemis_gentoken(event):
    session = event.pattern_match.group(1)
    if not session or not session.strip():
        return await event.eor(
            f"Usage: <code>{_h('gentoken')} SESSION</code>", parse_mode="html",
        )
    session = session.strip()
    status = await event.eor(
        "<b>Generating Token...</b>", parse_mode="html",
    )
    try:
        with contextlib.suppress(Exception):
            udB.set_key("SESSIONMRKT", session)
        token = await _generate_token_from_session(session)
        await status.edit(
            "✅ <b>MRKT token generated.</b>\n\n"
            f"<code>{token}</code>\n\n"
            "Saved to <code>ARTEMIS_TOKEN</code> "
            "and session to <code>SESSIONMRKT</code>.",
            parse_mode="html",
        )
    except Exception as e:
        LOGS.exception("Artemis .gentoken failed")
        await status.edit(
            f"❌ <b>Failed to generate token.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )


# ============================================================
# .gift FLOORS (MRKT / Portal / GetGems / Tonnel)
# ============================================================

async def _highest_order_ton(client, collection, model=None, backdrop=None):
    data = await client.request(
        "POST",
        "/orders/top",
        json={
            "collectionName": collection,
            "modelName": model,
            "backdropName": backdrop,
            "symbolName": None,
        },
    )
    if not data:
        return None
    nano = data.get("priceMaxNanoTONs")
    return nano_to_ton(nano) if nano is not None else None


def _lookup_attr_price(prices_map, target_name):
    if not isinstance(prices_map, dict) or not target_name:
        return None
    targets = {
        _loose_key(_strip_rarity(v)) for v in _name_variants(target_name)
    }
    targets.add(_loose_key(_strip_rarity(target_name)))
    for key, value in prices_map.items():
        clean = _strip_rarity(key)
        if _loose_key(clean) in targets or _loose_key(key) in targets:
            try:
                return Decimal(str(value))
            except Exception:
                return None
    return None


def _changes_path_segment(value):
    """URL path segment for changes.tg (spaces → dashes is fine; API is flexible)."""
    text = str(value or "").strip()
    if not text:
        return ""
    from urllib.parse import quote

    return quote(text, safe="")


async def _changes_api_json(path, session=None):
    """GET JSON from api.changes.tg. path must start with '/'."""
    url = f"{CHANGES_API}{path}"
    owns_session = session is None
    try:
        if owns_session:
            timeout = aiohttp.ClientTimeout(total=12, connect=6)
            session = aiohttp.ClientSession(timeout=timeout)
        async with session.get(url) as resp:
            if resp.status != 200:
                LOGS.info("changes.tg HTTP %s for %s", resp.status, url)
                return None
            return await resp.json(content_type=None)
    except Exception as e:
        LOGS.warning("changes.tg fetch failed for %s: %s", url, e)
        return None
    finally:
        if owns_session and session is not None:
            await session.close()


def _changes_find_named(rows, target):
    """Pick the best matching {name, ...} row for target."""
    if not target or not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if name and _match_attr(name, target):
            return row
    return None


async def _changes_gift_snapshot(collection, model=None, session=None):
    """
    Gift/model metadata + rarities from api.changes.tg.
    Replaces TelegramGifts for the .gift info path (not floors).
    thanks to @GiftChanges for this API
    """
    empty = {
        "gift": {},
        "model": {},
        "collection": {},
        "model_floor": None,
        "backdrop_prices": {},
        "backdrop_rarities": {},
        "collection_name": collection,
        "model_name": model,
    }
    gift_seg = _changes_path_segment(collection)
    if not gift_seg:
        return empty

    owns_session = session is None
    try:
        if owns_session:
            timeout = aiohttp.ClientTimeout(total=12, connect=6)
            session = aiohttp.ClientSession(timeout=timeout)

        data = await _changes_api_json(f"/gift/{gift_seg}", session=session)
        if not isinstance(data, dict) or not data:
            return empty

        gift_info = data.get("gift") if isinstance(data.get("gift"), dict) else {}
        canon_name = gift_info.get("name") or collection
        gift = {
            "name": canon_name,
            "id": gift_info.get("id"),
            "short_name": canon_name,
            "customEmojiId": gift_info.get("customEmojiId"),
        }

        backdrop_rarities = {}
        for row in data.get("backdrops") or []:
            if not isinstance(row, dict):
                continue
            name = row.get("name")
            if not name:
                continue
            pm = _pct_to_permille(row.get("rarity"))
            if pm is not None:
                backdrop_rarities[name] = pm

        model_data = {}
        model_name = model
        if model:
            model_seg = _changes_path_segment(model)
            info = None
            if model_seg:
                info = await _changes_api_json(
                    f"/model/{gift_seg}/{model_seg}/info",
                    session=session,
                )
            if isinstance(info, dict) and info.get("name"):
                model_data = {
                    "name": info.get("name"),
                    "rarityPermille": info.get("rarityPermille"),
                }
                model_name = info.get("name")
            else:
                row = _changes_find_named(data.get("models") or [], model)
                if row:
                    model_data = {
                        "name": row.get("name"),
                        "rarityPermille": _pct_to_permille(row.get("rarity")),
                    }
                    model_name = row.get("name") or model

        return {
            "gift": gift,
            "model": model_data,
            "collection": {},
            "model_floor": None,
            "backdrop_prices": {},
            "backdrop_rarities": backdrop_rarities,
            "collection_name": canon_name,
            "model_name": model_name,
        }
    finally:
        if owns_session and session is not None:
            await session.close()


async def _satellite_market_floors(collection, model=None, backdrop=None):
    """
    Floors via Gift Satellite Mini App (all markets incl. MRKT).

    Returns (collection_floors, model_floors|None, full_floors|None).
    """
    empty = {label: None for _, label in SATELLITE_MARKETS}
    if not collection:
        return dict(empty), (dict(empty) if model else None), (
            dict(empty) if (model and backdrop) else None
        )

    tasks = [
        asyncio.create_task(sat._all_market_floors(collection, None, None))
    ]
    if model:
        tasks.append(
            asyncio.create_task(sat._all_market_floors(collection, model, None))
        )
    if model and backdrop:
        tasks.append(
            asyncio.create_task(
                sat._all_market_floors(collection, model, backdrop)
            )
        )
    results = await asyncio.gather(*tasks, return_exceptions=True)

    def _ok(res, fallback):
        if isinstance(res, Exception):
            LOGS.warning("Satellite miniapp floors failed: %s", res)
            return fallback
        return res or fallback

    collection_floors = _ok(results[0], dict(empty))
    model_floors = None
    full_floors = None
    idx = 1
    if model:
        model_floors = _ok(results[idx], dict(empty))
        idx += 1
    if model and backdrop:
        full_floors = _ok(results[idx], dict(empty))
    return collection_floors, model_floors, full_floors


async def _mrkt_search_transferable(
    client,
    *,
    collection,
    model=None,
    backdrop=None,
    count=20,
):
    """
    POST /gifts/saling with transferable-only filter (no premarket / transfer lock).
    Falls back to a raw body when the installed Artemis SDK lacks is_transferable.
    """
    count = max(int(count or 1), 1)
    kwargs = {
        "collection_names": [collection],
        "ordering": "Price",
        "low_to_high": True,
        "count": count,
        "is_premarket": False,
        "is_transferable": True,
    }
    if model:
        kwargs["model_names"] = [model]
    if backdrop:
        kwargs["backdrop_names"] = [backdrop]
    try:
        return await client.market.search(**kwargs)
    except TypeError:
        from artemis.models import MRKTGift, GiftPage

        body = {
            "collectionNames": [collection],
            "modelNames": [model] if model else [],
            "backdropNames": [backdrop] if backdrop else [],
            "symbolNames": [],
            "ordering": "Price",
            "lowToHigh": True,
            "maxPrice": None,
            "minPrice": None,
            "mintable": None,
            "number": None,
            "count": count,
            "cursor": "",
            "query": None,
            "isPremarket": False,
            "promotedFirst": False,
            "isTransferable": True,
        }
        data = await client.request("POST", "/gifts/saling", json=body)
        raw = data if isinstance(data, dict) else {}
        items = [MRKTGift(x) for x in raw.get("gifts") or []]
        return GiftPage(items, raw.get("cursor"), raw)


async def _mrkt_cheapest(client, collection, model=None, backdrop=None, count=1):
    """
    Cheapest transferable MRKT listings (excludes premarket / locked).
    Tries canonical names first (fast path), then case/space variants if empty.
    """
    want = max(int(count or 1), 1)
    # Ask for a wider page so client-side lock filters still leave enough hits.
    fetch_count = max(want, 20)

    primary = [(collection, model, backdrop)]
    extras = []
    coll_variants = _name_variants(collection) or [collection]
    model_variants = _name_variants(model) if model else [None]
    backdrop_variants = _name_variants(backdrop) if backdrop else [None]
    for coll in coll_variants:
        for mod in model_variants:
            for back in backdrop_variants:
                trip = (coll, mod, back)
                if trip != primary[0]:
                    extras.append(trip)

    items = []
    used_collection = collection
    used_model = model
    used_backdrop = backdrop

    for coll, mod, back in primary + extras:
        try:
            page = await _mrkt_search_transferable(
                client,
                collection=coll,
                model=mod,
                backdrop=back,
                count=fetch_count,
            )
        except Exception:
            continue
        items = list(page.items or [])
        if items:
            used_collection = coll
            used_model = mod
            used_backdrop = back
            break

    if not items:
        return None, []

    # Prefer the true minimum among transferable listings, verifying attrs.
    best = None
    best_price = None
    matched = []
    for gift in items:
        if not _gift_without_transfer_lock(gift):
            continue
        raw = _get_raw(gift)
        item_model = (
            raw.get("modelName")
            or raw.get("modelTitle")
            or raw.get("model")
            or getattr(gift, "model", None)
        )
        item_backdrop = (
            raw.get("backdropName")
            or raw.get("backdropTitle")
            or raw.get("backdrop")
            or getattr(gift, "backdrop", None)
        )
        # Require exact filter match — missing attrs do not pass.
        if used_model and (
            not item_model or not _match_attr(item_model, used_model)
        ):
            continue
        if used_backdrop and (
            not item_backdrop or not _match_attr(item_backdrop, used_backdrop)
        ):
            continue
        price = getattr(gift, "price_ton", None)
        if price is None and raw.get("salePrice") is not None:
            price = nano_to_ton(raw.get("salePrice") or 0)
        price = _as_floor(price)
        if price is None:
            continue
        matched.append(gift)
        if best_price is None or price < best_price:
            best_price = price
            best = gift

    if not matched:
        return None, []
    return best_price, matched[:want]




def _format_tehran(value):
    """Format an ISO/unix timestamp as `D/M - HH:MM:SS` in Asia/Tehran."""
    ts = _parse_order_ts(value)
    if ts is None:
        return "—"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(TEHRAN_TZ)
    return f"{dt.day}/{dt.month} - {dt.strftime('%H:%M:%S')}"


async def _fetch_monochromes(collection, model):
    """Monochrome backdrops via Gift Satellite Mini App (not GiftWiki API key)."""
    return await sat._fetch_monochromes(collection, model)


def _format_monochrome_block(rows, highlight_backdrop=None):
    """
    Monochrome lines under Backdrop.
    Marks the current NFT/filter backdrop with ☑ when it matches.
    """
    lines = ["🖤 <b>Monochrome:</b>", ""]
    if not rows:
        lines.append("<b>Model has no monochrome color -_-</b>")
        lines.append("")
        return lines

    for row in rows:
        name = row.get("backdrop_name") or "—"
        level = row.get("type") or ""
        mark = ""
        if highlight_backdrop and _match_attr(name, highlight_backdrop):
            mark = " ☑"
        if level:
            lines.append(f"   {name} => {level}{mark}")
        else:
            lines.append(f"   {name}{mark}")
    lines.append("")
    return lines


async def _satellite_floors_for_filter(collection, model=None, backdrop=None):
    """Satellite miniapp floors for exactly one filter level."""
    if not collection:
        return {label: None for _, label in SATELLITE_MARKETS}
    try:
        return await sat._all_market_floors(collection, model, backdrop)
    except Exception as e:
        LOGS.warning("Satellite floors-for-filter failed: %s", e)
        return {label: None for _, label in SATELLITE_MARKETS}


def _sat_floor_rows(floors: dict | None):
    """Ordered (label, price) rows for all Satellite markets (incl. MRKT)."""
    floors = floors or {}
    return [(label, floors.get(label)) for _s, label in SATELLITE_MARKETS]


def _format_sat_sales_section(sales_by_market: dict | None, *, limit_note=4):
    """HTML block for multi-market latest sales (Satellite style)."""
    lines = [f"🧾 <b>Latest Sales</b> ({limit_note} / market)", ""]
    any_sales = False
    for _s, label in SATELLITE_MARKETS:
        sales = (sales_by_market or {}).get(label) or []
        lines.extend(sat._format_sales_market_block(label, sales, html_mode=True))
        lines.append("")
        if sales:
            any_sales = True
    if not any_sales:
        lines.append("<i>No matching sales found.</i>")
        lines.append("")
    return lines


async def _build_gift_floor_only(client, collection, model=None, backdrop=None):
    """
    Compact `.gift c` / inline floor output:
    headers + multi-market floors (Satellite) + matching quick sell (MRKT).
    ``client`` may be None for Satellite-only floor panels (faster inline).
    """
    sat_task = asyncio.create_task(
        _satellite_floors_for_filter(
            collection, model=model, backdrop=backdrop,
        )
    )
    quick_task = (
        asyncio.create_task(
            _highest_order_ton(client, collection, model, backdrop)
        )
        if client is not None else None
    )
    models_task = (
        asyncio.create_task(
            client.request(
                "POST", "/gifts/models", json={"collections": [collection]},
            )
        )
        if client is not None and model else None
    )
    backdrops_task = (
        asyncio.create_task(
            client.request(
                "POST",
                "/gifts/backdrops",
                json={"collections": [collection]},
            )
        )
        if client is not None and model and backdrop else None
    )
    tg_snap_task = (
        asyncio.create_task(_changes_gift_snapshot(collection, model))
        if model else None
    )

    try:
        sat_floors = await sat_task
    except Exception as e:
        LOGS.warning("Compact satellite floors failed: %s", e)
        sat_floors = {label: None for _, label in SATELLITE_MARKETS}

    quick = None
    if quick_task is not None:
        try:
            quick = await quick_task
        except Exception as e:
            LOGS.warning("Compact quick sell failed: %s", e)
            quick = None

    model_rarity = None
    backdrop_rarity = None
    tg_snap = {}
    if tg_snap_task is not None:
        try:
            tg_snap = await tg_snap_task
        except Exception as e:
            LOGS.warning("Compact gift snapshot failed: %s", e)
            tg_snap = {}

    if model:
        try:
            models = await models_task if models_task else []
        except Exception:
            models = []
        model_row = _find_named_row(models, ("modelName", "name"), model)
        model_rarity = model_row.get("rarityPerMille")
        if model_rarity is None:
            tg_model = (tg_snap or {}).get("model") or {}
            model_rarity = (
                tg_model.get("rarity_permille")
                or tg_model.get("rarityPerMille")
                or _rarity_from_label(tg_model.get("name"))
            )

    if model and backdrop:
        try:
            backdrops = await backdrops_task if backdrops_task else []
        except Exception:
            backdrops = []
        back_row = _find_named_row(
            backdrops, ("backdropName", "name"), backdrop,
        )
        backdrop_rarity = back_row.get("rarityPerMille")
        if backdrop_rarity is None:
            for key, pm in (tg_snap.get("backdrop_rarities") or {}).items():
                if _match_attr(key, backdrop):
                    backdrop_rarity = pm
                    break
        if backdrop_rarity is None:
            for key in (tg_snap.get("backdrop_prices") or {}):
                if _match_attr(key, backdrop):
                    backdrop_rarity = _rarity_from_label(key)
                    if backdrop_rarity is not None:
                        break

    def _md(value):
        text = str(value or "")
        return (
            text.replace("\\", "\\\\")
            .replace("_", "\\_")
            .replace("*", "\\*")
            .replace("`", "\\`")
            .replace("[", "\\[")
        )

    lines = [f"🎁 **Collection:** `{_md(collection)}`"]
    if model:
        lines.append(
            f"🧩 **Model:** `{_md(model)}` (`{_md(_rarity_pct(model_rarity))}`)"
        )
    if backdrop:
        lines.append(
            f"🎨 **Backdrop:** `{_md(backdrop)}` "
            f"(`{_md(_rarity_pct(backdrop_rarity))}`)"
        )
    lines.append("")
    for label, value in _sat_floor_rows(sat_floors):
        lines.append(f"💰 **{label}:** `{_md(_floor_ton(value))}`")
    lines.append("")

    quick_txt = _ton2(quick) if quick is not None else "—"
    if model and backdrop:
        lines.append(
            f"📊 **Quick Sell Collection + Model + Backdrop:** "
            f"`{_md(quick_txt)} TON`"
        )
    elif model:
        lines.append(
            f"📊 **Quick Sell Collection + Model:** `{_md(quick_txt)} TON`"
        )
    else:
        lines.append(
            f"📊 **Quick Sell Collection:** `{_md(quick_txt)} TON`"
        )
    # labels already bold via **Label:** above

    return "\n".join(lines)


async def _build_gift_info(
    client,
    collection,
    model=None,
    backdrop=None,
    *,
    include_listings=False,
    tg_snap=None,
    seed_rarities=None,
    nft_url=None,
    sat_task=None,
):
    tg_snap = tg_snap or await _changes_gift_snapshot(collection, model)
    tg_gift = tg_snap.get("gift") or {}
    tg_model = tg_snap.get("model") or {}
    seed_rarities = seed_rarities or {}

    # Satellite should already be running; start it here if not.
    if sat_task is None:
        sat_task = asyncio.create_task(
            _satellite_market_floors(
                collection, model=model, backdrop=backdrop,
            )
        )

    mono_task = (
        asyncio.create_task(_fetch_monochromes(collection, model))
        if model else None
    )

    model_rarity = seed_rarities.get("model_rarity")
    backdrop_rarity = seed_rarities.get("backdrop_rarity")
    listing_items = []
    model_row = {}
    back_row = {}

    # Artemis/MRKT: quick sells + cheapest listings only (floors via Satellite).
    quick_coll_task = asyncio.create_task(
        _highest_order_ton(client, collection),
    )
    quick_model_task = (
        asyncio.create_task(_highest_order_ton(client, collection, model))
        if model else None
    )
    quick_full_task = (
        asyncio.create_task(
            _highest_order_ton(client, collection, model, backdrop),
        )
        if model and backdrop else None
    )
    models_task = (
        asyncio.create_task(
            client.request(
                "POST", "/gifts/models", json={"collections": [collection]},
            )
        )
        if model else None
    )
    backdrops_task = (
        asyncio.create_task(
            client.request(
                "POST",
                "/gifts/backdrops",
                json={"collections": [collection]},
            )
        )
        if model and backdrop else None
    )
    # Prefer full-filter listings when backdrop is set (one search covers both).
    if model and backdrop and include_listings:
        model_list_task = None
        full_list_task = asyncio.create_task(
            _mrkt_cheapest(
                client, collection, model=model, backdrop=backdrop, count=5,
            ),
        )
    elif model and include_listings:
        model_list_task = asyncio.create_task(
            _mrkt_cheapest(client, collection, model=model, count=5),
        )
        full_list_task = None
    else:
        model_list_task = None
        full_list_task = None

    if model:
        try:
            models = await models_task if models_task else []
        except Exception:
            models = []
        model_row = _find_named_row(
            models, ("modelName", "name"), model,
        )

        if model_rarity is None:
            model_rarity = model_row.get("rarityPerMille")
        if model_rarity is None and tg_model:
            model_rarity = (
                tg_model.get("rarity_permille")
                or tg_model.get("rarityPerMille")
                or _rarity_from_label(tg_model.get("name"))
            )

        if backdrop:
            try:
                backdrops = await backdrops_task if backdrops_task else []
            except Exception:
                backdrops = []
            back_row = _find_named_row(
                backdrops, ("backdropName", "name"), backdrop,
            )
            if backdrop_rarity is None:
                backdrop_rarity = back_row.get("rarityPerMille")

            if backdrop_rarity is None:
                for key, pm in (tg_snap.get("backdrop_rarities") or {}).items():
                    if _match_attr(key, backdrop):
                        backdrop_rarity = pm
                        break
            if backdrop_rarity is None:
                for key in (tg_snap.get("backdrop_prices") or {}):
                    if _match_attr(key, backdrop):
                        backdrop_rarity = _rarity_from_label(key)
                        if backdrop_rarity is not None:
                            break

        if include_listings:
            try:
                if full_list_task is not None:
                    _, listing_items = await full_list_task
                elif model_list_task is not None:
                    _, listing_items = await model_list_task
            except Exception as e:
                LOGS.warning("MRKT cheapest listings failed: %s", e)
                listing_items = []

            if listing_items:
                raw = _get_raw(listing_items[0])
                if model_rarity is None:
                    model_rarity = raw.get("modelRarityPerMille")
                if backdrop and backdrop_rarity is None:
                    backdrop_rarity = raw.get("backdropRarityPerMille")

    # Await satellite floors + quicksells together.
    sat_result, quick_collection = await asyncio.gather(
        sat_task, quick_coll_task, return_exceptions=True,
    )
    if isinstance(sat_result, Exception):
        LOGS.warning("Satellite floors failed: %s", sat_result)
        sat_collection, sat_model, sat_full = (
            {label: None for _, label in SATELLITE_MARKETS},
            None,
            None,
        )
    else:
        sat_collection, sat_model, sat_full = sat_result

    if isinstance(quick_collection, Exception):
        LOGS.warning("Quicksell collection failed: %s", quick_collection)
        quick_collection = None

    quick_coll_model = None
    quick_full = None
    if quick_model_task is not None:
        try:
            quick_coll_model = await quick_model_task
        except Exception as e:
            LOGS.warning("Quicksell model failed: %s", e)
    if quick_full_task is not None:
        try:
            quick_full = await quick_full_task
        except Exception as e:
            LOGS.warning("Quicksell full failed: %s", e)

    def floor_block(title, values):
        lines = [title, ""]
        for label, value in values:
            lines.append(f"   <b>{label}</b>: {_floor_ton(value)}")
        lines.append("")
        return lines

    lines = []
    if nft_url:
        lines.append(
            f'🎁 <a href="{nft_url}"><b>NFT Info</b></a>'
        )
    else:
        lines.append("🎁 <b>NFT Info</b>")
    lines.append("")

    lines.extend(
        floor_block(
            f"🎁 <b>Collection:</b> {collection}",
            _sat_floor_rows(sat_collection),
        )
    )

    if model:
        lines.extend(
            floor_block(
                f"🧩 <b>Model:</b> {model} ({_rarity_pct(model_rarity)})",
                _sat_floor_rows(sat_model),
            )
        )

        if backdrop:
            lines.extend(
                floor_block(
                    f"🎨 <b>Backdrop:</b> {backdrop} "
                    f"({_rarity_pct(backdrop_rarity)})",
                    _sat_floor_rows(sat_full),
                )
            )
        else:
            lines.extend([
                "🎨 Backdrop: ANY",
                "",
            ])

        # Monochrome backdrops for this model (Satellite miniapp).
        mono_rows = []
        if mono_task is not None:
            try:
                mono_rows = await mono_task
            except Exception as e:
                LOGS.warning("Monochrome fetch failed: %s", e)
                mono_rows = []
        lines.extend(
            _format_monochrome_block(mono_rows, highlight_backdrop=backdrop)
        )

    lines.append(
        f"📊 <b>Quick Sell Collection:</b> "
        f"{_ton2(quick_collection) if quick_collection is not None else '—'} TON"
    )
    if model:
        lines.append(
            f"📊 <b>Quick Sell Collection + Model:</b> "
            f"{_ton2(quick_coll_model) if quick_coll_model is not None else '—'} TON"
        )
        if backdrop:
            lines.append(
                f"📊 <b>Quick Sell Collection + Model + Backdrop:</b> "
                f"{_ton2(quick_full) if quick_full is not None else '—'} TON"
            )
    lines.append("")

    if model and include_listings:
        # Exact filter: C+Model, or C+Model+Backdrop when backdrop is set.
        list_model = model
        list_backdrop = backdrop if backdrop else None
        if not listing_items:
            try:
                _, listing_items = await _mrkt_cheapest(
                    client,
                    collection,
                    model=list_model,
                    backdrop=list_backdrop,
                    count=5,
                )
            except Exception:
                listing_items = []
        if list_backdrop:
            list_title = "🎁 <b>MRKT Listings</b> (Collection + Model + Backdrop)"
        else:
            list_title = "🎁 <b>MRKT Listings</b> (Collection + Model)"
        lines.append(list_title)
        lines.append("")
        shown = listing_items[:5]
        for i, gift in enumerate(shown, 1):
            gift_id = getattr(gift, "id", "")
            gift_name = getattr(gift, "name", "")
            lines.append(
                f'    {i}. 🎁 <a href="{_mrkt_link(gift_id)}">MRKT</a> - '
                f'<a href="{_nft_link(gift_name)}">NFT</a>'
            )
            lines.append(
                f"        💰 {_ton2(getattr(gift, 'price_ton', 0))} TON"
            )
            lines.append("")
        lines.append(f"📊 Found: {len(shown)}")
        lines.append("")

    # Multi-market sales live on inline NFT Sales — gift output
    # only shows MRKT listings for the active filter.

    return "\n".join(lines).rstrip(), tg_gift, tg_model


# ============================================================
# MONITOR / BUY
# ============================================================

def _gift_without_transfer_lock(gift):
    """
    True when a listing has no Telegram transfer lock.
    Mirrors MRKT order filter isTransferable=True.
    """
    raw = getattr(gift, "raw", None)
    if not isinstance(raw, dict):
        raw = _get_raw(gift) if gift is not None else {}
    if "isTransferable" in raw:
        return bool(raw.get("isTransferable"))
    if getattr(gift, "is_locked", False) or raw.get("isLocked"):
        return False
    ntd = getattr(gift, "next_transfer_date", None)
    if ntd is None:
        ntd = raw.get("nextTransferDate")
    if not ntd:
        return True
    try:
        if isinstance(ntd, (int, float)):
            ts = float(ntd)
            if ts > 1e12:
                ts /= 1000.0
            return ts <= time.time()
        text = str(ntd).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp() <= time.time()
    except Exception:
        return True


async def _monitor_search(client, collection, model, backdrop, min_ton, max_ton):
    """
    Autobuy listing search — without transfer lock by default
    (isTransferable=True, same as .ordernew).
    """
    search_kwargs = {
        "collection_names": [collection],
        "model_names": [model],
        "ordering": "Price",
        "low_to_high": True,
        "min_price": float(min_ton),
        "max_price": float(max_ton),
        "count": 20,
        "is_transferable": True,
    }
    if backdrop:
        search_kwargs["backdrop_names"] = [backdrop]
    try:
        return await client.market.search(**search_kwargs)
    except TypeError:
        # Older artemis builds without is_transferable on search.
        from artemis.models import MRKTGift, GiftPage

        body = {
            "collectionNames": [collection],
            "modelNames": [model],
            "backdropNames": [backdrop] if backdrop else [],
            "symbolNames": [],
            "ordering": "Price",
            "lowToHigh": True,
            "maxPrice": ton_to_nano(float(max_ton)),
            "minPrice": ton_to_nano(float(min_ton)),
            "mintable": None,
            "number": None,
            "count": 20,
            "cursor": "",
            "query": None,
            "isPremarket": False,
            "promotedFirst": False,
            "isTransferable": True,
        }
        data = await client.request("POST", "/gifts/saling", json=body)
        raw = data if isinstance(data, dict) else {}
        items = [MRKTGift(x) for x in raw.get("gifts") or []]
        return GiftPage(items, raw.get("cursor"), raw)


async def _monitor_worker(monitor_id):
    monitor = BUY_MONITORS.get(monitor_id)
    if not monitor:
        return
    collection = monitor["collection"]
    model = monitor["model"]
    backdrop = monitor["backdrop"]
    min_ton = monitor["min_ton"]
    max_ton = monitor["max_ton"]
    min_nano = ton_to_nano(float(min_ton))
    max_nano = ton_to_nano(float(max_ton))
    try:
        while True:
            token = ARTEMIS_TOKEN
            if not token:
                LOGS.error(
                    "Artemis monitor #%s stopped: no token configured.",
                    monitor_id,
                )
                return
            async with MRKTClient(token=token) as client:
                try:
                    page = await _monitor_search(
                        client, collection, model, backdrop, min_ton, max_ton,
                    )
                    for gift in page.items:
                        if monitor_id not in BUY_MONITORS:
                            return
                        if not _gift_without_transfer_lock(gift):
                            continue
                        price_nano = getattr(gift, "price_nano", None) or 0
                        if not (min_nano <= price_nano <= max_nano):
                            continue
                        gift_id = getattr(gift, "id", None)
                        if gift_id is None:
                            continue
                        async with BUY_LOCK:
                            if monitor_id not in BUY_MONITORS:
                                return
                            try:
                                result = await client.market.buy(
                                    gift_id, price_nano,
                                )
                                LOGS.info(
                                    "Artemis purchase successful: monitor=%s gift=%s result=%s",
                                    monitor_id, gift_id, result,
                                )
                            except (TradingError, RequestError) as e:
                                LOGS.warning(
                                    "Artemis buy failed: monitor=%s gift=%s error=%s",
                                    monitor_id, gift_id, e,
                                )
                                continue
                            except Exception as e:
                                LOGS.exception(
                                    "Unexpected Artemis buy error: monitor=%s gift=%s error=%s",
                                    monitor_id, gift_id, e,
                                )
                                continue
                        await _send_purchase_log(client, gift, monitor_id)
                        if BUY_ONE:
                            return
                except asyncio.CancelledError:
                    raise
                except (TradingError, RequestError) as e:
                    if _is_token_expired_error(e):
                        try:
                            await _force_refresh_token()
                            LOGS.info(
                                "Artemis monitor #%s refreshed expired token",
                                monitor_id,
                            )
                        except Exception as refresh_err:
                            LOGS.warning(
                                "Artemis monitor #%s token refresh failed: %s",
                                monitor_id,
                                refresh_err,
                            )
                    LOGS.warning(
                        "Artemis monitor #%s request error: %s",
                        monitor_id, e,
                    )
                except Exception as e:
                    LOGS.exception(
                        "Artemis monitor #%s scan error: %s",
                        monitor_id, e,
                    )
            await asyncio.sleep(POLL_SECONDS)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        LOGS.exception("Artemis monitor #%s crashed: %s", monitor_id, e)
    finally:
        current = BUY_MONITORS.get(monitor_id)
        if current and current.get("task") is asyncio.current_task():
            BUY_MONITORS.pop(monitor_id, None)


def _start_monitor(collection, model, backdrop, min_ton, max_ton):
    monitor_id = _next_monitor_id()
    monitor = {
        "task": None,
        "collection": collection,
        "model": model,
        "backdrop": backdrop,
        "min_ton": min_ton,
        "max_ton": max_ton,
        "created_at": time.time(),
    }
    BUY_MONITORS[monitor_id] = monitor
    task = asyncio.create_task(_monitor_worker(monitor_id))
    monitor["task"] = task
    return monitor_id


async def _cancel_monitor(monitor_id, wait=True):
    monitor = BUY_MONITORS.pop(monitor_id, None)
    if not monitor:
        return False
    task = monitor.get("task")
    if task and not task.done():
        task.cancel()
        if wait:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
    return True


async def _restart_all_monitors():
    old_monitors = list(BUY_MONITORS.items())
    for _, monitor in old_monitors:
        task = monitor.get("task")
        if task and not task.done():
            task.cancel()
    for _, monitor in old_monitors:
        task = monitor.get("task")
        if task:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
    for monitor_id, monitor in old_monitors:
        new_monitor = {
            "task": None,
            "collection": monitor["collection"],
            "model": monitor["model"],
            "backdrop": monitor["backdrop"],
            "min_ton": monitor["min_ton"],
            "max_ton": monitor["max_ton"],
            "created_at": time.time(),
        }
        BUY_MONITORS[monitor_id] = new_monitor
        task = asyncio.create_task(_monitor_worker(monitor_id))
        new_monitor["task"] = task


@heartless_cmd(owner_only=True, pattern=r"buytoken(?:\s+(.+))?$")
async def artemis_buytoken(event):
    token = event.pattern_match.group(1)
    if not token or not token.strip():
        return await event.eor(
            "❌ <b>Artemis token is missing.</b>\n\n"
            f"Use:\n<code>{_h('buytoken')} YOUR_ARTEMIS_TOKEN</code>",
            parse_mode="html",
        )
    token = token.strip()
    async with TOKEN_LOCK:
        _store_artemis_token(token)
        monitor_count = len(BUY_MONITORS)
        if monitor_count:
            status = await event.eor(
                "🔄 <b>Updating Artemis token...</b>\n"
                f"Restarting <code>{monitor_count}</code> active monitor(s)...",
                parse_mode="html",
            )
            await _restart_all_monitors()
            return await status.edit(
                "✅ <b>Artemis token updated.</b>\n\n"
                f"🔄 Restarted <code>{monitor_count}</code> active monitor(s).\n"
                "Saved to DB key <code>ARTEMIS_TOKEN</code>.",
                parse_mode="html",
            )
    await event.eor(
        "✅ <b>Artemis token updated.</b>\n\n"
        "Saved to DB key <code>ARTEMIS_TOKEN</code>.\n"
        "No active monitors needed restarting.",
        parse_mode="html",
    )


@heartless_cmd(owner_only=True, pattern=r"b$")
async def artemis_balance(event):
    """Show MRKT hard balance in TON."""
    status = None
    try:
        if status is None:
            status = await event.eor(
                "<b>Fetching balance...</b>",
                parse_mode="html",
            )

        async def work(client):
            bal = await client.account.balance()
            raw = getattr(bal, "raw", None) or {}
            hard = raw.get("hard")
            if hard is None:
                hard = getattr(bal, "hard", None)
            return hard

        hard, status = await _with_mrkt(event, status, work)
        if hard is None:
            return await status.edit(
                "❌ <b>Could not read MRKT balance.</b>",
                parse_mode="html",
            )
        ton = Decimal(str(hard)) / Decimal("1000000000")
        return await status.edit(
            f"💰 <b>MRKT Balance:</b> "
            f"<code>{ton.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}</code> TON",
            parse_mode="html",
        )
    except ValueError as e:
        return await event.eor(f"❌ {e}", parse_mode="html")
    except (TradingError, RequestError, AuthError) as e:
        LOGS.warning("Artemis .b request error: %s", e)
        target = status or event
        return await target.edit(
            f"❌ <b>Artemis request failed.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        ) if status else await event.eor(
            f"❌ <b>Artemis request failed.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )
    except Exception as e:
        LOGS.exception("Artemis .b failed: %s", e)
        if status:
            return await status.edit(
                f"❌ <b>Failed to fetch balance.</b>\n\n<code>{e}</code>",
                parse_mode="html",
            )
        return await event.eor(
            f"❌ <b>Failed to fetch balance.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )


async def _fetch_my_listed_gifts(client, *, page_size=100, max_pages=20):
    """All gifts the account currently has listed for sale on MRKT."""
    items = []
    cursor = ""
    for _ in range(max_pages):
        page = await client.account.gifts(
            count=page_size,
            cursor=cursor or "",
            is_listed=True,
            ordering="Price",
            low_to_high=True,
        )
        batch = list(page.items or [])
        if not batch:
            break
        items.extend(batch)
        cursor = getattr(page, "cursor", None) or ""
        if not cursor:
            break
    return items


def _model_floor_from_map(floors_map, model_name):
    """Case/space-insensitive model floor lookup from a {name: Decimal} map."""
    if not floors_map or not model_name:
        return None
    direct = floors_map.get(model_name)
    amount = _as_floor(direct)
    if amount is not None:
        return amount
    target = _loose_key(model_name)
    for key, value in floors_map.items():
        if _loose_key(key) == target:
            return _as_floor(value)
    return None


async def _listed_nfts_message(client):
    gifts = await _fetch_my_listed_gifts(client)
    if not gifts:
        return "🏦 <b>Listed NFTs</b>\n\n— No listed NFTs."

    # Batch model floors per collection (one API call each).
    floor_cache = {}
    collections = []
    seen_coll = set()
    for gift in gifts:
        coll = (
            getattr(gift, "collection_name", None)
            or _get_raw(gift).get("collectionName")
        )
        if coll and _loose_key(coll) not in seen_coll:
            seen_coll.add(_loose_key(coll))
            collections.append(coll)

    async def _load_floors(coll):
        try:
            floors = await client.market.model_floors(coll)
            return coll, dict(getattr(floors, "values", None) or {})
        except Exception as e:
            LOGS.warning("Model floors failed for %s: %s", coll, e)
            return coll, {}

    coll_floors_task = asyncio.create_task(client.market.collection_floors())
    if collections:
        model_loads = asyncio.gather(
            *[_load_floors(c) for c in collections],
            return_exceptions=True,
        )
    else:
        async def _empty():
            return []
        model_loads = _empty()

    try:
        coll_floors = await coll_floors_task
    except Exception as e:
        LOGS.warning("Collection floors failed: %s", e)
        coll_floors = None

    loaded = await model_loads
    for row in loaded:
        if isinstance(row, Exception):
            continue
        coll, values = row
        floor_cache[_loose_key(coll)] = values

    lines = ["🏦 <b>Listed NFTs</b>", ""]
    for i, gift in enumerate(gifts, 1):
        raw = _get_raw(gift)
        gift_id = getattr(gift, "id", None) or raw.get("id") or ""
        gift_name = getattr(gift, "name", None) or raw.get("name") or ""
        price = _as_floor(getattr(gift, "price_ton", None))
        if price is None and raw.get("salePrice") is not None:
            price = _as_floor(nano_to_ton(raw.get("salePrice") or 0))

        coll = (
            getattr(gift, "collection_name", None)
            or raw.get("collectionName")
        )
        model = (
            getattr(gift, "model_name", None)
            or getattr(gift, "model", None)
            or raw.get("modelName")
        )
        model_floor = _model_floor_from_map(
            floor_cache.get(_loose_key(coll) if coll else "", {}),
            model,
        )
        collection_floor = _mrkt_floor_lookup(coll_floors, coll) if coll else None

        lines.append(
            f'{i}. <a href="{_mrkt_link(gift_id)}">MRKT</a> - '
            f'<a href="{_nft_link(gift_name)}">NFT</a>'
        )
        lines.append(
            f"   💰Price: {_ton2(price) if price is not None else '—'}"
        )
        lines.append(
            f"   💹 Model Floor: "
            f"{_ton2(model_floor) if model_floor is not None else '—'}"
        )
        lines.append(
            f"   ☯️ Collection Floor: "
            f"{_ton2(collection_floor) if collection_floor is not None else '—'}"
        )
        lines.append("")

    return "\n".join(lines).rstrip()


@heartless_cmd(owner_only=True, pattern=r"nfts$")
async def artemis_nfts(event):
    """Show your currently listed MRKT NFTs with model floors."""
    status = None
    try:
        status = await event.eor(
            "<b>Fetching listed NFTs...</b>",
            parse_mode="html",
        )

        async def work(client):
            return await _listed_nfts_message(client)

        message, status = await _with_mrkt(event, status, work)
        return await _edit_chunks(status, event, message, parse_mode="html")
    except ValueError as e:
        return await event.eor(f"❌ {e}", parse_mode="html")
    except (TradingError, RequestError) as e:
        LOGS.warning("Artemis .nfts request error: %s", e)
        if status:
            return await status.edit(
                f"❌ <b>Artemis request failed.</b>\n\n<code>{e}</code>",
                parse_mode="html",
            )
        return await event.eor(
            f"❌ <b>Artemis request failed.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )
    except Exception as e:
        LOGS.exception("Artemis .nfts failed: %s", e)
        if status:
            return await status.edit(
                f"❌ <b>Failed to fetch listed NFTs.</b>\n\n<code>{e}</code>",
                parse_mode="html",
            )
        return await event.eor(
            f"❌ <b>Failed to fetch listed NFTs.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )


@heartless_cmd(owner_only=True, pattern=r"buy(?:\s+(.+))?$")
async def artemis_buy(event):
    try:
        await _ensure_artemis_token(event)
    except ValueError as e:
        return await event.eor(f"❌ {e}", parse_mode="html")
    raw = event.pattern_match.group(1)
    if not raw:
        return await event.eor(
            "❌ <b>Filter is missing.</b>\n\n"
            "Correct format:\n"
            f"<code>{_h('buy')} Collection, Model, Backdrop, MIN-MAX</code>",
            parse_mode="html",
        )
    try:
        collection, model, backdrop, min_ton, max_ton = _parse_buy_command(raw)
    except ValueError as e:
        return await event.eor(
            f"❌ <b>Invalid filter:</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )
    try:
        async with MRKTClient(token=ARTEMIS_TOKEN) as client:
            collection, model, backdrop = await _resolve_gift_names(
                client, collection, model, backdrop,
            )
    except Exception as e:
        LOGS.warning("Buy name resolve failed: %s", e)

    monitor_id = _start_monitor(
        collection=collection,
        model=model,
        backdrop=backdrop,
        min_ton=min_ton,
        max_ton=max_ton,
    )
    await event.eor(
        "🟢 <b>Artemis monitor started</b>\n\n"
        f"🆔 <b>Monitor:</b> <code>#{monitor_id}</code>\n"
        f"📦 <b>Collection:</b> <code>{collection}</code>\n"
        f"🧬 <b>Model:</b> <code>{model}</code>\n"
        f"🎨 <b>Backdrop:</b> <code>{backdrop or 'ANY'}</code>\n"
        f"💰 <b>Price:</b> <code>{_format_ton(min_ton)} - {_format_ton(max_ton)} TON</code>\n"
        f"Cancel with <code>{_h('buycancel')} {monitor_id}</code>",
        parse_mode="html",
    )


@heartless_cmd(owner_only=True, pattern=r"buys$")
async def artemis_buys(event):
    if not BUY_MONITORS:
        return await event.eor(
            "📭 <b>No active Artemis monitors.</b>", parse_mode="html",
        )
    lines = ["🤖 <b>Artemis Auto Buy Monitors</b>", ""]
    for monitor_id, monitor in sorted(BUY_MONITORS.items()):
        task = monitor.get("task")
        if not task:
            status = "🟡 STARTING"
        elif task.done():
            status = "🔴 STOPPED"
        else:
            status = "🟢 MONITORING"
        lines.extend([
            "━━━━━━━━━━━━━━━━━━",
            f"🆔 <b>Monitor #{monitor_id}</b>",
            f"📦 <code>{monitor['collection']}</code>",
            f"🧬 <code>{monitor['model']}</code>",
            f"🎨 <code>{monitor['backdrop'] or 'ANY'}</code>",
            f"💰 <code>{_format_ton(monitor['min_ton'])} - {_format_ton(monitor['max_ton'])} TON</code>",
            f"📌 <code>{status}</code>",
            "",
        ])
    await event.eor("\n".join(lines), parse_mode="html")


@heartless_cmd(owner_only=True, pattern=r"buycancel(?:\s+(.+))?$")
async def artemis_buycancel(event):
    target = event.pattern_match.group(1)
    if not target:
        return await event.eor(
            f"Cancel one: <code>{_h('buycancel')} 1</code>\n"
            f"Cancel all: <code>{_h('buycancel')} all</code>",
            parse_mode="html",
        )
    target = target.strip().lower()
    if target == "all":
        monitor_ids = list(BUY_MONITORS.keys())
        if not monitor_ids:
            return await event.eor("📭 No active monitors.", parse_mode="html")
        for monitor_id in monitor_ids:
            await _cancel_monitor(monitor_id)
        return await event.eor(
            f"🛑 <b>All monitors cancelled.</b> ({len(monitor_ids)})",
            parse_mode="html",
        )
    try:
        monitor_id = int(target)
    except ValueError:
        return await event.eor(
            "❌ Monitor number must be an integer.", parse_mode="html",
        )
    if monitor_id not in BUY_MONITORS:
        return await event.eor(
            f"❌ Monitor <code>#{monitor_id}</code> does not exist.",
            parse_mode="html",
        )
    monitor = BUY_MONITORS.get(monitor_id)
    await _cancel_monitor(monitor_id)
    await event.eor(
        "🛑 <b>Monitor cancelled.</b>\n\n"
        f"🆔 <code>#{monitor_id}</code>\n"
        f"📦 <code>{monitor['collection']}</code>",
        parse_mode="html",
    )


@heartless_cmd(owner_only=True, pattern=r"gift(?:\s+(.+))?$")
async def artemis_gift(event):
    await _artemis_gift_handler(event)


# Inline `g` compact-floor picker sessions (answer fast; fetch on callback).
_GIFT_INLINE_TTL = 30 * 60
_GIFT_INLINE_SESSIONS: dict = {}


def _gift_inline_purge():
    now = time.monotonic()
    dead = [
        k
        for k, v in _GIFT_INLINE_SESSIONS.items()
        if now - float(v.get("at") or 0) > _GIFT_INLINE_TTL
    ]
    for k in dead:
        _GIFT_INLINE_SESSIONS.pop(k, None)


def _gift_inline_save(payload: dict) -> str:
    _gift_inline_purge()
    token = secrets.token_urlsafe(6)[:10]
    row = dict(payload)
    row["at"] = time.monotonic()
    _GIFT_INLINE_SESSIONS[token] = row
    return token


def _gift_inline_load(token: str):
    _gift_inline_purge()
    row = _GIFT_INLINE_SESSIONS.get(token)
    if not row:
        return None
    row["at"] = time.monotonic()
    return row


def _gift_inline_title(sess: dict) -> str:
    parts = [sess.get("collection") or "?"]
    if sess.get("model"):
        parts.append(sess["model"])
    if sess.get("backdrop"):
        parts.append(sess["backdrop"])
    return ", ".join(parts)


def _md_escape_inline(value) -> str:
    text = str(value or "")
    return (
        text.replace("\\", "\\\\")
        .replace("_", "\\_")
        .replace("*", "\\*")
        .replace("`", "\\`")
        .replace("[", "\\[")
    )


def _title_case_name(value: Optional[str]) -> str:
    """Display-friendly Title Case for collection / model / backdrop."""
    text = str(value or "").strip()
    if not text:
        return text
    # Keep existing capitals for multi-word canonical names; fix all-lower.
    if text != text.lower():
        return text
    return " ".join(w.capitalize() for w in text.split())


def _gift_inline_info_lines(sess: dict) -> list[str]:
    """Gift-style Collection / Model / Backdrop header lines."""
    lines = [
        f"🎁 **Collection:** `{_md_escape_inline(_title_case_name(sess.get('collection') or '?'))}`"
    ]
    model = sess.get("model")
    if model:
        lines.append(
            f"🧩 **Model:** `{_md_escape_inline(_title_case_name(model))}`"
        )
    backdrop = sess.get("backdrop")
    if backdrop:
        lines.append(
            f"🎨 **Backdrop:** `{_md_escape_inline(_title_case_name(backdrop))}`"
        )
    return lines


def _gift_inline_hub_text(sess: dict) -> str:
    return "\n".join(_gift_inline_info_lines(sess))


def _gift_inline_floor_picker_text(sess: dict) -> str:
    return "\n".join(_gift_inline_info_lines(sess))


def _gift_inline_action_row(
    raw: str,
    *,
    show_back: bool,
    owner_id: int,
    token: str,
    back_data: bytes | None = None,
):
    rows = [
        [
            Button.switch_inline("🔎 Search again", query="g ", same_peer=True),
            Button.switch_inline(
                "🔗 Share",
                query=f"g {raw}" if raw else "g ",
                same_peer=False,
            ),
        ]
    ]
    if show_back:
        data = back_data or f"gf:b:{owner_id}:{token}".encode()
        rows.append([Button.inline("⬅️ Back", data=data)])
    return rows


def _gift_inline_hub_buttons(owner_id: int, token: str, raw: str):
    rows = [
        [
            Button.inline(
                "Floor Price 📉",
                data=f"gu:s:{owner_id}:{token}:f".encode(),
            ),
            Button.inline(
                "Gift Chart 📊",
                data=f"gu:s:{owner_id}:{token}:c".encode(),
            ),
        ],
        [
            Button.inline(
                "NFT Sales 🧾",
                data=f"gu:s:{owner_id}:{token}:s".encode(),
            ),
        ],
    ]
    rows.extend(
        _gift_inline_action_row(
            raw,
            show_back=False,
            owner_id=owner_id,
            token=token,
        )
    )
    return rows


# Inline NFT Sales market keys → (history_key, display label)
_GIFT_SALES_MARKETS = (
    ("mrkt", "MRKT"),
    ("portals", "Portal"),
    ("tonnel", "Tonnel"),
    ("telegram", "Telegram"),
    ("getgems", "Getgems"),
)


def _gift_inline_sales_picker_text(sess: dict) -> str:
    lines = _gift_inline_info_lines(sess)
    lines.append("")
    lines.append("🧾 **NFT Sales** — pick a market for the 10 latest sales.")
    return "\n".join(lines)


def _gift_inline_sales_picker_buttons(sess: dict, owner_id: int, token: str):
    row1 = []
    row2 = []
    for i, (key, label) in enumerate(_GIFT_SALES_MARKETS):
        btn = Button.inline(
            label,
            data=f"gs:m:{owner_id}:{token}:{key}".encode(),
        )
        if i < 3:
            row1.append(btn)
        else:
            row2.append(btn)
    buttons = [row1]
    if row2:
        buttons.append(row2)
    buttons.extend(
        _gift_inline_action_row(
            sess.get("raw") or "",
            show_back=True,
            owner_id=owner_id,
            token=token,
            back_data=f"gu:h:{owner_id}:{token}".encode(),
        )
    )
    return buttons


def _gift_inline_sales_result_buttons(sess: dict, owner_id: int, token: str):
    return _gift_inline_action_row(
        sess.get("raw") or "",
        show_back=True,
        owner_id=owner_id,
        token=token,
        back_data=f"gs:b:{owner_id}:{token}".encode(),
    )


def _gift_inline_floor_picker_buttons(sess: dict, owner_id: int, token: str):
    depth = int(sess.get("depth") or 1)
    row = [
        Button.inline(
            "Collection Floor" if depth == 1 else "Collection",
            data=f"gf:f:{owner_id}:{token}:c".encode(),
        )
    ]
    if depth >= 2:
        row.append(
            Button.inline(
                "C+Model",
                data=f"gf:f:{owner_id}:{token}:cm".encode(),
            )
        )
    buttons = [row]
    if depth >= 3:
        buttons.append(
            [
                Button.inline(
                    "C+M+Backdrop",
                    data=f"gf:f:{owner_id}:{token}:cmb".encode(),
                )
            ]
        )
    # Stage 2+: always Back to hub.
    buttons.extend(
        _gift_inline_action_row(
            sess.get("raw") or "",
            show_back=True,
            owner_id=owner_id,
            token=token,
            back_data=f"gu:h:{owner_id}:{token}".encode(),
        )
    )
    return buttons


def _gift_inline_parse_raw(raw: str):
    """
    Fast local parse for inline picker (no network).

    Returns dict: collection, model, backdrop, nft_mode, depth, raw
    depth: 1=collection, 2=collection+model, 3=collection+model+backdrop/nft
    """
    text = (raw or "").strip()
    c_match = re.match(r"(?is)^c(?:\s+|$)(.*)$", text)
    if c_match is not None:
        text = (c_match.group(1) or "").strip()
    if not text:
        raise ValueError("empty")

    nft_mode = bool(_parse_nft_link(text))
    if nft_mode:
        parsed = _parse_nft_link(text)
        slug, short_slug, _number = parsed
        collection, _, _ = _resolve_collection_from_slug(short_slug)
        return {
            "collection": collection,
            "model": None,
            "backdrop": None,
            "nft_mode": True,
            "nft_raw": text,
            "slug": slug,
            "depth": 3,
            "raw": text,
        }

    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) == 1:
        return {
            "collection": parts[0],
            "model": None,
            "backdrop": None,
            "nft_mode": False,
            "depth": 1,
            "raw": text,
        }
    if len(parts) == 2:
        return {
            "collection": parts[0],
            "model": parts[1],
            "backdrop": None,
            "nft_mode": False,
            "depth": 2,
            "raw": text,
        }
    if len(parts) == 3:
        backdrop = parts[2]
        if backdrop.lower() in ("none", "null", "*", "-", "any"):
            backdrop = None
            depth = 2
        else:
            depth = 3
        return {
            "collection": parts[0],
            "model": parts[1],
            "backdrop": backdrop,
            "nft_mode": False,
            "depth": depth,
            "raw": text,
        }
    raise ValueError("bad_format")


async def _inline_nft_denied(event):
    article = await event.builder.article(
        title="❌ Not authorized",
        description="Ask the owner to .add your ID",
        text=(
            "❌ You are not on the NFT allow-list.\n"
            "Ask the owner to `.add <your id>`."
        ),
    )
    try:
        return await event.answer(
            [article],
            cache_time=5,
            switch_pm="Request access",
            switch_pm_param="start",
        )
    except Exception as e:
        if "query id is invalid" in str(e).lower():
            return
        raise


async def _gift_inline_answer(event, articles, **kwargs):
    try:
        return await event.answer(articles, **kwargs)
    except Exception as e:
        if "query id is invalid" in str(e).lower():
            LOGS.debug("Inline g answer skipped (expired query id)")
            return
        raise


async def _gift_inline_edit(event, text: str, buttons, *, parse_mode="md"):
    try:
        from telethon.errors import MessageNotModifiedError
        from telethon.tl.types import InputBotInlineMessageID
    except Exception:
        MessageNotModifiedError = Exception  # noqa: N806
        InputBotInlineMessageID = type(None)  # noqa: N806

    try:
        await event.edit(
            text,
            buttons=buttons,
            parse_mode=parse_mode,
            link_preview=False,
            file=None,
        )
        return
    except MessageNotModifiedError:
        with contextlib.suppress(Exception):
            await event.answer()
        return
    except Exception as exc:
        LOGS.debug("Inline g edit failed: %s", exc)
        try:
            is_inline = isinstance(
                getattr(event.query, "msg_id", None), InputBotInlineMessageID
            )
        except Exception:
            is_inline = False
        if is_inline:
            with contextlib.suppress(Exception):
                await event.answer(
                    "Couldn't update. Search again with g …", alert=True,
                )
            return
    try:
        await event.delete()
    except Exception:
        pass
    with contextlib.suppress(Exception):
        await event.respond(
            text,
            buttons=buttons,
            parse_mode=parse_mode,
            link_preview=False,
        )


@in_pattern(r"(?i)^g(?:\s+([\s\S]+))?$", owner=False)
async def artemis_gift_inline(event):
    """
    Inline `g` hub → Floor Price or Gift Chart.

    Answers immediately so Telegram does not expire the query id.
    """
    if not _nft_user_allowed(event.sender_id):
        return await _inline_nft_denied(event)

    raw = ""
    try:
        raw = (event.pattern_match.group(1) or "").strip()
    except Exception:
        raw = ""

    if not raw:
        article = await event.builder.article(
            title="🎁 Gift floors & charts",
            description="g Collection, Model, Backdrop | NFT link",
            text=(
                "**Gift floors & charts**\n\n"
                "`g Liberty Figure`\n"
                "`g Liberty Figure, Fire Opal`\n"
                "`g Liberty Figure, Fire Opal, Black`\n"
                "`g https://t.me/nft/LibertyFigure-214445`\n\n"
                "Then pick **Floor Price 📉** or **Gift Chart 📊**."
            ),
            buttons=[
                [
                    Button.switch_inline(
                        "Try Liberty Figure",
                        query="g Liberty Figure",
                        same_peer=True,
                    )
                ]
            ],
        )
        return await _gift_inline_answer(event, [article], cache_time=5)

    try:
        parsed = _gift_inline_parse_raw(raw)
    except ValueError as e:
        msg = (
            "❌ Gift filter is missing."
            if str(e) == "empty"
            else "❌ Invalid format.\n\n"
            "`g Collection`\n"
            "`g Collection, Model`\n"
            "`g Collection, Model, Backdrop`\n"
            "`g https://t.me/nft/Name-123`"
        )
        article = await event.builder.article(
            title="❌ Invalid query",
            description="g Collection, Model, Backdrop",
            text=msg,
        )
        return await _gift_inline_answer(event, [article], cache_time=5)

    owner_id = int(event.sender_id)
    # NFT links: resolve model/backdrop before answering so hub + share show them.
    if parsed.get("nft_mode"):
        try:
            coll, mod, back = await asyncio.wait_for(
                _gift_inline_resolve_nft_fast(parsed.get("nft_raw") or raw),
                timeout=4.0,
            )
            if coll:
                parsed["collection"] = coll
            if mod:
                parsed["model"] = mod
                parsed["depth"] = max(int(parsed.get("depth") or 1), 2)
            if back:
                parsed["backdrop"] = back
                parsed["depth"] = max(int(parsed.get("depth") or 1), 3)
            if mod and back:
                parsed["resolved"] = True
        except Exception as e:
            LOGS.debug("Inline g NFT pre-resolve skipped: %s", e)

    token = _gift_inline_save(
        {
            **parsed,
            "owner_id": owner_id,
            "resolved": bool(parsed.get("resolved")),
            "view": "hub",
            "last_mode": None,
        }
    )
    sess = _GIFT_INLINE_SESSIONS[token]
    title = _gift_inline_title(sess)
    desc_parts = [sess.get("collection") or "Gift"]
    if sess.get("model"):
        desc_parts.append(sess["model"])
    if sess.get("backdrop"):
        desc_parts.append(sess["backdrop"])
    article = await event.builder.article(
        title=f"🎁 {title}",
        description=" · ".join(desc_parts[:3]),
        text=_gift_inline_hub_text(sess),
        parse_mode="md",
        link_preview=False,
        buttons=_gift_inline_hub_buttons(owner_id, token, sess.get("raw") or ""),
    )
    return await _gift_inline_answer(event, [article], cache_time=0)


async def _gift_inline_resolve_nft_fast(raw: str):
    """
    Fast NFT → collection/model/backdrop for inline answer.
    Prefers GetUniqueStarGift; falls back to t.me HTML. No MRKT.
    """
    parsed = _parse_nft_link(raw)
    if not parsed:
        return None, None, None
    slug, short_slug, _number = parsed
    collection, _, _ = _resolve_collection_from_slug(short_slug)
    model = backdrop = None
    title = None
    try:
        model, backdrop, _mr, _br, title = await _fetch_unique_star_gift_attrs(
            heartless_bot, slug,
        )
    except Exception as e:
        LOGS.debug("Inline NFT MTProto resolve failed: %s", e)
    if title:
        collection = title
    if not model or not backdrop:
        try:
            hm, hb, *_rest = await _fetch_telegram_nft_attrs(slug)
            model = model or hm
            backdrop = backdrop or hb
        except Exception as e:
            LOGS.debug("Inline NFT HTML resolve failed: %s", e)
    return collection, model, backdrop


async def _gift_inline_resolve_session(sess: dict):
    """Resolve collection/model/backdrop names (and NFT attrs) via MRKT + user TG."""
    await _ensure_artemis_token()
    async with MRKTClient(token=ARTEMIS_TOKEN) as client:
        if sess.get("nft_mode"):
            coll, mod, back, _extras = await _resolve_nft_gift(
                client,
                sess.get("nft_raw") or sess.get("raw") or "",
                tg_client=heartless_bot,
            )
            coll, mod, back = await _resolve_gift_names(client, coll, mod, back)
        else:
            coll, mod, back = await _resolve_gift_names(
                client,
                sess.get("collection"),
                sess.get("model"),
                sess.get("backdrop"),
            )
    sess["collection"] = _title_case_name(coll) or coll
    sess["model"] = _title_case_name(mod) if mod else mod
    sess["backdrop"] = _title_case_name(back) if back else back
    if mod:
        sess["depth"] = max(int(sess.get("depth") or 1), 2)
    if back:
        sess["depth"] = max(int(sess.get("depth") or 1), 3)
    sess["resolved"] = True
    sess["at"] = time.monotonic()
    return sess


def _gift_inline_mode_filter(sess: dict, mode: str):
    coll = sess.get("collection")
    mod = sess.get("model")
    back = sess.get("backdrop")
    if mode == "c":
        return coll, None, None
    if mode == "cm":
        return coll, mod, None
    return coll, mod, back


@callback(re.compile(rb"^gu:s:(\d+):([A-Za-z0-9_-]{6,16}):([fcs])$"))
async def artemis_gift_inline_hub_select_cb(event):
    """Stage 1 → Floor picker / Chart picker / NFT Sales picker."""
    try:
        owner_id = int(event.data_match.group(1))
        token = event.data_match.group(2).decode()
        choice = event.data_match.group(3).decode()
    except Exception:
        return await event.answer("Invalid request.", alert=True)

    if int(event.sender_id) != owner_id:
        return await event.answer("This panel belongs to another user.", alert=True)

    sess = _gift_inline_load(token)
    if not sess:
        return await event.answer("Session expired — search again with g …", alert=True)

    # Ensure NFT attrs are populated before any stage-2 panel.
    if sess.get("nft_mode") and (
        not sess.get("resolved") or not sess.get("model") or not sess.get("backdrop")
    ):
        await event.answer("Resolving NFT…")
        try:
            sess = await _gift_inline_resolve_session(sess)
            _GIFT_INLINE_SESSIONS[token] = sess
        except Exception as e:
            LOGS.warning("g hub NFT resolve failed: %s", e)
            return await event.answer(str(e)[:180], alert=True)

    if choice == "f":
        # NFT always has collection+model+backdrop depth once resolved.
        if sess.get("nft_mode"):
            sess["depth"] = 3
        sess["view"] = "floor_pick"
        sess["at"] = time.monotonic()
        _GIFT_INLINE_SESSIONS[token] = sess
        if not sess.get("nft_mode"):
            await event.answer("Floor Price")
        return await _gift_inline_edit(
            event,
            _gift_inline_floor_picker_text(sess),
            _gift_inline_floor_picker_buttons(sess, owner_id, token),
            parse_mode="md",
        )

    if choice == "s":
        if sess.get("nft_mode"):
            sess["depth"] = 3
        if not sess.get("resolved"):
            await event.answer("Resolving…")
            try:
                sess = await _gift_inline_resolve_session(sess)
            except Exception as e:
                LOGS.warning("g sales resolve failed: %s", e)
                return await event.answer(str(e)[:180], alert=True)
        sess["view"] = "sales_pick"
        sess["at"] = time.monotonic()
        _GIFT_INLINE_SESSIONS[token] = sess
        await event.answer("NFT Sales")
        return await _gift_inline_edit(
            event,
            _gift_inline_sales_picker_text(sess),
            _gift_inline_sales_picker_buttons(sess, owner_id, token),
            parse_mode="md",
        )

    # Gift Chart path — open giftcharts stage under the same hub token.
    if not sess.get("nft_mode"):
        await event.answer("Gift Chart")

    gift_q = sess.get("collection") or ""
    model_q = sess.get("model")
    raw = sess.get("raw") or ""
    source = "nft" if sess.get("nft_mode") else "text"

    if not gift_q:
        return await event.answer("Could not resolve collection.", alert=True)

    has_model = bool(model_q)
    gc_token = gc._save_session(
        {
            "gift_q": gift_q,
            "model_q": model_q,
            "owner_id": owner_id,
            "gift": gift_q,
            "model": model_q,
            "model_id": None,
            "has_model": has_model,
            "mode": None if has_model else "collection",
            "source": source,
            "raw": raw,
            "hub_token": token,
            "hub_owner": owner_id,
            "chart_stage": "root",
        }
    )
    sess["gc_token"] = gc_token
    sess["view"] = "chart_root"
    sess["at"] = time.monotonic()
    _GIFT_INLINE_SESSIONS[token] = sess

    gc_sess = gc._SESSIONS[gc_token]
    if has_model:
        text = gc._picker_text(gc_sess)
        buttons = gc._picker_buttons(gc_token, owner_id, show_back=True)
    else:
        text = gc._intervals_text(gc_sess, "collection")
        buttons = gc._interval_buttons(
            gc_token, owner_id, "", show_back=True,
        )
    return await _gift_inline_edit(event, text, buttons, parse_mode="md")


@callback(re.compile(rb"^gu:h:(\d+):([A-Za-z0-9_-]{6,16})$"))
async def artemis_gift_inline_hub_cb(event):
    """Back to stage-1 Floor/Chart hub."""
    try:
        owner_id = int(event.data_match.group(1))
        token = event.data_match.group(2).decode()
    except Exception:
        return await event.answer("Invalid request.", alert=True)

    if int(event.sender_id) != owner_id:
        return await event.answer("This panel belongs to another user.", alert=True)

    sess = _gift_inline_load(token)
    if not sess:
        return await event.answer("Session expired — search again with g …", alert=True)

    sess["view"] = "hub"
    sess["last_mode"] = None
    sess["at"] = time.monotonic()
    _GIFT_INLINE_SESSIONS[token] = sess
    await event.answer("Back")
    return await _gift_inline_edit(
        event,
        _gift_inline_hub_text(sess),
        _gift_inline_hub_buttons(owner_id, token, sess.get("raw") or ""),
        parse_mode="md",
    )


@callback(re.compile(rb"^gf:f:(\d+):([A-Za-z0-9_-]{6,16}):(c|cm|cmb)$"))
async def artemis_gift_inline_floor_cb(event):
    try:
        owner_id = int(event.data_match.group(1))
        token = event.data_match.group(2).decode()
        mode = event.data_match.group(3).decode()
    except Exception:
        return await event.answer("Invalid request.", alert=True)

    if int(event.sender_id) != owner_id:
        return await event.answer("This panel belongs to another user.", alert=True)

    sess = _gift_inline_load(token)
    if not sess:
        return await event.answer("Session expired — search again with g …", alert=True)

    depth = int(sess.get("depth") or 1)
    if mode == "cm" and depth < 2:
        return await event.answer("Model not in this query.", alert=True)
    if mode == "cmb" and depth < 3:
        return await event.answer("Backdrop not in this query.", alert=True)

    # Answer immediately so group buttons feel snappy.
    with contextlib.suppress(Exception):
        await event.answer("Loading floors…")
    try:
        if not sess.get("resolved") or sess.get("nft_mode"):
            sess = await _gift_inline_resolve_session(sess)
            _GIFT_INLINE_SESSIONS[token] = sess
        coll, mod, back = _gift_inline_mode_filter(sess, mode)
        if mode in ("cm", "cmb") and not mod:
            return await event.answer("Could not resolve model.", alert=True)
        if mode == "cmb" and not back:
            return await event.answer("Could not resolve backdrop.", alert=True)

        # Floors are Satellite-only — no MRKT round-trip needed for floor panel.
        message = await _build_gift_floor_only(None, coll, mod, back)
    except Exception as e:
        LOGS.warning("Inline g floor failed: %s", e)
        return await event.answer(str(e)[:180], alert=True)

    sess["last_mode"] = mode
    sess["view"] = "floor_out"
    sess["at"] = time.monotonic()
    _GIFT_INLINE_SESSIONS[token] = sess
    # Always Back from floor output (stage 3) → floor picker (stage 2).
    buttons = _gift_inline_action_row(
        sess.get("raw") or "",
        show_back=True,
        owner_id=owner_id,
        token=token,
        back_data=f"gf:b:{owner_id}:{token}".encode(),
    )
    return await _gift_inline_edit(event, message, buttons, parse_mode="md")


@callback(re.compile(rb"^gf:b:(\d+):([A-Za-z0-9_-]{6,16})$"))
async def artemis_gift_inline_back_cb(event):
    """Floor output → floor picker (stage 2)."""
    try:
        owner_id = int(event.data_match.group(1))
        token = event.data_match.group(2).decode()
    except Exception:
        return await event.answer("Invalid request.", alert=True)

    if int(event.sender_id) != owner_id:
        return await event.answer("This panel belongs to another user.", alert=True)

    sess = _gift_inline_load(token)
    if not sess:
        return await event.answer("Session expired — search again with g …", alert=True)

    sess["view"] = "floor_pick"
    sess["last_mode"] = None
    sess["at"] = time.monotonic()
    _GIFT_INLINE_SESSIONS[token] = sess
    await event.answer("Back")
    return await _gift_inline_edit(
        event,
        _gift_inline_floor_picker_text(sess),
        _gift_inline_floor_picker_buttons(sess, owner_id, token),
        parse_mode="md",
    )


@callback(
    re.compile(
        rb"^gs:m:(\d+):([A-Za-z0-9_-]{6,16}):(mrkt|portals|tonnel|telegram|getgems)$"
    )
)
async def artemis_gift_inline_sales_market_cb(event):
    """NFT Sales market → 10 latest sales (Satellite miniapp)."""
    try:
        owner_id = int(event.data_match.group(1))
        token = event.data_match.group(2).decode()
        market_key = event.data_match.group(3).decode()
    except Exception:
        return await event.answer("Invalid request.", alert=True)

    if int(event.sender_id) != owner_id:
        return await event.answer("This panel belongs to another user.", alert=True)

    sess = _gift_inline_load(token)
    if not sess:
        return await event.answer("Session expired — search again with g …", alert=True)

    label = dict(_GIFT_SALES_MARKETS).get(market_key, market_key.title())
    await event.answer(f"{label} sales…")
    try:
        if not sess.get("resolved"):
            sess = await _gift_inline_resolve_session(sess)
            _GIFT_INLINE_SESSIONS[token] = sess
        coll = sess.get("collection")
        mod = sess.get("model")
        back = sess.get("backdrop")
        if not coll:
            return await event.answer("Could not resolve collection.", alert=True)

        sales = await sat._latest_sales_for_market(
            coll, market_key, mod, back, limit=10,
        )
        lines = [
            "🧾 **NFT Sales**",
            "",
            *_gift_inline_info_lines(sess),
            "",
            f"🏪 **10 Latest {label} Sales**",
            "",
        ]
        if not sales:
            lines.append("**No Sale Found -_-**")
        else:
            for i, sale in enumerate(sales, 1):
                price_txt = sale.get("price_display") or "—"
                when = sat._fmt_sold_at(sale.get("sold_at")) or "—"
                slug = sale.get("slug") or ""
                url = sale.get("nft_url") or (
                    f"https://t.me/nft/{slug}" if slug else None
                )
                title = sat._sale_number_label(sale)
                if url:
                    link = f"[{_md_escape_inline(title)}]({url})"
                else:
                    link = f"`{_md_escape_inline(title)}`"
                lines.append(
                    f"**{i}. {link} · {_md_escape_inline(price_txt)} · "
                    f"{_md_escape_inline(when)}**"
                )
        text = "\n".join(lines)
    except Exception as e:
        LOGS.warning("Inline g sales failed: %s", e)
        return await event.answer(str(e)[:180], alert=True)

    sess["view"] = "sales_out"
    sess["sales_market"] = market_key
    sess["at"] = time.monotonic()
    _GIFT_INLINE_SESSIONS[token] = sess
    return await _gift_inline_edit(
        event,
        text,
        _gift_inline_sales_result_buttons(sess, owner_id, token),
        parse_mode="md",
    )


@callback(re.compile(rb"^gs:b:(\d+):([A-Za-z0-9_-]{6,16})$"))
async def artemis_gift_inline_sales_back_cb(event):
    """Sales result → sales market picker."""
    try:
        owner_id = int(event.data_match.group(1))
        token = event.data_match.group(2).decode()
    except Exception:
        return await event.answer("Invalid request.", alert=True)

    if int(event.sender_id) != owner_id:
        return await event.answer("This panel belongs to another user.", alert=True)

    sess = _gift_inline_load(token)
    if not sess:
        return await event.answer("Session expired — search again with g …", alert=True)

    sess["view"] = "sales_pick"
    sess["at"] = time.monotonic()
    _GIFT_INLINE_SESSIONS[token] = sess
    await event.answer("Back")
    return await _gift_inline_edit(
        event,
        _gift_inline_sales_picker_text(sess),
        _gift_inline_sales_picker_buttons(sess, owner_id, token),
        parse_mode="md",
    )


async def _notify_owner_asst_cmd(event):
    """Forward verified-user assistant commands to owner bot DM."""
    try:
        owner = OWNER_ID or (owner_and_sudos() or [None])[0]
        if not owner:
            return
        # Don't echo the owner's own assistant usage back to themselves.
        if int(event.sender_id) == int(owner):
            return
        sender = await event.get_sender()
        link = _user_profile_link(sender) if sender else f"<code>{event.sender_id}</code>"
        text = html.escape(event.text or "")
        msg = (
            "📨 <b>Assistant command</b>\n\n"
            f"👤 {link} [<code>{event.sender_id}</code>]\n"
            f"💬 <code>{text}</code>"
        )
        await asst.send_message(int(owner), msg, parse_mode="html", link_preview=False)
    except Exception as e:
        LOGS.warning("Failed to notify owner of assistant cmd: %s", e)


@asst_cmd(pattern=r"gift(?:\s+(.+))?$", func=lambda e: e.is_private)
async def artemis_gift_asst(event):
    if not _asst_nft_ok(event):
        return
    await _notify_owner_asst_cmd(event)
    await _artemis_gift_handler(event)


@asst_cmd(pattern=r"p(?:\s+(.+))?$", func=lambda e: e.is_private)
async def artemis_price_asst(event):
    if not _asst_nft_ok(event):
        return
    await _artemis_price_handler(event)


@asst_cmd(pattern=r"ordertop(?:\s+(.+))?$", func=lambda e: e.is_private)
async def artemis_ordertop_asst(event):
    if not _asst_nft_ok(event):
        return
    await _notify_owner_asst_cmd(event)
    await _artemis_ordertop_handler(event)


@asst_cmd(pattern=r"order(?:\s+(.+))?$", func=lambda e: e.is_private)
async def artemis_order_asst(event):
    if not _asst_nft_ok(event):
        return
    await _notify_owner_asst_cmd(event)
    await _artemis_order_book_handler(event)


async def _artemis_gift_handler(event):
    raw = event.pattern_match.group(1)
    usage = (
        "❌ <b>Gift filter is missing.</b>\n\n"
        "Formats:\n"
        f"<code>{_h('gift')} Collection</code>\n"
        f"<code>{_h('gift')} Collection, Model</code>\n"
        f"<code>{_h('gift')} Collection, Model, Backdrop</code>\n"
        f"<code>{_h('gift')} c Collection, Model, Backdrop</code>\n"
        f"<code>{_h('gift')} c https://t.me/nft/LibertyFigure-214445</code>\n"
        f"<code>{_h('gift')} https://t.me/nft/LibertyFigure-214445</code>"
    )
    if not raw:
        return await event.eor(usage, parse_mode="html")

    raw = raw.strip()
    compact = False
    # Strip leading `c` first — NFT URLs also match `_parse_nft_link`, so
    # checking the link before `c` incorrectly forced full gift mode.
    c_match = re.match(r"(?is)^c(?:\s+|$)(.*)$", raw)
    if c_match is not None:
        compact = True
        raw = (c_match.group(1) or "").strip()
        if not raw:
            return await event.eor(
                "❌ <b>Gift filter is missing.</b>\n\n"
                f"<code>{_h('gift')} c Collection, Model, Backdrop</code>\n"
                f"<code>{_h('gift')} c https://t.me/nft/Name-123</code>",
                parse_mode="html",
            )

    seed_rarities = {}
    nft_mode = bool(_parse_nft_link(raw))
    collection = model = backdrop = None
    include_listings = False

    if nft_mode:
        # Full NFT mode lists; compact `c` still resolves model/backdrop floors.
        include_listings = not compact
    else:
        parts = [part.strip() for part in raw.split(",")]
        if len(parts) == 1:
            collection = parts[0]
            model = None
            backdrop = None
            include_listings = False
        elif len(parts) == 2:
            collection, model = parts
            backdrop = None
            include_listings = True
        elif len(parts) == 3:
            collection, model, backdrop = parts
            include_listings = True
            if backdrop.lower() in ("none", "null", "*", "-", "any"):
                backdrop = None
                include_listings = True
        else:
            return await event.eor(
                "❌ <b>Invalid format.</b>\n\n" + usage.partition("\n\n")[2],
                parse_mode="html",
            )

        if not collection:
            return await event.eor(
                "❌ Collection cannot be empty.",
                parse_mode="html",
            )
        if model is not None and not model:
            return await event.eor(
                "❌ Model cannot be empty.",
                parse_mode="html",
            )

    status = None
    try:
        status = await event.eor(
            "<b>Fetching floor...</b>" if compact else "<b>Fetching NFT Info...</b>",
            parse_mode="html",
        )

        async def work(client):
            nonlocal seed_rarities
            nft_url = None
            if nft_mode:
                (
                    coll,
                    mod,
                    back,
                    extras,
                ) = await _resolve_nft_gift(
                    client,
                    raw,
                    tg_client=event.client,
                )
                seed_rarities = {
                    "model_rarity": extras.get("model_rarity"),
                    "backdrop_rarity": extras.get("backdrop_rarity"),
                }
                nft_url = extras.get("nft_url")
                coll, mod, back = await _resolve_gift_names(
                    client, coll, mod, back,
                )
                listings = include_listings
            else:
                coll, mod, back = await _resolve_gift_names(
                    client, collection, model, backdrop,
                )
                listings = include_listings

            if compact:
                return await _build_gift_floor_only(
                    client, coll, mod, back,
                )

            sat_task = asyncio.create_task(
                _satellite_market_floors(
                    coll, model=mod, backdrop=back,
                )
            )
            tg_snap = await _changes_gift_snapshot(coll, mod)
            message, _, _ = await _build_gift_info(
                client,
                coll,
                mod,
                back,
                include_listings=listings,
                tg_snap=tg_snap,
                seed_rarities=seed_rarities,
                nft_url=nft_url,
                sat_task=sat_task,
            )
            return message

        message, status = await _with_mrkt(event, status, work)
        return await status.edit(
            message,
            parse_mode="md" if compact else "html",
            link_preview=False,
        )

    except ValueError as e:
        return await event.eor(f"❌ {e}", parse_mode="html")
    except (TradingError, RequestError, AuthError) as e:
        LOGS.warning("Artemis gift request error: %s", e)
        err = f"❌ <b>Artemis request failed.</b>\n\n<code>{e}</code>"
        if status is None:
            return await event.eor(err, parse_mode="html")
        return await status.edit(err, parse_mode="html")
    except Exception as e:
        LOGS.exception("Artemis gift failed: %s", e)
        err = (
            "❌ <b>Failed to fetch NFT information.</b>\n\n"
            f"<code>{e}</code>"
        )
        if status is None:
            return await event.eor(err, parse_mode="html")
        return await status.edit(err, parse_mode="html")


async def _artemis_price_handler(event):
    raw = (event.pattern_match.group(1) or "").strip()
    usage = (
        "❌ <b>Usage:</b>\n"
        f"<code>{_h('p')} ton</code>\n"
        f"<code>{_h('p')} stars</code>\n"
        f"<code>{_h('p')} usdt</code>\n"
        f"<code>{_h('p')} 5 ton</code>\n"
        f"<code>{_h('p')} 50 stars</code>\n"
        f"<code>{_h('p')} 5 usdt</code>\n"
        f"<code>{_h('p')} 5 usdt ton</code>\n"
        f"<code>{_h('p')} 5 usdt stars</code>\n"
        f"<code>{_h('p')} 50 ton stars</code>\n"
        f"<code>{_h('p')} 1000 stars ton</code>\n"
        f"<code>{_h('p')} 1000000 t ton</code>\n"
        f"<code>{_h('p')} 1000000 t usdt</code>\n"
        f"<code>{_h('p')} 1000000 t stars</code>"
    )
    if not raw:
        return await event.eor(usage, parse_mode="html")

    try:
        amount, src, dst = _parse_price_query(raw)
    except ValueError:
        return await event.eor(usage, parse_mode="html")

    if amount <= 0:
        return await event.eor("❌ Amount must be positive.", parse_mode="html")

    status = await event.eor("<b>Converting...</b>", parse_mode="html")
    try:
        message = await _price_convert_message(amount, src, dst)
        return await status.edit(message, parse_mode="html")
    except ValueError as e:
        return await status.edit(f"❌ {e}", parse_mode="html")
    except Exception as e:
        LOGS.exception("Artemis .p failed: %s", e)
        return await status.edit(
            f"❌ <b>Conversion failed.</b>\n\n<code>{e}</code>",
            parse_mode="html",
        )


@heartless_cmd(owner_only=True, pattern=r"p(?:\s+(.+))?$")
async def artemis_price(event):
    await _artemis_price_handler(event)


@heartless_cmd(owner_only=True, pattern=r"add(?:\s+(.+))?$")
async def artemis_add_nftid(event):
    """Append a Telegram user (id or username) to the assistant allow-list."""
    raw = (event.pattern_match.group(1) or "").strip()
    if not raw:
        return await event.eor(
            "❌ <b>Usage:</b> "
            f"<code>{_h('add')} USER_ID</code> or "
            f"<code>{_h('add')} @username</code>",
            parse_mode="html",
        )

    try:
        entity = await _resolve_tg_user(event, raw)
    except ValueError as e:
        return await event.eor(f"❌ {e}", parse_mode="html")

    _add_nftid(entity.id)
    link = _user_profile_link(entity)
    return await event.eor(
        f"<b>{link} added to database</b>",
        parse_mode="html",
    )


@heartless_cmd(owner_only=True, pattern=r"rm(?:\s+(.+))?$")
async def artemis_rm_nftid(event):
    """Remove a Telegram user (id or username) from the assistant allow-list."""
    raw = (event.pattern_match.group(1) or "").strip()
    if not raw:
        return await event.eor(
            "❌ <b>Usage:</b> "
            f"<code>{_h('rm')} USER_ID</code> or "
            f"<code>{_h('rm')} @username</code>",
            parse_mode="html",
        )

    try:
        entity = await _resolve_tg_user(event, raw)
    except ValueError as e:
        return await event.eor(f"❌ {e}", parse_mode="html")

    _, removed = _rm_nftid(entity.id)
    link = _user_profile_link(entity)
    if not removed:
        return await event.eor(
            f"<b>{link} is not in the database</b>",
            parse_mode="html",
        )
    return await event.eor(
        f"<b>{link} removed from database</b>",
        parse_mode="html",
    )


# Resume autotop after plugin load when DB flag is enabled.
_autotop_bootstrap()

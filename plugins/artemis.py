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
   Allow a user for assistant `/gift` `/p` `/order` `/ordertop`.

• `{i}rm <id|@username>`
   Remove a user from that allow-list.

• `{i}buy Collection, Model, Backdrop, MIN-MAX`
   Auto buy (owner) — without transfer lock only.

• `{i}buys` | `{i}buycancel N` | `{i}buycancel all`
   List / cancel auto-buy monitors.

• `{i}gift Collection`
   Collection floors only.

• `{i}gift Collection, Model`
   Floors + quick sells + up to 5 cheapest MRKT listings.

• `{i}gift Collection, Model, Backdrop`
   Floors + quick sells + cheapest listings + latest sales.

• `{i}gift https://t.me/nft/Name-123`
   Floors + backdrop rarity + listings + latest sales.

• `{i}p usdt` | `{i}p ton` | `{i}p stars`
   Convert 1 unit (+ Tomans & USDT).

• `{i}p 5 usdt` | `{i}p 5 ton` | `{i}p 50 stars`
   Convert an amount (+ Tomans & USDT).

• `{i}p 50 ton stars` | `{i}p 1000 stars ton`
   Explicit conversion direction.

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

• `{i}orderup N`
   Cancel + recreate order N at top+0.01.

• `{i}orderupall`
   Orderup every active order that is not already top.

• `{i}orderdel N` | `{i}orderdelall`
   Delete one / all orders.

Auto: missing/expired token regenerates from DB `SESSIONMRKT`.
"""

import io
import os
import html
import requests
import asyncio
import contextlib
import time
import re
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

from . import (
    cipherx_cmd,
    asst_cmd,
    LOGS,
    cipherx_bot,
    asst,
    udB,
    HNDLR,
    OWNER_ID,
)
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

TELEGRAM_GIFTS = TelegramGifts(
    cache_mode="http",
    asset_mode="lazy",
    ttl_seconds=600,
)

TG_ASSETS_BASE = (
    "https://raw.githubusercontent.com/"
    "ssamy2/TelegramGiftsAssests/main"
)

# Direct gift sticker assets (TGS/WebP)
TG_PHOTOS_BASE = (
    "https://cdn.jsdelivr.net/gh/"
    "ssamy2/TG_Photos@main"
)

# Gift Changes API — stickers + gift/model metadata/rarity
# thanks to @GiftChanges for this API (api.changes.tg)
CHANGES_API = "https://api.changes.tg"
GIFT_CHANGES_CREDIT = "thanks to @GiftChanges for this API"

TEHRAN_TZ = ZoneInfo("Asia/Tehran")
FRAGMENT_GIFT_TGS = "https://nft.fragment.com/gift/{slug}.tgs"

# Gift Satellite floors (Portal / Tonnel / Telegram / GetGems)
SATELLITE_API = "https://gift-satellite.dev/api"
SATELLITE_MARKETS = (
    ("portals", "Portal"),
    ("tonnel", "Tonnel"),
    ("tg", "Telegram"),
    ("getgems", "GetGems"),
)
# API hard limit: ~1 request / second. Slightly over to avoid 429s.
SATELLITE_MIN_INTERVAL = 1.05
_SATELLITE_LOCK = asyncio.Lock()
_SATELLITE_NEXT_AT = 0.0
_SATELLITE_CACHE = {}
_SATELLITE_CACHE_TTL = 45.0

# Fragment-style Stars USD reference (override with DB key STAR_USD).
DEFAULT_STAR_USD = Decimal("0.015")
_RATE_CACHE = {"at": 0.0, "ton_usd": None, "usdt_toman": None}
_RATE_CACHE_TTL = 60.0

# GiftWiki monochrome backdrops for a model
GIFTWIKI_API = "https://api.giftwiki.tg"
_MONOCHROME_CACHE = {}
_MONOCHROME_CACHE_TTL = 120.0


def _h(*parts):
    """Command usage with the active Ultroid handler."""
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
    return f"{d:.2f}"


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


def _is_valid_tgs(data):
    """Telegram .tgs files are gzip-compressed Lottie JSON."""
    return bool(data) and data[:2] == b"\x1f\x8b"


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

    # Prefer the chat client, then fall back to cipherx_bot.
    tg_clients = []
    for candidate in (tg_client, cipherx_bot):
        if candidate is not None and candidate not in tg_clients:
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
        await cipherx_bot.send_message(
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
    """True when the order should not appear in `.orders`."""
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
        if status in _FINISHED_STATUS_TOKENS:
            return True
        if any(
            token in status
            for token in (
                "finish",
                "cancel",
                "complete",
                "close",
                "expire",
                "fail",
                "reject",
            )
        ):
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

    now = time.time()
    for key in (
        "finishedAt",
        "endAt",
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
    orders = []
    cursor = ""
    while True:
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
                "count": 20,
            },
        )
        batch = (data or {}).get("orders") or []
        orders.extend(batch)
        cursor = (data or {}).get("cursor") or ""
        if not cursor or len(batch) < 20:
            break

    active = []
    for order in orders:
        if _order_finished(order):
            LOGS.info(
                "Skipping finished MRKT order id=%s finishedAt=%r endAt=%r",
                order.get("id"),
                order.get("finishedAt"),
                order.get("endAt"),
            )
            continue
        active.append(order)
    return active


def _store_artemis_token(token):
    """Persist token in memory + Ultroid DB."""
    global ARTEMIS_TOKEN
    token = str(token or "").strip()
    if not token:
        raise ValueError("Token cannot be empty.")
    ARTEMIS_TOKEN = token
    with contextlib.suppress(Exception):
        udB.set_key("ARTEMIS_TOKEN", token)
    return token


async def _generate_token_from_session(session):
    session = str(session or "").strip()
    if not session:
        raise ValueError("SESSIONMRKT is empty.")
    if not MRKT_API_ID or not MRKT_API_HASH:
        raise ValueError(
            "api_id / api_hash are missing from Ultroid DB."
        )
    async with MRKTClient() as client:
        token = await client.auth.login(
            api_id=MRKT_API_ID,
            api_hash=MRKT_API_HASH,
            session="mrkt",
            session_string=session,
            bot_username="mrkt",
            platform="android",
        )
    return _store_artemis_token(token)


def _is_token_expired_error(exc):
    if isinstance(exc, AuthError):
        return True
    status = getattr(exc, "status_code", None)
    if status == 401:
        return True
    msg = str(exc or "").lower()
    if "401" in msg or "unauthorized" in msg:
        return True
    if "expired" in msg and "token" in msg:
        return True
    if "invalid" in msg and "token" in msg:
        return True
    return False


async def _force_refresh_token(event=None, status=None):
    """Drop expired token and mint a new one from SESSIONMRKT."""
    global ARTEMIS_TOKEN
    async with TOKEN_LOCK:
        ARTEMIS_TOKEN = None
        with contextlib.suppress(Exception):
            udB.del_key("ARTEMIS_TOKEN")

        session = udB.get_key("SESSIONMRKT")
        if not session or not str(session).strip():
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
                        "<b>Token expired — regenerating...</b>",
                        parse_mode="html",
                    )
            else:
                with contextlib.suppress(Exception):
                    status = await event.eor(
                        "<b>Token expired — regenerating...</b>",
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
    global ARTEMIS_TOKEN

    async with TOKEN_LOCK:
        if ARTEMIS_TOKEN:
            return ARTEMIS_TOKEN, status

        stored = udB.get_key("ARTEMIS_TOKEN")
        if stored and str(stored).strip():
            ARTEMIS_TOKEN = str(stored).strip()
            return ARTEMIS_TOKEN, status

        session = udB.get_key("SESSIONMRKT")
        if not session or not str(session).strip():
            raise ValueError(
                "Artemis token is not configured.\n\n"
                f"Use <code>{_h('buytoken')} YOUR_TOKEN</code>\n"
                "or set DB key <code>SESSIONMRKT</code> "
                f"(and optionally run <code>{_h('gentoken')}</code>)."
            )

        if event is not None:
            if status is not None:
                status = await status.edit(
                    "<b>Generating Token...</b>",
                    parse_mode="html",
                )
            else:
                status = await event.eor(
                    "<b>Generating Token...</b>",
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
        LOGS.warning("Artemis auth failed (%s); refreshing token", e)
        _, status = await _force_refresh_token(event, status)
        return await runner(), status


async def _with_mrkt(event, status, work):
    """
    Run `await work(client)` with auto token refresh on expiry.
    Returns (result, status).
    """
    async def runner():
        async with MRKTClient(token=ARTEMIS_TOKEN) as client:
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
    Convert / price amount in ton, stars, or usdt.

    - src can be ton, stars, or usdt.
    - dst is None (`.p ton`, `.p 50 stars`, `.p 1 usdt`): IRT + USDT only
    - dst set (`.p 50 ton stars`, `.p 1000 stars usdt`, `.p 5 usdt ton`): conversion line + IRT + USDT
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

    raise ValueError("Supported: ton↔stars↔usdt only.")


def _parse_price_query(raw):
    """
    Parse:
      ton / stars / usdt
      5 ton / 50 stars / 5 usdt
      50 ton stars / 1000 stars ton / 5 usdt ton
    Returns (amount: Decimal, src, dst|None).
    """
    parts = [p for p in str(raw or "").strip().split() if p]
    if not parts:
        raise ValueError("empty")

    units = {"ton", "tons", "stars", "star", "usdt", "usdts", "tether"}

    def _unit(word):
        w = word.lower()
        if w in ("ton", "tons"):
            return "ton"
        if w in ("stars", "star"):
            return "stars"
        if w in ("usdt", "usdts", "tether"):
            return "usdt"
        return None

    # ton / stars / usdt  → amount 1
    if len(parts) == 1:
        unit = _unit(parts[0])
        if not unit:
            raise ValueError("bad")
        return Decimal("1"), unit, None

    # 5 ton / 50 stars / 5 usdt
    if len(parts) == 2:
        # either AMOUNT UNIT or UNIT UNIT (invalid) or UNIT AMOUNT
        u0, u1 = _unit(parts[0]), _unit(parts[1])
        if u0 and not u1:
            # ton 5 — unusual; treat as invalid unless amount second
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

    # 50 ton stars / 1000 stars ton / 5 usdt ton
    if len(parts) == 3:
        u1, u2 = _unit(parts[1]), _unit(parts[2])
        if not u1 or not u2 or u1 == u2:
            raise ValueError("bad")
        try:
            amount = Decimal(str(parts[0]).replace(",", ""))
        except Exception as e:
            raise ValueError("bad") from e
        return amount, u1, u2

    raise ValueError("bad")


async def _top_order(client, order_or_filter):
    return await client.request(
        "POST",
        "/orders/top",
        json={
            "collectionName": order_or_filter.get("collectionName") or None,
            "modelName": order_or_filter.get("modelName") or None,
            "backdropName": order_or_filter.get("backdropName") or None,
            "symbolName": order_or_filter.get("symbolName") or None,
        },
    )


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
        f"🔢 <b>Total offers:</b> <code>{total}</code>",
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
    if skipped_429 or skipped_other:
        LOGS.info(
            "ordertop %s: scanned %s models, skipped 429=%s other=%s",
            collection,
            len(models),
            skipped_429,
            skipped_other,
        )

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
            f"{_h('ordernew')} Collection, Model, MIN-MAX"
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
            "<b>Fetching top offers...</b>",
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
                f"❌ <b>Failed to fetch top offers.</b>\n\n<code>{e}</code>",
                parse_mode="html",
            )
        return await event.eor(
            f"❌ <b>Failed to fetch top offers.</b>\n\n<code>{e}</code>",
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


@cipherx_cmd(owner_only=True, pattern=r"ordertop(?:\s+(.+))?$")
async def artemis_ordertop(event):
    await _artemis_ordertop_handler(event)


@cipherx_cmd(owner_only=True, pattern=r"order(?:\s+(.+))?$")
async def artemis_order_book(event):
    await _artemis_order_book_handler(event)


@cipherx_cmd(owner_only=True, pattern=r"orders$")
async def artemis_orders(event):
    global ORDER_CACHE
    status = None
    try:
        status = await event.eor("<b>Processing...</b>", parse_mode="html")

        async def work(client):
            global ORDER_CACHE
            orders = await _fetch_my_orders(client)
            ORDER_CACHE = orders
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


async def _orderup_one(client, order):
    """
    Raise one order to market top + 0.01 when it is not already highest.

    Returns a result dict:
      status: "updated" | "skipped" | "error"
      plus label / price fields for reporting.
    """
    label = _order_label(order)
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

    filt = {
        "collectionName": collection,
        "modelName": model,
        "backdropName": backdrop,
        "symbolName": symbol,
    }

    try:
        top = await _top_order(client, filt)
        if top and top.get("priceMaxNanoTONs") is not None:
            top_max = nano_to_ton(top.get("priceMaxNanoTONs"))
        else:
            top_max = old_max

        if _order_is_highest(order, top):
            return {
                "status": "skipped",
                "label": label,
                "oid": oid,
                "old_min": old_min,
                "old_max": old_max,
                "top_max": top_max,
            }

        await _cancel_order(client, oid)
        top = await _top_order(client, filt)
        if top and top.get("priceMaxNanoTONs") is not None:
            top_max = nano_to_ton(top.get("priceMaxNanoTONs"))
        else:
            top_max = old_max
        new_max = Decimal(str(top_max)) + Decimal("0.01")
        if new_max < old_min:
            new_max = old_min
        await _create_order(
            client,
            collection=collection,
            model=model,
            backdrop=backdrop,
            symbol=symbol,
            price_min_ton=old_min,
            price_max_ton=new_max,
            quantity=remaining_quantity,
        )
        return {
            "status": "updated",
            "label": label,
            "oid": oid,
            "old_min": old_min,
            "old_max": old_max,
            "top_max": top_max,
            "new_max": new_max,
            "qty": remaining_quantity,
        }
    except Exception as e:
        LOGS.exception("orderup failed for %s: %s", oid, e)
        return {
            "status": "error",
            "label": label,
            "oid": oid,
            "error": str(e),
        }


@cipherx_cmd(owner_only=True, pattern=r"orderupall$")
async def artemis_orderupall(event):
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
        async with MRKTClient(token=ARTEMIS_TOKEN) as client:
            orders = await _fetch_my_orders(client)
            ORDER_CACHE = orders
            if not orders:
                return await status.edit(
                    "📭 <b>No active orders.</b>",
                    parse_mode="html",
                )

            updated = []
            skipped = 0
            errors = []
            for order in orders:
                result = await _orderup_one(client, order)
                if result["status"] == "updated":
                    updated.append(result)
                elif result["status"] == "skipped":
                    skipped += 1
                else:
                    errors.append(result)

            ORDER_CACHE = await _fetch_my_orders(client)

        lines = [
            "🚀 <b>Orderup All</b>",
            "",
            f"✅ Updated: <code>{len(updated)}</code>",
            f"⏭ Already top: <code>{skipped}</code>",
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
                    f"   📊 Prev top: {_ton2(row['top_max'])} TON\n"
                    f"   🔢 Qty: {row['qty']}\n"
                    f"   🆔 <code>{row['oid']}</code>"
                )
                lines.append("")
        elif not errors:
            lines.append("✅ <b>All active orders were already the highest.</b>")
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

        return await _edit_chunks(
            status, event, "\n".join(lines).rstrip(),
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


@cipherx_cmd(owner_only=True, pattern=r"orderup(?:\s+(.+))?$")
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
        async with MRKTClient(token=ARTEMIS_TOKEN) as client:
            result = await _orderup_one(client, order)
            ORDER_CACHE = await _fetch_my_orders(client)

        if result["status"] == "skipped":
            return await status.edit(
                "✅ <b>Your order is already the highest.</b>\n\n"
                f"📦 <b>Order:</b> {result['label']}\n"
                f"🆔 <code>{result['oid']}</code>\n"
                f"💰 <b>Yours:</b> "
                f"<code>{_ton2(result['old_min'])}-{_ton2(result['old_max'])} TON</code>\n"
                f"📊 <b>Market top:</b> "
                f"<code>{_ton2(result['top_max'])} TON</code>",
                parse_mode="html",
            )
        if result["status"] == "error":
            return await status.edit(
                f"❌ <b>Order update failed.</b>\n\n"
                f"<code>{result.get('error')}</code>",
                parse_mode="html",
            )
        return await status.edit(
            "✅ <b>Order updated successfully.</b>\n\n"
            f"📦 <b>Order:</b> {result['label']}\n"
            f"🆔 <b>Old ID:</b> <code>{result['oid']}</code>\n"
            f"💰 <b>Old:</b> "
            f"<code>{_ton2(result['old_min'])}-{_ton2(result['old_max'])} TON</code>\n"
            f"📊 <b>Previous top:</b> "
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


@cipherx_cmd(owner_only=True, pattern=r"orderdelall$")
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
        async with MRKTClient(token=ARTEMIS_TOKEN) as client:
            orders = await _fetch_my_orders(client)
            if not orders:
                ORDER_CACHE = []
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


@cipherx_cmd(owner_only=True, pattern=r"orderdel(?:\s+(.+))?$")
async def artemis_orderdel(event):
    global ORDER_CACHE
    try:
        _, status = await _ensure_artemis_token(event)
    except ValueError as e:
        return await event.eor(f"❌ {e}", parse_mode="html")
    raw_idx = event.pattern_match.group(1)
    if not raw_idx or not raw_idx.strip().isdigit():
        return await event.eor(f"Usage: <code>{_h('orderdel')} N</code>", parse_mode="html")
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
        oid = _require_order_uuid(order["id"])
        async with MRKTClient(token=ARTEMIS_TOKEN) as client:
            await _cancel_order(client, oid)
            ORDER_CACHE = await _fetch_my_orders(client)
        return await status.edit(
            "🗑 <b>Order deleted.</b>\n\n"
            f"📦 {_order_label(order)}\n"
            f"🆔 <code>{oid}</code>",
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


@cipherx_cmd(owner_only=True, pattern=r"ordernew(?:\s+(.+))?$")
async def artemis_ordernew(event):
    global ORDER_CACHE
    raw = event.pattern_match.group(1)
    if not raw:
        return await event.eor(
            "Usage:\n"
            f"<code>{_h('ordernew')} Collection, Model, Backdrop, QTY, MIN-MAX</code>\n"
            f"<code>{_h('ordernew')} Collection, Model, Backdrop, MIN-MAX</code>\n"
            f"<code>{_h('ordernew')} Collection, Model, MIN-MAX</code>",
            parse_mode="html",
        )
    try:
        collection, model, backdrop, quantity, lo, hi = _parse_ordernew(
            raw.strip()
        )
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


@cipherx_cmd(owner_only=True, pattern=r"gentoken(?:\s+(.+))?$")
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


def _satellite_token():
    token = udB.get_key("SATTELITE")
    if token is None:
        return None
    token = str(token).strip()
    return token or None


def _satellite_cache_key(market, collection, model=None, backdrop=None):
    return (
        str(market or ""),
        _loose_key(collection) if collection else "",
        _loose_key(model) if model else "",
        _loose_key(backdrop) if backdrop else "",
    )


def _satellite_cache_get(key):
    row = _SATELLITE_CACHE.get(key)
    if not row:
        return False, None
    expires, value = row
    if time.monotonic() >= expires:
        _SATELLITE_CACHE.pop(key, None)
        return False, None
    return True, value


def _satellite_cache_set(key, value):
    _SATELLITE_CACHE[key] = (
        time.monotonic() + _SATELLITE_CACHE_TTL,
        value,
    )


async def _satellite_acquire_slot():
    """Serialize satellite calls to ~1 request / second."""
    global _SATELLITE_NEXT_AT
    async with _SATELLITE_LOCK:
        now = time.monotonic()
        wait = _SATELLITE_NEXT_AT - now
        if wait > 0:
            await asyncio.sleep(wait)
        _SATELLITE_NEXT_AT = time.monotonic() + SATELLITE_MIN_INTERVAL


async def _satellite_floor_once(
    session,
    market,
    collection,
    model=None,
    backdrop=None,
):
    """
    One rate-limited satellite search. Names are expected canonical
    (post-_resolve_gift_names); no variant spam.
    """
    global _SATELLITE_NEXT_AT
    from urllib.parse import quote

    key = _satellite_cache_key(market, collection, model, backdrop)
    hit, cached = _satellite_cache_get(key)
    if hit:
        return cached

    await _satellite_acquire_slot()
    url = (
        f"{SATELLITE_API}/search/{market}/"
        f"{quote(str(collection), safe='')}"
    )
    params = {}
    if model:
        params["models"] = model
    if backdrop:
        params["backdrops"] = backdrop

    amount = None
    try:
        async with session.get(url, params=params or None) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                if isinstance(data, list) and data:
                    amount = _as_floor(data[0].get("normalizedPrice"))
            elif resp.status == 429:
                LOGS.warning("Satellite rate-limited on %s/%s", market, collection)
                # Back off one extra interval so the global queue recovers.
                async with _SATELLITE_LOCK:
                    _SATELLITE_NEXT_AT = (
                        time.monotonic() + SATELLITE_MIN_INTERVAL * 2
                    )
            else:
                LOGS.info(
                    "Satellite HTTP %s for %s/%s",
                    resp.status,
                    market,
                    collection,
                )
    except Exception as e:
        LOGS.warning(
            "Satellite floor failed (%s / %s): %s",
            market,
            collection,
            e,
        )

    _satellite_cache_set(key, amount)
    return amount


async def _satellite_market_floors(collection, model=None, backdrop=None):
    """
    Floors for Portal / Tonnel / Telegram / GetGems.
    Returns (collection_floors, model_floors|None, full_floors|None).

    Requests are queued at 1/s (API limit). Prefer starting this as a Task
    while the sticker uploads so floors finish in the background.
    """
    empty = {label: None for _, label in SATELLITE_MARKETS}
    collection_floors = dict(empty)
    model_floors = dict(empty) if model else None
    full_floors = dict(empty) if (model and backdrop) else None

    token = _satellite_token()
    if not token or not collection:
        return collection_floors, model_floors, full_floors

    jobs = []
    for market, label in SATELLITE_MARKETS:
        jobs.append(("coll", market, label, None, None))
        if model:
            jobs.append(("model", market, label, model, None))
        if model and backdrop:
            jobs.append(("full", market, label, model, backdrop))

    headers = {"Authorization": f"Token {token}"}
    timeout = aiohttp.ClientTimeout(total=20, connect=8)
    async with aiohttp.ClientSession(
        timeout=timeout, headers=headers,
    ) as session:
        for kind, market, label, mod, back in jobs:
            price = await _satellite_floor_once(
                session, market, collection, model=mod, backdrop=back,
            )
            if kind == "coll":
                collection_floors[label] = price
            elif kind == "model" and model_floors is not None:
                model_floors[label] = price
            elif kind == "full" and full_floors is not None:
                full_floors[label] = price

    return collection_floors, model_floors, full_floors


async def _mrkt_cheapest(client, collection, model=None, backdrop=None, count=1):
    """
    Cheapest MRKT listings. Tries canonical names first (fast path), then
    case/space variants only if empty.
    """
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
        kwargs = {
            "collection_names": [coll],
            "ordering": "Price",
            "low_to_high": True,
            "count": max(count, 1),
        }
        if mod:
            kwargs["model_names"] = [mod]
        if back:
            kwargs["backdrop_names"] = [back]
        try:
            page = await client.market.search(**kwargs)
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

    # Prefer the true minimum among returned listings, verifying attrs.
    best = None
    best_price = None
    matched = []
    for gift in items:
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
        if used_model and item_model and not _match_attr(item_model, used_model):
            continue
        if (
            used_backdrop
            and item_backdrop
            and not _match_attr(item_backdrop, used_backdrop)
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

    if best is None:
        price = _as_floor(getattr(items[0], "price_ton", None))
        return price, items
    return best_price, matched or items


async def _download_sticker_url(
    url,
    filename,
    mime_type="application/x-tgsticker",
    session=None,
):
    """Download a sticker URL into a BytesIO buffer. Rejects broken TGS/WebP."""
    owns_session = session is None
    try:
        if owns_session:
            timeout = aiohttp.ClientTimeout(total=20, connect=8)
            session = aiohttp.ClientSession(timeout=timeout)
        async with session.get(url) as resp:
            if resp.status != 200:
                LOGS.info("Sticker HTTP %s for %s", resp.status, url)
                return None
            data = await resp.read()
        if not data:
            return None
        # Broken/non-gzip .tgs arrives as HTML/JSON and Telegram sends it as a file.
        if mime_type == "application/x-tgsticker" and not _is_valid_tgs(data):
            LOGS.info("Invalid TGS payload for %s (%s bytes)", url, len(data))
            return None
        if mime_type == "image/webp" and not data.startswith(b"RIFF"):
            LOGS.info("Invalid WebP payload for %s (%s bytes)", url, len(data))
            return None
        buf = io.BytesIO(data)
        buf.name = filename
        buf.mime_type = mime_type
        return buf
    except Exception as e:
        LOGS.warning("Sticker download failed for %s: %s", url, e)
        return None
    finally:
        if owns_session and session is not None:
            await session.close()


async def _fetch_model_format(tg_gift, tg_model, ext, session=None):
    """Download model `.tgs` or `.webp` from TelegramGiftsAssests (legacy fallback)."""
    if not isinstance(tg_gift, dict) or not isinstance(tg_model, dict):
        return None
    short_name = tg_gift.get("short_name")
    model_name = tg_model.get("name")
    if not short_name or not model_name:
        return None

    links = tg_model.get("links") or {}
    slug = str(model_name).strip().replace(" ", "_")
    key = _name_key(model_name)
    if ext == "tgs":
        url = links.get("tgs") or (
            f"{TG_ASSETS_BASE}/models/{short_name}/{slug}.tgs"
        )
        mime = "application/x-tgsticker"
    else:
        url = links.get("webp") or (
            f"{TG_ASSETS_BASE}/models/{short_name}/{slug}.webp"
        )
        mime = "image/webp"
    if not url:
        return None
    return await _download_sticker_url(url, f"{key}.{ext}", mime, session=session)


def _changes_path_segment(value):
    """URL path segment for changes.tg (spaces → dashes is fine; API is flexible)."""
    text = str(value or "").strip()
    if not text:
        return ""
    from urllib.parse import quote
    return quote(text, safe="")


async def _fetch_changes_model(collection, model, ext="tgs", session=None):
    """
    Model sticker from api.changes.tg — replaces TelegramGiftsAssets for stickers.
    Prefer `.tgs` (animated). No WebP; PNG exists but is not used as sticker mime.
    """
    if not collection or not model or ext != "tgs":
        return None
    gift_seg = _changes_path_segment(collection)
    model_seg = _changes_path_segment(model)
    if not gift_seg or not model_seg:
        return None
    url = f"{CHANGES_API}/model/{gift_seg}/{model_seg}.tgs"
    return await _download_sticker_url(
        url,
        f"{_name_key(model)}.tgs",
        "application/x-tgsticker",
        session=session,
    )


async def _fetch_changes_original(collection, ext="tgs", session=None):
    """Collection/original sticker from api.changes.tg (un-upgraded gift)."""
    if not collection or ext != "tgs":
        return None
    gift_seg = _changes_path_segment(collection)
    if not gift_seg:
        return None
    url = f"{CHANGES_API}/original/{gift_seg}.tgs"
    return await _download_sticker_url(
        url,
        f"{_name_key(collection)}.tgs",
        "application/x-tgsticker",
        session=session,
    )


async def _fetch_fragment_format(gift_name, ext, session=None):
    """Fragment CDN `.tgs` / `.webp` for a concrete NFT slug (backdrop painted)."""
    slug = str(gift_name or "").strip()
    if not slug or "-" not in slug:
        return None
    mime = (
        "application/x-tgsticker" if ext == "tgs" else "image/webp"
    )
    return await _download_sticker_url(
        f"https://nft.fragment.com/gift/{slug}.{ext}",
        f"{_name_key(slug)}.{ext}",
        mime,
        session=session,
    )


async def _fetch_photos_format(name, ext, session=None):
    """TG_Photos collection sticker by name (legacy fallback)."""
    slug = _name_key(name)
    if not slug:
        return None
    if ext == "tgs":
        url = f"{TG_PHOTOS_BASE}/tgs/by_name/{slug}.tgs"
        mime = "application/x-tgsticker"
    else:
        url = f"{TG_PHOTOS_BASE}/webp/by_name/{slug}.webp"
        mime = "image/webp"
    return await _download_sticker_url(
        url, f"{slug}.{ext}", mime, session=session,
    )


async def _listing_nft_names(
    client,
    collection,
    model=None,
    backdrop=None,
    count=2,
):
    """NFT slugs from cheapest matching MRKT listings (small count for speed)."""
    try:
        _, items = await _mrkt_cheapest(
            client,
            collection,
            model=model,
            backdrop=backdrop,
            count=count,
        )
    except Exception as e:
        LOGS.warning("Fragment listing lookup failed: %s", e)
        return []
    names = []
    for gift in items or []:
        name = getattr(gift, "name", None) or _get_raw(gift).get("name")
        if name and name not in names:
            names.append(name)
    return names


async def _collect_gift_stickers(
    client,
    collection,
    model=None,
    backdrop=None,
    tg_snap=None,
    nft_slug=None,
):
    """
    Build sticker candidates: every healthy TGS first, then WebP fallbacks.

    Sticker sources (fast path first):
      - NFT slug / model+backdrop → Fragment (backdrop painted; changes.tg cannot)
      - Model only → api.changes.tg model TGS, then legacy assets / Fragment
      - Collection → api.changes.tg original TGS, then TG_Photos

    thanks to @GiftChanges for this API (api.changes.tg)
    """
    tg_snap = tg_snap or {}
    tgs_out = []
    webp_out = []
    seen = set()

    def _add(buf):
        if not buf:
            return
        key = (getattr(buf, "name", None), getattr(buf, "mime_type", None))
        if key in seen:
            return
        seen.add(key)
        if getattr(buf, "mime_type", "") == "application/x-tgsticker":
            tgs_out.append(buf)
        else:
            webp_out.append(buf)

    timeout = aiohttp.ClientTimeout(total=20, connect=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # 1) Concrete NFT slug (link mode) — Fragment includes that NFT's backdrop
        if nft_slug:
            tgs_task = asyncio.create_task(
                _fetch_fragment_format(nft_slug, "tgs", session=session),
            )
            webp_task = asyncio.create_task(
                _fetch_fragment_format(nft_slug, "webp", session=session),
            )
            _add(await tgs_task)
            _add(await webp_task)
            return tgs_out + webp_out

        # 2) Model + backdrop → Fragment listing (backdrop painted in WebP too)
        if model and backdrop:
            names = await _listing_nft_names(
                client, collection, model=model, backdrop=backdrop, count=2,
            )
            for name in names[:2]:
                _add(await _fetch_fragment_format(name, "tgs", session=session))
                if tgs_out:
                    break
            for name in names[:2]:
                _add(await _fetch_fragment_format(name, "webp", session=session))
                if webp_out:
                    break
            return tgs_out + webp_out

        # 3) Model only → changes.tg model TGS (no TelegramGiftsAssets / tg_snap)
        if model:
            _add(await _fetch_changes_model(
                collection, model, "tgs", session=session,
            ))
            if not tgs_out:
                gift = tg_snap.get("gift") or {}
                tg_model = tg_snap.get("model") or {}
                _add(await _fetch_model_format(
                    gift, tg_model, "tgs", session=session,
                ))
            if not tgs_out:
                names = await _listing_nft_names(
                    client, collection, model=model, backdrop=None, count=2,
                )
                for name in names[:2]:
                    _add(await _fetch_fragment_format(
                        name, "tgs", session=session,
                    ))
                    if tgs_out:
                        break
            # Static WebP fallback (changes.tg has no webp)
            gift = tg_snap.get("gift") or {}
            tg_model = tg_snap.get("model") or {}
            _add(await _fetch_model_format(
                gift, tg_model, "webp", session=session,
            ))
            if not webp_out:
                names = await _listing_nft_names(
                    client, collection, model=model, backdrop=None, count=2,
                )
                for name in names[:2]:
                    _add(await _fetch_fragment_format(
                        name, "webp", session=session,
                    ))
                    if webp_out:
                        break
            if tgs_out or webp_out:
                return tgs_out + webp_out

        # 4) Collection sticker — changes.tg original, then TG_Photos
        _add(await _fetch_changes_original(
            collection, "tgs", session=session,
        ))
        if not tgs_out:
            _add(await _fetch_photos_format(
                collection, "tgs", session=session,
            ))
        if not webp_out:
            _add(await _fetch_photos_format(
                collection, "webp", session=session,
            ))
        return tgs_out + webp_out


async def _send_gift_sticker(client, chat_id, sticker):
    """
    Send one TGS/WebP buffer as a sticker via in-memory Telethon upload
    (avoids slow temp-file round-trips).
    Returns True only when Telegram accepted it as sticker media (not a raw file).
    """
    if not sticker:
        return False
    mime_type = getattr(
        sticker,
        "mime_type",
        "application/x-tgsticker",
    )
    filename = getattr(sticker, "name", None) or (
        "gift.tgs"
        if mime_type == "application/x-tgsticker"
        else "gift.webp"
    )
    if not str(filename).lower().endswith((".tgs", ".webp")):
        filename = (
            f"{filename}.tgs"
            if mime_type == "application/x-tgsticker"
            else f"{filename}.webp"
        )
    try:
        sticker.seek(0)
        data = sticker.read()
        sticker.seek(0)
    except Exception:
        data = b""
    if mime_type == "application/x-tgsticker" and not _is_valid_tgs(data):
        LOGS.warning("Refusing to send invalid TGS sticker")
        return False
    if not data:
        return False

    msg = None
    try:
        file_obj = io.BytesIO(data)
        file_obj.name = filename

        try:
            from telethon.tl.types import DocumentAttributeFilename
            attrs = [DocumentAttributeFilename(os.path.basename(filename))]
        except Exception:
            attrs = None

        # upload_file over MTProto is the fast path vs send_file(tmp_path).
        try:
            uploaded = await client.upload_file(
                file_obj,
                file_name=filename,
                part_size_kb=512,
            )
        except TypeError:
            file_obj.seek(0)
            uploaded = await client.upload_file(file_obj, file_name=filename)

        send_kwargs = {"force_document": False, "allow_cache": True}
        if attrs is not None:
            send_kwargs["attributes"] = attrs
        if mime_type:
            send_kwargs["mime_type"] = mime_type

        try:
            msg = await client.send_file(chat_id, uploaded, **send_kwargs)
        except TypeError:
            send_kwargs.pop("mime_type", None)
            try:
                msg = await client.send_file(chat_id, uploaded, **send_kwargs)
            except TypeError:
                msg = await client.send_file(
                    chat_id, uploaded, force_document=False,
                )
    except Exception:
        LOGS.exception("Failed to send gift sticker as %s", mime_type)
        return False

    if msg is None:
        return False
    if getattr(msg, "photo", None) is not None:
        return True

    doc = getattr(msg, "document", None)
    if doc is None:
        return True

    got_mime = (getattr(doc, "mime_type", None) or "").lower()
    if mime_type == "application/x-tgsticker":
        if got_mime == "application/x-tgsticker":
            return True
        LOGS.warning(
            "Gift TGS landed as raw file (mime=%s) — removing, will try WebP",
            got_mime,
        )
        with contextlib.suppress(Exception):
            await msg.delete()
        return False

    if got_mime.startswith("image/") or "webp" in got_mime:
        return True
    if got_mime in ("application/octet-stream", "application/gzip"):
        with contextlib.suppress(Exception):
            await msg.delete()
        return False
    return True


async def _send_best_gift_sticker(
    client,
    chat_id,
    mrkt_client,
    collection,
    model=None,
    backdrop=None,
    tg_snap=None,
    nft_slug=None,
):
    """
    Try animated TGS first; if Telegram rejects it as a file, fall back to WebP
    (Fragment WebP keeps the backdrop painted as sticker background).
    """
    candidates = await _collect_gift_stickers(
        mrkt_client,
        collection,
        model=model,
        backdrop=backdrop,
        tg_snap=tg_snap,
        nft_slug=nft_slug,
    )
    for sticker in candidates:
        if getattr(sticker, "mime_type", "") != "application/x-tgsticker":
            continue
        if await _send_gift_sticker(client, chat_id, sticker):
            return True

    webp_candidates = [
        s for s in candidates
        if getattr(s, "mime_type", "") != "application/x-tgsticker"
    ]
    # Safety net: if collect somehow skipped WebP, fetch it now.
    if not webp_candidates:
        webp_candidates = await _collect_webp_fallbacks(
            mrkt_client,
            collection,
            model=model,
            backdrop=backdrop,
            tg_snap=tg_snap,
            nft_slug=nft_slug,
        )

    for sticker in webp_candidates:
        if await _send_gift_sticker(client, chat_id, sticker):
            return True
    return False


async def _collect_webp_fallbacks(
    client,
    collection,
    model=None,
    backdrop=None,
    tg_snap=None,
    nft_slug=None,
):
    """Late WebP-only fetch when TGS sent as a file and no WebP was buffered."""
    out = []
    tg_snap = tg_snap or {}
    timeout = aiohttp.ClientTimeout(total=20, connect=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        if nft_slug:
            buf = await _fetch_fragment_format(
                nft_slug, "webp", session=session,
            )
            if buf:
                out.append(buf)
            return out

        if model and backdrop:
            names = await _listing_nft_names(
                client, collection, model=model, backdrop=backdrop, count=2,
            )
            for name in names[:2]:
                buf = await _fetch_fragment_format(
                    name, "webp", session=session,
                )
                if buf:
                    out.append(buf)
                    return out
            return out

        if model:
            gift = (tg_snap or {}).get("gift") or {}
            tg_model = (tg_snap or {}).get("model") or {}
            buf = await _fetch_model_format(
                gift, tg_model, "webp", session=session,
            )
            if buf:
                out.append(buf)
                return out
            names = await _listing_nft_names(
                client, collection, model=model, backdrop=None, count=2,
            )
            for name in names[:2]:
                buf = await _fetch_fragment_format(
                    name, "webp", session=session,
                )
                if buf:
                    out.append(buf)
                    return out
            return out

        buf = await _fetch_photos_format(collection, "webp", session=session)
        if buf:
            out.append(buf)
    return out


def _format_tehran(value):
    """Format an ISO/unix timestamp as `D/M - HH:MM:SS` in Asia/Tehran."""
    ts = _parse_order_ts(value)
    if ts is None:
        return "—"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(TEHRAN_TZ)
    return f"{dt.day}/{dt.month} - {dt.strftime('%H:%M:%S')}"


async def _mrkt_latest_sales(
    client,
    collection,
    model,
    backdrop,
    limit=5,
):
    """
    Latest MRKT sales for collection+model+backdrop via POST /feed.
    Returns list of dicts: {name, price_ton, date}.
    """
    if not collection or not model or not backdrop:
        return []

    sales = []
    cursor = ""
    try:
        for _ in range(12):
            data = await client.request(
                "POST",
                "/feed",
                json={
                    "collectionNames": [collection],
                    "modelNames": [model],
                    "backdropNames": [backdrop],
                    "count": 20,
                    "cursor": cursor or "",
                },
            )
            items = (data or {}).get("items") or []
            for item in items:
                if str(item.get("type") or "").lower() != "sale":
                    continue
                gift = item.get("gift") if isinstance(item.get("gift"), dict) else {}
                name = gift.get("name")
                if not name:
                    continue
                amount = item.get("amount")
                price = nano_to_ton(amount) if amount is not None else None
                sales.append(
                    {
                        "name": name,
                        "price_ton": price,
                        "date": item.get("date"),
                    }
                )
                if len(sales) >= limit:
                    return sales
            cursor = (data or {}).get("cursor") or ""
            if not cursor or not items:
                break
    except Exception as e:
        LOGS.warning("MRKT latest sales failed: %s", e)
    return sales


def _monochrome_token():
    token = udB.get_key("MONOCHROME")
    if token is None:
        return None
    token = str(token).strip()
    return token or None


def _fetch_monochromes_sync(collection, model):
    """
    GiftWiki monochrome backdrops for a collection+model.
    Returns list of dicts: {backdrop_name, type}.
    """
    token = _monochrome_token()
    if not token or not collection or not model:
        return []

    cache_key = (_loose_key(collection), _loose_key(model))
    row = _MONOCHROME_CACHE.get(cache_key)
    if row:
        expires, value = row
        if time.monotonic() < expires:
            return list(value)

    try:
        response = requests.get(
            f"{GIFTWIKI_API}/gifts/monochromes",
            headers={"X-API-Key": token},
            params={"model_name": model},
            timeout=15,
        )
        if response.status_code != 200:
            LOGS.info(
                "GiftWiki monochrome HTTP %s for %s / %s",
                response.status_code,
                collection,
                model,
            )
            return []
        data = response.json()
        if not isinstance(data, list):
            return []

        found = []
        target = _loose_key(collection)
        for item in data:
            if not isinstance(item, dict):
                continue
            gift_name = item.get("gift_name") or item.get("collection") or ""
            if _loose_key(gift_name) != target:
                continue
            backdrop_name = (
                item.get("backdrop_name")
                or item.get("backdrop")
                or item.get("name")
            )
            if not backdrop_name:
                continue
            level = str(item.get("type") or item.get("level") or "").strip()
            found.append({
                "backdrop_name": str(backdrop_name).strip(),
                "type": level.upper() if level else "",
            })

        _MONOCHROME_CACHE[cache_key] = (
            time.monotonic() + _MONOCHROME_CACHE_TTL,
            found,
        )
        return found
    except Exception as e:
        LOGS.warning(
            "GiftWiki monochrome failed (%s / %s): %s",
            collection,
            model,
            e,
        )
        return []


async def _fetch_monochromes(collection, model):
    return await asyncio.to_thread(
        _fetch_monochromes_sync, collection, model,
    )


def _format_monochrome_block(rows, highlight_backdrop=None):
    """
    Monochrome lines under Backdrop.
    Marks the current NFT/filter backdrop with ☑ when it matches.
    """
    lines = ["🖤 <b>Monochrome:</b>", ""]
    if not rows:
        lines.append("   —")
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
    mrkt_collection = None
    mrkt_model = None
    mrkt_full = None
    listing_items = []
    model_row = {}
    back_row = {}

    # Kick off independent MRKT work in parallel with satellite.
    coll_floors_task = asyncio.create_task(client.market.collection_floors())
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
    if model and backdrop:
        model_list_task = asyncio.create_task(
            _mrkt_cheapest(client, collection, model=model, count=5),
        )
        full_list_task = asyncio.create_task(
            _mrkt_cheapest(
                client, collection, model=model, backdrop=backdrop, count=5,
            ),
        )
    elif model:
        model_list_task = asyncio.create_task(
            _mrkt_cheapest(client, collection, model=model, count=5),
        )
        full_list_task = None
    else:
        model_list_task = None
        full_list_task = None
        cheap_coll_task = asyncio.create_task(
            _mrkt_cheapest(client, collection, count=1),
        )

    try:
        coll_floors = await coll_floors_task
    except Exception as e:
        LOGS.warning("MRKT collection floors failed: %s", e)
        coll_floors = None
    mrkt_collection = _mrkt_floor_lookup(coll_floors, collection)

    if model:
        try:
            mrkt_model, listing_items = await model_list_task
        except Exception as e:
            LOGS.warning("MRKT model cheapest failed: %s", e)
            mrkt_model, listing_items = None, []
        mrkt_model = _as_floor(mrkt_model)

        try:
            models = await models_task if models_task else []
        except Exception:
            models = []
        model_row = _find_named_row(
            models, ("modelName", "name"), model,
        )
        if mrkt_model is None:
            mrkt_model = _as_floor(
                nano_to_ton(model_row.get("floorPriceNanoTons") or 0)
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

            try:
                mrkt_full, full_items = await full_list_task
            except Exception as e:
                LOGS.warning("MRKT full cheapest failed: %s", e)
                mrkt_full, full_items = None, []
            mrkt_full = _as_floor(mrkt_full)
            if full_items:
                listing_items = full_items
        elif include_listings and len(listing_items) < 5:
            try:
                _, more = await _mrkt_cheapest(
                    client, collection, model=model, count=5,
                )
                if more:
                    listing_items = more
            except Exception:
                pass

        if listing_items:
            raw = _get_raw(listing_items[0])
            if model_rarity is None:
                model_rarity = raw.get("modelRarityPerMille")
            if backdrop and backdrop_rarity is None:
                backdrop_rarity = raw.get("backdropRarityPerMille")
            if backdrop and mrkt_full is None:
                mrkt_full = _as_floor(
                    getattr(listing_items[0], "price_ton", None),
                )
    else:
        if mrkt_collection is None:
            try:
                cheapest, _ = await cheap_coll_task
                mrkt_collection = _as_floor(cheapest)
            except Exception:
                pass

    # Await satellite + quicksells together (satellite likely already done).
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
            lines.append(f"   {label}: {_floor_ton(value)}")
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

    collection_rows = [
        ("MRKT", mrkt_collection),
        ("Portal", sat_collection.get("Portal")),
        ("Tonnel", sat_collection.get("Tonnel")),
        ("Telegram", sat_collection.get("Telegram")),
        ("GetGems", sat_collection.get("GetGems")),
    ]

    lines.extend(
        floor_block(
            f"🎁 <b>Collection:</b> {collection}",
            collection_rows,
        )
    )

    if model:
        model_rows = [
            ("MRKT", mrkt_model),
            ("Portal", (sat_model or {}).get("Portal")),
            ("Tonnel", (sat_model or {}).get("Tonnel")),
            ("Telegram", (sat_model or {}).get("Telegram")),
            ("GetGems", (sat_model or {}).get("GetGems")),
        ]
        lines.extend(
            floor_block(
                f"🧩 <b>Model:</b> {model} ({_rarity_pct(model_rarity)})",
                model_rows,
            )
        )

        if backdrop:
            full_rows = [
                ("MRKT", mrkt_full),
                ("Portal", (sat_full or {}).get("Portal")),
                ("Tonnel", (sat_full or {}).get("Tonnel")),
                ("Telegram", (sat_full or {}).get("Telegram")),
                ("GetGems", (sat_full or {}).get("GetGems")),
            ]
            lines.extend(
                floor_block(
                    f"🎨 <b>Backdrop:</b> {backdrop} "
                    f"({_rarity_pct(backdrop_rarity)})",
                    full_rows,
                )
            )
        else:
            lines.extend([
                "🎨 Backdrop: ANY",
                "",
            ])

        # Monochrome backdrops for this model (GiftWiki).
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
        f"📊 Quick Sell Collection: "
        f"{_ton2(quick_collection) if quick_collection is not None else '—'} TON"
    )
    if model:
        lines.append(
            f"📊 Quick Sell Collection + Model: "
            f"{_ton2(quick_coll_model) if quick_coll_model is not None else '—'} TON"
        )
        if backdrop:
            lines.append(
                f"📊 Quick Sell Collection + Model + Backdrop: "
                f"{_ton2(quick_full) if quick_full is not None else '—'} TON"
            )
    lines.append("")

    sales_task = None
    if model and backdrop:
        sales_task = asyncio.create_task(
            _mrkt_latest_sales(
                client, collection, model, backdrop, limit=5,
            )
        )

    if model and include_listings:
        if not listing_items:
            _, listing_items = await _mrkt_cheapest(
                client, collection, model=model, backdrop=backdrop, count=5,
            )
        lines.append("🎁 <b>MRKT Cheapest Listings</b>")
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

    if model and backdrop:
        try:
            sales = await sales_task if sales_task else []
        except Exception as e:
            LOGS.warning("MRKT latest sales failed: %s", e)
            sales = []
        lines.append("🏪 <b>MRKT Latest Sales</b>")
        lines.append("")
        if not sales:
            lines.append("   —")
            lines.append("")
        else:
            for i, sale in enumerate(sales, 1):
                nft_name = sale.get("name") or ""
                lines.append(
                    f'    {i}. <a href="{_nft_link(nft_name)}">NFT</a> - '
                    f'🪙 {_ton2(sale.get("price_ton"))} TON'
                )
                lines.append(
                    f'        🕒 {_format_tehran(sale.get("date"))}'
                )
                lines.append("")

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


@cipherx_cmd(owner_only=True, pattern=r"buytoken(?:\s+(.+))?$")
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


@cipherx_cmd(owner_only=True, pattern=r"b$")
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
    except (TradingError, RequestError) as e:
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


@cipherx_cmd(owner_only=True, pattern=r"nfts$")
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


@cipherx_cmd(owner_only=True, pattern=r"buy(?:\s+(.+))?$")
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


@cipherx_cmd(owner_only=True, pattern=r"buys$")
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


@cipherx_cmd(owner_only=True, pattern=r"buycancel(?:\s+(.+))?$")
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


@cipherx_cmd(owner_only=True, pattern=r"gift(?:\s+(.+))?$")
async def artemis_gift(event):
    await _artemis_gift_handler(event)


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
    if not raw:
        return await event.eor(
            "❌ <b>Gift filter is missing.</b>\n\n"
            "Formats:\n"
            f"<code>{_h('gift')} Collection</code>\n"
            f"<code>{_h('gift')} Collection, Model</code>\n"
            f"<code>{_h('gift')} Collection, Model, Backdrop</code>\n"
            f"<code>{_h('gift')} https://t.me/nft/LibertyFigure-214445</code>",
            parse_mode="html",
        )

    raw = raw.strip()
    seed_rarities = {}
    nft_mode = bool(_parse_nft_link(raw))
    collection = model = backdrop = None
    include_listings = False

    if nft_mode:
        include_listings = True
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
                "❌ <b>Invalid format.</b>\n\n"
                "Use:\n"
                f"<code>{_h('gift')} Collection</code>\n"
                f"<code>{_h('gift')} Collection, Model</code>\n"
                f"<code>{_h('gift')} Collection, Model, Backdrop</code>\n"
                f"<code>{_h('gift')} https://t.me/nft/LibertyFigure-214445</code>",
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
    status_deleted = False
    try:
        status = await event.eor(
            "<b>Fetching NFT Info...</b>",
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
                nft_slug = extras.get("slug")
                coll, mod, back = await _resolve_gift_names(
                    client, coll, mod, back,
                )
                listings = True
            else:
                coll, mod, back = await _resolve_gift_names(
                    client, collection, model, backdrop,
                )
                nft_slug = None
                listings = include_listings

            sat_task = asyncio.create_task(
                _satellite_market_floors(
                    coll, model=mod, backdrop=back,
                )
            )
            tg_snap = await _changes_gift_snapshot(coll, mod)
            sticker_task = asyncio.create_task(
                _send_best_gift_sticker(
                    event.client,
                    event.chat_id,
                    client,
                    coll,
                    model=mod,
                    backdrop=back,
                    tg_snap=tg_snap,
                    nft_slug=nft_slug,
                )
            )
            info_task = asyncio.create_task(
                _build_gift_info(
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
            )
            await sticker_task
            message, _, _ = await info_task
            return message

        message, status = await _with_mrkt(event, status, work)

        with contextlib.suppress(Exception):
            await status.delete()
            status_deleted = True

        return await event.respond(
            message,
            parse_mode="html",
            link_preview=False,
        )

    except ValueError as e:
        return await event.eor(f"❌ {e}", parse_mode="html")
    except (TradingError, RequestError, AuthError) as e:
        LOGS.warning("Artemis gift request error: %s", e)
        err = f"❌ <b>Artemis request failed.</b>\n\n<code>{e}</code>"
        if status_deleted or status is None:
            return await event.respond(err, parse_mode="html")
        return await status.edit(err, parse_mode="html")
    except Exception as e:
        LOGS.exception("Artemis gift failed: %s", e)
        err = (
            "❌ <b>Failed to fetch NFT information.</b>\n\n"
            f"<code>{e}</code>"
        )
        if status_deleted or status is None:
            return await event.respond(err, parse_mode="html")
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
        f"<code>{_h('p')} 1000 stars ton</code>"
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


@cipherx_cmd(owner_only=True, pattern=r"p(?:\s+(.+))?$")
async def artemis_price(event):
    await _artemis_price_handler(event)


@cipherx_cmd(owner_only=True, pattern=r"add(?:\s+(.+))?$")
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


@cipherx_cmd(owner_only=True, pattern=r"rm(?:\s+(.+))?$")
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

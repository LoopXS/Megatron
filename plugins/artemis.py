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

• `{i}add <id|@username> [days]`
   Allow a user for assistant NFT cmds / inline `g` `a` `ch`.
   Optional days (e.g. 24 / 30) sets timed access; omit for permanent.

• `{i}rm <id|@username>`
   Remove a user from that allow-list.

• Assistant `/pay` | `t.me/AssisXBot?start=pay`
   Subscribe: **250 Stars** or **2.79 TON** (+ unique cents).
   Success → NFTIDS for **30 days** (udB: `TON_WALLET`, `TONAPI_KEY`).

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
   Hub: Floor Price 📉 / Gift Chart 📊 / NFT Sales 🧾 / Listings 🏷️.
   NFT links also show (Link) + SeeTG Owner History (Gift Sent).

• Inline: `@AssisXBot a`
   NFT Heatmap — choose timeline (24H…All), then Search again / Share.

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

• `{i}s 9200`
   NFT Stars listing → net after 20% fee; Fragment keeps 0.013/0.015 Stars then → TON.

• `{i}ds 67`
   Desired TON after Fragment → restore Stars (0.013→0.015) then +20% listing.

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

• `{i}autotop on` | `{i}autotop on 20s` | `{i}autotop 1m` | `{i}autotop off`
   Auto orderupall every N seconds/minutes (default 30s).
   Active orders are stored in DB and recreated if missing.
   Turns itself off when no active orders remain.

• `{i}orderdel N` | `{i}orderdel 1, 2, 3`
   Delete one or multiple orders by `.orders` index.

• `{i}orderdelall`
   Delete all orders.

Auto: missing/expired token regenerates from DB `SESSIONMRKT`.
"""

import os
import io
import html
import random
import requests
import asyncio
import contextlib
import secrets
import base64
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

from telethon import Button, events, functions, types as tl_types
from telethon.tl.custom.message import CustomMarkdown
from telethon.tl.types import (
    DataJSON,
    InputMediaInvoice,
    InputWebDocument,
    Invoice,
    KeyboardButtonStyle,
    LabeledPrice,
    MessageActionPaymentSentMe,
    UpdateBotPrecheckoutQuery,
)
from urllib.parse import quote as _url_quote

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
from . import _seetg_tma as seetg
from CythonX._misc import owner_and_sudos
from CythonX.fns.helper import cusmo

# ToxygenX Telethon: enable CustomMarkdown on assistant (tg-emoji / emoji/ links).
try:
    if asst is not None:
        asst.parse_mode = CustomMarkdown()
except Exception:
    pass


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
CHANGES_CDN = "https://cdn.changes.tg"
GIFT_CHANGES_CREDIT = "thanks to @GiftChanges for this API"

# Custom-emoji pack cache: collection → {collection, models{}, backdrops{}, models_list[]}
# Memory-only (Changes customEmojiId); no udB persistence.
_EMOJI_PACK_CACHE: dict = {}
_EMOJI_PACK_TTL = 45 * 60
_MODELS_PAGE_SIZE = 10  # 5 rows × 2 cols

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

# Gift Satellite miniapp markets (display labels; floors+sales via sat TMA)
SATELLITE_MARKETS = tuple(
    (search, label) for search, label, _hist in sat.SAT_MARKETS
)

# Fragment-style Stars USD reference (override with DB key STAR_USD).
DEFAULT_STAR_USD = Decimal("0.015")
# Fragment Stars→TON: of every 0.015 Stars, Fragment keeps 0.013 (drops 0.002),
# then that reduced Stars sum is converted to TON at the normal STAR_USD rate.
FRAGMENT_STARS_BASE = Decimal("0.015")
FRAGMENT_STARS_KEEP = Decimal("0.013")
# Telegram NFT Stars sale commission.
NFT_STARS_FEE_RATE = Decimal("0.20")
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


def _get_nft_subs() -> dict:
    """user_id(str) → expiry unix. Missing / 0 = permanent (list-only)."""
    raw = udB.get_key("NFTSUBS")
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        try:
            out[str(int(k))] = int(v)
        except Exception:
            continue
    return out


def _set_nft_subs(mapping: dict):
    clean = {}
    for k, v in (mapping or {}).items():
        try:
            clean[str(int(k))] = int(v)
        except Exception:
            continue
    udB.set_key("NFTSUBS", clean)
    return clean


def _purge_expired_nft_subs() -> list[int]:
    """Drop timed subscribers whose expiry has passed. Returns removed ids."""
    now = int(time.time())
    subs = _get_nft_subs()
    removed = []
    keep = {}
    for k, exp in subs.items():
        try:
            uid = int(k)
            exp_i = int(exp)
        except Exception:
            continue
        if exp_i > 0 and exp_i <= now:
            removed.append(uid)
            continue
        keep[str(uid)] = exp_i
    if removed:
        _set_nft_subs(keep)
        ids = _get_nftids()
        _set_nftids([x for x in ids if x not in set(removed)])
        LOGS.info("NFTIDS expired removed: %s", removed)
    return removed


def _add_nftid(user_id, *, days: int | None = None):
    """
    Add to NFTIDS. ``days``:
      None → permanent (clear any timed expiry)
      int  → access until now + days
    """
    uid = int(user_id)
    ids = _get_nftids()
    if uid not in ids:
        ids.append(uid)
        _set_nftids(ids)
    subs = _get_nft_subs()
    key = str(uid)
    if days is None:
        subs.pop(key, None)
    else:
        d = max(1, int(days))
        subs[key] = int(time.time()) + d * 86400
    _set_nft_subs(subs)
    return ids


def _rm_nftid(user_id):
    uid = int(user_id)
    ids = _get_nftids()
    removed = False
    if uid in ids:
        ids = [x for x in ids if x != uid]
        _set_nftids(ids)
        removed = True
    subs = _get_nft_subs()
    if str(uid) in subs:
        subs.pop(str(uid), None)
        _set_nft_subs(subs)
        removed = True
    return ids, removed


def _nft_user_allowed(user_id):
    try:
        uid = int(user_id)
    except Exception:
        return False
    if uid in set(owner_and_sudos() or []):
        return True
    if OWNER_ID and uid == int(OWNER_ID):
        return True
    _purge_expired_nft_subs()
    return uid in _get_nftids()


def _nft_sub_expiry(user_id) -> int | None:
    """Return expiry unix for timed sub, 0 for permanent, None if not listed."""
    _purge_expired_nft_subs()
    uid = int(user_id)
    if uid not in _get_nftids():
        return None
    return int(_get_nft_subs().get(str(uid)) or 0)


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


def _gram_ce_md(fallback: str = "TON") -> str:
    """``addemoji gram`` — replaces the TON unit label on floor/quick-sell lines."""
    return _emp_ce_md("gram", fallback)


def _gram_ce_html(fallback: str = "TON") -> str:
    return _emp_ce_html("gram", fallback)


def _price_txt_with_gram_md(price_txt: str) -> str:
    """``1.23 TON`` → ``1.23 {gram CE}``; ``9200 Stars`` → ``9200 {stars CE}``."""
    txt = str(price_txt or "—").strip()
    if re.search(r"(?i)\bTON\s*$", txt):
        amount = re.sub(r"(?i)\s*TON\s*$", "", txt).strip() or "—"
        return f"{_md_escape_inline(amount)} {_gram_ce_md('TON')}"
    if re.search(r"(?i)\bStars?\s*$", txt):
        amount = re.sub(r"(?i)\s*Stars?\s*$", "", txt).strip() or "—"
        return f"{_md_escape_inline(amount)} {_emp_ce_md('stars', '⭐')}"
    return _md_escape_inline(txt)


def _floor_ton(value):
    """Price + gram/TON unit with a single space (no double-spacing)."""
    amount = _as_floor(value)
    unit = _gram_ce_html("TON")
    if amount is None:
        return f"— {unit}"
    return f"{_ton2(amount)} {unit}"


def _floor_price_code(value):
    """Markdown code-span price only (TON label stays outside)."""
    amount = _as_floor(value)
    if amount is None:
        return "—"
    return _ton2(amount)


def _model_rarity_from_changes(tg_snap) -> Optional[int]:
    """Model rarity per-mille from api.changes.tg snapshot (preferred source)."""
    tg_model = (tg_snap or {}).get("model") or {}
    for key in ("rarityPermille", "rarityPerMille", "rarity_permille"):
        val = tg_model.get(key)
        if val is None or val == "":
            continue
        try:
            return int(val)
        except Exception:
            pm = _pct_to_permille(val)
            if pm is not None:
                return pm
    return None


def _model_rarity_tier(tg_snap) -> Optional[str]:
    """Crafted tier phrase from Changes (rare / legendary / …)."""
    tg_model = (tg_snap or {}).get("model") or {}
    tier = tg_model.get("rarityTier") or tg_model.get("rarity_tier")
    if tier is None or tier == "":
        return None
    text = str(tier).strip()
    return text or None


def _model_rarity_display(tg_snap, fallback_permille=None) -> str:
    """
    Display rarity for Model lines.

    Numeric % when per-mille > 0; otherwise exact Changes ``rarityTier``
    (crafted models like Guard Dog → legendary) instead of ``0%``.
    """
    pm = _model_rarity_from_changes(tg_snap)
    if pm is None and fallback_permille is not None and fallback_permille != "":
        try:
            pm = int(fallback_permille)
        except Exception:
            pm = _pct_to_permille(fallback_permille)
    tier = _model_rarity_tier(tg_snap)
    if pm is not None and pm != 0:
        return _rarity_pct(pm)
    if tier:
        return tier
    if pm is None:
        return "?"
    return "?"


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


def _star_gift_unique_attrs(gift):
    """Extract model/backdrop/title from a StarGiftUnique (or similar)."""
    try:
        from telethon.tl.types import (
            StarGiftAttributeBackdrop,
            StarGiftAttributeModel,
            StarGiftUnique,
        )
    except Exception:
        return None, None, None, None, None

    if gift is None:
        return None, None, None, None, None
    # payments.UniqueStarGift wraps .gift; webpage attr may pass StarGiftUnique
    inner = getattr(gift, "gift", None)
    if inner is not None and not isinstance(gift, StarGiftUnique):
        gift = inner
    if not isinstance(gift, StarGiftUnique):
        # Duck-type: some layers still expose attributes/title
        if not getattr(gift, "attributes", None):
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


async def _fetch_unique_star_gift_attrs(tg_client, slug):
    """
    Resolve NFT attributes via MTProto payments.getUniqueStarGift.
    This works even when t.me HTML scraping is blocked.
    Burned gifts raise STARGIFT_ALREADY_BURNED — callers should fall back.
    """
    if tg_client is None:
        return None, None, None, None, None

    try:
        from telethon.tl.functions.payments import (
            GetUniqueStarGiftRequest,
        )
    except Exception as e:
        LOGS.warning("Telethon gift imports failed: %s", e)
        return None, None, None, None, None

    try:
        result = await tg_client(
            GetUniqueStarGiftRequest(slug=slug)
        )
    except Exception as e:
        err = str(e).upper()
        level = LOGS.debug if "STARGIFT_ALREADY_BURNED" in err or "BURNED" in err else LOGS.warning
        level(
            "GetUniqueStarGift failed for %s: %s: %r",
            slug,
            type(e).__name__,
            e,
        )
        return None, None, None, None, None

    gift = getattr(result, "gift", None)
    model, backdrop, mr, br, title = _star_gift_unique_attrs(gift)
    if not model and not backdrop and not title:
        LOGS.warning(
            "Unexpected unique gift type for %s: %r",
            slug,
            type(gift),
        )
    return model, backdrop, mr, br, title


async def _fetch_nft_attrs_via_webpage(tg_client, slug):
    """
    Fallback for burned / unavailable unique gifts: messages.getWebPage on
    https://t.me/nft/<slug> often still embeds WebPageAttributeUniqueStarGift.
    """
    if tg_client is None or not slug:
        return None, None, None, None, None
    try:
        from telethon.tl.functions.messages import GetWebPageRequest
        from telethon.tl.types import WebPageAttributeUniqueStarGift
    except Exception as e:
        LOGS.debug("GetWebPage import failed: %s", e)
        return None, None, None, None, None

    url = f"https://t.me/nft/{slug}"
    try:
        result = await tg_client(GetWebPageRequest(url=url, hash=0))
    except Exception as e:
        LOGS.debug("GetWebPage NFT failed for %s: %s", slug, e)
        return None, None, None, None, None

    webpage = getattr(result, "webpage", None) or result
    attrs = getattr(webpage, "attributes", None) or []
    for attr in attrs:
        if isinstance(attr, WebPageAttributeUniqueStarGift):
            return _star_gift_unique_attrs(getattr(attr, "gift", None))
        # Duck-type older/newer constructors
        gift = getattr(attr, "gift", None)
        if gift is not None and getattr(gift, "attributes", None):
            parsed = _star_gift_unique_attrs(gift)
            if parsed[0] or parsed[1] or parsed[4]:
                return parsed
    return None, None, None, None, None


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

    # 1b) WebPage embed — works for many burned gifts
    if not model or not backdrop:
        for tg in tg_clients:
            (
                wm,
                wb,
                wmr,
                wbr,
                wtitle,
            ) = await _fetch_nft_attrs_via_webpage(tg, slug)
            model = model or wm
            backdrop = backdrop or wb
            if model_rarity is None:
                model_rarity = wmr
            if backdrop_rarity is None:
                backdrop_rarity = wbr
            if wtitle:
                collection = wtitle
            if model and backdrop:
                break

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


async def _fetch_ton_usd(session: aiohttp.ClientSession) -> Optional[Decimal]:
    try:
        async with session.get(
            "https://tonapi.io/v2/rates",
            params={"tokens": "ton", "currencies": "usd"},
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json(content_type=None)
            return Decimal(str(data["rates"]["TON"]["prices"]["USD"]))
    except Exception as e:
        LOGS.warning("TON/USD rate fetch failed: %s", e)
        return None


async def _fetch_usdt_toman(session: aiohttp.ClientSession) -> Optional[Decimal]:
    """USDT→Toman — tetherland first, then Bitpin / iran-market fallbacks."""
    # 1) tetherland (primary)
    try:
        async with session.get("https://api.tetherland.com/currencies") as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                return Decimal(
                    str(data["data"]["currencies"]["USDT"]["price"])
                )
    except Exception as e:
        LOGS.warning("USDT/Toman tetherland failed: %s", e)

    # 2) Bitpin USDT_IRT
    try:
        async with session.get("https://api.bitpin.ir/v1/mkt/markets/") as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                for row in data.get("results") or []:
                    c1 = ((row.get("currency1") or {}).get("code") or "").upper()
                    c2 = ((row.get("currency2") or {}).get("code") or "").upper()
                    if c1 == "USDT" and c2 in ("IRT", "TMN", "IRR"):
                        price = row.get("price")
                        if price is None:
                            info = row.get("price_info") or {}
                            price = info.get("price")
                        if price is not None:
                            return Decimal(str(price))
    except Exception as e:
        LOGS.warning("USDT/Toman bitpin failed: %s", e)

    # 3) iran-market popular.json (USDT_IRR ≈ toman)
    try:
        async with session.get(
            "https://raw.githubusercontent.com/iran-market/"
            "iran-market.github.io/main/data/popular.json"
        ) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                for item in data.get("data") or []:
                    if str(item.get("symbol") or "").upper() == "USDT_IRR":
                        return Decimal(str(item["price"]))
    except Exception as e:
        LOGS.warning("USDT/Toman iran-market failed: %s", e)
    return None


async def _live_ton_usd() -> Decimal:
    """TON/USD only (for ``.s`` / ``.ds`` — no Toman dependency)."""
    now = time.monotonic()
    cached = _RATE_CACHE.get("ton_usd")
    if cached is not None and now - _RATE_CACHE["at"] < _RATE_CACHE_TTL:
        return cached

    timeout = aiohttp.ClientTimeout(total=12, connect=6)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        ton_usd = await _fetch_ton_usd(session)

    if ton_usd is None and cached is not None:
        LOGS.warning("TON/USD live failed — using stale cache")
        return cached
    if ton_usd is None:
        raise ValueError("Could not fetch live TON/USD rate.")

    _RATE_CACHE["at"] = now
    _RATE_CACHE["ton_usd"] = ton_usd
    return ton_usd


async def _live_ton_usdt_toman():
    """
    Live TON/USD (tonapi) + USDT/Toman (tetherland → Bitpin → iran-market).
    Cached briefly to keep `{i}p` snappy. Falls back to stale cache on failure.
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
    timeout = aiohttp.ClientTimeout(total=12, connect=6)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        ton_usd = await _fetch_ton_usd(session)
        usdt_toman = await _fetch_usdt_toman(session)

    if ton_usd is None:
        ton_usd = _RATE_CACHE.get("ton_usd")
    if usdt_toman is None:
        usdt_toman = _RATE_CACHE.get("usdt_toman")

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


def _fragment_stars_keep_ratio() -> Decimal:
    """Fragment keeps 0.013 of every 0.015 Stars (drops 0.002 per 0.015)."""
    return FRAGMENT_STARS_KEEP / FRAGMENT_STARS_BASE


def _fragment_reduce_stars(stars) -> Decimal:
    """Apply Fragment Stars haircut: amount * (0.013 / 0.015)."""
    return Decimal(str(stars)) * _fragment_stars_keep_ratio()


def _fragment_restore_stars(reduced_stars) -> Decimal:
    """Undo Fragment haircut: reduced * (0.015 / 0.013)."""
    return Decimal(str(reduced_stars)) / _fragment_stars_keep_ratio()


def _stars_to_ton(stars, star_usd: Decimal, ton_usd: Decimal) -> Decimal:
    """Convert a Stars sum to TON at the given USD/star rate."""
    return (Decimal(str(stars)) * star_usd) / ton_usd


def _ton_to_stars(tons, star_usd: Decimal, ton_usd: Decimal) -> Decimal:
    """Convert TON to a Stars sum at the given USD/star rate."""
    return (Decimal(str(tons)) * ton_usd) / star_usd


async def _stars_listing_fee_message(listing_stars, *, fmt: str = "html") -> str:
    """
    ``.s 9200`` — listing Stars → net after 20% fee + Fragment TON.

    1. Pure Stars = listing × 0.8
    2. Fee line TON = pure Stars → TON at normal STAR_USD (0.015)
    3. Fragment: reduce Stars by 0.013/0.015, then convert that sum → TON

    ``fmt="md"`` — CustomMarkdown CE (inline ``s``, same as g sales output).
    """
    listing = Decimal(
        Decimal(str(listing_stars)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    if listing <= 0:
        raise ValueError("Stars must be positive.")
    ton_usd = await _live_ton_usd()
    star_usd = _star_usd_rate()
    pure = (listing * (Decimal("1") - NFT_STARS_FEE_RATE)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    ton_after_fee = _stars_to_ton(pure, star_usd, ton_usd)
    # Fragment reduces the Stars amount first, then convert the sum to TON.
    reduced = _fragment_reduce_stars(pure)
    ton_fragment = _stars_to_ton(reduced, star_usd, ton_usd)
    if fmt == "md":
        star_e = _emp_ce_md("stars", "⭐")
        gram = _gram_ce_md("TON")
        return (
            f"**Listing Price :** `{_fmt_stars(listing)}` {star_e}\n"
            f"**- 20% Fee :** `{_fmt_stars(pure)}` {star_e}/"
            f"`{_fmt_amount(ton_after_fee)}` {gram}\n"
            f"**Fragment Convert :** `{_fmt_amount(ton_fragment)}` {gram}"
        )
    star_e = _emp_ce_html("stars", "⭐")
    gram = _gram_ce_html("TON")
    return (
        f"<b>Listing Price :</b> <code>{_fmt_stars(listing)}</code> {star_e}\n"
        f"<b>- 20% Fee :</b> <code>{_fmt_stars(pure)}</code> {star_e}/"
        f"<code>{_fmt_amount(ton_after_fee)}</code> {gram}\n"
        f"<b>Fragment Convert :</b> <code>{_fmt_amount(ton_fragment)}</code> {gram}"
    )


async def _desired_ton_listing_message(desired_ton, *, fmt: str = "html") -> str:
    """
    ``.ds 67`` — desired pure TON (after Fragment) → fair Stars listing.

    1. Entry TON → Stars sum at normal rate (= Fragment-reduced Stars)
    2. Restore 0.013→0.015 to get pure Stars; show pure Stars / TON@0.015
    3. Gross up +20% fee for listing Stars

    ``fmt="md"`` — CustomMarkdown CE (inline ``ds``, same as g sales output).
    """
    tons = Decimal(str(desired_ton))
    if tons <= 0:
        raise ValueError("TON must be positive.")
    ton_usd = await _live_ton_usd()
    star_usd = _star_usd_rate()
    # TON is what remains after Fragment — invert: TON→reduced Stars→pure Stars.
    reduced = _ton_to_stars(tons, star_usd, ton_usd)
    pure_stars = _fragment_restore_stars(reduced).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    ton_at_full = _stars_to_ton(pure_stars, star_usd, ton_usd)
    listing = (pure_stars / (Decimal("1") - NFT_STARS_FEE_RATE)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    if fmt == "md":
        star_e = _emp_ce_md("stars", "⭐")
        gram = _gram_ce_md("TON")
        return (
            f"**Entry Price :** `{_fmt_amount(tons)}` {gram}\n"
            f"**Fragment Convert :** `{_fmt_stars(pure_stars)}` {star_e}/"
            f"`{_fmt_amount(ton_at_full)}` {gram}\n"
            f"**+ 20% Fee :** `{_fmt_stars(listing)}` {star_e}"
        )
    star_e = _emp_ce_html("stars", "⭐")
    gram = _gram_ce_html("TON")
    return (
        f"<b>Entry Price :</b> <code>{_fmt_amount(tons)}</code> {gram}\n"
        f"<b>Fragment Convert :</b> <code>{_fmt_stars(pure_stars)}</code> {star_e}/"
        f"<code>{_fmt_amount(ton_at_full)}</code> {gram}\n"
        f"<b>+ 20% Fee :</b> <code>{_fmt_stars(listing)}</code> {star_e}"
    )


async def _price_convert_message(amount, src, dst=None, *, fmt: str = "html"):
    """
    Convert / price amount in ton, stars, usdt, or tomans (`t`).

    - src can be ton, stars, usdt, or toman.
    - dst is None (`.p ton`, `.p 50 stars`, `.p 1 usdt`): IRT + USDT only
    - dst set (`.p 50 ton stars`, `.p 1000 stars usdt`, `.p 5 usdt ton`):
      conversion line + IRT + USDT
    - toman source (`.p 1000000 t ton|usdt|stars`): conversion only —
      no Tomans equivalent line in the output.
    Stars are rounded to whole numbers when shown as converted output.
    ``fmt="md"`` — CustomMarkdown CE (inline ``p``, same as g sales output).
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
    md = fmt == "md"
    # TON unit uses addemoji ``gram`` (same as floors / .s / .ds) — not ``ton``.
    if md:
        price_e = _emp_ce_md("ex", "💱")
        star_e = _emp_ce_md("stars", "⭐")
        ton_e = _gram_ce_md("TON")
        irt_e = _emp_ce_md("irt", "🇮🇷")
        usdt_e = _emp_ce_md("usdt", "💲")
        title = f"{price_e} **Price Convert**"
    else:
        price_e = _emp_ce_html("ex", "💱")
        star_e = _emp_ce_html("stars", "⭐")
        ton_e = _gram_ce_html("TON")
        irt_e = _emp_ce_html("irt", "🇮🇷")
        usdt_e = _emp_ce_html("usdt", "💲")
        title = f"{price_e} <b>Price Convert</b>"

    def _value_block(irt, usdt, show_usdt=True):
        if md:
            if show_usdt:
                return (
                    f"{irt_e} **IRT:** `{_fmt_toman(irt)}` Tomans\n"
                    f"{usdt_e} **USDT:** `{_fmt_usdt(usdt)}` $"
                )
            return f"{irt_e} **IRT:** `{_fmt_toman(irt)}` Tomans"
        if show_usdt:
            return (
                f"{irt_e} <b>IRT:</b> <code>{_fmt_toman(irt)}</code> Tomans\n"
                f"{usdt_e} <b>USDT:</b> <code>{_fmt_usdt(usdt)}</code> $"
            )
        return (
            f"{irt_e} <b>IRT:</b> <code>{_fmt_toman(irt)}</code> Tomans"
        )

    if src == "toman":
        if not show_convert or dst not in ("ton", "usdt", "stars"):
            raise ValueError("Supported: t→ton/usdt/stars only.")
        usdt = amount / usdt_toman
        if dst == "usdt":
            if md:
                return (
                    f"{title}\n\n"
                    f"{irt_e} **{_fmt_toman(amount)} Tomans** → "
                    f"{usdt_e} **{_fmt_usdt(usdt)} USDT**"
                )
            return (
                f"{title}\n\n"
                f"{irt_e} <b>{_fmt_toman(amount)} Tomans</b> → "
                f"{usdt_e} <b>{_fmt_usdt(usdt)} USDT</b>"
            )
        if dst == "ton":
            tons = usdt / ton_usd
            if md:
                return (
                    f"{title}\n\n"
                    f"{irt_e} **{_fmt_toman(amount)} Tomans** → "
                    f"{ton_e} **{_fmt_amount(tons)}**"
                )
            return (
                f"{title}\n\n"
                f"{irt_e} <b>{_fmt_toman(amount)} Tomans</b> → "
                f"{ton_e} <b>{_fmt_amount(tons)}</b>"
            )
        stars = usdt / star_usd
        stars_i = Decimal(
            stars.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        if md:
            return (
                f"{title}\n\n"
                f"{irt_e} **{_fmt_toman(amount)} Tomans** → "
                f"{star_e} **{_fmt_stars(stars_i)} Stars**"
            )
        return (
            f"{title}\n\n"
            f"{irt_e} <b>{_fmt_toman(amount)} Tomans</b> → "
            f"{star_e} <b>{_fmt_stars(stars_i)} Stars</b>"
        )

    if src == "ton":
        irt = amount * ton_toman
        usdt = amount * ton_usd
        if not show_convert:
            if md:
                return (
                    f"{title}\n\n"
                    f"{ton_e} **{_fmt_amount(amount)}**\n\n"
                    f"{_value_block(irt, usdt)}"
                )
            return (
                f"{title}\n\n"
                f"{ton_e} <b>{_fmt_amount(amount)}</b>\n\n"
                f"{_value_block(irt, usdt)}"
            )
        if dst == "usdt":
            if md:
                return (
                    f"{title}\n\n"
                    f"{ton_e} **{_fmt_amount(amount)}** → "
                    f"{usdt_e} **{_fmt_usdt(usdt)} USDT**\n\n"
                    f"{_value_block(irt, usdt)}"
                )
            return (
                f"{title}\n\n"
                f"{ton_e} <b>{_fmt_amount(amount)}</b> → "
                f"{usdt_e} <b>{_fmt_usdt(usdt)} USDT</b>\n\n"
                f"{_value_block(irt, usdt)}"
            )
        stars = (amount * ton_usd) / star_usd
        stars_i = Decimal(
            stars.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        if md:
            return (
                f"{title}\n\n"
                f"{ton_e} **{_fmt_amount(amount)}** → "
                f"{star_e} **{_fmt_stars(stars_i)} Stars**\n\n"
                f"{_value_block(irt, usdt)}"
            )
        return (
            f"{title}\n\n"
            f"{ton_e} <b>{_fmt_amount(amount)}</b> → "
            f"{star_e} <b>{_fmt_stars(stars_i)} Stars</b>\n\n"
            f"{_value_block(irt, usdt)}"
        )

    if src == "stars":
        stars_i = Decimal(
            Decimal(str(amount)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        irt = stars_i * star_usd * usdt_toman
        usdt = stars_i * star_usd
        if not show_convert:
            if md:
                return (
                    f"{title}\n\n"
                    f"{star_e} **{_fmt_stars(stars_i)} Stars**\n\n"
                    f"{_value_block(irt, usdt)}"
                )
            return (
                f"{title}\n\n"
                f"{star_e} <b>{_fmt_stars(stars_i)} Stars</b>\n\n"
                f"{_value_block(irt, usdt)}"
            )
        if dst == "usdt":
            if md:
                return (
                    f"{title}\n\n"
                    f"{star_e} **{_fmt_stars(stars_i)} Stars** → "
                    f"{usdt_e} **{_fmt_usdt(usdt)} USDT**\n\n"
                    f"{_value_block(irt, usdt)}"
                )
            return (
                f"{title}\n\n"
                f"{star_e} <b>{_fmt_stars(stars_i)} Stars</b> → "
                f"{usdt_e} <b>{_fmt_usdt(usdt)} USDT</b>\n\n"
                f"{_value_block(irt, usdt)}"
            )
        tons = (stars_i * star_usd) / ton_usd
        if md:
            return (
                f"{title}\n\n"
                f"{star_e} **{_fmt_stars(stars_i)} Stars** → "
                f"{ton_e} **{_fmt_amount(tons)}**\n\n"
                f"{_value_block(irt, usdt)}"
            )
        return (
            f"{title}\n\n"
            f"{star_e} <b>{_fmt_stars(stars_i)} Stars</b> → "
            f"{ton_e} <b>{_fmt_amount(tons)}</b>\n\n"
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
            if md:
                return (
                    f"{title}\n\n"
                    f"{usdt_e} **{_fmt_usdt(amount)} USDT**\n\n"
                    f"{_value_block(irt, usdt, show_usdt=False)}"
                )
            return (
                f"{title}\n\n"
                f"{usdt_e} <b>{_fmt_usdt(amount)} USDT</b>\n\n"
                f"{_value_block(irt, usdt, show_usdt=False)}"
            )
        if dst == "ton":
            if md:
                return (
                    f"{title}\n\n"
                    f"{usdt_e} **{_fmt_usdt(amount)} USDT** → "
                    f"{ton_e} **{_fmt_amount(tons)}**\n\n"
                    f"{_value_block(irt, usdt, show_usdt=False)}"
                )
            return (
                f"{title}\n\n"
                f"{usdt_e} <b>{_fmt_usdt(amount)} USDT</b> → "
                f"{ton_e} <b>{_fmt_amount(tons)}</b>\n\n"
                f"{_value_block(irt, usdt, show_usdt=False)}"
            )
        if dst == "stars":
            if md:
                return (
                    f"{title}\n\n"
                    f"{usdt_e} **{_fmt_usdt(amount)} USDT** → "
                    f"{star_e} **{_fmt_stars(stars_i)} Stars**\n\n"
                    f"{_value_block(irt, usdt, show_usdt=False)}"
                )
            return (
                f"{title}\n\n"
                f"{usdt_e} <b>{_fmt_usdt(amount)} USDT</b> → "
                f"{star_e} <b>{_fmt_stars(stars_i)} Stars</b>\n\n"
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
            _loading_html("Fetching top orders..."),
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
            _loading_html("Fetching order book..."),
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
        status = await event.eor(_loading_html("Processing..."), parse_mode="html")

        async def work(client):
            global ORDER_CACHE
            orders = await _fetch_my_orders(client)
            ORDER_CACHE = orders
            _autotop_orders_sync_live(orders, trusted=bool(orders))
            if not orders:
                return None
            lines = [
                f"{_emp_ce_html('order', '📋')} <b>Active Orders</b> ({len(orders)})",
                "",
            ]
            for i, order in enumerate(orders, 1):
                top = await _top_order(client, order)
                my_range = _order_range(order)
                max_range = _order_range(top) if top else "—"
                highest = _order_is_highest(order, top)
                mark = f" {_emp_ce_html('tick', '✅')}" if highest else ""
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
                    f"   {_emp_ce_html('cash', '💰')} {my_range} {_gram_ce_html('TON')}{mark}\n"
                    f"   {_emp_ce_html('qs', '📊')} Max: {max_range} {_gram_ce_html('TON')}\n"
                    f"   {_emp_ce_html('qnt', '🔢')} Qty: {qty_text}\n"
                    f"   {_emp_ce_html('id', '🆔')} <code>{oid}</code>"
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


def _parse_autotop_interval(raw):
    """Parse ``20``, ``20s``, ``40s``, ``1m``, ``1.5m`` → seconds.

    Returns ``None`` when the string is not a duration.
    """
    if raw is None:
        return None
    text = str(raw).strip().lower().replace(" ", "")
    if not text:
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(s|sec|secs|second|seconds|m|min|mins|minute|minutes)?", text)
    if not m:
        return None
    amount = float(m.group(1))
    unit = m.group(2) or "s"
    if unit.startswith("m"):
        return amount * 60.0
    return amount


def _fmt_autotop_interval(seconds):
    try:
        secs = float(seconds)
    except Exception:
        secs = float(AUTOTOP_DEFAULT_INTERVAL)
    if secs >= 60 and abs(secs % 60) < 1e-9:
        mins = int(round(secs / 60.0))
        return f"{mins}m"
    if abs(secs - int(secs)) < 1e-9:
        return f"{int(secs)}s"
    return f"{secs:g}s"


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
        f"🔁 Interval: <code>{_fmt_autotop_interval(AUTOTOP_INTERVAL)}</code>",
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
    """Log when autotop turns itself off (no owner DM)."""
    LOGS.info("Autotop disabled: %s", reason)


async def _autotop_notify_problems(result: dict):
    """Log when autotop loses/restores orders or hits errors (no Saved Messages)."""
    lost = result.get("lost") or []
    restored = result.get("restored") or []
    recreated = result.get("recreated") or []
    errors = result.get("errors") or []
    if not lost and not restored and not recreated and not errors:
        return
    lines = ["Autotop orderup warning"]
    if recreated:
        lines.append(f"DB-recreated missing: {len(recreated)}")
        for row in recreated[:8]:
            lines.append(f"• {row.get('label') or '?'}")
    if lost:
        lines.append(f"Lost bids: {len(lost)}")
        for row in lost[:8]:
            lines.append(f"• {row.get('label') or '?'}: {row.get('error') or ''}")
    if restored:
        lines.append(f"Restored at old price: {len(restored)}")
        for row in restored[:8]:
            lines.append(f"• {row.get('label') or '?'}")
    if errors:
        lines.append(f"Errors: {len(errors)}")
        for row in errors[:5]:
            lines.append(f"• {row.get('label') or '?'}: {row.get('error') or ''}")
    LOGS.warning("\n".join(lines))


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
        status = await event.eor(_loading_html("Processing..."), parse_mode="html")
    else:
        status = await status.edit(_loading_html("Processing..."), parse_mode="html")
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

    if raw in ("off", "stop", "disable", "0", "false"):
        await _autotop_stop()
        return await event.eor(
            "🔴 <b>Autotop disabled.</b>\n\n"
            f"Use <code>{_h('autotop')} on</code> to enable again.",
            parse_mode="html",
        )

    interval_raw = None
    on_match = re.match(
        r"^(on|start|enable|true)(?:\s+(.+))?$",
        raw,
    )
    if on_match:
        interval_raw = (on_match.group(2) or "").strip() or None
    else:
        # Shorthand: `.autotop 20s` / `.autotop 1m` also enables.
        parsed = _parse_autotop_interval(raw)
        if parsed is not None:
            interval_raw = raw
        else:
            return await event.eor(
                "❌ <b>Usage:</b>\n"
                f"<code>{_h('autotop')}</code>\n"
                f"<code>{_h('autotop')} on</code> — default 30s\n"
                f"<code>{_h('autotop')} on 20s</code> / "
                f"<code>{_h('autotop')} 40s</code> / "
                f"<code>{_h('autotop')} 1m</code>\n"
                f"<code>{_h('autotop')} off</code>",
                parse_mode="html",
            )

    try:
        await _ensure_artemis_token(event)
    except ValueError as e:
        return await event.eor(f"❌ {e}", parse_mode="html")

    if interval_raw:
        parsed = _parse_autotop_interval(interval_raw)
        if parsed is None:
            return await event.eor(
                "❌ Invalid interval. Use e.g. "
                "<code>20s</code>, <code>40s</code>, <code>1m</code>.",
                parse_mode="html",
            )
        interval = _autotop_set_interval(parsed)
    else:
        interval = _autotop_set_interval(AUTOTOP_DEFAULT_INTERVAL)

    # Seed DB tracker from current live orders before the worker runs.
    try:
        async with ORDERUP_LOCK:
            async with MRKTClient(token=ARTEMIS_TOKEN) as client:
                live = await _fetch_my_orders(client)
                _autotop_orders_sync_live(live)
    except Exception as e:
        LOGS.warning("Autotop seed sync failed: %s", e)
    started = _autotop_start(interval)
    pretty = _fmt_autotop_interval(interval)
    if started:
        msg = (
            "🟢 <b>Autotop enabled.</b>\n\n"
            f"🔁 Checking every <code>{pretty}</code>.\n"
            f"💾 Active orders are tracked in DB and recreated if missing.\n"
            f"Use <code>{_h('autotop')} off</code> to disable."
        )
    else:
        msg = (
            "🟢 <b>Autotop is already running.</b>\n\n"
            f"🔁 Interval updated to <code>{pretty}</code>."
        )
    return await event.eor(
        msg + "\n\n" + _autotop_status_message(),
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
        status = await event.eor(_loading_html("Processing..."), parse_mode="html")
    else:
        status = await status.edit(_loading_html("Processing..."), parse_mode="html")
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
        status = await event.eor(_loading_html("Processing..."), parse_mode="html")
    else:
        status = await status.edit(_loading_html("Processing..."), parse_mode="html")
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
        status = await event.eor(_loading_html("Processing..."), parse_mode="html")
    else:
        status = await status.edit(_loading_html("Processing..."), parse_mode="html")
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
        status = await event.eor(_loading_html("Processing..."), parse_mode="html")

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
    # 404 = unknown / partial collection (e.g. typing "Resistance") — not an error.
    try:
        if owns_session:
            timeout = aiohttp.ClientTimeout(total=12, connect=6)
            session = aiohttp.ClientSession(timeout=timeout)
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json(content_type=None)
            if resp.status == 404:
                LOGS.debug("changes.tg HTTP 404 for %s", url)
                return None
            LOGS.debug("changes.tg HTTP %s for %s", resp.status, url)
    except Exception as e:
        LOGS.debug("changes.tg aiohttp failed for %s: %s", url, e)
    finally:
        if owns_session and session is not None:
            await session.close()
    # Fallback: sync requests (some hosts break aiohttp TLS/DNS). Skip after 404.
    try:
        def _req():
            r = requests.get(url, timeout=12)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                LOGS.debug("changes.tg requests HTTP 404 for %s", url)
                return None
            LOGS.debug("changes.tg requests HTTP %s for %s", r.status_code, url)
            return None

        return await asyncio.to_thread(_req)
    except Exception as e:
        LOGS.debug("changes.tg requests failed for %s: %s", url, e)
        return None


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


def _can_use_custom_emoji(client=None) -> bool:
    """
    Prefer CE when bot/user can use it. Missing ``me`` must not block CE tags
    when we already have a document id (Telegram strips them if disallowed).
    """
    try:
        for who in (client, asst, heartless_bot):
            if who is None:
                continue
            me = getattr(who, "me", None)
            if me is None:
                continue
            if bool(getattr(me, "bot", False)):
                return True
            if bool(getattr(me, "premium", False)):
                return True
    except Exception:
        pass
    # Default allow — callers only emit CE when a document id exists.
    return True


# document_id → alt glyph (from GetCustomEmojiDocuments)
_EMOJI_ALT_CACHE: dict[int, str] = {}


def _ce_md(doc_id, fallback: str = "✨") -> str:
    """CustomMarkdown `[alt](emoji/id)` for userbot messages (heartless_bot)."""
    if not doc_id:
        return fallback
    try:
        did = int(doc_id)
        alt = _EMOJI_ALT_CACHE.get(did) or "✨"
        return f"[{alt}](emoji/{did})"
    except Exception:
        try:
            return cusmo(int(doc_id))
        except Exception:
            return fallback


def _ce_html(doc_id, fallback: str = "✨") -> str:
    """
    ToxygenX Telethon HTML custom emoji:
    ``<tg-emoji emoji-id="…">alt</tg-emoji>`` → MessageEntityCustomEmoji.
    """
    if not doc_id:
        return html.escape(fallback)
    try:
        did = int(doc_id)
        alt = html.escape(_EMOJI_ALT_CACHE.get(did) or "✨")
        return f'<tg-emoji emoji-id="{did}">{alt}</tg-emoji>'
    except Exception:
        return html.escape(fallback)


def _emp_doc_id(name: str):
    """Resolve ``addemoji`` DB name → document id (``EMP`` key)."""
    if not name:
        return None
    try:
        from CythonX.dB.premium_db import list_emp

        ok = list_emp() or {}
    except Exception:
        return None
    raw = str(name).strip()
    # Aliases: price-convert used to look up ``ton``; packs store TON as ``gram``.
    aliases = {
        "ton": ("ton", "gram"),
        "💎": ("gram", "ton"),
    }
    candidates = aliases.get(raw.lower(), (raw,))
    bucket = None
    for cand in candidates:
        bucket = ok.get(cand)
        if not bucket:
            low = str(cand).lower()
            for k, v in ok.items():
                if str(k).lower() == low and v:
                    bucket = v
                    break
        if bucket:
            break
    if not bucket:
        return None
    try:
        return int(random.choice(list(bucket)))
    except Exception:
        return None


def _emp_ce_md(name: str, fallback: str = "✨") -> str:
    """CustomMarkdown CE from ``addemoji`` name."""
    return _ce_md(_emp_doc_id(name), fallback)


def _emp_ce_html(name: str, fallback: str = "✨") -> str:
    """HTML ``tg-emoji`` from ``addemoji`` name."""
    return _ce_html(_emp_doc_id(name), fallback)


def _loading_html(label: str = "Loading...") -> str:
    """Prefix status lines with ``addemoji load``."""
    return f'{_emp_ce_html("load", "⏳")} <b>{label}</b>'


def _gift_kb_button(
    label: str,
    *,
    emp: str | None = None,
    data: bytes | None = None,
    url: str | None = None,
    switch_query: str | None = None,
    same_peer: bool = True,
):
    """KeyboardInlineButton with optional EMP ``KeyboardButtonStyle.icon``."""
    icon = None
    if emp:
        try:
            raw = _emp_doc_id(emp)
            if raw is not None:
                icon = int(raw)
        except Exception:
            icon = None
    style = (
        KeyboardButtonStyle(bg_primary=True, icon=icon) if icon is not None else None
    )
    if data is not None:
        typ = tl_types.InlineButtonTypeCallback(data=data)
    elif url is not None:
        typ = tl_types.InlineButtonTypeUrl(url=url)
    elif switch_query is not None:
        typ = tl_types.InlineButtonTypeSwitchInline(
            query=switch_query, same_peer=same_peer,
        )
    else:
        raise ValueError("gift kb button needs data, url, or switch_query")
    return tl_types.KeyboardInlineButton(text=label, type=typ, style=style)


def _market_emp_name(market: str) -> str:
    """Map market key/label → ``addemoji`` name (mrkt/portal/tonnel/…)."""
    m = re.sub(r"[^a-z0-9]+", "", (market or "").lower())
    aliases = {
        "mrkt": "mrkt",
        "market": "mrkt",
        "portal": "portal",
        "portals": "portal",
        "tonnel": "tonnel",
        "tunnel": "tonnel",
        "telegram": "telegram",
        "tg": "telegram",
        "getgems": "getgems",
        "getgem": "getgems",
    }
    return aliases.get(m, m)


def _market_ce_md(market: str, fallback: str = "💰") -> str:
    return _emp_ce_md(_market_emp_name(market), fallback)


def _market_ce_html(market: str, fallback: str = "💰") -> str:
    return _emp_ce_html(_market_emp_name(market), fallback)


def _gift_parse_mode(compact: bool = False):
    """Gift panels use HTML so ToxygenX ``tg-emoji`` entities parse correctly."""
    if compact and _can_use_custom_emoji():
        return CustomMarkdown()
    if compact:
        return "md"
    return "html"


def _norm_emoji_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())



def _lookup_emoji_id(mapping: dict, name: str):
    if not mapping or not name:
        return None
    direct = mapping.get(name)
    if direct:
        return direct
    key = _norm_emoji_key(name)
    for k, v in mapping.items():
        if _norm_emoji_key(k) == key:
            return v
    return None


def _canonical_attr_name(pack: dict, kind: str, name: str) -> str:
    """Resolve CDN-correct casing from emoji pack (e.g. breaker → Breaker)."""
    raw = (name or "").strip()
    if not raw:
        return raw
    mapping = {}
    if kind == "model":
        mapping = (pack or {}).get("models") or {}
        for item in (pack or {}).get("models_list") or []:
            n = item.get("name") if isinstance(item, dict) else None
            if n:
                mapping.setdefault(str(n), True)
    elif kind == "backdrop":
        mapping = (pack or {}).get("backdrops") or {}
    key = _norm_emoji_key(raw)
    for k in mapping:
        if _norm_emoji_key(k) == key:
            return str(k)
    return _title_case_name(raw) if raw == raw.lower() else raw


def _changes_cdn_png(collection: str, model: str = "Original") -> Optional[str]:
    col = (collection or "").strip()
    mod = (model or "Original").strip() or "Original"
    if not col:
        return None
    return (
        f"{CHANGES_CDN}/gifts/models/"
        f"{_url_quote(col, safe='')}/png/{_url_quote(mod, safe='')}.png"
    )


def _inline_thumb(url: Optional[str], *, mime: str = "image/png"):
    """Telegram InputWebDocument rejects webp — use image/png (or jpeg)."""
    if not url:
        return None
    mime = (mime or "image/png").lower()
    if mime not in ("image/png", "image/jpeg", "image/gif"):
        mime = "image/png"
    try:
        return InputWebDocument(url, 0, mime, [])
    except Exception:
        return None


def _inline_article_media(url: Optional[str], *, mime: str = "image/jpeg") -> dict:
    """
    Thumb kwargs for ``builder.article`` — same pattern as urltools / inlinestuff:
    set both ``thumb`` and ``content`` to the same InputWebDocument.
    """
    doc = _inline_thumb(url, mime=mime)
    if doc is None:
        return {}
    return {"thumb": doc, "content": doc}


def _gift_inline_thumb_for_sess(sess: dict):
    """
    Collection → Original.png · model/NFT → model PNG from changes CDN.
    Always image/png (no fragment webp).
    """
    pack = _sess_emoji_pack(sess)
    col = (sess.get("collection") or "").strip()
    if not col:
        return None
    model = sess.get("model")
    if model:
        model = _canonical_attr_name(pack, "model", model)
        return _inline_thumb(_changes_cdn_png(col, model))
    return _inline_thumb(_changes_cdn_png(col, "Original"))


def _pack_has_emojis(pack: dict) -> bool:
    if not isinstance(pack, dict):
        return False
    if pack.get("collection"):
        return True
    if pack.get("models_list"):
        return True
    if pack.get("models"):
        return True
    return False


async def _fetch_emoji_pack(collection: str, *, force: bool = False) -> dict:
    """
    GET /emoji/{collection} (+ /gift fallback for collection id).

    Document ids come from Changes ``customEmojiId`` fields (same IDs used on
    KeyboardButtonStyle.icon). Successful packs are cached in memory only.
    Empty / 404 (partial typing) is never cached.
    """
    empty = {
        "collection": None,
        "models": {},
        "backdrops": {},
        "models_list": [],
        "emojisets": [],
    }
    col = (collection or "").strip()
    if not col:
        return empty
    cache_key = _norm_emoji_key(col)

    def _from_mem():
        cached = _EMOJI_PACK_CACHE.get(cache_key)
        if (
            cached
            and (time.monotonic() - float(cached.get("at") or 0)) < _EMOJI_PACK_TTL
            and _pack_has_emojis(cached.get("pack") or {})
        ):
            return cached.get("pack") or empty
        return None

    if not force:
        hit = _from_mem()
        if hit is not None:
            return hit

    pack = dict(empty)
    seg = _changes_path_segment(col)
    emoji_data = None
    try:
        emoji_data = await _changes_api_json(f"/emoji/{seg}")
        if isinstance(emoji_data, dict):
            raw_col = emoji_data.get("originalCustomEmojiId")
            if raw_col is not None:
                try:
                    pack["collection"] = str(int(raw_col))
                except Exception:
                    pack["collection"] = str(raw_col)
            models = {}
            models_list = []
            for row in emoji_data.get("models") or []:
                if not isinstance(row, dict):
                    continue
                name = row.get("name")
                eid = row.get("customEmojiId")
                if not name or eid is None:
                    continue
                try:
                    eid_s = str(int(eid))
                except Exception:
                    eid_s = str(eid)
                models[str(name)] = eid_s
                models_list.append({"name": str(name), "id": eid_s})
            backdrops = {}
            for row in emoji_data.get("backdrops") or []:
                if not isinstance(row, dict):
                    continue
                name = row.get("name")
                eid = row.get("customEmojiId")
                if not name or eid is None:
                    continue
                try:
                    backdrops[str(name)] = str(int(eid))
                except Exception:
                    backdrops[str(name)] = str(eid)
            pack["models"] = models
            pack["backdrops"] = backdrops
            pack["models_list"] = models_list
            sets = []
            for key in (
                "modelsEmojisetName",
                "modelsCraftedEmojisetName",
            ):
                val = emoji_data.get(key)
                if val and str(val) not in sets:
                    sets.append(str(val))
            pack["emojisets"] = sets
    except Exception as e:
        LOGS.warning("emoji pack /emoji failed for %s: %s", col, e)

    # /gift fallback only when /emoji returned JSON without a collection glyph.
    # Skip on HTTP 404 (partial typing like "Resistance") — avoids noisy double-404.
    if not pack.get("collection") and isinstance(emoji_data, dict):
        try:
            gdata = await _changes_api_json(f"/gift/{seg}")
            gift = (gdata or {}).get("gift") if isinstance(gdata, dict) else None
            if isinstance(gift, dict) and gift.get("customEmojiId") is not None:
                try:
                    pack["collection"] = str(int(gift["customEmojiId"]))
                except Exception:
                    pack["collection"] = str(gift["customEmojiId"])
        except Exception as e:
            LOGS.debug("emoji pack /gift fallback failed for %s: %s", col, e)

    if _pack_has_emojis(pack):
        _EMOJI_PACK_CACHE[cache_key] = {"at": time.monotonic(), "pack": pack}
        return pack

    # API miss (404 / partial name): fall back to last good mem pack.
    hit = _from_mem()
    if hit is not None:
        return hit
    LOGS.debug("emoji pack empty for %s (not cached)", col)
    return pack


_LOADED_EMOJISETS: set[str] = set()


async def _load_emoji_stickersets(short_names: list) -> None:
    """
    Fetch (+ install on userbot) gift emoji stickersets so asst may emit
    MessageEntityCustomEmoji / KeyboardButtonStyle.icon for those docs.
    """
    names = [str(n).strip() for n in (short_names or []) if n]
    names = [n for n in names if n and n not in _LOADED_EMOJISETS]
    if not names:
        return
    try:
        from telethon.tl.functions.messages import (
            GetStickerSetRequest,
            UninstallStickerSetRequest,
        )
        from telethon.tl.types import InputStickerSetShortName
    except Exception as e:
        LOGS.debug("GetStickerSet import: %s", e)
        return

    def _input_set(name: str):
        try:
            return InputStickerSetShortName(short_name=name)
        except TypeError:
            return InputStickerSetShortName(name)

    for name in names:
        stickerset = _input_set(name)
        # Fetch set metadata only — never InstallStickerSet (keeps packs out of
        # the owner's saved emoji / sticker lists).
        for client, tag in ((asst, "asst"), (heartless_bot, "userbot")):
            if client is None:
                continue
            try:
                await client(GetStickerSetRequest(stickerset=stickerset, hash=0))
            except TypeError:
                with contextlib.suppress(Exception):
                    await client(GetStickerSetRequest(stickerset=stickerset))
            except Exception as e:
                LOGS.debug("%s GetStickerSet %s: %s", tag, name, e)
        # Undo installs from older builds that polluted the emoji list.
        if heartless_bot is not None:
            with contextlib.suppress(Exception):
                await heartless_bot(UninstallStickerSetRequest(stickerset=stickerset))
        _LOADED_EMOJISETS.add(name)


async def _warm_custom_emoji_docs(doc_ids: list) -> None:
    """Fetch emoji docs on asst + userbot; cache alt glyphs."""
    ids = []
    seen = set()
    for d in doc_ids or []:
        try:
            i = int(d)
        except Exception:
            continue
        if i in seen:
            continue
        seen.add(i)
        ids.append(i)
    if not ids:
        return
    try:
        from telethon.tl.functions.messages import GetCustomEmojiDocumentsRequest
    except Exception as e:
        LOGS.debug("GetCustomEmojiDocuments import: %s", e)
        return

    for client in (asst, heartless_bot):
        if client is None:
            continue
        for i in range(0, len(ids), 100):
            chunk = ids[i : i + 100]
            try:
                docs = await client(GetCustomEmojiDocumentsRequest(document_id=chunk))
            except Exception as e:
                LOGS.debug("warm custom emoji docs via %s: %s", client, e)
                continue
            for doc in docs or []:
                try:
                    did = int(getattr(doc, "id", 0) or 0)
                except Exception:
                    continue
                if not did:
                    continue
                alt = "✨"
                for attr in getattr(doc, "attributes", None) or []:
                    a = getattr(attr, "alt", None)
                    if a:
                        alt = str(a)
                        break
                _EMOJI_ALT_CACHE[did] = alt


async def _warm_emp_names(*names: str) -> None:
    """Warm ``addemoji`` EMP document ids (same as g inline pack warm)."""
    try:
        from CythonX.dB.premium_db import list_emp

        ok = list_emp() or {}
    except Exception:
        return
    ids = []
    for name in names:
        raw = str(name or "").strip()
        if not raw:
            continue
        bucket = ok.get(raw)
        if not bucket:
            low = raw.lower()
            for k, v in ok.items():
                if str(k).lower() == low and v:
                    bucket = v
                    break
        if bucket:
            ids.extend(bucket)
    if ids:
        await _warm_custom_emoji_docs(ids)


def _price_tools_inline_pm():
    """Same CE parse mode as g floor/sales inline output (CustomMarkdown)."""
    if _can_use_custom_emoji():
        return CustomMarkdown()
    return "md"


async def _attach_emoji_pack(sess: dict, *, warm: bool = True, force: bool = False) -> dict:
    """Load emoji pack + stickersets into session; refetch if missing/empty."""
    existing = sess.get("emoji_pack") if isinstance(sess.get("emoji_pack"), dict) else {}
    if force or not _pack_has_emojis(existing):
        try:
            pack = await asyncio.wait_for(
                _fetch_emoji_pack(sess.get("collection") or "", force=force),
                timeout=10.0,
            )
        except Exception as e:
            LOGS.warning("attach emoji pack: %s", e)
            pack = existing or {
                "collection": None,
                "models": {},
                "backdrops": {},
                "models_list": [],
                "emojisets": [],
            }
        sess["emoji_pack"] = pack
    pack = sess.get("emoji_pack") or {}
    if warm and _pack_has_emojis(pack):
        # Stickersets first — required before Telegram accepts CE / button icons.
        with contextlib.suppress(Exception):
            await _load_emoji_stickersets(pack.get("emojisets") or [])
        ids = []
        if pack.get("collection"):
            ids.append(pack["collection"])
        # Warm only first page (+collection) — keep inline under Telegram timeout.
        for item in (pack.get("models_list") or [])[:_MODELS_PAGE_SIZE]:
            if item.get("id"):
                ids.append(item["id"])
        with contextlib.suppress(Exception):
            await _warm_custom_emoji_docs(ids)
    return sess


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
                    "rarityTier": info.get("rarityTier"),
                    "crafted": info.get("crafted"),
                }
                model_name = info.get("name")
            else:
                row = _changes_find_named(data.get("models") or [], model)
                if row:
                    model_data = {
                        "name": row.get("name"),
                        "rarityPermille": (
                            row.get("rarityPermille")
                            if row.get("rarityPermille") is not None
                            else _pct_to_permille(row.get("rarity"))
                        ),
                        "rarityTier": row.get("rarityTier"),
                        "crafted": row.get("crafted"),
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
        # Prefer api.changes.tg rarity; MRKT / label only as fallback.
        model_rarity = _model_rarity_from_changes(tg_snap)
        if model_rarity is None:
            model_rarity = model_row.get("rarityPerMille")
        if model_rarity is None:
            tg_model = (tg_snap or {}).get("model") or {}
            model_rarity = _rarity_from_label(tg_model.get("name"))

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

    emoji_pack = await _fetch_emoji_pack(collection)
    col_e = _ce_md(emoji_pack.get("collection"), "🎁")
    lines = [f"{col_e} **Collection:** `{_md(collection)}`"]
    if model:
        rarity = _md(_model_rarity_display(tg_snap, model_rarity))
        mod_e = _ce_md(
            _lookup_emoji_id(emoji_pack.get("models") or {}, model), "🧩"
        )
        lines.append(
            f"{mod_e} **Model:** `{_md(model)}` (`{rarity}`)"
        )
    if backdrop:
        back_e = _ce_md(
            _lookup_emoji_id(emoji_pack.get("backdrops") or {}, backdrop), "🎨"
        )
        lines.append(
            f"{back_e} **Backdrop:** `{_md(backdrop)}` "
            f"(`{_md(_rarity_pct(backdrop_rarity))}`)"
        )
    lines.append("")
    gram = _gram_ce_md("TON")
    for label, value in _sat_floor_rows(sat_floors):
        # Price in code, single space, then gram/TON unit.
        m_e = _market_ce_md(label, "💰")
        lines.append(
            f"{m_e} **{label}:** `{_md(_floor_price_code(value))}` {gram}"
        )
    lines.append("")

    qs_e = _emp_ce_md("qs", "📊")
    quick_txt = _ton2(quick) if quick is not None else "—"
    if model and backdrop:
        lines.append(
            f"{qs_e} **Quick Sell Collection + Model + Backdrop:** "
            f"`{_md(quick_txt)}` {gram}"
        )
    elif model:
        lines.append(
            f"{qs_e} **Quick Sell Collection + Model:** `{_md(quick_txt)}` {gram}"
        )
    else:
        lines.append(
            f"{qs_e} **Quick Sell Collection:** `{_md(quick_txt)}` {gram}"
        )

    return "\n".join(lines)


def _floor_copy_text(message_md: str) -> str:
    """Plain-text clipboard payload for floor panel (≤256 chars)."""
    text = re.sub(r"[*_`]", "", message_md or "")
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[ \t]+\n", "\n", text).strip()
    if len(text) > 256:
        text = text[:253] + "..."
    return text


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

        # Prefer api.changes.tg (even over NFT/MRKT seed).
        ch_rarity = _model_rarity_from_changes(tg_snap)
        if ch_rarity is not None:
            model_rarity = ch_rarity
        elif model_rarity is None:
            model_rarity = model_row.get("rarityPerMille")
        if model_rarity is None and tg_model:
            model_rarity = _rarity_from_label(tg_model.get("name"))

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
            m_e = _market_ce_html(label, "💰")
            lines.append(f"   {m_e} <b>{label}</b>: {_floor_ton(value)}")
        lines.append("")
        return lines

    emoji_pack = await _fetch_emoji_pack(collection)
    col_e = _ce_html(emoji_pack.get("collection"), "🎁")
    lines = []
    if nft_url:
        lines.append(
            f'{col_e} <a href="{nft_url}"><b>NFT Info</b></a>'
        )
    else:
        lines.append(f"{col_e} <b>NFT Info</b>")
    lines.append("")

    lines.extend(
        floor_block(
            f"{col_e} <b>Collection:</b> {html.escape(str(collection))}",
            _sat_floor_rows(sat_collection),
        )
    )

    if model:
        mod_e = _ce_html(
            _lookup_emoji_id(emoji_pack.get("models") or {}, model), "🧩"
        )
        lines.extend(
            floor_block(
                f"{mod_e} <b>Model:</b> {html.escape(str(model))} "
                f"({html.escape(_model_rarity_display(tg_snap, model_rarity))})",
                _sat_floor_rows(sat_model),
            )
        )

        if backdrop:
            back_e = _ce_html(
                _lookup_emoji_id(emoji_pack.get("backdrops") or {}, backdrop),
                "🎨",
            )
            lines.extend(
                floor_block(
                    f"{back_e} <b>Backdrop:</b> {html.escape(str(backdrop))} "
                    f"({_rarity_pct(backdrop_rarity)})",
                    _sat_floor_rows(sat_full),
                )
            )
        else:
            lines.extend([
                f"{_ce_html(None, '🎨')} Backdrop: ANY",
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

    qs_e = _emp_ce_html("qs", "📊")
    gram = _gram_ce_html("TON")
    lines.append(
        f"{qs_e} <b>Quick Sell Collection:</b> "
        f"{_ton2(quick_collection) if quick_collection is not None else '—'} {gram}"
    )
    if model:
        lines.append(
            f"{qs_e} <b>Quick Sell Collection + Model:</b> "
            f"{_ton2(quick_coll_model) if quick_coll_model is not None else '—'} {gram}"
        )
        if backdrop:
            lines.append(
                f"{qs_e} <b>Quick Sell Collection + Model + Backdrop:</b> "
                f"{_ton2(quick_full) if quick_full is not None else '—'} {gram}"
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
                _loading_html("Fetching balance..."),
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
            f"{_emp_ce_html('balance', '💰')} <b>MRKT Balance:</b> "
            f"<code>{ton.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}</code> {_gram_ce_html('TON')}",
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
            _loading_html("Fetching listed NFTs..."),
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
# (user_id, normalized raw query) → session token — for ChosenInlineResult CE refresh
_GIFT_INLINE_QUERY_INDEX: dict[tuple[int, str], str] = {}


def _gift_inline_query_key(user_id: int, raw: str) -> tuple[int, str]:
    return (int(user_id), re.sub(r"\s+", " ", (raw or "").strip().lower()))


def _gift_inline_purge():
    now = time.monotonic()
    dead = [
        k
        for k, v in _GIFT_INLINE_SESSIONS.items()
        if now - float(v.get("at") or 0) > _GIFT_INLINE_TTL
    ]
    for k in dead:
        _GIFT_INLINE_SESSIONS.pop(k, None)
    if dead:
        dead_set = set(dead)
        for qk, tok in list(_GIFT_INLINE_QUERY_INDEX.items()):
            if tok in dead_set:
                _GIFT_INLINE_QUERY_INDEX.pop(qk, None)


def _gift_inline_save(payload: dict) -> str:
    _gift_inline_purge()
    token = secrets.token_urlsafe(6)[:10]
    row = dict(payload)
    row["at"] = time.monotonic()
    _GIFT_INLINE_SESSIONS[token] = row
    try:
        uid = int(row.get("owner_id") or 0)
        raw = row.get("raw") or row.get("nft_raw") or ""
        if uid and raw:
            _GIFT_INLINE_QUERY_INDEX[_gift_inline_query_key(uid, raw)] = token
    except Exception:
        pass
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


def _gift_inline_nft_url(sess: dict) -> Optional[str]:
    url = sess.get("nft_url")
    if url:
        return str(url)
    slug = sess.get("slug")
    if slug:
        return f"https://t.me/nft/{slug}"
    raw = sess.get("nft_raw") or sess.get("raw") or ""
    parsed = _parse_nft_link(raw)
    if parsed:
        return f"https://t.me/nft/{parsed[0]}"
    return None


def _sess_emoji_pack(sess: dict) -> dict:
    pack = sess.get("emoji_pack")
    return pack if isinstance(pack, dict) else {}


def _gift_inline_info_lines(sess: dict, *, fmt: str = "html") -> list[str]:
    """
    Collection / Model / Backdrop headers.

    ``fmt="html"`` — ToxygenX ``<tg-emoji emoji-id>`` (hub / pickers).
    ``fmt="md"`` — CustomMarkdown ``[alt](emoji/id)`` (floor/sales bodies).
    """
    pack = _sess_emoji_pack(sess)
    col_raw = _title_case_name(sess.get("collection") or "?")
    model = sess.get("model")
    backdrop = sess.get("backdrop")
    mid = _lookup_emoji_id(pack.get("models") or {}, model) if model else None
    bid = (
        _lookup_emoji_id(pack.get("backdrops") or {}, backdrop) if backdrop else None
    )
    nft_url = _gift_inline_nft_url(sess) if model else None

    if fmt == "md":
        lines = [
            f"{_ce_md(pack.get('collection'), '🎁')} **Collection:** "
            f"`{_md_escape_inline(col_raw)}`"
        ]
        if model:
            model_line = (
                f"{_ce_md(mid, '🧩')} **Model:** "
                f"`{_md_escape_inline(_title_case_name(model))}`"
            )
            if nft_url:
                model_line += f" ([Link]({nft_url}))"
            lines.append(model_line)
        if backdrop:
            lines.append(
                f"{_ce_md(bid, '🎨')} **Backdrop:** "
                f"`{_md_escape_inline(_title_case_name(backdrop))}`"
            )
        return lines

    # HTML (default) — required for asst inline so CE is not left as bare ✨
    lines = [
        f"{_ce_html(pack.get('collection'), '🎁')} <b>Collection:</b> "
        f"<code>{html.escape(col_raw)}</code>"
    ]
    if model:
        model_line = (
            f"{_ce_html(mid, '🧩')} <b>Model:</b> "
            f"<code>{html.escape(_title_case_name(model))}</code>"
        )
        if nft_url:
            model_line += f' (<a href="{html.escape(nft_url, quote=True)}">Link</a>)'
        lines.append(model_line)
    if backdrop:
        lines.append(
            f"{_ce_html(bid, '🎨')} <b>Backdrop:</b> "
            f"<code>{html.escape(_title_case_name(backdrop))}</code>"
        )
    return lines


def _gift_inline_hub_text(sess: dict) -> str:
    return "\n".join(_gift_inline_info_lines(sess))


def _gift_inline_floor_picker_text(sess: dict) -> str:
    return "\n".join(_gift_inline_info_lines(sess))


def _gift_inline_pm():
    """Inline gift panels always use HTML (ToxygenX tg-emoji)."""
    return "html"


def _button_copy(text: str, label: str = "📋 Copy"):
    """Clipboard button (same KeyboardButtonCopy approach as translate)."""
    if not text:
        return None
    payload = text if len(text) <= 256 else text[:253] + "..."
    constructor = getattr(tl_types, "KeyboardButtonCopy", None)
    if constructor is None:
        return None
    try:
        original = Button._is_inline
        if not getattr(Button, "_heartless_copy_patch", False):
            def _patched_is_inline(button):
                if isinstance(button, constructor):
                    return True
                return original(button)
            Button._is_inline = staticmethod(_patched_is_inline)
            Button._heartless_copy_patch = True
    except Exception:
        return None
    try:
        return constructor(text=label, copy_text=payload)
    except TypeError:
        try:
            return constructor(label, payload)
        except Exception:
            return None


def _gift_inline_action_row(
    raw: str,
    *,
    show_back: bool,
    owner_id: int,
    token: str,
    back_data: bytes | None = None,
    show_refresh: bool = False,
    copy_text: str | None = None,
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
    extra = []
    if show_refresh:
        extra.append(
            Button.inline(
                "🔄 Refresh",
                data=_gift_cb("gr:r", owner_id, token),
            )
        )
    copy_btn = _button_copy(copy_text) if copy_text else None
    if copy_btn is not None:
        extra.append(copy_btn)
    if extra:
        rows.append(extra)
    if show_back:
        data = back_data or _gift_cb("gf:b", owner_id, token)
        rows.append([Button.inline("⬅️ Back", data=data)])
    return rows


def _gift_inline_hub_buttons(owner_id: int, token: str, raw: str, sess: dict | None = None):
    sess = sess or {}
    rows = [
        [
            Button.inline(
                "Floor Price 📉",
                data=_gift_cb("gu:s", owner_id, token, "f"),
            ),
            Button.inline(
                "Gift Chart 📊",
                data=_gift_cb("gu:s", owner_id, token, "c"),
            ),
        ],
        [
            Button.inline(
                "NFT Sales 🧾",
                data=_gift_cb("gu:s", owner_id, token, "s"),
            ),
            Button.inline(
                "Listings 🏷️",
                data=_gift_cb("gu:s", owner_id, token, "l"),
            ),
        ],
    ]
    # Collection-only: Models via bot DM (editInline still strips button icons).
    if int(sess.get("depth") or 1) == 1 and not sess.get("nft_mode"):
        rows.append(
            [
                Button.url(
                    "Models",
                    url=_gift_models_start_url(token),
                )
            ]
        )
    if sess.get("nft_mode") or sess.get("slug") or _gift_inline_nft_url(sess):
        rows.append(
            [
                Button.inline(
                    "Owner History 📜",
                    data=_gift_cb("gu:s", owner_id, token, "h"),
                )
            ]
        )
    show_back = bool(sess.get("from_models"))
    back_data = (
        _gift_cb("gm:l", owner_id, token, int(sess.get("models_page") or 0))
        if show_back
        else None
    )
    rows.extend(
        _gift_inline_action_row(
            raw,
            show_back=show_back,
            owner_id=owner_id,
            token=token,
            back_data=back_data,
        )
    )
    return rows



def _gift_cb(tag: str, *parts) -> bytes:
    """
    Encode gift button callback data.

    Wire format: ``{tag}:{urlsafe_b64(part:part:…)}`` (Telegram max 64 bytes).
    ``tag`` stays plain so ``@callback`` can route; owner/token/args are opaque.
    """
    raw = ":".join("" if p is None else str(p) for p in parts).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).rstrip(b"=")
    data = f"{tag}:".encode("ascii") + body
    if len(data) > 64:
        LOGS.warning(
            "gift cb exceeds 64 bytes tag=%s len=%s parts=%s",
            tag,
            len(data),
            parts,
        )
    return data


def _gift_cb_decode(payload: bytes) -> list[str]:
    """Decode the b64 payload captured after ``tag:``."""
    if isinstance(payload, str):
        payload = payload.encode("ascii")
    pad = b"=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode(payload + pad).decode("utf-8").split(":")


def _gift_cb_parse(payload: bytes, *kinds: str):
    """
    Decode payload into typed fields.

    ``kinds`` entries: ``"i"`` → int, ``"s"`` → str.
    """
    parts = _gift_cb_decode(payload)
    if len(parts) != len(kinds):
        raise ValueError(f"gift cb arity {len(parts)}!={len(kinds)}")
    out = []
    for part, kind in zip(parts, kinds):
        if kind == "i":
            out.append(int(part))
        else:
            out.append(part)
    return out


def _gift_models_start_url(token: str) -> str:
    """Deep link so Models panel is a direct bot message (button icons work)."""
    uname = getattr(getattr(asst, "me", None), "username", None) or "AssisXBot"
    return f"https://t.me/{uname}?start=models_{token}"


def _gift_models_panel_text(sess: dict) -> str:
    """Hub lines + short Models header (CE lives on button icons, not in text)."""
    lines = _gift_inline_info_lines(sess)
    lines.append("")
    lines.append("<b>Pick a model</b>")
    return "\n".join(lines)


async def handle_gift_models_start(event, args: str) -> bool:
    """
    Legacy ``/start models_<token>`` → Models panel in bot DM.

    Prefer inline Models callback. Still consumed so start.py skips welcome.
    NFTIDS-only; others get no reply.
    """
    raw = (args or "").strip()
    if not raw.lower().startswith("models"):
        return False
    # Always consume this deep-link so start.py does not send a welcome.
    if not _nft_user_allowed(event.sender_id):
        LOGS.info(
            "gift models start denied (not NFTIDS) user=%s",
            event.sender_id,
        )
        return True
    token = ""
    if raw.lower().startswith("models_"):
        token = raw[7:].strip()
    elif raw.lower().startswith("models-"):
        token = raw[7:].strip()
    if not token:
        # Bare start=models — no session; stay silent for privacy.
        return True
    sess = _gift_inline_load(token)
    if not sess:
        return True
    try:
        owner_id = int(sess.get("owner_id") or 0)
    except Exception:
        owner_id = 0
    if owner_id and owner_id != int(event.sender_id):
        return True
    if int(sess.get("depth") or 1) != 1 or sess.get("nft_mode"):
        return True
    try:
        await _attach_emoji_pack(
            sess, force=not _pack_has_emojis(_sess_emoji_pack(sess)),
        )
    except Exception as e:
        LOGS.warning("models start emoji pack: %s", e)
    pack = _sess_emoji_pack(sess)
    if not (pack.get("models_list") or []):
        try:
            await _ensure_artemis_token()
            async with MRKTClient(token=ARTEMIS_TOKEN) as client:
                names = await _list_collection_model_names(
                    client, sess.get("collection")
                )
            sess["model_names"] = list(names or [])
        except Exception as e:
            LOGS.debug("models start MRKT fallback: %s", e)
            sess["model_names"] = []
    sess["view"] = "models"
    sess["from_models"] = False
    sess["models_page"] = 0
    sess["at"] = time.monotonic()
    if not owner_id:
        sess["owner_id"] = int(event.sender_id)
        owner_id = int(event.sender_id)
    _GIFT_INLINE_SESSIONS[token] = sess
    page_ids = []
    for item in (pack.get("models_list") or [])[:_MODELS_PAGE_SIZE]:
        if item.get("id"):
            page_ids.append(item["id"])
    with contextlib.suppress(Exception):
        await _load_emoji_stickersets(pack.get("emojisets") or [])
    with contextlib.suppress(Exception):
        await _warm_custom_emoji_docs(page_ids)
    text = _gift_models_panel_text(sess)
    buttons = _gift_models_buttons(sess, owner_id, token, 0)
    await _gift_send_direct_icon_panel(event, text, buttons)
    return True


def _model_button(label: str, data: bytes, emoji_id=None):
    """
    Callback button with custom-emoji icon::

        KeyboardInlineButton(
            text=...,
            type=InlineButtonTypeCallback(data=...),
            style=KeyboardButtonStyle(bg_primary=True, icon=document_id),
        )

    ``emoji_id`` is Changes ``customEmojiId`` from the in-memory emoji pack.
    """
    icon = None
    if emoji_id is not None and emoji_id != "":
        try:
            icon = int(str(emoji_id).strip())
        except Exception:
            icon = None
        if icon is not None and icon <= 0:
            icon = None
    if icon is not None:
        style = KeyboardButtonStyle(bg_primary=True, icon=icon)
    else:
        style = None
    return tl_types.KeyboardInlineButton(
        text=label,
        type=tl_types.InlineButtonTypeCallback(data=data),
        style=style,
    )


async def _gift_send_direct_icon_panel(event, text: str, buttons: list):
    """Send Models panel as a direct bot message so button icons render."""
    if asst is None:
        return False
    peer = None
    try:
        peer = await event.get_input_chat()
    except Exception:
        peer = None
    if peer is None:
        try:
            peer = await asst.get_input_entity(int(event.sender_id))
        except Exception as e:
            LOGS.debug("gift Models direct peer: %s", e)
            return False
    try:
        await asst.send_message(
            peer,
            text,
            buttons=buttons,
            parse_mode="html",
            link_preview=False,
        )
        return True
    except Exception as e:
        LOGS.debug("gift Models SendMessage failed: %s", e)
        return False


async def _gift_edit_icon_panel(event, text: str, buttons: list, *, sess=None) -> bool:
    """Edit bot-owned Models DM panel, keeping ``KeyboardButtonStyle.icon``."""
    if asst is None:
        return False
    from telethon.errors import MessageNotModifiedError
    from telethon.tl.types import (
        InputBotInlineMessageID,
        InputBotInlineMessageID64,
    )

    msg_id = getattr(getattr(event, "query", None), "msg_id", None)
    if msg_id is None:
        return False
    # Inline edits still strip KeyboardButtonStyle.icon — DM/start panel only.
    if isinstance(msg_id, (InputBotInlineMessageID, InputBotInlineMessageID64)):
        return False
    try:
        peer = await event.get_input_chat()
        await asst.edit_message(
            peer,
            int(msg_id),
            text,
            buttons=buttons,
            parse_mode="html",
            link_preview=False,
        )
        return True
    except MessageNotModifiedError:
        return True
    except Exception as e:
        if "not modified" in str(e).lower():
            return True
        LOGS.debug("gift Models edit_message failed: %s", e)
        return False



def _gift_model_icon_id(pack: dict, item: dict, name: str):
    """Resolve customEmojiId for a model row (list id → models map → None)."""
    for raw in (
        (item or {}).get("id"),
        (item or {}).get("customEmojiId"),
        (pack.get("models") or {}).get(name),
        _lookup_emoji_id(pack.get("models") or {}, name),
    ):
        if raw is None or raw == "":
            continue
        try:
            icon = int(str(raw).strip())
        except Exception:
            continue
        if icon > 0:
            return icon
    return None


def _gift_models_buttons(sess: dict, owner_id: int, token: str, page: int = 0):
    pack = _sess_emoji_pack(sess)
    models = list(pack.get("models_list") or [])
    if not models and pack.get("models"):
        models = [
            {"name": n, "id": i} for n, i in (pack.get("models") or {}).items()
        ]
    if not models:
        models = [{"name": n, "id": None} for n in (sess.get("model_names") or [])]
    total = len(models)
    last_page = max(0, (total - 1) // _MODELS_PAGE_SIZE) if total else 0
    page = max(0, min(int(page), last_page))
    sess["models_page"] = page
    start = page * _MODELS_PAGE_SIZE
    chunk = models[start : start + _MODELS_PAGE_SIZE]
    rows = []
    for i in range(0, len(chunk), 2):
        row = []
        for j, item in enumerate(chunk[i : i + 2]):
            idx = start + i + j
            name = str(item.get("name") or f"#{idx}")
            label = name if len(name) <= 28 else name[:27] + "…"
            data = _gift_cb("gm:m", owner_id, token, idx)
            row.append(
                _model_button(label, data, _gift_model_icon_id(pack, item, name))
            )
        rows.append(row)
    if not rows:
        rows.append(
            [_model_button("No models found", _gift_cb("gm:n", owner_id, token))]
        )
    nav = []
    if page > 0:
        nav.append(
            _model_button(
                "⬅️ Previous",
                _gift_cb("gm:l", owner_id, token, page - 1),
            )
        )
    nav.append(
        _model_button(
            f"{page + 1}/{last_page + 1}",
            _gift_cb("gm:n", owner_id, token),
        )
    )
    if page < last_page:
        nav.append(
            _model_button(
                "Next ➡️",
                _gift_cb("gm:l", owner_id, token, page + 1),
            )
        )
    rows.append(nav)
    rows.append(
        [
            _model_button(
                "⬅️ Back",
                _gift_cb("gu:h", owner_id, token),
            )
        ]
    )
    return rows


# Inline NFT Sales / Listings market keys → (history_key, display label)
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
    sale_e = _emp_ce_html("sale", "🧾")
    lines.append(f"{sale_e} <b>Choose one for 10 latest sales</b>")
    return "\n".join(lines)


def _gift_inline_listings_picker_text(sess: dict) -> str:
    lines = _gift_inline_info_lines(sess)
    lines.append("")
    list_e = _emp_ce_html("listing", "🏷️")
    lines.append(f"{list_e} <b>Choose one for 10 latest listings</b>")
    return "\n".join(lines)


def _gift_inline_market_picker_buttons(
    sess: dict,
    owner_id: int,
    token: str,
    *,
    prefix: str,
    back_data: bytes,
):
    row1 = []
    row2 = []
    for i, (key, label) in enumerate(_GIFT_SALES_MARKETS):
        btn = Button.inline(
            label,
            data=_gift_cb(prefix, owner_id, token, key),
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
            back_data=back_data,
        )
    )
    return buttons


def _gift_inline_sales_picker_buttons(sess: dict, owner_id: int, token: str):
    return _gift_inline_market_picker_buttons(
        sess, owner_id, token,
        prefix="gs:m",
        back_data=_gift_cb("gu:h", owner_id, token),
    )


def _gift_inline_listings_picker_buttons(sess: dict, owner_id: int, token: str):
    return _gift_inline_market_picker_buttons(
        sess, owner_id, token,
        prefix="gl:m",
        back_data=_gift_cb("gu:h", owner_id, token),
    )


def _gift_inline_sales_result_buttons(sess: dict, owner_id: int, token: str):
    return _gift_inline_action_row(
        sess.get("raw") or "",
        show_back=True,
        owner_id=owner_id,
        token=token,
        back_data=_gift_cb("gs:b", owner_id, token),
        show_refresh=True,
    )


def _gift_inline_listings_result_buttons(sess: dict, owner_id: int, token: str):
    return _gift_inline_action_row(
        sess.get("raw") or "",
        show_back=True,
        owner_id=owner_id,
        token=token,
        back_data=_gift_cb("gl:b", owner_id, token),
        show_refresh=True,
    )


def _gift_inline_floor_picker_buttons(sess: dict, owner_id: int, token: str):
    depth = int(sess.get("depth") or 1)
    row = [
        Button.inline(
            "Collection Floor" if depth == 1 else "Collection",
            data=_gift_cb("gf:f", owner_id, token, "c"),
        )
    ]
    if depth >= 2:
        row.append(
            Button.inline(
                "C+Model",
                data=_gift_cb("gf:f", owner_id, token, "cm"),
            )
        )
    buttons = [row]
    if depth >= 3:
        buttons.append(
            [
                Button.inline(
                    "C+M+Backdrop",
                    data=_gift_cb("gf:f", owner_id, token, "cmb"),
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
            back_data=_gift_cb("gu:h", owner_id, token),
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
        description="Subscribe via @AssisXBot /pay",
        text=(
            "❌ You are not on the NFT allow-list.\n"
            "Purchase via /pay or t.me/AssisXBot?start=pay"
        ),
    )
    try:
        return await event.answer(
            [article],
            cache_time=5,
            switch_pm="Open /pay to subscribe",
            switch_pm_param="pay",
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


def _blank_media_file():
    """1×1 transparent PNG — Telegram cannot turn media messages into text-only."""
    # PNG IHDR 1x1 RGBA fully transparent
    raw = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    bio = io.BytesIO(raw)
    bio.name = "blank.png"
    return bio


async def _gift_inline_edit(event, text: str, buttons, *, parse_mode=None):
    # Hub/pickers: HTML + tg-emoji. Floor/chart bodies may still pass "md".
    if parse_mode is None:
        parse_mode = _gift_inline_pm()
    elif parse_mode == "md" and _can_use_custom_emoji():
        parse_mode = CustomMarkdown()
    try:
        from telethon.errors import MessageNotModifiedError
        from telethon.tl.types import (
            InputBotInlineMessageID,
            InputBotInlineMessageID64,
        )
    except Exception:
        MessageNotModifiedError = Exception  # noqa: N806
        InputBotInlineMessageID = type(None)  # noqa: N806
        InputBotInlineMessageID64 = type(None)  # noqa: N806

    try:
        is_inline = isinstance(
            getattr(event.query, "msg_id", None),
            (InputBotInlineMessageID, InputBotInlineMessageID64),
        )
    except Exception:
        is_inline = False

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
        LOGS.debug("Inline g text edit failed: %s", exc)

    # Chart/media messages cannot become text-only via Bot API — swap to a
    # tiny blank image and put the panel text in the caption.
    try:
        await event.edit(
            text,
            file=_blank_media_file(),
            buttons=buttons,
            parse_mode=parse_mode,
            link_preview=False,
        )
        return
    except MessageNotModifiedError:
        with contextlib.suppress(Exception):
            await event.answer()
        return
    except Exception as exc:
        LOGS.debug("Inline g blank-media edit failed: %s", exc)
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
            title="🎁 NFT Info Commands",
            description="@AssisXBot g Collection · Model · Backdrop",
            text=(
                "**NFT Info Commands**\n\n"
                "`@AssisXBot g Liberty Figure`\n"
                "`@AssisXBot g Liberty Figure, Fire Opal`\n"
                "`@AssisXBot g Liberty Figure, Fire Opal, Black`\n"
                "`@AssisXBot g https://t.me/nft/LibertyFigure-214445`\n\n"
                "Then pick a button"
            ),
            **_inline_article_media(
                "https://cdn.dbimg.app/3X0OOZEC.jpg", mime="image/jpeg",
            ),
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
        slug = parsed.get("slug")
        if slug:
            parsed["nft_url"] = f"https://t.me/nft/{slug}"
        try:
            coll, mod, back = await asyncio.wait_for(
                _gift_inline_resolve_nft_fast(parsed.get("nft_raw") or raw),
                timeout=8.0,
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
        # Best-effort SeeTG history (don't block past Telegram inline timeout).
        if parsed.get("slug"):
            try:
                tmp = {
                    **parsed,
                    "owner_id": owner_id,
                    "nft_mode": True,
                }
                tmp = await asyncio.wait_for(
                    _gift_inline_load_transfer_history(tmp),
                    timeout=3.5,
                )
                if tmp.get("transfer_history_md"):
                    parsed["transfer_history_md"] = tmp["transfer_history_md"]
            except Exception as e:
                LOGS.debug("Inline g SeeTG history skipped: %s", e)

    token = _gift_inline_save(
        {
            **parsed,
            "owner_id": owner_id,
            "resolved": bool(parsed.get("resolved")),
            "view": "hub",
            "last_mode": None,
            "from_models": False,
        }
    )
    sess = _GIFT_INLINE_SESSIONS[token]
    try:
        await _attach_emoji_pack(sess, force=True)
    except Exception as e:
        LOGS.warning("Inline g emoji pack skipped: %s", e)

    # Canonicalize model/backdrop casing for CDN thumbs + display.
    pack = _sess_emoji_pack(sess)
    # Partial typing ("Resistance") → empty pack / 404. Don't ship a fake hub.
    if (
        not sess.get("nft_mode")
        and int(sess.get("depth") or 1) == 1
        and not _pack_has_emojis(pack)
        and not sess.get("model")
    ):
        col = sess.get("collection") or raw
        tip = await event.builder.article(
            title=f"⏳ {col}…",
            description="Keep typing the full collection name",
            text=(
                f"⏳ Keep typing the full collection name.\n"
                f"<code>{html.escape(str(col))}</code>"
            ),
            parse_mode="html",
        )
        return await _gift_inline_answer(event, [tip], cache_time=0)
    if not pack.get("collection"):
        LOGS.debug(
            "Inline g missing collection emoji for %r pack_models=%s",
            sess.get("collection"),
            len(pack.get("models_list") or []),
        )
    if sess.get("model"):
        sess["model"] = _canonical_attr_name(pack, "model", sess["model"])
    if sess.get("backdrop"):
        sess["backdrop"] = _canonical_attr_name(pack, "backdrop", sess["backdrop"])

    title = _gift_inline_title(sess)
    desc_parts = [sess.get("collection") or "Gift"]
    if sess.get("model"):
        desc_parts.append(sess["model"])
    if sess.get("backdrop"):
        desc_parts.append(sess["backdrop"])

    # Thumbs: collection Original.png · model/NFT → model PNG (image/png only)
    thumb = None
    try:
        thumb = _gift_inline_thumb_for_sess(sess)
    except Exception as e:
        LOGS.debug("Inline g thumb skipped: %s", e)

    title_emoji = "🎁"
    if sess.get("model"):
        mid = _lookup_emoji_id(pack.get("models") or {}, sess["model"])
        title_emoji = "🧩" if mid else "🎁"

    hub_text = _gift_inline_hub_text(sess)
    article_kwargs = dict(
        title=f"{title_emoji} {title}",
        description=" · ".join(desc_parts[:3]),
        text=hub_text,
        parse_mode=_gift_inline_pm(),
        link_preview=False,
        buttons=_gift_inline_hub_buttons(
            owner_id, token, sess.get("raw") or "", sess,
        ),
    )
    if thumb is not None:
        article_kwargs["thumb"] = thumb
        article_kwargs["content"] = thumb
    try:
        article = await event.builder.article(**article_kwargs)
        return await _gift_inline_answer(event, [article], cache_time=0)
    except Exception as e:
        # Retry without thumb on mime/webdocument errors.
        if "webdocument" in str(e).lower() or "mime" in str(e).lower():
            LOGS.warning("Inline g thumb rejected, retrying plain: %s", e)
            article_kwargs.pop("thumb", None)
            article_kwargs.pop("content", None)
            article = await event.builder.article(**article_kwargs)
            return await _gift_inline_answer(event, [article], cache_time=0)
        raise


async def _gift_inline_resolve_nft_fast(raw: str):
    """
    Fast NFT → collection/model/backdrop for inline answer.

    Runs GetUniqueStarGift + GetWebPage + t.me HTML in parallel so burned
    gifts (STARGIFT_ALREADY_BURNED) still resolve model/backdrop.
    """
    parsed = _parse_nft_link(raw)
    if not parsed:
        return None, None, None
    slug, short_slug, _number = parsed
    collection, _, _ = _resolve_collection_from_slug(short_slug)

    async def _mtproto():
        return await _fetch_unique_star_gift_attrs(heartless_bot, slug)

    async def _webpage():
        return await _fetch_nft_attrs_via_webpage(heartless_bot, slug)

    async def _html():
        return await _fetch_telegram_nft_attrs(slug)

    results = await asyncio.gather(
        _mtproto(), _webpage(), _html(), return_exceptions=True,
    )
    model = backdrop = title = None
    for res in results:
        if isinstance(res, Exception) or not res:
            continue
        m, b, _mr, _br, t = res
        if t and not title:
            title = t
        if m and not model:
            model = m
        if b and not backdrop:
            backdrop = b
        if model and backdrop:
            break
    if title:
        collection = title
    LOGS.info(
        "inline NFT resolve slug=%s collection=%s model=%s backdrop=%s",
        slug,
        collection,
        model,
        backdrop,
    )
    return collection, model, backdrop


async def _gift_inline_resolve_session(sess: dict):
    """Resolve collection/model/backdrop names (and NFT attrs) via MRKT + user TG."""
    await _ensure_artemis_token()
    extras = {}
    async with MRKTClient(token=ARTEMIS_TOKEN) as client:
        if sess.get("nft_mode"):
            coll, mod, back, extras = await _resolve_nft_gift(
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
    if extras.get("nft_url"):
        sess["nft_url"] = extras["nft_url"]
    if extras.get("slug"):
        sess["slug"] = extras["slug"]
    elif sess.get("nft_mode"):
        parsed = _parse_nft_link(sess.get("nft_raw") or sess.get("raw") or "")
        if parsed:
            sess["slug"] = parsed[0]
            sess["nft_url"] = sess.get("nft_url") or f"https://t.me/nft/{parsed[0]}"
    if mod:
        sess["depth"] = max(int(sess.get("depth") or 1), 2)
    if back:
        sess["depth"] = max(int(sess.get("depth") or 1), 3)
    sess["resolved"] = True
    sess["at"] = time.monotonic()
    return sess


async def _gift_inline_load_transfer_history(sess: dict) -> dict:
    """Attach SeeTG Owner History (Gift Sent only) when session is an NFT link."""
    from urllib.parse import quote as _quote

    if not sess.get("nft_mode"):
        return sess
    slug = sess.get("slug")
    if not slug:
        parsed = _parse_nft_link(sess.get("nft_raw") or sess.get("raw") or "")
        if parsed:
            slug = parsed[0]
            sess["slug"] = slug
    if not slug:
        return sess
    see_url = f"https://t.me/seetgbot/nft?startapp={_quote(slug, safe='')}"
    try:
        rows = await seetg.fetch_transfer_history(slug, limit=10, sent_only=True)
        sess["transfer_history_md"] = "\n".join(
            seetg.format_history_md(rows, nft_url=see_url)
        )
    except Exception as e:
        LOGS.warning("SeeTG owner history failed for %s: %s", slug, e)
        # Soft-fail: show empty-state copy rather than a scary error panel.
        sess["transfer_history_md"] = "\n".join(
            seetg.format_history_md([], nft_url=see_url)
        )
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


@callback(re.compile(rb"^gu:s:([A-Za-z0-9_-]+)$"))
async def artemis_gift_inline_hub_select_cb(event):
    """Stage 1 → Floor / Chart / Sales / Listings / Owner History."""
    try:
        owner_id, token, choice = _gift_cb_parse(
            event.data_match.group(1), "i", "s", "s"
        )
    except Exception:
        return await event.answer("Invalid request.", alert=True)
    if choice not in ("f", "c", "s", "l", "h"):
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

    if choice == "h":
        if not (sess.get("nft_mode") or sess.get("slug") or _gift_inline_nft_url(sess)):
            return await event.answer("Owner history needs an NFT link.", alert=True)
        await event.answer("Owner History…")
        try:
            sess = await _gift_inline_load_transfer_history(sess)
        except Exception as e:
            LOGS.warning("g owner history failed: %s", e)
            return await event.answer(str(e)[:180], alert=True)
        text = sess.get("transfer_history_md") or (
            "📜 **Owner History**\n\nNo History Found -_-"
        )
        # Prepend collection/model header (md — body is markdown)
        text = "\n".join(
            [*_gift_inline_info_lines(sess, fmt="md"), "", text]
        )
        sess["view"] = "history_out"
        sess["at"] = time.monotonic()
        _GIFT_INLINE_SESSIONS[token] = sess
        return await _gift_inline_edit(
            event,
            text,
            _gift_inline_action_row(
                sess.get("raw") or "",
                show_back=True,
                owner_id=owner_id,
                token=token,
                back_data=_gift_cb("gu:h", owner_id, token),
                show_refresh=True,
            ),
            parse_mode="md",
        )

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
            parse_mode="html",
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
            parse_mode="html",
        )

    if choice == "l":
        if sess.get("nft_mode"):
            sess["depth"] = 3
        if not sess.get("resolved"):
            await event.answer("Resolving…")
            try:
                sess = await _gift_inline_resolve_session(sess)
            except Exception as e:
                LOGS.warning("g listings resolve failed: %s", e)
                return await event.answer(str(e)[:180], alert=True)
        sess["view"] = "listings_pick"
        sess["at"] = time.monotonic()
        _GIFT_INLINE_SESSIONS[token] = sess
        await event.answer("Listings")
        return await _gift_inline_edit(
            event,
            _gift_inline_listings_picker_text(sess),
            _gift_inline_listings_picker_buttons(sess, owner_id, token),
            parse_mode="html",
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
    # From Models: never open collection-only chart when a model is set.
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
            "emoji_pack": sess.get("emoji_pack") or {},
            "from_models": bool(sess.get("from_models")),
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


@callback(re.compile(rb"^gu:h:([A-Za-z0-9_-]+)$"))
async def artemis_gift_inline_hub_cb(event):
    """Back to stage-1 Floor/Chart hub."""
    try:
        owner_id, token = _gift_cb_parse(event.data_match.group(1), "i", "s")
    except Exception:
        return await event.answer("Invalid request.", alert=True)

    if int(event.sender_id) != owner_id:
        return await event.answer("This panel belongs to another user.", alert=True)

    sess = _gift_inline_load(token)
    if not sess:
        return await event.answer("Session expired — search again with g …", alert=True)

    # Back from Models browser → collection hub.
    if sess.get("view") == "models":
        sess["model"] = None
        sess["backdrop"] = None
        sess["depth"] = 1
        sess["from_models"] = False
        sess["raw"] = sess.get("collection") or sess.get("raw") or ""
    # else: keep from_models / model when returning from Sales/Listings/etc.
    sess["view"] = "hub"
    sess["last_mode"] = None
    sess["at"] = time.monotonic()
    _GIFT_INLINE_SESSIONS[token] = sess
    await event.answer("Back")
    return await _gift_inline_edit(
        event,
        _gift_inline_hub_text(sess),
        _gift_inline_hub_buttons(
            owner_id, token, sess.get("raw") or "", sess,
        ),
    )


@callback(re.compile(rb"^gm:n:([A-Za-z0-9_-]+)$"))
async def artemis_gift_models_noop_cb(event):
    return await event.answer(cache_time=0)


@callback(re.compile(rb"^gm:l:([A-Za-z0-9_-]+)$"))
async def artemis_gift_models_list_cb(event):
    """Open / paginate Models in place (inline edit with button icons)."""
    try:
        owner_id, token, page = _gift_cb_parse(
            event.data_match.group(1), "i", "s", "i"
        )
    except Exception:
        return await event.answer("Invalid request.", alert=True)

    if int(event.sender_id) != owner_id:
        return await event.answer("This panel belongs to another user.", alert=True)

    sess = _gift_inline_load(token)
    if not sess:
        return await event.answer("Session expired — search again with g …", alert=True)

    with contextlib.suppress(Exception):
        await event.answer()

    try:
        await _attach_emoji_pack(
            sess,
            force=not _pack_has_emojis(_sess_emoji_pack(sess)),
            warm=False,
        )
    except Exception as e:
        LOGS.debug("models emoji pack: %s", e)

    pack = _sess_emoji_pack(sess)
    if not (pack.get("models_list") or pack.get("models")):
        try:
            await _ensure_artemis_token()
            async with MRKTClient(token=ARTEMIS_TOKEN) as client:
                names = await _list_collection_model_names(
                    client, sess.get("collection")
                )
            sess["model_names"] = list(names or [])
        except Exception as e:
            LOGS.debug("models MRKT fallback: %s", e)
            sess["model_names"] = []

    sess["view"] = "models"
    sess["from_models"] = False
    if int(sess.get("depth") or 1) > 1 and not sess.get("nft_mode"):
        sess["model"] = None
        sess["backdrop"] = None
        sess["depth"] = 1
        sess["raw"] = sess.get("collection") or sess.get("raw") or ""
    sess["models_page"] = page
    sess["at"] = time.monotonic()
    _GIFT_INLINE_SESSIONS[token] = sess

    page_ids = []
    start_i = page * _MODELS_PAGE_SIZE
    for item in (pack.get("models_list") or [])[start_i : start_i + _MODELS_PAGE_SIZE]:
        if item.get("id"):
            page_ids.append(item["id"])
    if not page_ids:
        for _name, eid in list((pack.get("models") or {}).items())[
            start_i : start_i + _MODELS_PAGE_SIZE
        ]:
            page_ids.append(eid)
    with contextlib.suppress(Exception):
        await _load_emoji_stickersets(pack.get("emojisets") or [])
    with contextlib.suppress(Exception):
        await _warm_custom_emoji_docs(page_ids)

    buttons = _gift_models_buttons(sess, owner_id, token, page)
    panel_text = _gift_models_panel_text(sess)
    if await _gift_edit_icon_panel(event, panel_text, buttons, sess=sess):
        return
    return await _gift_inline_edit(event, panel_text, buttons)


@callback(re.compile(rb"^gm:m:([A-Za-z0-9_-]+)$"))
async def artemis_gift_models_pick_cb(event):
    """Model button → collection+model hub (Floor/Chart kept; no collection-only options)."""
    try:
        owner_id, token, idx = _gift_cb_parse(
            event.data_match.group(1), "i", "s", "i"
        )
    except Exception:
        return await event.answer("Invalid request.", alert=True)

    if int(event.sender_id) != owner_id:
        return await event.answer("This panel belongs to another user.", alert=True)

    sess = _gift_inline_load(token)
    if not sess:
        return await event.answer("Session expired — search again with g …", alert=True)

    pack = _sess_emoji_pack(sess)
    models = list(pack.get("models_list") or [])
    if not models:
        models = [
            {"name": n, "id": None} for n in (sess.get("model_names") or [])
        ]
    if idx < 0 or idx >= len(models):
        return await event.answer("Model not found.", alert=True)

    model_name = str(models[idx].get("name") or "").strip()
    if not model_name:
        return await event.answer("Model not found.", alert=True)

    col = sess.get("collection") or ""
    sess["model"] = model_name
    sess["backdrop"] = None
    sess["depth"] = 2
    sess["raw"] = f"{col}, {model_name}" if col else model_name
    sess["from_models"] = True
    sess["view"] = "hub"
    sess["at"] = time.monotonic()
    _GIFT_INLINE_SESSIONS[token] = sess
    await event.answer(model_name[:40])
    return await _gift_inline_edit(
        event,
        _gift_inline_hub_text(sess),
        _gift_inline_hub_buttons(
            owner_id, token, sess.get("raw") or "", sess,
        ),
    )


@callback(re.compile(rb"^gf:f:([A-Za-z0-9_-]+)$"))
async def artemis_gift_inline_floor_cb(event):
    try:
        owner_id, token, mode = _gift_cb_parse(
            event.data_match.group(1), "i", "s", "s"
        )
    except Exception:
        return await event.answer("Invalid request.", alert=True)
    if mode not in ("c", "cm", "cmb"):
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

        # Satellite floors + MRKT quick sell (client required for /orders/top).
        await _ensure_artemis_token()
        async with MRKTClient(token=ARTEMIS_TOKEN) as client:
            message = await _build_gift_floor_only(client, coll, mod, back)
    except Exception as e:
        LOGS.warning("Inline g floor failed: %s", e)
        return await event.answer(str(e)[:180], alert=True)

    sess["last_mode"] = mode
    sess["view"] = "floor_out"
    sess["last_floor_text"] = message
    sess["at"] = time.monotonic()
    _GIFT_INLINE_SESSIONS[token] = sess
    # Floor panel: refresh + copy + back → floor picker.
    buttons = _gift_inline_action_row(
        sess.get("raw") or "",
        show_back=True,
        owner_id=owner_id,
        token=token,
        back_data=_gift_cb("gf:b", owner_id, token),
        show_refresh=True,
        copy_text=_floor_copy_text(message),
    )
    return await _gift_inline_edit(event, message, buttons, parse_mode="md")


@callback(re.compile(rb"^gf:b:([A-Za-z0-9_-]+)$"))
async def artemis_gift_inline_back_cb(event):
    """Floor output → floor picker (stage 2)."""
    try:
        owner_id, token = _gift_cb_parse(event.data_match.group(1), "i", "s")
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
        parse_mode="html",
    )


@callback(
    re.compile(
        rb"^gs:m:([A-Za-z0-9_-]+)$"
    )
)
async def artemis_gift_inline_sales_market_cb(event):
    """NFT Sales market → 10 latest sales (Satellite miniapp)."""
    try:
        owner_id, token, market_key = _gift_cb_parse(
            event.data_match.group(1), "i", "s", "s"
        )
    except Exception:
        return await event.answer("Invalid request.", alert=True)
    if market_key not in dict(_GIFT_SALES_MARKETS):
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
        # Filter depth matches search: c / c+m / c+m+b
        depth = int(sess.get("depth") or 1)
        mode = "cmb" if depth >= 3 else "cm" if depth >= 2 else "c"
        coll, mod, back = _gift_inline_mode_filter(sess, mode)
        if not coll:
            return await event.answer("Could not resolve collection.", alert=True)

        sales = await sat._latest_sales_for_market(
            coll, market_key, mod, back, limit=10,
        )
        sale_e = _emp_ce_md("sale", "🧾")
        mkt_e = _market_ce_md(market_key, "🏪")
        lines = [
            f"{sale_e} **NFT Sales**",
            "",
            *_gift_inline_info_lines(sess, fmt="md"),
            "",
            f"{mkt_e} **10 Latest {label} Sales**",
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
                    f"**{i}. {link} · {_price_txt_with_gram_md(price_txt)} · "
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


@callback(re.compile(rb"^gs:b:([A-Za-z0-9_-]+)$"))
async def artemis_gift_inline_sales_back_cb(event):
    """Sales result → sales market picker."""
    try:
        owner_id, token = _gift_cb_parse(event.data_match.group(1), "i", "s")
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
        parse_mode="html",
    )


async def _gift_inline_build_listings_text(sess: dict, market_key: str) -> str:
    label = dict(_GIFT_SALES_MARKETS).get(market_key, market_key.title())
    depth = int(sess.get("depth") or 1)
    mode = "cmb" if depth >= 3 else "cm" if depth >= 2 else "c"
    coll, mod, back = _gift_inline_mode_filter(sess, mode)
    if not coll:
        raise ValueError("Could not resolve collection.")
    listings = await sat._latest_listings_for_market(
        coll, market_key, mod, back, limit=10,
    )
    list_e = _emp_ce_md("listing", "🏷️")
    mkt_e = _market_ce_md(market_key, "🏪")
    lines = [
        f"{list_e} **Listings**",
        "",
        *_gift_inline_info_lines(sess, fmt="md"),
        "",
        f"{mkt_e} **10 Latest {label} Listings**",
        "",
    ]
    mkey = sat._norm_market_key(market_key)
    no_time_markets = {"telegram", "tg", "getgems"}
    buy_markets = {"mrkt", "portals", "tonnel"}
    if not listings:
        lines.append("**No Listing Found -_-**")
    else:
        for i, row in enumerate(listings, 1):
            price_txt = row.get("price_display") or "—"
            slug = row.get("slug") or ""
            url = row.get("nft_url") or (
                f"https://t.me/nft/{slug}" if slug else None
            )
            title = sat._sale_number_label(row)
            if url:
                link = f"[{_md_escape_inline(title)}]({url})"
            else:
                link = f"`{_md_escape_inline(title)}`"
            # MRKT / Portal / Tonnel: hyperlinked (buy) next to NFT #
            buy_url = row.get("buy_url")
            if mkey in buy_markets and buy_url:
                link = f"{link} ([{_md_escape_inline('buy')}]({buy_url}))"
            parts = [f"**{i}. {link} · {_price_txt_with_gram_md(price_txt)}**"]
            # Telegram / Getgems have no listing time in Satellite — omit the dash.
            if mkey not in no_time_markets:
                when = sat._fmt_sold_at(row.get("listed_at"))
                if when:
                    parts[0] = (
                        f"**{i}. {link} · {_price_txt_with_gram_md(price_txt)} · "
                        f"{_md_escape_inline(when)}**"
                    )
            lines.append(parts[0])
    return "\n".join(lines)


@callback(
    re.compile(
        rb"^gl:m:([A-Za-z0-9_-]+)$"
    )
)
async def artemis_gift_inline_listings_market_cb(event):
    """Listings market → 10 latest transferable listings (skip premarket)."""
    try:
        owner_id, token, market_key = _gift_cb_parse(
            event.data_match.group(1), "i", "s", "s"
        )
    except Exception:
        return await event.answer("Invalid request.", alert=True)
    if market_key not in dict(_GIFT_SALES_MARKETS):
        return await event.answer("Invalid request.", alert=True)

    if int(event.sender_id) != owner_id:
        return await event.answer("This panel belongs to another user.", alert=True)

    sess = _gift_inline_load(token)
    if not sess:
        return await event.answer("Session expired — search again with g …", alert=True)

    label = dict(_GIFT_SALES_MARKETS).get(market_key, market_key.title())
    await event.answer(f"{label} listings…")
    try:
        if not sess.get("resolved"):
            sess = await _gift_inline_resolve_session(sess)
            _GIFT_INLINE_SESSIONS[token] = sess
        text = await _gift_inline_build_listings_text(sess, market_key)
    except Exception as e:
        LOGS.warning("Inline g listings failed: %s", e)
        return await event.answer(str(e)[:180], alert=True)

    sess["view"] = "listings_out"
    sess["listings_market"] = market_key
    sess["at"] = time.monotonic()
    _GIFT_INLINE_SESSIONS[token] = sess
    return await _gift_inline_edit(
        event,
        text,
        _gift_inline_listings_result_buttons(sess, owner_id, token),
        parse_mode="md",
    )


@callback(re.compile(rb"^gl:b:([A-Za-z0-9_-]+)$"))
async def artemis_gift_inline_listings_back_cb(event):
    """Listings result → listings market picker."""
    try:
        owner_id, token = _gift_cb_parse(event.data_match.group(1), "i", "s")
    except Exception:
        return await event.answer("Invalid request.", alert=True)

    if int(event.sender_id) != owner_id:
        return await event.answer("This panel belongs to another user.", alert=True)

    sess = _gift_inline_load(token)
    if not sess:
        return await event.answer("Session expired — search again with g …", alert=True)

    sess["view"] = "listings_pick"
    sess["at"] = time.monotonic()
    _GIFT_INLINE_SESSIONS[token] = sess
    await event.answer("Back")
    return await _gift_inline_edit(
        event,
        _gift_inline_listings_picker_text(sess),
        _gift_inline_listings_picker_buttons(sess, owner_id, token),
        parse_mode="html",
    )


@callback(re.compile(rb"^gr:r:([A-Za-z0-9_-]+)$"))
async def artemis_gift_inline_refresh_cb(event):
    """Re-fetch the active floor / sales / listings / chart panel."""
    try:
        owner_id, token = _gift_cb_parse(event.data_match.group(1), "i", "s")
    except Exception:
        return await event.answer("Invalid request.", alert=True)

    if int(event.sender_id) != owner_id:
        return await event.answer("This panel belongs to another user.", alert=True)

    sess = _gift_inline_load(token)
    if not sess:
        return await event.answer("Session expired — search again with g …", alert=True)

    view = sess.get("view") or ""
    await event.answer("Refreshing…")

    try:
        if view == "floor_out":
            mode = sess.get("last_mode") or "c"
            if not sess.get("resolved") or sess.get("nft_mode"):
                sess = await _gift_inline_resolve_session(sess)
            coll, mod, back = _gift_inline_mode_filter(sess, mode)
            await _ensure_artemis_token()
            async with MRKTClient(token=ARTEMIS_TOKEN) as client:
                message = await _build_gift_floor_only(client, coll, mod, back)
            sess["last_floor_text"] = message
            sess["at"] = time.monotonic()
            _GIFT_INLINE_SESSIONS[token] = sess
            return await _gift_inline_edit(
                event,
                message,
                _gift_inline_action_row(
                    sess.get("raw") or "",
                    show_back=True,
                    owner_id=owner_id,
                    token=token,
                    back_data=_gift_cb("gf:b", owner_id, token),
                    show_refresh=True,
                    copy_text=_floor_copy_text(message),
                ),
                parse_mode="md",
            )

        if view == "sales_out":
            market_key = sess.get("sales_market") or "mrkt"
            if not sess.get("resolved"):
                sess = await _gift_inline_resolve_session(sess)
            depth = int(sess.get("depth") or 1)
            mode = "cmb" if depth >= 3 else "cm" if depth >= 2 else "c"
            coll, mod, back = _gift_inline_mode_filter(sess, mode)
            label = dict(_GIFT_SALES_MARKETS).get(market_key, market_key.title())
            sales = await sat._latest_sales_for_market(
                coll, market_key, mod, back, limit=10,
            )
            sale_e = _emp_ce_md("sale", "🧾")
            mkt_e = _market_ce_md(market_key, "🏪")
            lines = [
                f"{sale_e} **NFT Sales**",
                "",
                *_gift_inline_info_lines(sess, fmt="md"),
                "",
                f"{mkt_e} **10 Latest {label} Sales**",
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
                        f"**{i}. {link} · {_price_txt_with_gram_md(price_txt)} · "
                        f"{_md_escape_inline(when)}**"
                    )
            sess["at"] = time.monotonic()
            _GIFT_INLINE_SESSIONS[token] = sess
            return await _gift_inline_edit(
                event,
                "\n".join(lines),
                _gift_inline_sales_result_buttons(sess, owner_id, token),
                parse_mode="md",
            )

        if view == "listings_out":
            market_key = sess.get("listings_market") or "mrkt"
            if not sess.get("resolved"):
                sess = await _gift_inline_resolve_session(sess)
            text = await _gift_inline_build_listings_text(sess, market_key)
            sess["at"] = time.monotonic()
            _GIFT_INLINE_SESSIONS[token] = sess
            return await _gift_inline_edit(
                event,
                text,
                _gift_inline_listings_result_buttons(sess, owner_id, token),
                parse_mode="md",
            )

        if view == "history_out":
            sess = await _gift_inline_load_transfer_history(sess)
            text = sess.get("transfer_history_md") or (
                "📜 **Owner History**\n\nNo History Found -_-"
            )
            text = "\n".join(
                [*_gift_inline_info_lines(sess, fmt="md"), "", text]
            )
            sess["at"] = time.monotonic()
            _GIFT_INLINE_SESSIONS[token] = sess
            return await _gift_inline_edit(
                event,
                text,
                _gift_inline_action_row(
                    sess.get("raw") or "",
                    show_back=True,
                    owner_id=owner_id,
                    token=token,
                    back_data=_gift_cb("gu:h", owner_id, token),
                    show_refresh=True,
                ),
                parse_mode="md",
            )

        # Chart panels live in giftcharts session
        gc_token = sess.get("gc_token")
        if gc_token and view in ("chart_root", "chart_out", "chart"):
            gc_sess = gc._load_session(gc_token)
            if not gc_sess:
                return await event.answer("Chart session expired.", alert=True)
            tf = gc_sess.get("timeframe") or "24h"
            gift_q, model_q = gc._chart_queries(gc_sess)
            bundle = await gc._load_chart_bundle(gift_q, model_q, tf)
            return await gc._deliver_chart(
                event, bundle, owner_id=owner_id, token=gc_token,
            )

        if sess.get("nft_mode"):
            sess = await _gift_inline_resolve_session(sess)
            sess["view"] = "hub"
            sess["at"] = time.monotonic()
            _GIFT_INLINE_SESSIONS[token] = sess
            return await _gift_inline_edit(
                event,
                _gift_inline_hub_text(sess),
                _gift_inline_hub_buttons(
                    owner_id, token, sess.get("raw") or "", sess,
                ),
                parse_mode="html",
            )
    except Exception as e:
        LOGS.warning("Inline g refresh failed: %s", e)
        return await event.answer(str(e)[:180], alert=True)

    return await event.answer("Nothing to refresh.", alert=True)


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


@asst_cmd(pattern=r"s(?:\s+(.+))?$", func=lambda e: e.is_private)
async def artemis_stars_fee_asst(event):
    if not _asst_nft_ok(event):
        return
    await _artemis_stars_fee_handler(event)


@asst_cmd(pattern=r"ds(?:\s+(.+))?$", func=lambda e: e.is_private)
async def artemis_desired_ton_asst(event):
    if not _asst_nft_ok(event):
        return
    await _artemis_desired_ton_handler(event)


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
            _loading_html("Fetching floor...") if compact else _loading_html("Fetching NFT Info..."),
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
        if compact and _can_use_custom_emoji():
            pm = CustomMarkdown()
        elif compact:
            pm = "md"
        else:
            pm = "html"
        return await status.edit(
            message,
            parse_mode=pm,
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

    status = await event.eor(_loading_html("Converting..."), parse_mode="html")
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


async def _artemis_stars_fee_handler(event):
    """``.s 9200`` — Stars listing net of 20% fee + Fragment TON."""
    raw = (event.pattern_match.group(1) or "").strip()
    usage = (
        "❌ <b>Usage:</b> "
        f"<code>{_h('s')} 9200</code>"
    )
    if not raw:
        return await event.eor(usage, parse_mode="html")
    try:
        amount = Decimal(str(raw).replace(",", ""))
    except Exception:
        return await event.eor(usage, parse_mode="html")
    if amount <= 0:
        return await event.eor("❌ Stars must be positive.", parse_mode="html")

    status = await event.eor(_loading_html("Calculating..."), parse_mode="html")
    try:
        message = await _stars_listing_fee_message(amount)
        return await status.edit(message, parse_mode="html")
    except ValueError as e:
        return await status.edit(f"❌ {e}", parse_mode="html")
    except Exception as e:
        LOGS.exception("Artemis .s failed: %s", e)
        return await status.edit(
            f"❌ <b>Failed.</b>\n\n<code>{html.escape(str(e))}</code>",
            parse_mode="html",
        )


async def _artemis_desired_ton_handler(event):
    """``.ds 67`` — desired pure TON → fair Stars listing."""
    raw = (event.pattern_match.group(1) or "").strip()
    usage = (
        "❌ <b>Usage:</b> "
        f"<code>{_h('ds')} 67</code>"
    )
    if not raw:
        return await event.eor(usage, parse_mode="html")
    try:
        amount = Decimal(str(raw).replace(",", ""))
    except Exception:
        return await event.eor(usage, parse_mode="html")
    if amount <= 0:
        return await event.eor("❌ TON must be positive.", parse_mode="html")

    status = await event.eor(_loading_html("Calculating..."), parse_mode="html")
    try:
        message = await _desired_ton_listing_message(amount)
        return await status.edit(message, parse_mode="html")
    except ValueError as e:
        return await status.edit(f"❌ {e}", parse_mode="html")
    except Exception as e:
        LOGS.exception("Artemis .ds failed: %s", e)
        return await status.edit(
            f"❌ <b>Failed.</b>\n\n<code>{html.escape(str(e))}</code>",
            parse_mode="html",
        )


@heartless_cmd(owner_only=True, pattern=r"s(?:\s+(.+))?$")
async def artemis_stars_fee(event):
    await _artemis_stars_fee_handler(event)


@heartless_cmd(owner_only=True, pattern=r"ds(?:\s+(.+))?$")
async def artemis_desired_ton(event):
    await _artemis_desired_ton_handler(event)


@in_pattern(r"(?i)^p(?:\s+([\s\S]+))?$", owner=False)
async def artemis_price_inline(event):
    """Inline ``p`` — HTML ``tg-emoji`` like g hub panel."""
    if not _nft_user_allowed(event.sender_id):
        return await _inline_nft_denied(event)

    raw = ""
    try:
        raw = (event.pattern_match.group(1) or "").strip()
    except Exception:
        raw = ""

    with contextlib.suppress(Exception):
        await _warm_emp_names("ex", "stars", "gram", "irt", "usdt")
    pm = _gift_inline_pm()  # html — same as g hub CE
    ex_e = _emp_ce_html("ex", "💱")
    usage = (
        f"{ex_e} <b>Price Convert</b>\n\n"
        "<code>@AssisXBot p 50 ton</code>\n"
        "<code>@AssisXBot p 1000 stars ton</code>\n"
        "<code>@AssisXBot p 5 usdt stars</code>\n"
        "<code>@AssisXBot p 1000000 t ton</code>"
    )
    if not raw:
        article = await event.builder.article(
            title="💱 Price Convert (p)",
            description="@AssisXBot p 50 ton stars",
            text=usage,
            parse_mode=pm,
            link_preview=False,
        )
        return await _gift_inline_answer(event, [article], cache_time=10)

    try:
        amount, src, dst = _parse_price_query(raw)
        if amount <= 0:
            raise ValueError("Amount must be positive.")
        message = await _price_convert_message(amount, src, dst, fmt="html")
        title = "💱 Price Convert"
        desc = raw[:64]
    except ValueError as e:
        err = html.escape(str(e)) if str(e) else ""
        message = f"❌ {err}\n\n{usage}" if err else usage
        if "Supported" not in str(e) and "positive" not in str(e).lower():
            message = f"❌ Invalid query.\n\n{usage}"
        title = "❌ Price Convert"
        desc = "Check usage"
    except Exception as e:
        LOGS.exception("Inline p failed: %s", e)
        message = (
            f"❌ <b>Conversion failed.</b>\n\n"
            f"<code>{html.escape(str(e))}</code>"
        )
        title = "❌ Price Convert"
        desc = "Failed"

    article = await event.builder.article(
        title=title,
        description=desc,
        text=message,
        parse_mode=pm,
        link_preview=False,
    )
    return await _gift_inline_answer(event, [article], cache_time=5)


@in_pattern(r"(?i)^s(?:\s+([\s\S]+))?$", owner=False)
async def artemis_stars_fee_inline(event):
    """Inline ``s`` — HTML ``tg-emoji`` like g hub panel."""
    if not _nft_user_allowed(event.sender_id):
        return await _inline_nft_denied(event)

    raw = ""
    try:
        raw = (event.pattern_match.group(1) or "").strip()
    except Exception:
        raw = ""

    with contextlib.suppress(Exception):
        await _warm_emp_names("stars", "gram")
    pm = _gift_inline_pm()
    star_e = _emp_ce_html("stars", "⭐")
    gram = _gram_ce_html("TON")
    usage = (
        f"{star_e} <b>Stars Fee</b>\n\n"
        "<code>@AssisXBot s 9200</code>\n\n"
        f"Listing → −20% fee → Fragment {gram}"
    )
    if not raw:
        article = await event.builder.article(
            title="⭐ Stars Fee (s)",
            description="@AssisXBot s 9200",
            text=usage,
            parse_mode=pm,
            link_preview=False,
        )
        return await _gift_inline_answer(event, [article], cache_time=10)

    try:
        amount = Decimal(str(raw).replace(",", ""))
        if amount <= 0:
            raise ValueError("Stars must be positive.")
        message = await _stars_listing_fee_message(amount, fmt="html")
        title = "⭐ Stars Fee"
        desc = f"{_fmt_stars(amount)} Stars"
    except Exception as e:
        if isinstance(e, ValueError) and "positive" in str(e).lower():
            message = f"❌ {html.escape(str(e))}"
        else:
            try:
                Decimal(str(raw).replace(",", ""))
                LOGS.exception("Inline s failed: %s", e)
                message = (
                    f"❌ <b>Failed.</b>\n\n<code>{html.escape(str(e))}</code>"
                )
            except Exception:
                message = f"❌ Invalid amount.\n\n{usage}"
        title = "❌ Stars Fee"
        desc = "Check usage"

    article = await event.builder.article(
        title=title,
        description=desc,
        text=message,
        parse_mode=pm,
        link_preview=False,
    )
    return await _gift_inline_answer(event, [article], cache_time=5)


@in_pattern(r"(?i)^ds(?:\s+([\s\S]+))?$", owner=False)
async def artemis_desired_ton_inline(event):
    """Inline ``ds`` — HTML ``tg-emoji`` like g hub panel."""
    if not _nft_user_allowed(event.sender_id):
        return await _inline_nft_denied(event)

    raw = ""
    try:
        raw = (event.pattern_match.group(1) or "").strip()
    except Exception:
        raw = ""

    with contextlib.suppress(Exception):
        await _warm_emp_names("stars", "gram")
    pm = _gift_inline_pm()
    star_e = _emp_ce_html("stars", "⭐")
    gram = _gram_ce_html("TON")
    usage = (
        f"{gram} <b>Desired TON → Listing</b>\n\n"
        "<code>@AssisXBot ds 67</code>\n\n"
        f"Entry {gram} → Fragment → listing {star_e}"
    )
    if not raw:
        article = await event.builder.article(
            title="💎 Desired TON (ds)",
            description="@AssisXBot ds 67",
            text=usage,
            parse_mode=pm,
            link_preview=False,
        )
        return await _gift_inline_answer(event, [article], cache_time=10)

    try:
        amount = Decimal(str(raw).replace(",", ""))
        if amount <= 0:
            raise ValueError("TON must be positive.")
        message = await _desired_ton_listing_message(amount, fmt="html")
        title = "💎 Desired TON"
        desc = f"{_fmt_amount(amount)} TON"
    except Exception as e:
        if isinstance(e, ValueError) and "positive" in str(e).lower():
            message = f"❌ {html.escape(str(e))}"
        else:
            try:
                Decimal(str(raw).replace(",", ""))
                LOGS.exception("Inline ds failed: %s", e)
                message = (
                    f"❌ <b>Failed.</b>\n\n<code>{html.escape(str(e))}</code>"
                )
            except Exception:
                message = f"❌ Invalid amount.\n\n{usage}"
        title = "❌ Desired TON"
        desc = "Check usage"

    article = await event.builder.article(
        title=title,
        description=desc,
        text=message,
        parse_mode=pm,
        link_preview=False,
    )
    return await _gift_inline_answer(event, [article], cache_time=5)


@heartless_cmd(owner_only=True, pattern=r"add(?:\s+(.+))?$")
async def artemis_add_nftid(event):
    """Append a Telegram user (id or username) to the assistant allow-list."""
    raw = (event.pattern_match.group(1) or "").strip()
    if not raw:
        return await event.eor(
            "❌ <b>Usage:</b> "
            f"<code>{_h('add')} @user</code> · "
            f"<code>{_h('add')} ID</code> · "
            f"<code>{_h('add')} @user 30</code>",
            parse_mode="html",
        )

    parts = raw.split()
    days = None
    if len(parts) >= 2 and parts[-1].isdigit():
        days = int(parts[-1])
        if days < 1:
            return await event.eor("❌ Days must be ≥ 1.", parse_mode="html")
        user_raw = " ".join(parts[:-1]).strip()
    else:
        user_raw = raw

    try:
        entity = await _resolve_tg_user(event, user_raw)
    except ValueError as e:
        return await event.eor(f"❌ {e}", parse_mode="html")

    _add_nftid(entity.id, days=days)
    link = _user_profile_link(entity)
    if days:
        until = datetime.fromtimestamp(
            int(time.time()) + days * 86400, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M UTC")
        return await event.eor(
            f"<b>{link} added for {days}d</b>\nExpires: <code>{until}</code>",
            parse_mode="html",
        )
    return await event.eor(
        f"<b>{link} added to database</b> (permanent)",
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


# ============================================================
# /pay — Stars (250) + TON (2.79 + unique) → NFTIDS 30 days
# udB: TON_WALLET, TONAPI_KEY, PAY_STARS, PAY_TON, PAY_TIMEOUT
# ============================================================

_PAY_STARS_DEFAULT = 250
_PAY_TON_DEFAULT = 2.79
_PAY_DAYS = 30
_PAY_TIMEOUT_DEFAULT = 600  # seconds
_PAY_PAYLOAD = b"artemis_nft_sub_30d"
_TONAPI_BASE = "https://tonapi.io/v2"

_pay_stars_pending: set[int] = set()
_pay_ton_pending: dict[int, dict] = {}  # uid → {amount, expires, base}
_pay_seen_tx: set[str] = set()


def _pay_stars_amount() -> int:
    try:
        return max(1, int(udB.get_key("PAY_STARS") or _PAY_STARS_DEFAULT))
    except Exception:
        return _PAY_STARS_DEFAULT


def _pay_ton_base() -> float:
    try:
        return float(udB.get_key("PAY_TON") or _PAY_TON_DEFAULT)
    except Exception:
        return _PAY_TON_DEFAULT


def _pay_timeout_sec() -> int:
    try:
        return max(60, int(udB.get_key("PAY_TIMEOUT") or _PAY_TIMEOUT_DEFAULT))
    except Exception:
        return _PAY_TIMEOUT_DEFAULT


def _pay_ton_wallet() -> str | None:
    w = udB.get_key("TON_WALLET") or udB.get_key("TON_WALLET_ADDRESS")
    return str(w).strip() if w else None


def _pay_tonapi_key() -> str | None:
    k = udB.get_key("TONAPI_KEY")
    return str(k).strip() if k else None


def _pay_log_chat():
    return udB.get_key("LOG_CHANNEL") or LOG_CHAT_ID or OWNER_ID


def _pay_stars_invoice(stars: int) -> InputMediaInvoice:
    price = LabeledPrice(label=f"{stars} Stars", amount=stars)
    invoice = Invoice(
        currency="XTR",
        prices=[price],
        name_requested=False,
        phone_requested=False,
        email_requested=False,
        shipping_address_requested=False,
        flexible=False,
        phone_to_provider=False,
        email_to_provider=False,
    )
    return InputMediaInvoice(
        title="Heartless NFT Access",
        description=f"{_PAY_DAYS}-day access to Artemis NFT tools",
        invoice=invoice,
        payload=_PAY_PAYLOAD,
        provider="",
        provider_data=DataJSON("{}"),
        start_param="pay",
    )


async def send_pay_menu(event):
    """Public entry for /pay and /start pay."""
    stars = _pay_stars_amount()
    ton = _pay_ton_base()
    uid = event.sender_id
    _purge_expired_nft_subs()
    exp = _nft_sub_expiry(uid)
    status = ""
    if exp is not None:
        if exp > 0:
            until = datetime.fromtimestamp(exp, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"
            )
            status = f"\n\n✅ You already have access until <code>{until}</code>."
        else:
            status = "\n\n✅ You already have permanent access."

    text = (
        f"<b>Heartless NFT Access</b>\n\n"
        f"Unlock assistant NFT commands &amp; inline tools for "
        f"<b>{_PAY_DAYS} days</b>.\n\n"
        f"⭐ <b>Stars:</b> <code>{stars}</code>\n"
        f"💎 <b>TON:</b> <code>{ton}</code> (+ unique micro-amount)\n"
        f"{status}"
    )
    buttons = [
        [Button.inline(f"Pay {stars} ⭐", data="paystars")],
        [Button.inline(f"Pay ~{ton} TON", data="payton")],
    ]
    await event.respond(text, buttons=buttons, parse_mode="html")


@asst_cmd(pattern=r"pay$", func=lambda e: e.is_private)
async def asst_pay_cmd(event):
    await send_pay_menu(event)


@callback("paystars")
async def cb_pay_stars(event):
    stars = _pay_stars_amount()
    _pay_stars_pending.add(int(event.sender_id))
    await event.answer()
    try:
        await event.edit(
            f"⭐ Pay <b>{stars} Stars</b> for {_PAY_DAYS}-day NFT access.\n"
            f"Tap the invoice below.",
            parse_mode="html",
            buttons=None,
        )
    except Exception:
        pass
    await asst.send_message(
        event.chat_id,
        file=_pay_stars_invoice(stars),
        message=f"Pay {stars} ⭐ for {_PAY_DAYS}-day access:",
    )


@callback("payton")
async def cb_pay_ton(event):
    wallet = _pay_ton_wallet()
    api_key = _pay_tonapi_key()
    if not wallet or not api_key:
        return await event.answer(
            "TON payments not configured (TON_WALLET / TONAPI_KEY).",
            alert=True,
        )
    uid = int(event.sender_id)
    if uid in _pay_ton_pending:
        return await event.answer("You already have a pending TON payment.", alert=True)

    base = _pay_ton_base()
    unique_suffix = ((uid % 1000) + int(time.time()) % 1000) / 1e6
    unique_amount = round(base + unique_suffix, 6)
    timeout = _pay_timeout_sec()
    expires = int(time.time()) + timeout
    _pay_ton_pending[uid] = {
        "amount": unique_amount,
        "expires": expires,
        "base": base,
    }
    ton_link = f"ton://transfer/{wallet}?amount={int(unique_amount * 1e9)}"
    await event.answer()
    try:
        await event.edit(
            f"💎 <b>TON payment</b>\n\n"
            f"Base: <code>{base}</code> TON\n"
            f"Pay exactly: <code>{unique_amount}</code> TON\n"
            f"⏱ Timeout: <b>{timeout // 60} min</b>\n\n"
            f"⚠️ Send the exact unique amount.",
            buttons=[[Button.url("Pay with TON", ton_link)]],
            parse_mode="html",
        )
    except Exception:
        await asst.send_message(
            event.chat_id,
            f"💎 Pay exactly <code>{unique_amount}</code> TON",
            buttons=[[Button.url("Pay with TON", ton_link)]],
            parse_mode="html",
        )
    asyncio.create_task(_watch_ton_payment(uid, unique_amount, base))


async def _grant_paid_access(uid: int, method: str, detail: str = ""):
    _add_nftid(uid, days=_PAY_DAYS)
    until = datetime.fromtimestamp(
        int(time.time()) + _PAY_DAYS * 86400, tz=timezone.utc
    ).strftime("%Y-%m-%d %H:%M UTC")
    user_text = (
        f"✅ <b>Payment confirmed</b> ({html.escape(method)})\n"
        f"NFT access granted for <b>{_PAY_DAYS} days</b>.\n"
        f"Expires: <code>{until}</code>"
    )
    if detail:
        user_text += f"\n{detail}"
    try:
        await asst.send_message(uid, user_text, parse_mode="html")
    except Exception as e:
        LOGS.warning("pay notify user failed: %s", e)

    log_chat = _pay_log_chat()
    if log_chat:
        try:
            ent = await asst.get_entity(uid)
            name = html.escape(get_display_name(ent) or str(uid))
            await asst.send_message(
                log_chat,
                f"✅ <b>NFT sub</b> {method}\n"
                f"User: <a href=\"tg://user?id={uid}\">{name}</a> "
                f"(<code>{uid}</code>)\n"
                f"Until: <code>{until}</code>\n"
                f"{detail}",
                parse_mode="html",
            )
        except Exception as e:
            LOGS.warning("pay log failed: %s", e)


@asst.on(events.Raw(UpdateBotPrecheckoutQuery))
async def _pay_precheckout(event: UpdateBotPrecheckoutQuery):
    try:
        payload = event.payload or b""
        if payload != _PAY_PAYLOAD:
            return
        await asst(
            functions.messages.SetBotPrecheckoutResultsRequest(
                query_id=event.query_id,
                success=True,
                error=None,
            )
        )
    except Exception as e:
        LOGS.exception("pay precheckout: %s", e)


@asst.on(events.Raw(tl_types.UpdateNewMessage))
async def _pay_stars_received(event):
    msg = getattr(event, "message", None)
    if not msg or not isinstance(getattr(msg, "action", None), MessageActionPaymentSentMe):
        return
    payment: MessageActionPaymentSentMe = msg.action
    if (payment.payload or b"") != _PAY_PAYLOAD:
        return
    try:
        uid = int(msg.peer_id.user_id)
    except Exception:
        return
    _pay_stars_pending.discard(uid)
    stars = payment.total_amount or _pay_stars_amount()
    await _grant_paid_access(uid, "Stars", f"Amount: <code>{stars}</code> ⭐")


async def _ton_fetch_transactions(address: str, limit: int = 20) -> list:
    key = _pay_tonapi_key()
    if not key:
        return []
    url = f"{_TONAPI_BASE}/blockchain/accounts/{address}/transactions?limit={limit}"
    headers = {"Authorization": f"Bearer {key}"}
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    LOGS.warning("tonapi tx status=%s", resp.status)
                    return []
                data = await resp.json()
                return data.get("transactions") or []
    except Exception as e:
        LOGS.warning("tonapi fetch: %s", e)
        return []


async def _watch_ton_payment(uid: int, expected_amount: float, base_amount: float):
    wallet = _pay_ton_wallet()
    timeout = _pay_timeout_sec()
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            if uid not in _pay_ton_pending:
                return
            txs = await _ton_fetch_transactions(wallet, limit=25)
            for tx in txs:
                tx_hash = str(tx.get("hash") or "")
                if tx_hash and tx_hash in _pay_seen_tx:
                    continue
                in_msg = tx.get("in_msg") or {}
                raw_val = in_msg.get("value")
                if raw_val is None:
                    continue
                try:
                    value = int(raw_val) / 1e9
                except Exception:
                    continue
                if not tx.get("success"):
                    continue
                if abs(value - expected_amount) >= 1e-9:
                    continue
                if tx_hash:
                    _pay_seen_tx.add(tx_hash)
                    if len(_pay_seen_tx) > 500:
                        _pay_seen_tx.clear()
                _pay_ton_pending.pop(uid, None)
                sender = (in_msg.get("source") or {}).get("address", "?")
                detail = (
                    f"Amount: <code>{value}</code> TON\n"
                    f"Tx: <code>{html.escape(tx_hash or 'N/A')}</code>\n"
                    f"From: <code>{html.escape(str(sender))}</code>"
                )
                await _grant_paid_access(uid, "TON", detail)
                return
            await asyncio.sleep(5)
    except Exception as e:
        LOGS.exception("watch ton pay: %s", e)
    finally:
        if uid in _pay_ton_pending:
            _pay_ton_pending.pop(uid, None)
            try:
                await asst.send_message(
                    uid,
                    f"⏰ TON payment timed out after {timeout // 60} minutes. "
                    f"Use /pay to try again.",
                )
            except Exception:
                pass


async def _gift_refresh_inline_ce(msg_id, sess: dict, token: str, user_id: int) -> bool:
    """
    Re-edit an already-sent inline gift message so CE + button icons render.

    Initial SetInlineBotResults often shows plain alts; the first edit (same as
    tapping any hub button) activates MessageEntityCustomEmoji / style.icon in
    private, groups, and supergroups when the bot owner has Premium.
    """
    if asst is None or msg_id is None or not sess:
        return False
    try:
        await _attach_emoji_pack(
            sess, force=not _pack_has_emojis(_sess_emoji_pack(sess)),
        )
    except Exception as e:
        LOGS.debug("refresh inline CE pack: %s", e)
    pack = _sess_emoji_pack(sess)
    if sess.get("model"):
        sess["model"] = _canonical_attr_name(pack, "model", sess["model"])
    if sess.get("backdrop"):
        sess["backdrop"] = _canonical_attr_name(pack, "backdrop", sess["backdrop"])
    text = _gift_inline_hub_text(sess)
    buttons = _gift_inline_hub_buttons(
        user_id, token, sess.get("raw") or "", sess,
    )
    try:
        await asst.edit_message(
            msg_id,
            text,
            buttons=buttons,
            parse_mode="html",
            link_preview=False,
        )
        return True
    except Exception as e:
        # Force a visible change if Telegram treats content as unmodified.
        if "not modified" in str(e).lower():
            with contextlib.suppress(Exception):
                await asst.edit_message(
                    msg_id,
                    text + "\u200b",
                    buttons=buttons,
                    parse_mode="html",
                    link_preview=False,
                )
                return True
        LOGS.warning("refresh inline CE edit failed: %s", e)
        return False


@asst.on(events.Raw(tl_types.UpdateBotInlineSend))
async def artemis_gift_inline_chosen(update):
    """
    On pick of ``g …``, immediately re-edit the sent inline message so custom
    emoji (text + button icons) appear without requiring a manual button tap.

    Needs BotFather ``/setinlinefeedback`` enabled (msg_id / inline_message_id).
    """
    try:
        query = (getattr(update, "query", None) or "").strip()
        user_id = int(getattr(update, "user_id", 0) or 0)
        msg_id = getattr(update, "msg_id", None)
    except Exception:
        return
    if not user_id or not query:
        return
    m = re.match(r"(?i)^g(?:\s+([\s\S]+))?$", query)
    if not m:
        return
    raw = (m.group(1) or "").strip()
    if not raw:
        return
    if msg_id is None:
        LOGS.warning(
            "gift chosen-inline missing msg_id for user=%s — enable "
            "BotFather /setinlinefeedback so CE can refresh on send",
            user_id,
        )
        return

    token = _GIFT_INLINE_QUERY_INDEX.get(_gift_inline_query_key(user_id, raw))
    sess = _gift_inline_load(token) if token else None
    if not sess:
        try:
            parsed = _gift_inline_parse_raw(raw)
        except Exception:
            return
        token = _gift_inline_save(
            {
                **parsed,
                "owner_id": user_id,
                "resolved": bool(parsed.get("resolved")),
                "view": "hub",
                "last_mode": None,
                "from_models": False,
            }
        )
        sess = _GIFT_INLINE_SESSIONS[token]
        if sess.get("nft_mode"):
            try:
                coll, mod, back = await asyncio.wait_for(
                    _gift_inline_resolve_nft_fast(sess.get("nft_raw") or raw),
                    timeout=8.0,
                )
                if coll:
                    sess["collection"] = coll
                if mod:
                    sess["model"] = mod
                    sess["depth"] = max(int(sess.get("depth") or 1), 2)
                if back:
                    sess["backdrop"] = back
                    sess["depth"] = max(int(sess.get("depth") or 1), 3)
                if mod and back:
                    sess["resolved"] = True
            except Exception as e:
                LOGS.debug("chosen inline NFT resolve: %s", e)

    ok = await _gift_refresh_inline_ce(msg_id, sess, token, user_id)
    if ok:
        sess["inline_msg_id"] = msg_id
        sess["at"] = time.monotonic()
        _GIFT_INLINE_SESSIONS[token] = sess



# Resume autotop after plugin load when DB flag is enabled.
_autotop_bootstrap()

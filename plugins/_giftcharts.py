"""GiftCharts helpers (private module — loaded via Artemis).

Charts for inline ``g`` hub + ``.ch`` command.
Credentials: Heartless DB ``api_id`` / ``api_hash`` / ``SESSIONMRKT`` (same as Artemis).
"""

from __future__ import annotations

import asyncio
import contextlib
import html
import io
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote, urlparse, parse_qs

import aiohttp
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from telethon import Button, TelegramClient, functions, utils
from telethon.errors import MessageNotModifiedError
from telethon.sessions import StringSession
from telethon.tl.custom.message import CustomMarkdown
from telethon.tl.types import InputBotInlineMessageID

from . import LOGS, asst, callback, heartless_cmd, in_pattern, udB


def _chart_pm():
    """CustomMarkdown so ``[alt](emoji/id)`` / addemoji CE render on chart panels."""
    return CustomMarkdown()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GC_API = "https://api.giftcharts.com/api"
GC_SITE = "https://giftcharts.com"
GC_IMG_CDN = "https://images.giftcharts.com"
GC_BOT = "@gift_charts_bot"

BRAND = "CɪᴘʜᴇʀX"
BRAND_FULL = "CɪᴘʜᴇʀX Ⲉⲭⲥⳑυⲋⲓⳳⲉ ⲃⲟⲧ"

# Official baseline field on GiftCharts (site default).
GC_FIELD = "gramPrice"

# Collection charts support 7d; model charts do not — we derive 7d from 1m.
INTERVALS = ("24h", "3d", "7d", "1m", "3m", "6m", "1y", "all")
MODEL_NATIVE_TF = {"24h", "3d", "1m", "3m", "6m", "1y", "all"}
# Heatmap UI intervals match gift charts; API maps 7d→1w, all→1y.
# API currency enum is only ``gram`` | ``usd`` (not ton).
HEATMAP_FIELD = "marketCap"
HEATMAP_CURRENCY = "gram"
HEATMAP_LIMIT = 200
HEATMAP_TF_API = {"7d": "1w", "all": "1y"}

AUTH_TTL = 45 * 60
SESSION_TTL = 30 * 60
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=25, connect=10)
HEATMAP_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=90, connect=15)

_AUTH_LOCK = asyncio.Lock()
_AUTH_CACHE: dict[str, Any] = {"token": None, "at": 0.0}
_TG_LOCK = asyncio.Lock()

# token -> {gift, model, model_id, image, owner_id, at}
_SESSIONS: dict[str, dict[str, Any]] = {}
# token -> heatmap session
_HEAT_SESSIONS: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _api_id() -> Optional[int]:
    raw = udB.get_key("api_id")
    try:
        return int(raw) if raw is not None else None
    except Exception:
        return None


def _api_hash() -> Optional[str]:
    raw = udB.get_key("api_hash")
    return str(raw).strip() if raw else None


def _session_str() -> Optional[str]:
    raw = udB.get_key("SESSIONMRKT")
    return str(raw).strip() if raw else None


def _purge_sessions() -> None:
    now = time.monotonic()
    dead = [k for k, v in _SESSIONS.items() if now - v.get("at", 0) > SESSION_TTL]
    for k in dead:
        _SESSIONS.pop(k, None)


def _save_session(payload: dict[str, Any]) -> str:
    _purge_sessions()
    token = secrets.token_urlsafe(6)[:10]
    payload = dict(payload)
    payload["at"] = time.monotonic()
    _SESSIONS[token] = payload
    return token


def _load_session(token: str) -> Optional[dict[str, Any]]:
    _purge_sessions()
    row = _SESSIONS.get(token)
    if not row:
        return None
    row["at"] = time.monotonic()
    return row


def _parse_query(raw: str) -> tuple[str, Optional[str]]:
    text = (raw or "").strip()
    if not text:
        return "", None
    if "," in text:
        left, right = text.split(",", 1)
        gift, model = left.strip(), right.strip()
        return gift, model or None
    return text, None


def _nft_allowed(user_id) -> bool:
    try:
        from .artemis import _nft_user_allowed
        return bool(_nft_user_allowed(user_id))
    except Exception:
        return False


async def _inline_denied(event):
    article = await event.builder.article(
        title="❌ Not authorized",
        description="Purchase subscription from @AssisXBot",
        text=(
            "❌ You are not on the NFT allow-list.\n"
            "Purchase subscription from @AssisXBot"
        ),
    )
    return await event.answer(
        [article],
        cache_time=5,
        switch_pm="Purchase subscription",
        switch_pm_param="start",
    )


async def _resolve_ch_input(raw: str, tg_client=None) -> tuple[str, Optional[str], str]:
    """
    Parse ch query text or NFT link → (gift, model, source).
    source is ``nft`` or ``text``.
    """
    text = (raw or "").strip()
    if not text:
        return "", None, "text"

    try:
        from .artemis import (
            _parse_nft_link,
            _resolve_collection_from_slug,
            _fetch_telegram_nft_attrs,
            _fetch_unique_star_gift_attrs,
            heartless_bot as _cx_bot,
        )
    except Exception:
        return (*_parse_query(text), "text")

    parsed = _parse_nft_link(text)
    if not parsed:
        return (*_parse_query(text), "text")

    slug, short_slug, _number = parsed
    collection, _, _ = _resolve_collection_from_slug(short_slug)
    model = backdrop = None
    # GetUniqueStarGift is user-only — never use the assistant bot.
    for tg in (_cx_bot,):
        if tg is None:
            continue
        try:
            m, b, *_rest = await _fetch_unique_star_gift_attrs(tg, slug)
        except Exception:
            m = b = None
        if m:
            model = m
            backdrop = b
            break
    if not model or not backdrop:
        try:
            html_model, html_back, *_r = await _fetch_telegram_nft_attrs(slug)
            model = model or html_model
            backdrop = backdrop or html_back
        except Exception:
            pass

    # Canonicalize against GiftCharts when possible.
    try:
        gift = await _resolve_gift(collection)
        collection = gift.get("name") or collection
    except Exception:
        pass
    if model:
        try:
            row = await _resolve_model(collection, model)
            model = row.get("name") or model
        except Exception:
            pass
    # backdrop kept for callers that store hub session; charts use model only.
    _ = backdrop
    return collection, model, "nft"



def _norm_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _gift_image_url(image_name: Optional[str]) -> Optional[str]:
    if not image_name:
        return None
    name = str(image_name).lstrip("/")
    if name.startswith("http"):
        return name
    return f"{GC_IMG_CDN}/gifts/{name}"


def _analytics_url(gift: str, model_id: Optional[int] = None) -> str:
    if model_id:
        return f"{GC_SITE}/analytics/gift/{quote(gift)}/models/{model_id}"
    return f"{GC_SITE}/analytics/gift/{quote(gift)}"


def _share_query(gift: str, model: Optional[str] = None) -> str:
    gift = (gift or "").strip()
    model = (model or "").strip() if model else ""
    if gift and model:
        return f"g {gift}, {model}"
    if gift:
        return f"g {gift}"
    return "g "


def _sanitize_chart_points(points: list[dict]) -> list[dict]:
    """Drop null/invalid GiftCharts points (longer TFs can include holes)."""
    out: list[dict] = []
    for p in points or []:
        if not isinstance(p, dict):
            continue
        raw_val = p.get("value")
        if raw_val is None or raw_val == "":
            continue
        raw_ts = p.get("timestamp")
        if raw_ts is None or raw_ts == "":
            continue
        try:
            val = float(raw_val)
            ts = int(raw_ts)
        except Exception:
            continue
        if val != val:  # NaN
            continue
        out.append({"value": val, "timestamp": ts})
    return out


def _pct_change(points: list[dict]) -> Optional[float]:
    clean = _sanitize_chart_points(points)
    if len(clean) < 2:
        return None
    first = float(clean[0]["value"])
    last = float(clean[-1]["value"])
    if first == 0:
        return None
    return ((last - first) / first) * 100.0


def _fmt_price(value: float) -> str:
    if value >= 100:
        return f"{value:,.2f}"
    if value >= 10:
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _fmt_int(value: Any) -> str:
    try:
        return str(int(round(float(value))))
    except Exception:
        return "—"

def _fmt_mcap(value: Any) -> str:
    try:
        num = float(value)
    except Exception:
        return "—"
    abs_n = abs(num)
    if abs_n >= 1_000_000_000:
        text = f"{num / 1_000_000_000:.2f}".rstrip("0").rstrip(".")
        return f"{text}B"
    if abs_n >= 1_000_000:
        text = f"{num / 1_000_000:.2f}".rstrip("0").rstrip(".")
        return f"{text}M"
    if abs_n >= 1_000:
        text = f"{num / 1_000:.2f}".rstrip("0").rstrip(".")
        return f"{text}K"
    return _fmt_int(num)


def _fmt_usd_plain(value: Any) -> str:
    try:
        num = float(value)
    except Exception:
        return "—"
    if abs(num - round(num)) < 1e-9:
        return f"{int(round(num))}$"
    text = f"{num:.2f}".rstrip("0").rstrip(".")
    return f"{text}$"


def _tf_label(tf: str) -> str:
    """Display label: 24H / 3D / 7D / 1M / 1Y / All (API values stay lowercase)."""
    if tf == "all":
        return "All"
    # Heatmap uses 1w; show as 7D to match chart button style.
    if tf == "1w":
        return "7D"
    return "".join(ch.upper() if ch in "dhmyw" else ch for ch in (tf or ""))


def _md_escape(text: Any) -> str:
    value = str(text or "")
    return (
        value.replace("\\", "\\\\")
        .replace("_", "\\_")
        .replace("*", "\\*")
        .replace("`", "\\`")
        .replace("[", "\\[")
    )

# ---------------------------------------------------------------------------
# GiftCharts auth + HTTP
# ---------------------------------------------------------------------------

async def _mint_tma_token(start_param: str = "app") -> str:
    """Request Mini App initData via SESSIONMRKT (same creds as Artemis)."""
    api_id, api_hash, session = _api_id(), _api_hash(), _session_str()
    if not api_id or not api_hash:
        raise ValueError("api_id / api_hash missing from Heartless DB.")
    if not session:
        raise ValueError("SESSIONMRKT is not set in Heartless DB.")

    async with _TG_LOCK:
        client = TelegramClient(StringSession(session), api_id, api_hash)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise ValueError("SESSIONMRKT is not authorized.")
            bot = await client.get_entity(GC_BOT)
            web_view = await client(
                functions.messages.RequestMainWebViewRequest(
                    peer=utils.get_input_peer(bot),
                    bot=utils.get_input_user(bot),
                    start_param=start_param or "app",
                    platform="android",
                )
            )
        finally:
            with contextlib.suppress(Exception):
                await client.disconnect()

    parsed = urlparse(web_view.url)
    auth = parse_qs(parsed.fragment, keep_blank_values=True).get(
        "tgWebAppData", [None]
    )[0]
    if not auth:
        auth = parse_qs(parsed.query, keep_blank_values=True).get(
            "tgWebAppData", [None]
        )[0]
    if not auth:
        raise RuntimeError("GiftCharts webview returned no tgWebAppData.")
    try:
        auth.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise RuntimeError("GiftCharts initData is not latin-1 safe.") from exc
    return auth


async def _get_auth(force: bool = False, *, start_param: str = "app") -> str:
    cache_key = f"token:{start_param or 'app'}"
    at_key = f"at:{start_param or 'app'}"
    async with _AUTH_LOCK:
        now = time.monotonic()
        token = _AUTH_CACHE.get(cache_key)
        if (
            not force
            and token
            and now - float(_AUTH_CACHE.get(at_key) or 0) < AUTH_TTL
        ):
            return token
        # Back-compat: older cache used bare "token"/"at" for app.
        if (
            not force
            and (start_param or "app") == "app"
            and _AUTH_CACHE.get("token")
            and now - float(_AUTH_CACHE.get("at") or 0) < AUTH_TTL
        ):
            return _AUTH_CACHE["token"]
        token = await _mint_tma_token(start_param=start_param or "app")
        _AUTH_CACHE[cache_key] = token
        _AUTH_CACHE[at_key] = now
        if (start_param or "app") == "app":
            _AUTH_CACHE["token"] = token
            _AUTH_CACHE["at"] = now
        return token


async def _gc_get(
    path: str,
    *,
    params: Optional[dict] = None,
    auth: Optional[str] = None,
    expect_json: bool = True,
) -> Any:
    token = auth or await _get_auth()
    headers = {
        "Authorization": f"tma {token}",
        "Accept": "application/json" if expect_json else "*/*",
        "User-Agent": "Heartless-GiftCharts/1.0",
    }
    url = f"{GC_API}{path}"
    async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status == 401:
                # Refresh Mini App token once.
                token = await _get_auth(force=True)
                headers["Authorization"] = f"tma {token}"
                async with session.get(url, headers=headers, params=params) as resp2:
                    if resp2.status >= 400:
                        text = await resp2.text()
                        raise RuntimeError(
                            f"GiftCharts HTTP {resp2.status}: {text[:240]}"
                        )
                    return await resp2.json() if expect_json else await resp2.read()
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"GiftCharts HTTP {resp.status}: {text[:240]}")
            return await resp.json() if expect_json else await resp.read()


# ---------------------------------------------------------------------------
# Resolve gift / model
# ---------------------------------------------------------------------------

async def _gift_detail(gift_name: str) -> dict[str, Any]:
    """Full collection meta (supply / mcap / init price)."""
    payload = await _gc_get(f"/v1/gifts/{quote(gift_name)}")
    data = (payload or {}).get("data")
    return data if isinstance(data, dict) else {}


async def _resolve_gift(name: str) -> dict[str, Any]:
    needle = name.strip()
    if not needle:
        raise ValueError("Collection name is required.")

    # Exact / fuzzy via filter-list search.
    payload = await _gc_get(
        "/v1/gifts/filter-list",
        params={"page": 1, "limit": 30, "search": needle},
    )
    items = list((payload or {}).get("data") or [])
    key = _norm_key(needle)
    exact = next((g for g in items if _norm_key(g.get("name") or "") == key), None)
    if exact:
        return exact
    # Partial contains
    partial = [
        g for g in items
        if key in _norm_key(g.get("name") or "")
        or _norm_key(g.get("name") or "") in key
    ]
    if len(partial) == 1:
        return partial[0]
    if partial:
        # Prefer shortest name distance
        partial.sort(key=lambda g: abs(len(g.get("name") or "") - len(needle)))
        return partial[0]

    # Fallback: full gifts dump (cached lightly via search miss)
    payload = await _gc_get("/v1/gifts")
    items = list((payload or {}).get("data") or [])
    exact = next((g for g in items if _norm_key(g.get("name") or "") == key), None)
    if exact:
        return exact
    partial = [g for g in items if key in _norm_key(g.get("name") or "")]
    if partial:
        partial.sort(key=lambda g: abs(len(g.get("name") or "") - len(needle)))
        return partial[0]
    raise ValueError(f"GiftCharts collection not found: {needle}")

async def _resolve_model(gift_name: str, model_name: str) -> dict[str, Any]:
    needle = model_name.strip()
    payload = await _gc_get(
        "/v1/gifts/models",
        params={
            "giftNames": gift_name,
            "search": needle,
            "limit": 30,
        },
    )
    items = list((payload or {}).get("data") or [])
    # Keep models that belong to this gift when possible.
    scoped = [
        m for m in items
        if _norm_key(m.get("giftName") or "") == _norm_key(gift_name)
    ] or items
    key = _norm_key(needle)
    exact = next((m for m in scoped if _norm_key(m.get("name") or "") == key), None)
    if exact:
        return exact
    partial = [m for m in scoped if key in _norm_key(m.get("name") or "")]
    if partial:
        partial.sort(key=lambda m: abs(len(m.get("name") or "") - len(needle)))
        return partial[0]
    raise ValueError(
        f"GiftCharts model not found: {gift_name}, {needle}"
    )


# ---------------------------------------------------------------------------
# Chart data
# ---------------------------------------------------------------------------

async def _fetch_collection_chart(gift: str, timeframe: str) -> dict[str, Any]:
    return await _gc_get(
        "/v1/charts",
        params={"gift": gift, "timeframe": timeframe, "field": GC_FIELD},
    )


async def _fetch_model_chart(model_id: int, timeframe: str) -> dict[str, Any]:
    # Native model timeframes exclude 7d — derive from 1m.
    if timeframe == "7d":
        raw = await _gc_get(
            "/v1/model-charts",
            params={
                "modelId": int(model_id),
                "timeframe": "1m",
                "field": GC_FIELD,
            },
        )
        points = list((raw or {}).get("data") or [])
        if len(points) > 7:
            points = points[-7:]
        return {
            "modelId": model_id,
            "timeframe": "7d",
            "field": GC_FIELD,
            "data": points,
            "derived_from": "1m",
        }
    if timeframe not in MODEL_NATIVE_TF:
        raise ValueError(f"Unsupported model timeframe: {timeframe}")
    return await _gc_get(
        "/v1/model-charts",
        params={
            "modelId": int(model_id),
            "timeframe": timeframe,
            "field": GC_FIELD,
        },
    )


async def _load_chart_bundle(
    gift_query: str,
    model_query: Optional[str],
    timeframe: str,
) -> dict[str, Any]:
    gift = await _resolve_gift(gift_query)
    gift_name = gift.get("name") or gift_query
    image = gift.get("image")
    detail = await _gift_detail(gift_name)
    if detail.get("image"):
        image = detail.get("image")
    model = None
    model_id = None
    if model_query:
        model = await _resolve_model(gift_name, model_query)
        model_id = int(model["id"])
        chart = await _fetch_model_chart(model_id, timeframe)
        title = f"{gift_name}, {model.get('name')}"
    else:
        chart = await _fetch_collection_chart(gift_name, timeframe)
        title = gift_name

    points = _sanitize_chart_points(list((chart or {}).get("data") or []))
    if not points:
        raise RuntimeError("GiftCharts returned no chart points for this filter.")

    init_supply = detail.get("initSupply")
    total_supply = detail.get("totalSupply")
    upgraded = detail.get("upgradedSupply")
    burned = detail.get("burnedSupply")
    if burned is None and init_supply is not None and total_supply is not None:
        try:
            burned = max(int(init_supply) - int(total_supply), 0)
        except Exception:
            burned = None
    mcap = detail.get("marketCapGram")
    if mcap is None:
        mcap = detail.get("marketCap") or gift.get("marketCap")

    return {
        "gift": gift_name,
        "model": (model or {}).get("name") if model else None,
        "model_id": model_id,
        "image": image,
        "title": title,
        "timeframe": timeframe,
        "field": GC_FIELD,
        "points": points,
        "derived_from": chart.get("derived_from"),
        "market_cap": mcap,
        "init_stars": detail.get("initStarsPrice"),
        "init_usd": detail.get("initUsdPrice"),
        "init_supply": init_supply,
        "current_supply": total_supply,
        "upgraded": upgraded,
        "burned": burned,
    }

# ---------------------------------------------------------------------------
# Baseline chart renderer (GiftCharts-style area baseline)
# ---------------------------------------------------------------------------

def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/system/fonts/Roboto-Bold.ttf" if bold else "/system/fonts/Roboto-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _render_baseline_chart(
    *,
    title: str,
    timeframe: str,
    points: list[dict],
    field: str = GC_FIELD,
) -> bytes:
    """Render an area/baseline chart image from official GiftCharts points."""
    width, height = 1200, 675
    margin_l, margin_r, margin_t, margin_b = 70, 40, 90, 70
    bg = (11, 14, 20)
    panel = (17, 22, 31)
    grid = (35, 42, 55)
    text_main = (235, 240, 250)
    text_muted = (140, 150, 170)
    up = (46, 204, 113)
    down = (231, 76, 60)

    points = _sanitize_chart_points(points)
    if len(points) < 2:
        raise RuntimeError("Not enough chart points to render.")
    values = np.array([float(p["value"]) for p in points], dtype=np.float64)
    times = [int(p["timestamp"]) for p in points]
    first, last = float(values[0]), float(values[-1])
    baseline = first
    change = _pct_change(points)
    bullish = last >= first
    accent = up if bullish else down

    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img, "RGBA")
    draw.rounded_rectangle(
        (24, 24, width - 24, height - 24),
        radius=28,
        fill=panel,
    )

    font_title = _font(36, bold=True)
    font_sub = _font(22)
    font_val = _font(42, bold=True)
    font_axis = _font(16)

    draw.text((56, 44), title, fill=text_main, font=font_title)
    subtitle = f"{BRAND} . {_tf_label(timeframe)} . TON"
    draw.text((56, 90), subtitle, fill=text_muted, font=font_sub)

    price_txt = f"{_fmt_price(last)} TON"
    bbox = draw.textbbox((0, 0), price_txt, font=font_val)
    draw.text((width - 56 - (bbox[2] - bbox[0]), 44), price_txt, fill=accent, font=font_val)
    if change is not None:
        ch = f"{change:+.2f}%"
        bbox2 = draw.textbbox((0, 0), ch, font=font_sub)
        draw.text(
            (width - 56 - (bbox2[2] - bbox2[0]), 96),
            ch,
            fill=accent,
            font=font_sub,
        )

    plot_x0, plot_y0 = margin_l, margin_t + 40
    plot_x1, plot_y1 = width - margin_r, height - margin_b
    plot_w = max(plot_x1 - plot_x0, 1)
    plot_h = max(plot_y1 - plot_y0, 1)

    vmin = float(np.min(values))
    vmax = float(np.max(values))
    pad = (vmax - vmin) * 0.08 if vmax > vmin else max(abs(vmax) * 0.02, 0.01)
    vmin -= pad
    vmax += pad
    if vmax <= vmin:
        vmax = vmin + 1.0

    def xy(i: int, value: float) -> tuple[float, float]:
        x = plot_x0 + (i / max(len(values) - 1, 1)) * plot_w
        y = plot_y1 - ((value - vmin) / (vmax - vmin)) * plot_h
        return x, y

    # Grid
    for g in range(5):
        y = plot_y0 + (g / 4) * plot_h
        draw.line((plot_x0, y, plot_x1, y), fill=grid + (120,), width=1)
        val = vmax - (g / 4) * (vmax - vmin)
        draw.text((18, y - 8), _fmt_price(val), fill=text_muted, font=font_axis)

    # Baseline dashed
    bx, by = xy(0, baseline)
    for x in range(int(plot_x0), int(plot_x1), 14):
        draw.line((x, by, min(x + 7, plot_x1), by), fill=text_muted + (100,), width=1)

    coords = [xy(i, float(values[i])) for i in range(len(values))]
    # Fill to baseline
    fill_pts = list(coords) + [(coords[-1][0], by), (coords[0][0], by)]
    fill_color = accent + (55,)
    draw.polygon(fill_pts, fill=fill_color)
    try:
        draw.line(coords, fill=accent + (255,), width=4, joint="curve")
    except TypeError:
        draw.line(coords, fill=accent + (255,), width=4)

    # End marker
    ex, ey = coords[-1]
    draw.ellipse((ex - 6, ey - 6, ex + 6, ey + 6), fill=accent)

    # Time labels
    if times:
        for idx, label_i in ((0, 0), (len(times) // 2, 1), (len(times) - 1, 2)):
            ts = datetime.fromtimestamp(times[idx], tz=timezone.utc)
            label = ts.strftime("%d %b %H:%M" if timeframe in {"24h", "3d"} else "%d %b")
            x = coords[idx][0]
            bbox = draw.textbbox((0, 0), label, font=font_axis)
            tw = bbox[2] - bbox[0]
            draw.text((x - tw / 2, plot_y1 + 12), label, fill=text_muted, font=font_axis)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    buf.name = "giftcharts.png"
    return buf.getvalue()


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def _back_data(token: str, owner_id: int) -> bytes:
    """Back target: hub if attached, else chart picker/root."""
    sess = _SESSIONS.get(token) or {}
    stage = sess.get("chart_stage") or "root"
    hub_token = sess.get("hub_token")
    hub_owner = sess.get("hub_owner") or owner_id
    if hub_token and stage == "root":
        return f"gu:h:{hub_owner}:{hub_token}".encode()
    return f"gc:b:{owner_id}:{token}".encode()


def _action_row(token: str, owner_id: int, *, show_back: bool = False) -> list:
    sess = _SESSIONS.get(token) or {}
    raw = sess.get("raw") or ""
    gift = sess.get("gift") or sess.get("gift_q") or ""
    model = sess.get("model") or sess.get("model_q")
    if raw:
        share_q = f"g {raw}"
    else:
        share_q = _share_query(gift, model)
    rows = [
        [
            Button.switch_inline("🔎 Search again", query="g ", same_peer=True),
            Button.switch_inline("🔗 Share", query=share_q, same_peer=False),
        ]
    ]
    hub_token = sess.get("hub_token")
    hub_owner = int(sess.get("hub_owner") or owner_id)
    # Refresh only on the rendered chart image — not Collection/Model pickers.
    if hub_token and sess.get("chart_stage") == "chart":
        rows.append(
            [
                Button.inline(
                    "🔄 Refresh",
                    data=f"gr:r:{hub_owner}:{hub_token}".encode(),
                )
            ]
        )
    if show_back:
        rows.append([Button.inline("⬅️ Back", data=_back_data(token, owner_id))])
    return rows


def _picker_buttons(token: str, owner_id: int, *, show_back: bool = False) -> list:
    rows = [
        [
            Button.inline(
                "Collection 📉",
                data=f"gc:m:{owner_id}:{token}:c".encode(),
            ),
            Button.inline(
                "Model 📊",
                data=f"gc:m:{owner_id}:{token}:m".encode(),
            ),
        ]
    ]
    rows.extend(_action_row(token, owner_id, show_back=show_back))
    return rows


def _interval_buttons(
    token: str,
    owner_id: int,
    active: str,
    *,
    show_back: bool = False,
) -> list:
    rows = []
    chunk: list = []
    for tf in INTERVALS:
        mark = "• " if tf == active else ""
        chunk.append(
            Button.inline(
                f"{mark}{_tf_label(tf)}",
                data=f"gc:t:{owner_id}:{token}:{tf}".encode(),
            )
        )
        if len(chunk) == 4:
            rows.append(chunk)
            chunk = []
    if chunk:
        rows.append(chunk)
    rows.extend(_action_row(token, owner_id, show_back=show_back))
    return rows


def _chart_header_lines(sess: dict, *, include_model: bool = True) -> list[str]:
    """Collection/Model headers — CustomMarkdown CE (chart panels use parse_mode md)."""
    gift = sess.get("gift") or sess.get("gift_q") or "?"
    model = sess.get("model") or sess.get("model_q")
    pack = sess.get("emoji_pack") if isinstance(sess.get("emoji_pack"), dict) else {}
    col_e, mod_e = "🎁", "🧩"
    try:
        from plugins.artemis import (  # lazy — artemis imports this module
            _ce_md,
            _lookup_emoji_id,
        )

        col_e = _ce_md(pack.get("collection"), "🎁")
        if model:
            mod_e = _ce_md(
                _lookup_emoji_id(pack.get("models") or {}, model), "🧩"
            )
    except Exception:
        pass
    lines = [f"{col_e} **Collection:** `{_md_escape(gift)}`"]
    if include_model and model:
        lines.append(f"{mod_e} **Model:** `{_md_escape(model)}`")
    return lines


def _picker_text(sess: dict) -> str:
    return "\n".join(_chart_header_lines(sess, include_model=True))


def _intervals_text(sess: dict, mode: str) -> str:
    include_model = mode == "model"
    return "\n".join(_chart_header_lines(sess, include_model=include_model))


def _caption(
    bundle: dict[str, Any],
    *,
    emoji_pack: dict | None = None,
) -> str:
    points = _sanitize_chart_points(bundle.get("points") or [])
    if not points:
        return "📈 **Chart**\n_No chart points._"
    last = float(points[-1]["value"])
    change = _pct_change(points)
    ch = f"{change:+.2f}%" if change is not None else "—"
    stars = bundle.get("init_stars")
    init_usd = bundle.get("init_usd")
    if stars is not None and init_usd is not None:
        init_price = f"{_fmt_int(stars)} stars ({_fmt_usd_plain(init_usd)})"
    elif stars is not None:
        init_price = f"{_fmt_int(stars)} stars"
    else:
        init_price = "—"

    title = _md_escape(bundle["title"])
    tf = _tf_label(bundle["timeframe"])
    price = _md_escape(_fmt_price(last))
    # Collection CE + addemoji names (timeline/price/mrktcap/init/supply/upg/burn)
    col_e = "📈"
    tl_e, pr_e, mc_e = "⏱", "💰", "🧢"
    in_e, su_e, up_e, bu_e = "🌟", "✅", "🆙", "🔥"
    try:
        from plugins.artemis import _ce_md, _emp_ce_md

        pack = emoji_pack if isinstance(emoji_pack, dict) else {}
        col_e = _ce_md(pack.get("collection"), "📈")
        tl_e = _emp_ce_md("timeline", "⏱")
        pr_e = _emp_ce_md("price", "💰")
        mc_e = _emp_ce_md("mrktcap", "🧢")
        in_e = _emp_ce_md("init", "🌟")
        su_e = _emp_ce_md("supply", "✅")
        cur_e = _emp_ce_md("sup", "⏰")
        gram = _emp_ce_md("gram", "TON")
        up_e = _emp_ce_md("upg", "🆙")
        bu_e = _emp_ce_md("burn", "🔥")
    except Exception:
        cur_e, gram = "⏰", "TON"
    return (
        f"{col_e} **{title}**\n"
        f"{tl_e} **{tf} Baseline Chart**\n"
        f"{pr_e} **{price} {gram}**  `({_md_escape(ch)})`\n"
        f"{mc_e} **Market Cap** : `{_md_escape(_fmt_mcap(bundle.get('market_cap')))}`\n"
        f"{in_e} **Initial Price** : `{_md_escape(init_price)}`\n"
        f"{su_e} **Initial Supply** : `{_md_escape(_fmt_int(bundle.get('init_supply')))}`\n"
        f"{cur_e} **Current Supply** : `{_md_escape(_fmt_int(bundle.get('current_supply')))}`\n"
        f"{up_e} **Upgraded** : `{_md_escape(_fmt_int(bundle.get('upgraded')))}`\n"
        f"{bu_e} **Burned** : `{_md_escape(_fmt_int(bundle.get('burned')))}`"
    )


def _is_inline_callback(event) -> bool:
    """True when the callback targets an inline message (no chat entity)."""
    try:
        return isinstance(getattr(event.query, "msg_id", None), InputBotInlineMessageID)
    except Exception:
        return False


def _blank_media_file():
    """1×1 transparent PNG — Telegram cannot turn media messages into text-only."""
    raw = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    bio = io.BytesIO(raw)
    bio.name = "blank.png"
    return bio


async def _edit_panel(event, text: str, buttons: list):
    """Edit callback message back to a text panel (strip chart media if possible)."""
    try:
        await event.edit(
            text,
            buttons=buttons,
            parse_mode=_chart_pm(),
            link_preview=False,
            file=None,
        )
        return
    except MessageNotModifiedError:
        with contextlib.suppress(Exception):
            await event.answer()
        return
    except Exception as exc:
        LOGS.debug("GiftCharts panel text edit failed: %s", exc)

    # Bot API cannot convert a media message into text-only. Replace the chart
    # with a tiny blank image and put the panel text in the caption.
    try:
        await event.edit(
            text,
            file=_blank_media_file(),
            buttons=buttons,
            parse_mode=_chart_pm(),
            link_preview=False,
        )
        return
    except MessageNotModifiedError:
        with contextlib.suppress(Exception):
            await event.answer()
        return
    except Exception as exc:
        LOGS.debug("GiftCharts blank-media edit failed: %s", exc)
        if _is_inline_callback(event):
            with contextlib.suppress(Exception):
                await event.answer(
                    "Couldn't update panel. Search again with g …", alert=True,
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
            parse_mode=_chart_pm(),
            link_preview=False,
        )


async def _deliver_chart(event, bundle: dict[str, Any], *, owner_id: int, token: str):
    sess = _SESSIONS.get(token) or {}
    sess["chart_stage"] = "chart"
    sess["timeframe"] = bundle.get("timeframe") or sess.get("timeframe") or "24h"
    sess["at"] = time.monotonic()
    _SESSIONS[token] = sess
    # Keep hub session view in sync so 🔄 Refresh works from Artemis.
    hub_token = sess.get("hub_token")
    if hub_token:
        try:
            from . import artemis as art
            hub = art._gift_inline_load(hub_token)
            if hub is not None:
                hub["view"] = "chart_out"
                hub["gc_token"] = token
                hub["at"] = time.monotonic()
                art._GIFT_INLINE_SESSIONS[hub_token] = hub
        except Exception:
            pass
    show_back = True  # stage 2+ always has Back
    png = await asyncio.to_thread(
        _render_baseline_chart,
        title=bundle["title"],
        timeframe=bundle["timeframe"],
        points=bundle["points"],
        field=bundle["field"],
    )
    buttons = _interval_buttons(
        token, owner_id, bundle["timeframe"], show_back=show_back,
    )
    pack = sess.get("emoji_pack") if isinstance(sess.get("emoji_pack"), dict) else {}
    if not pack.get("collection"):
        # Prefer hub session pack when chart was opened from inline g
        hub_token = sess.get("hub_token")
        if hub_token:
            try:
                from . import artemis as art

                hub = art._gift_inline_load(hub_token)
                if hub and isinstance(hub.get("emoji_pack"), dict):
                    pack = hub["emoji_pack"]
            except Exception:
                pass
        if not pack.get("collection"):
            try:
                from . import artemis as art

                gift_name = sess.get("gift") or sess.get("gift_q") or bundle.get("title")
                pack = await art._fetch_emoji_pack(str(gift_name or ""))
                sess["emoji_pack"] = pack
                _SESSIONS[token] = sess
            except Exception:
                pack = pack or {}
    caption = _caption(bundle, emoji_pack=pack)
    file = io.BytesIO(png)
    file.name = "giftcharts.png"
    try:
        await event.edit(
            caption,
            file=file,
            buttons=buttons,
            parse_mode=_chart_pm(),
            link_preview=False,
        )
        return
    except MessageNotModifiedError:
        # Same interval re-tapped — content identical; nothing to do.
        with contextlib.suppress(Exception):
            await event.answer()
        return
    except Exception as exc:
        LOGS.debug("GiftCharts chart edit failed: %s", exc)

    # Inline results have no resolvable chat — never send_file there.
    if _is_inline_callback(event):
        with contextlib.suppress(Exception):
            await event.answer(
                "Couldn't update chart. Try another interval or Search again.",
                alert=True,
            )
        return

    try:
        await event.client.send_file(
            event.chat_id,
            file,
            caption=caption,
            buttons=buttons,
            parse_mode=_chart_pm(),
            link_preview=False,
            reply_to=getattr(event, "message_id", None),
        )
        with contextlib.suppress(Exception):
            await event.answer("Chart sent.")
    except Exception as exc:
        LOGS.warning("GiftCharts chart send failed: %s", exc)
        with contextlib.suppress(Exception):
            await event.answer("Couldn't send chart.", alert=True)


def _chart_queries(sess: dict) -> tuple[str, Optional[str]]:
    """Gift/model queries for the active picker mode."""
    gift = sess.get("gift_q") or sess.get("gift") or ""
    model = sess.get("model_q") or sess.get("model")
    mode = sess.get("mode") or ("model" if model else "collection")
    if mode == "model" and model:
        return gift, model
    return gift, None


# ---------------------------------------------------------------------------
# Inline + commands
# ---------------------------------------------------------------------------

_HELP = (
    f"**{BRAND_FULL}**\n\n"
    "`g Liberty Figure`\n"
    "`g Resistance Dog, Cocoon`\n"
    "`g https://t.me/nft/LibertyFigure-214445`\n\n"
    "First pick **Floor Price 📉** or **Gift Chart 📊**.\n"
    "Intervals: **24H · 3D · 7D · 1M · 3M · 6M · 1Y · All**"
)


@in_pattern(r"(?i)^ch(?:\s+([\s\S]+))?$", owner=False)
async def giftcharts_inline(event):
    """Alias: redirect users to unified inline `g`."""
    if not _nft_allowed(event.sender_id):
        return await _inline_denied(event)
    raw = ""
    try:
        raw = (event.pattern_match.group(1) or "").strip()
    except Exception:
        raw = ""
    q = f"g {raw}".rstrip() if raw else "g "
    article = await event.builder.article(
        title=f"📈 {BRAND}",
        description="Use g … (floors + charts)",
        text=(
            f"{_HELP}\n\n"
            "ℹ️ Inline charts/floors are under **`g`** now."
        ),
        buttons=[
            [Button.switch_inline("Open with g", query=q, same_peer=True)]
        ],
    )
    return await event.answer([article], cache_time=5)


@callback(re.compile(rb"^gc:m:(\d+):([A-Za-z0-9_-]{6,16}):([cm])$"))
async def giftcharts_mode_cb(event):
    try:
        owner_id = int(event.data_match.group(1))
        token = event.data_match.group(2).decode()
        mode_flag = event.data_match.group(3).decode()
    except Exception:
        return await event.answer("Invalid chart request.", alert=True)

    if int(event.sender_id) != owner_id:
        return await event.answer("This chart panel belongs to another user.", alert=True)

    sess = _load_session(token)
    if not sess:
        return await event.answer("Session expired — search again with g …", alert=True)

    mode = "model" if mode_flag == "m" else "collection"
    if mode == "model" and not (sess.get("model") or sess.get("model_q")):
        return await event.answer("No model in this query.", alert=True)

    sess["mode"] = mode
    sess["chart_stage"] = "intervals"
    sess["at"] = time.monotonic()
    _SESSIONS[token] = sess
    await event.answer("Collection" if mode == "collection" else "Model")
    await _edit_panel(
        event,
        _intervals_text(sess, mode),
        _interval_buttons(token, owner_id, "", show_back=True),
    )


@callback(re.compile(rb"^gc:b:(\d+):([A-Za-z0-9_-]{6,16})$"))
async def giftcharts_back_cb(event):
    try:
        owner_id = int(event.data_match.group(1))
        token = event.data_match.group(2).decode()
    except Exception:
        return await event.answer("Invalid chart request.", alert=True)

    if int(event.sender_id) != owner_id:
        return await event.answer("This chart panel belongs to another user.", alert=True)

    sess = _load_session(token)
    if not sess:
        return await event.answer("Session expired — search again with g …", alert=True)

    stage = sess.get("chart_stage") or "root"
    await event.answer("Back")

    # Chart image → interval / picker panel (not hub).
    if stage == "chart":
        mode = sess.get("mode") or "collection"
        if sess.get("has_model"):
            sess["chart_stage"] = "intervals"
            _SESSIONS[token] = sess
            return await _edit_panel(
                event,
                _intervals_text(sess, mode),
                _interval_buttons(token, owner_id, "", show_back=True),
            )
        # Collection-only: intervals are the chart root; Back from there → hub.
        sess["chart_stage"] = "root"
        _SESSIONS[token] = sess
        return await _edit_panel(
            event,
            _intervals_text(sess, "collection"),
            _interval_buttons(token, owner_id, "", show_back=True),
        )

    if stage == "intervals" and sess.get("has_model"):
        sess["mode"] = None
        sess["chart_stage"] = "root"
        _SESSIONS[token] = sess
        return await _edit_panel(
            event,
            _picker_text(sess),
            _picker_buttons(token, owner_id, show_back=True),
        )

    # Root chart panel → hub if present
    hub_token = sess.get("hub_token")
    if hub_token:
        from . import artemis as art
        hub = art._gift_inline_load(hub_token)
        if not hub:
            return await event.answer("Hub session expired.", alert=True)
        hub_owner = int(sess.get("hub_owner") or owner_id)
        hub["view"] = "hub"
        art._GIFT_INLINE_SESSIONS[hub_token] = hub
        return await art._gift_inline_edit(
            event,
            art._gift_inline_hub_text(hub),
            art._gift_inline_hub_buttons(
                hub_owner, hub_token, hub.get("raw") or "", hub,
            ),
            parse_mode=_chart_pm(),
        )

    return await event.answer("Nothing to go back to.", alert=True)


@callback(
    re.compile(
        rb"^gc:t:(\d+):([A-Za-z0-9_-]{6,16}):(24h|3d|7d|1m|3m|6m|1y|all)$"
    )
)
async def giftcharts_interval_cb(event):
    try:
        owner_id = int(event.data_match.group(1))
        token = event.data_match.group(2).decode()
        timeframe = event.data_match.group(3).decode()
    except Exception:
        return await event.answer("Invalid chart request.", alert=True)

    if int(event.sender_id) != owner_id:
        return await event.answer("This chart panel belongs to another user.", alert=True)

    sess = _load_session(token)
    if not sess:
        return await event.answer("Session expired — search again with g …", alert=True)

    gift_q, model_q = _chart_queries(sess)
    await event.answer(f"Loading {timeframe}…")
    try:
        bundle = await _load_chart_bundle(gift_q, model_q, timeframe)
    except Exception as exc:
        LOGS.warning("GiftCharts fetch failed: %s", exc)
        return await event.answer(str(exc)[:180], alert=True)

    sess.update(
        {
            "gift": bundle["gift"],
            "model": bundle.get("model") or sess.get("model") or sess.get("model_q"),
            "model_id": bundle.get("model_id"),
            "image": bundle.get("image"),
            "chart_stage": "chart",
            "at": time.monotonic(),
        }
    )
    _SESSIONS[token] = sess
    await _deliver_chart(event, bundle, owner_id=owner_id, token=token)


@heartless_cmd(owner_only=True, pattern=r"ch(?:\s+([\s\S]+))?$")
async def giftcharts_cmd(event):
    raw = (event.pattern_match.group(1) or "").strip()
    if not raw:
        return await event.eor(
            "❌ <b>Usage</b>\n"
            f"<code>.ch Collection</code>\n"
            f"<code>.ch Collection, Model</code>\n"
            f"<code>.ch https://t.me/nft/Name-123</code>\n\n"
            "Or inline: <code>@{} ch …</code>".format(
                getattr(getattr(asst, "me", None), "username", "AssisXBot")
            ),
            parse_mode="html",
        )

    status = await event.eor("<b>Fetching GiftCharts…</b>", parse_mode="html")
    owner_id = int(event.sender_id)
    try:
        gift_q, model_q, _source = await _resolve_ch_input(
            raw, tg_client=event.client,
        )
        if not gift_q:
            return await status.edit(
                "❌ Could not resolve collection from query.",
                parse_mode="html",
            )
        token = _save_session(
            {
                "gift_q": gift_q,
                "model_q": model_q,
                "owner_id": owner_id,
                "gift": gift_q,
                "model": model_q,
                "model_id": None,
                "has_model": bool(model_q),
                "mode": "model" if model_q else "collection",
            }
        )
        bundle = await _load_chart_bundle(gift_q, model_q, "24h")
        sess = _load_session(token) or {}
        sess.update(
            {
                "gift": bundle["gift"],
                "model": bundle.get("model") or model_q,
                "model_id": bundle.get("model_id"),
                "image": bundle.get("image"),
                "gift_q": gift_q,
                "model_q": model_q,
                "owner_id": owner_id,
                "has_model": bool(model_q),
                "mode": "model" if model_q else "collection",
                "chart_stage": "chart",
                "at": time.monotonic(),
            }
        )
        _SESSIONS[token] = sess

        png = await asyncio.to_thread(
            _render_baseline_chart,
            title=bundle["title"],
            timeframe=bundle["timeframe"],
            points=bundle["points"],
            field=bundle["field"],
        )
        file = io.BytesIO(png)
        file.name = "giftcharts.png"
        await status.delete()
        pack = sess.get("emoji_pack") if isinstance(sess.get("emoji_pack"), dict) else {}
        if not pack.get("collection"):
            try:
                from . import artemis as art

                pack = await art._fetch_emoji_pack(str(gift_q or ""))
                sess["emoji_pack"] = pack
                _SESSIONS[token] = sess
            except Exception:
                pack = {}
        await event.client.send_file(
            event.chat_id,
            file,
            caption=_caption(bundle, emoji_pack=pack),
            buttons=_interval_buttons(
                token, owner_id, "24h", show_back=bool(model_q),
            ),
            parse_mode=_chart_pm(),
            link_preview=False,
            reply_to=event.reply_to_msg_id,
        )
    except Exception as exc:
        LOGS.exception("GiftCharts .ch failed: %s", exc)
        return await status.edit(
            f"❌ <b>GiftCharts failed.</b>\n\n<code>{html.escape(str(exc))}</code>",
            parse_mode="html",
        )


# ---------------------------------------------------------------------------
# NFT Heatmap (inline ``a``) — GiftCharts /v1/heatmap/image
# ---------------------------------------------------------------------------

def _purge_heat_sessions() -> None:
    now = time.monotonic()
    dead = [
        k for k, v in _HEAT_SESSIONS.items()
        if now - float(v.get("at") or 0) > SESSION_TTL
    ]
    for k in dead:
        _HEAT_SESSIONS.pop(k, None)


def _heat_session_new(owner_id: int, timeframe: str = "24h") -> str:
    _purge_heat_sessions()
    token = secrets.token_urlsafe(9)
    tf = timeframe if timeframe in INTERVALS else "24h"
    _HEAT_SESSIONS[token] = {
        "owner_id": int(owner_id),
        "timeframe": tf,
        "field": HEATMAP_FIELD,
        "currency": HEATMAP_CURRENCY,
        "at": time.monotonic(),
    }
    return token


def _heat_session_get(token: str) -> Optional[dict]:
    _purge_heat_sessions()
    row = _HEAT_SESSIONS.get(token)
    if not row:
        return None
    row["at"] = time.monotonic()
    return row


def _heatmap_api_tf(timeframe: str) -> str:
    """Map chart-style interval → GiftCharts heatmap timeRange."""
    tf = timeframe if timeframe in INTERVALS else "24h"
    return HEATMAP_TF_API.get(tf, tf)


def _heatmap_params(timeframe: str) -> dict[str, Any]:
    return {
        "field": HEATMAP_FIELD,
        "currency": HEATMAP_CURRENCY,  # gram | usd only
        "timeRange": _heatmap_api_tf(timeframe),
        "limit": HEATMAP_LIMIT,
        "colorMode": "default",
        "shape": "default",
    }


async def _fetch_heatmap_image(timeframe: str = "24h") -> bytes:
    """Download rendered heatmap PNG from GiftCharts (startapp=heatmap)."""
    params = _heatmap_params(timeframe)
    token = await _get_auth(start_param="heatmap")
    headers = {
        "Authorization": f"tma {token}",
        "Accept": "image/png,image/*,*/*",
        "User-Agent": "Heartless-GiftCharts/1.0",
    }
    url = f"{GC_API}/v1/heatmap/image"
    async with aiohttp.ClientSession(timeout=HEATMAP_HTTP_TIMEOUT) as session:
        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status == 401:
                token = await _get_auth(force=True, start_param="heatmap")
                headers["Authorization"] = f"tma {token}"
                async with session.get(url, headers=headers, params=params) as resp2:
                    if resp2.status >= 400:
                        text = await resp2.text()
                        raise RuntimeError(
                            f"Heatmap HTTP {resp2.status}: {text[:240]}"
                        )
                    data = await resp2.read()
            elif resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"Heatmap HTTP {resp.status}: {text[:240]}")
            else:
                data = await resp.read()
    if not data or len(data) < 100:
        raise RuntimeError("Heatmap image was empty.")
    return data


def _heatmap_chooser_text() -> str:
    return "🔥 **NFT Heatmap**\n⏩ **Choose Timeline**"


def _heatmap_caption(timeframe: str) -> str:
    tf = _tf_label(timeframe)
    return f"🔥 **NFT Heatmap**\n⏱ **{tf}** · Market Cap"


def _heatmap_buttons(
    token: str,
    owner_id: int,
    active: Optional[str] = None,
) -> list:
    """Chart-style interval rows + Search again / Share only."""
    rows: list = []
    chunk: list = []
    for tf in INTERVALS:
        mark = "• " if active and tf == active else ""
        chunk.append(
            Button.inline(
                f"{mark}{_tf_label(tf)}",
                data=f"gh:t:{owner_id}:{token}:{tf}".encode(),
            )
        )
        if len(chunk) == 4:
            rows.append(chunk)
            chunk = []
    if chunk:
        rows.append(chunk)
    rows.append(
        [
            Button.switch_inline("🔎 Search again", query="a", same_peer=True),
            Button.switch_inline("🔗 Share", query="a", same_peer=False),
        ]
    )
    return rows


async def _deliver_heatmap(
    event,
    *,
    owner_id: int,
    token: str,
    timeframe: str,
    png: bytes,
):
    sess = _heat_session_get(token) or {}
    sess["timeframe"] = timeframe
    sess["owner_id"] = int(owner_id)
    sess["at"] = time.monotonic()
    _HEAT_SESSIONS[token] = sess
    caption = _heatmap_caption(timeframe)
    buttons = _heatmap_buttons(token, owner_id, timeframe)
    file = io.BytesIO(png)
    file.name = "heatmap.png"
    try:
        await event.edit(
            caption,
            file=file,
            buttons=buttons,
            parse_mode=_chart_pm(),
            link_preview=False,
        )
        return
    except MessageNotModifiedError:
        with contextlib.suppress(Exception):
            await event.answer()
        return
    except Exception as exc:
        LOGS.debug("Heatmap edit failed: %s", exc)
    if _is_inline_callback(event):
        with contextlib.suppress(Exception):
            await event.answer(
                "Couldn't update heatmap. Search again with a.",
                alert=True,
            )
        return
    try:
        await event.client.send_file(
            event.chat_id,
            file,
            caption=caption,
            buttons=buttons,
            parse_mode=_chart_pm(),
            link_preview=False,
            reply_to=getattr(event, "message_id", None),
        )
    except Exception as exc:
        LOGS.warning("Heatmap send failed: %s", exc)
        with contextlib.suppress(Exception):
            await event.answer("Couldn't send heatmap.", alert=True)


def _heatmap_inline_media() -> dict:
    """Inline switch thumb for ``@AssisXBot a`` (thumb+content like urltools)."""
    try:
        from plugins.artemis import _inline_article_media

        return _inline_article_media(
            "https://cdn.dbimg.app/pyQWD5gj.jpg", mime="image/jpeg",
        )
    except Exception:
        try:
            from telethon.tl.types import InputWebDocument

            doc = InputWebDocument(
                "https://cdn.dbimg.app/pyQWD5gj.jpg", 0, "image/jpeg", [],
            )
            return {"thumb": doc, "content": doc}
        except Exception:
            return {}


@in_pattern(r"(?i)^a\s*$", owner=False)
async def giftcharts_heatmap_inline(event):
    """Inline `a` (no args) → timeline chooser panel (no image yet)."""
    if not _nft_allowed(event.sender_id):
        return await _inline_denied(event)

    owner_id = int(event.sender_id)
    token = _heat_session_new(owner_id, "24h")
    kwargs = dict(
        title="🔥 NFT Heatmap",
        description="@AssisXBot a",
        text=_heatmap_chooser_text(),
        buttons=_heatmap_buttons(token, owner_id, active=None),
        **_heatmap_inline_media(),
    )
    article = await event.builder.article(**kwargs)
    try:
        return await event.answer([article], cache_time=5)
    except Exception:
        return


@in_pattern(r"(?i)^a\s+\S", owner=False)
async def giftcharts_heatmap_inline_noargs(event):
    """Reject `a …` args — heatmap is chooser-only."""
    if not _nft_allowed(event.sender_id):
        return await _inline_denied(event)
    kwargs = dict(
        title="🔥 NFT Heatmap",
        description="No args — type just a",
        text=(
            "**NFT Heatmap Command**\n\n"
            "`@AssisXBot a`\n\n"
            "Then pick a button"
        ),
        **_heatmap_inline_media(),
    )
    article = await event.builder.article(**kwargs)
    try:
        return await event.answer([article], cache_time=10)
    except Exception:
        return


@callback(re.compile(rb"^gh:t:(\d+):([A-Za-z0-9_-]{6,16}):([0-9a-z]+)$"))
async def giftcharts_heatmap_tf_cb(event):
    async def _ack(text: str = None, *, alert: bool = False):
        with contextlib.suppress(Exception):
            if text is None:
                await event.answer()
            else:
                await event.answer(text, alert=alert)

    try:
        owner_id = int(event.data_match.group(1))
        token = event.data_match.group(2).decode()
        timeframe = event.data_match.group(3).decode()
    except Exception:
        return await _ack("Invalid request.", alert=True)
    if int(event.sender_id) != owner_id:
        return await _ack("This panel belongs to another user.", alert=True)
    if timeframe not in INTERVALS:
        return await _ack("Unknown interval.", alert=True)
    sess = _heat_session_get(token)
    if not sess:
        return await _ack("Session expired — search again with a.", alert=True)
    # Ack immediately so Telegram doesn't expire the query id.
    await _ack(f"Loading {_tf_label(timeframe)}…")
    try:
        png = await _fetch_heatmap_image(timeframe)
    except Exception as exc:
        LOGS.warning("Heatmap tf fetch failed: %s", exc)
        return await _ack(str(exc)[:160], alert=True)
    return await _deliver_heatmap(
        event, owner_id=owner_id, token=token, timeframe=timeframe, png=png,
    )

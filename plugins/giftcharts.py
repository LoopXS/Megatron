"""
✘ Commands Available -

• Inline: `@assistant ch Collection`
   GiftCharts collection baseline chart with 24h / 3d / 7d / 1m switches.

• Inline: `@assistant ch Collection, Model`
   GiftCharts model baseline chart (same interval switches).

• `{i}ch Collection[, Model]`
   Same as inline, sent directly in chat.

Uses DB `api_id` / `api_hash` / `SESSIONMRKT` (same as Artemis) to mint a
GiftCharts Mini App token. Chart values come from GiftCharts
`/v1/charts` and `/v1/model-charts` (gramPrice baseline) — not MRKT floors.
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
from urllib.parse import quote, urlencode, urlparse, parse_qs

import aiohttp
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from telethon import Button, TelegramClient, functions, utils
from telethon.sessions import StringSession

from . import LOGS, asst, callback, heartless_cmd, in_pattern, udB

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GC_API = "https://api.giftcharts.com/api"
GC_SITE = "https://giftcharts.com"
GC_IMG_CDN = "https://images.giftcharts.com"
GC_BOT = "@gift_charts_bot"

# Official baseline field on GiftCharts (site default).
GC_FIELD = "gramPrice"

# Collection charts support 7d; model charts do not — we derive 7d from 1m.
INTERVALS = ("24h", "3d", "7d", "1m")
MODEL_NATIVE_TF = {"24h", "3d", "1m", "3m", "6m", "1y", "all"}

AUTH_TTL = 45 * 60
SESSION_TTL = 30 * 60
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=25, connect=10)

_AUTH_LOCK = asyncio.Lock()
_AUTH_CACHE: dict[str, Any] = {"token": None, "at": 0.0}
_TG_LOCK = asyncio.Lock()

# token -> {gift, model, model_id, image, owner_id, at}
_SESSIONS: dict[str, dict[str, Any]] = {}


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


def _share_url(gift: str, model_id: Optional[int], timeframe: str) -> str:
    page = _analytics_url(gift, model_id)
    text = f"{gift} • {timeframe} baseline (GiftCharts)"
    return "https://t.me/share/url?" + urlencode({"url": page, "text": text})


def _pct_change(points: list[dict]) -> Optional[float]:
    if len(points) < 2:
        return None
    first = float(points[0]["value"])
    last = float(points[-1]["value"])
    if first == 0:
        return None
    return ((last - first) / first) * 100.0


def _fmt_price(value: float) -> str:
    if value >= 100:
        return f"{value:,.2f}"
    if value >= 10:
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return f"{value:.4f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# GiftCharts auth + HTTP
# ---------------------------------------------------------------------------

async def _mint_tma_token() -> str:
    """Request Mini App initData via SESSIONMRKT (same creds as Artemis)."""
    api_id, api_hash, session = _api_id(), _api_hash(), _session_str()
    if not api_id or not api_hash:
        raise ValueError("api_id / api_hash missing from DB.")
    if not session:
        raise ValueError("SESSIONMRKT is not set in DB.")

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
                    start_param="app",
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


async def _get_auth(force: bool = False) -> str:
    async with _AUTH_LOCK:
        now = time.monotonic()
        token = _AUTH_CACHE.get("token")
        if (
            not force
            and token
            and now - float(_AUTH_CACHE.get("at") or 0) < AUTH_TTL
        ):
            return token
        token = await _mint_tma_token()
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

    points = list((chart or {}).get("data") or [])
    if not points:
        raise RuntimeError("GiftCharts returned no chart points for this filter.")
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
    subtitle = f"GiftCharts baseline • {timeframe} • {field}"
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

    draw.text(
        (56, height - 48),
        "Source: api.giftcharts.com  •  Heartless",
        fill=text_muted,
        font=font_axis,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    buf.name = "giftcharts.png"
    return buf.getvalue()


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def _interval_buttons(token: str, owner_id: int, active: str) -> list:
    row = []
    for tf in INTERVALS:
        mark = "• " if tf == active else ""
        row.append(
            Button.inline(
                f"{mark}{tf}",
                data=f"gc:t:{owner_id}:{token}:{tf}".encode(),
            )
        )
    return [
        row,
        [
            Button.switch_inline(
                "🔎 Search again",
                query="ch ",
                same_peer=True,
            ),
            Button.url(
                "🔗 Share",
                _share_url(
                    _SESSIONS.get(token, {}).get("gift") or "Gift",
                    _SESSIONS.get(token, {}).get("model_id"),
                    active,
                ),
            ),
        ],
    ]


def _caption(bundle: dict[str, Any]) -> str:
    points = bundle["points"]
    last = float(points[-1]["value"])
    change = _pct_change(points)
    ch = f"{change:+.2f}%" if change is not None else "—"
    derived = bundle.get("derived_from")
    note = ""
    if derived:
        note = (
            f"\nℹ️ Model charts have no native <code>7d</code> on GiftCharts; "
            f"showing last 7 points from <code>{html.escape(derived)}</code>."
        )
    return (
        f"📈 <b>{html.escape(bundle['title'])}</b>\n"
        f"⏱ <b>{html.escape(bundle['timeframe'])}</b> · "
        f"<code>{html.escape(bundle['field'])}</code>\n"
        f"💰 <b>{html.escape(_fmt_price(last))} TON</b>  ({html.escape(ch)})\n"
        f"🌐 <a href=\"{html.escape(_analytics_url(bundle['gift'], bundle.get('model_id')))}\">"
        f"Open on GiftCharts</a>"
        f"{note}"
    )


async def _deliver_chart(event, bundle: dict[str, Any], *, owner_id: int, token: str):
    png = await asyncio.to_thread(
        _render_baseline_chart,
        title=bundle["title"],
        timeframe=bundle["timeframe"],
        points=bundle["points"],
        field=bundle["field"],
    )
    buttons = _interval_buttons(token, owner_id, bundle["timeframe"])
    caption = _caption(bundle)
    file = io.BytesIO(png)
    file.name = "giftcharts.png"
    try:
        await event.edit(
            caption,
            file=file,
            buttons=buttons,
            parse_mode="html",
            link_preview=False,
        )
    except Exception:
        # Fallback: send as a new message in the chat.
        chat = event.chat_id
        await event.client.send_file(
            chat,
            file,
            caption=caption,
            buttons=buttons,
            parse_mode="html",
            link_preview=False,
            reply_to=getattr(event, "message_id", None),
        )
        with contextlib.suppress(Exception):
            await event.answer("Chart sent.")


# ---------------------------------------------------------------------------
# Inline + commands
# ---------------------------------------------------------------------------

_HELP = (
    "**GiftCharts**\n\n"
    "`ch Liberty Figure`\n"
    "`ch Liberty Figure, Fire Opal`\n\n"
    "Intervals: **24h · 3d · 7d · 1m**\n"
    "Baseline field: `gramPrice` (official GiftCharts)."
)


@in_pattern(r"(?i)^ch(?:\s+([\s\S]+))?$", owner=True)
async def giftcharts_inline(event):
    raw = ""
    try:
        raw = (event.pattern_match.group(1) or "").strip()
    except Exception:
        raw = ""

    if not raw:
        article = await event.builder.article(
            title="📈 GiftCharts",
            description="ch Collection[, Model]",
            text=_HELP,
            buttons=[
                [
                    Button.switch_inline(
                        "Try Liberty Figure",
                        query="ch Liberty Figure",
                        same_peer=True,
                    )
                ]
            ],
        )
        return await event.answer([article], cache_time=5)

    gift_q, model_q = _parse_query(raw)
    owner_id = int(event.sender_id)
    token = _save_session(
        {
            "gift_q": gift_q,
            "model_q": model_q,
            "owner_id": owner_id,
            "gift": gift_q,
            "model": model_q,
            "model_id": None,
        }
    )

    title = gift_q if not model_q else f"{gift_q}, {model_q}"
    text = (
        f"📈 **{title}**\n\n"
        "Pick a GiftCharts baseline interval:"
    )
    buttons = [
        [
            Button.inline(tf, data=f"gc:t:{owner_id}:{token}:{tf}".encode())
            for tf in INTERVALS
        ],
        [
            Button.switch_inline(
                "🔎 Search again",
                query="ch ",
                same_peer=True,
            )
        ],
    ]
    article = await event.builder.article(
        title=f"📈 {title}",
        description="24h · 3d · 7d · 1m baseline charts",
        text=text,
        buttons=buttons,
    )
    return await event.answer([article], cache_time=0)


@callback(re.compile(rb"^gc:t:(\d+):([A-Za-z0-9_-]{6,16}):(24h|3d|7d|1m)$"))
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
        return await event.answer("Session expired — search again with ch …", alert=True)

    await event.answer(f"Loading {timeframe}…")
    try:
        bundle = await _load_chart_bundle(
            sess.get("gift_q") or sess.get("gift") or "",
            sess.get("model_q") or sess.get("model"),
            timeframe,
        )
    except Exception as exc:
        LOGS.warning("GiftCharts fetch failed: %s", exc)
        return await event.answer(str(exc)[:180], alert=True)

    # Refresh session with resolved names for share URL.
    sess.update(
        {
            "gift": bundle["gift"],
            "model": bundle.get("model"),
            "model_id": bundle.get("model_id"),
            "image": bundle.get("image"),
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
            f"<code>.ch Collection, Model</code>\n\n"
            "Or inline: <code>@{} ch …</code>".format(
                getattr(getattr(asst, "me", None), "username", "AssisXBot")
            ),
            parse_mode="html",
        )

    gift_q, model_q = _parse_query(raw)
    status = await event.eor("<b>Fetching GiftCharts…</b>", parse_mode="html")
    owner_id = int(event.sender_id)
    token = _save_session(
        {
            "gift_q": gift_q,
            "model_q": model_q,
            "owner_id": owner_id,
            "gift": gift_q,
            "model": model_q,
            "model_id": None,
        }
    )
    try:
        bundle = await _load_chart_bundle(gift_q, model_q, "24h")
        sess = _load_session(token) or {}
        sess.update(
            {
                "gift": bundle["gift"],
                "model": bundle.get("model"),
                "model_id": bundle.get("model_id"),
                "image": bundle.get("image"),
                "gift_q": gift_q,
                "model_q": model_q,
                "owner_id": owner_id,
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
        await event.client.send_file(
            event.chat_id,
            file,
            caption=_caption(bundle),
            buttons=_interval_buttons(token, owner_id, "24h"),
            parse_mode="html",
            link_preview=False,
            reply_to=event.reply_to_msg_id,
        )
    except Exception as exc:
        LOGS.exception("GiftCharts .ch failed: %s", exc)
        return await status.edit(
            f"❌ <b>GiftCharts failed.</b>\n\n<code>{html.escape(str(exc))}</code>",
            parse_mode="html",
        )

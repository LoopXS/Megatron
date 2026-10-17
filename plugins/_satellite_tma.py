"""Shared Gift Satellite Mini App client (TMA initData).

Used by ``plugins.artemis`` (gift / inline g floors, sales, monochrome).
Auth via Telegram WebView initData — not the rate-limited Token API.

Credentials match Artemis: Heartless DB ``api_id`` / ``api_hash`` / ``SESSIONMRKT``.
"""

from __future__ import annotations

import asyncio
import contextlib
import html
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import parse_qs, quote, urlparse
from zoneinfo import ZoneInfo

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

import aiohttp
from telethon import TelegramClient, functions, utils
from telethon.sessions import StringSession

from . import LOGS, udB

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SAT_API = "https://gift-satellite.dev/api"
SAT_BOT = "gift_satellite_bot"
SAT_WEBAPP = "https://gift-satellite.dev/"

# (search_path, display_label, history_markets_key)
# Search uses `tg`; history sales filter uses `telegram`.
SAT_MARKETS = (
    ("portals", "Portal", "portals"),
    ("tonnel", "Tonnel", "tonnel"),
    ("tg", "Telegram", "telegram"),
    ("mrkt", "MRKT", "mrkt"),
    ("getgems", "GetGems", "getgems"),
)

AUTH_TTL = 45 * 60
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=12)
SALES_PER_MARKET = 4
# Satellite history API rejects pageSize > 20 and rate-limits aggressively.
HISTORY_PAGE_SIZE = 20
HISTORY_MIN_INTERVAL = 1.15

_AUTH_LOCK = asyncio.Lock()
_TG_LOCK = asyncio.Lock()
_HISTORY_LOCK = asyncio.Lock()
_HISTORY_NEXT_AT = 0.0
_AUTH_CACHE: dict[str, Any] = {"token": None, "at": 0.0}
_COLLECTIONS_CACHE: dict[str, Any] = {"at": 0.0, "names": []}


# ---------------------------------------------------------------------------
# Creds / helpers  (same DB keys as Artemis / GiftCharts)
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


def _norm(value: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=False)


def _fmt_ton(value: Any) -> str:
    try:
        amount = float(value)
    except Exception:
        return "—"
    if amount >= 100:
        text = f"{amount:,.2f}"
    elif amount >= 10:
        text = f"{amount:.2f}"
    elif amount >= 1:
        text = f"{amount:.3f}".rstrip("0").rstrip(".")
        return text or "0"
    else:
        text = f"{amount:.4f}".rstrip("0").rstrip(".")
        return text or "0"
    # 867.00 → 867 (only exact .00)
    if text.endswith(".00"):
        return text[:-3]
    return text


def _parse_query(raw: str) -> tuple[str, Optional[str], Optional[str]]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty")
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) == 1:
        return parts[0], None, None
    if len(parts) == 2:
        return parts[0], parts[1], None
    if len(parts) >= 3:
        back = parts[2]
        if back.lower() in ("none", "null", "*", "-", "any"):
            back = None
        return parts[0], parts[1], back
    raise ValueError("bad_format")


def _is_premarket(item: dict) -> bool:
    """Timer-icon / locked listings are premarket — exclude from floors."""
    if item.get("isLocked") is True:
        return True
    if item.get("premarket") is True:
        return True
    return False


def _item_price(item: dict) -> Optional[float]:
    for key in ("normalizedPrice", "price", "originalPrice"):
        raw = item.get(key)
        if raw is None or raw == "":
            continue
        try:
            val = float(raw)
        except Exception:
            continue
        # nanoTON-style integers from some markets
        if val > 1_000_000:
            val = val / 1_000_000_000.0
        if val > 0:
            return val
    return None


def _match_attr(have: Optional[str], want: Optional[str]) -> bool:
    if not want:
        return True
    return _norm(have) == _norm(want) or _norm(want) in _norm(have)


# ---------------------------------------------------------------------------
# Mini App auth (same pattern as GiftCharts)
# ---------------------------------------------------------------------------

async def _mint_tma_token() -> str:
    """Request Mini App initData via SESSIONMRKT (same creds as Artemis)."""
    api_id, api_hash, session = _api_id(), _api_hash(), _session_str()
    if not api_id or not api_hash:
        raise ValueError("api_id / api_hash missing from Heartless DB.")
    if not session:
        raise ValueError("SESSIONMRKT is not set in Heartless DB.")

    async with _TG_LOCK:
        client = TelegramClient(
            StringSession(session),
            api_id,
            api_hash,
            connection_retries=3,
            retry_delay=1,
            timeout=20,
        )
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise ValueError("Satellite session is not authorized.")
            bot = await client.get_entity(SAT_BOT)
            try:
                web_view = await client(
                    functions.messages.RequestMainWebViewRequest(
                        peer=utils.get_input_peer(bot),
                        bot=utils.get_input_user(bot),
                        platform="android",
                    )
                )
            except Exception:
                web_view = await client(
                    functions.messages.RequestWebViewRequest(
                        peer=utils.get_input_peer(bot),
                        bot=utils.get_input_user(bot),
                        platform="android",
                        url=SAT_WEBAPP,
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
        raise RuntimeError("Gift Satellite webview returned no tgWebAppData.")
    try:
        auth.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise RuntimeError("Gift Satellite initData is not latin-1 safe.") from exc
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


def _sat_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": token,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Heartless-Satellite/1.0",
    }


async def _sat_request(
    method: str,
    path: str,
    *,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
    auth: Optional[str] = None,
    retries: int = 4,
) -> Any:
    """
    Mini App HTTP call.

    Authorization is the raw Telegram initData string (not `tma` / `Token`).
    Retries on 429 (Satellite history is ~1 req/s).
    """
    token = auth or await _get_auth()
    url = f"{SAT_API}{path}"
    last_err = None
    async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
        for attempt in range(max(1, retries)):
            headers = _sat_headers(token)
            async with session.request(
                method.upper(),
                url,
                headers=headers,
                params=params,
                json=json_body,
            ) as resp:
                if resp.status == 401 and attempt == 0:
                    token = await _get_auth(force=True)
                    continue
                if resp.status == 429:
                    wait = 1.2 + attempt * 0.4
                    LOGS.info("Satellite 429 on %s — retry in %.1fs", path, wait)
                    await asyncio.sleep(wait)
                    last_err = RuntimeError("Satellite rate limited (429)")
                    continue
                if resp.status >= 400:
                    text = await resp.text()
                    raise RuntimeError(
                        f"Satellite HTTP {resp.status}: {text[:240]}"
                    )
                return await resp.json(content_type=None)
    if last_err:
        raise last_err
    raise RuntimeError("Satellite request failed")


async def _sat_get(
    path: str,
    *,
    params: Optional[dict] = None,
    auth: Optional[str] = None,
) -> Any:
    return await _sat_request("GET", path, params=params, auth=auth)


async def _sat_post(
    path: str,
    body: dict,
    *,
    auth: Optional[str] = None,
) -> Any:
    return await _sat_request("POST", path, json_body=body, auth=auth)


def _as_list(payload: Any) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "content", "items", "results"):
            val = payload.get(key)
            if isinstance(val, list):
                return val
            if isinstance(val, dict) and isinstance(val.get("content"), list):
                return val["content"]
    return []


# ---------------------------------------------------------------------------
# Resolve + floors + sales
# ---------------------------------------------------------------------------

async def _load_collections() -> list[str]:
    now = time.monotonic()
    if (
        _COLLECTIONS_CACHE.get("names")
        and now - float(_COLLECTIONS_CACHE.get("at") or 0) < 3600
    ):
        return list(_COLLECTIONS_CACHE["names"])
    try:
        payload = await _sat_get("/gift/collections", params={"premarket": "0"})
        names = [
            str(row.get("name") or "").strip()
            for row in _as_list(payload)
            if isinstance(row, dict) and row.get("name")
        ]
        _COLLECTIONS_CACHE["names"] = names
        _COLLECTIONS_CACHE["at"] = now
        return names
    except Exception as e:
        LOGS.warning("Satellite collections failed: %s", e)
        return list(_COLLECTIONS_CACHE.get("names") or [])


async def _resolve_collection(name: str) -> str:
    needle = (name or "").strip()
    if not needle:
        raise ValueError("Collection is required.")
    names = await _load_collections()
    nkey = _norm(needle)
    for cand in names:
        if _norm(cand) == nkey:
            return cand
    # fuzzy contains
    hits = [c for c in names if nkey and nkey in _norm(c)]
    if len(hits) == 1:
        return hits[0]
    # title-ish fallback
    for cand in names:
        if _norm(cand).startswith(nkey) or nkey.startswith(_norm(cand)):
            return cand
    return needle


async def _resolve_model_backdrop(
    collection: str,
    model: Optional[str],
    backdrop: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Best-effort canonicalize model/backdrop via /gift/collection meta."""
    if not model and not backdrop:
        return model, backdrop
    try:
        payload = await _sat_get(f"/gift/collection/{quote(collection, safe='')}")
    except Exception:
        return model, backdrop
    if not isinstance(payload, dict):
        return model, backdrop

    if model:
        models = payload.get("models") or []
        if isinstance(models, list):
            nkey = _norm(model)
            for row in models:
                name = (
                    row.get("name")
                    if isinstance(row, dict)
                    else (row if isinstance(row, str) else None)
                )
                if name and _norm(name) == nkey:
                    model = str(name)
                    break

    if backdrop:
        backs = payload.get("backdrops") or []
        if isinstance(backs, list):
            nkey = _norm(backdrop)
            for row in backs:
                name = (
                    row.get("name")
                    if isinstance(row, dict)
                    else (row if isinstance(row, str) else None)
                )
                if name and _norm(name) == nkey:
                    backdrop = str(name)
                    break
    return model, backdrop


async def _search_market(
    market: str,
    collection: str,
    model: Optional[str] = None,
    backdrop: Optional[str] = None,
    *,
    auth: Optional[str] = None,
) -> list[dict]:
    params: dict[str, str] = {}
    if model:
        params["models"] = model
    if backdrop:
        params["backdrops"] = backdrop
    path = f"/search/{market}/{quote(collection, safe='')}"
    try:
        payload = await _sat_get(path, params=params or None, auth=auth)
    except Exception as e:
        LOGS.info("Satellite search %s/%s failed: %s", market, collection, e)
        return []
    return [x for x in _as_list(payload) if isinstance(x, dict)]


async def _floor_for_market(
    market: str,
    collection: str,
    model: Optional[str] = None,
    backdrop: Optional[str] = None,
    *,
    auth: Optional[str] = None,
) -> Optional[float]:
    items = await _search_market(
        market, collection, model, backdrop, auth=auth,
    )
    transferable = [it for it in items if not _is_premarket(it)]
    priced = []
    for it in transferable:
        price = _item_price(it)
        if price is not None:
            priced.append(price)
    if not priced:
        return None
    return min(priced)


async def _all_market_floors(
    collection: str,
    model: Optional[str] = None,
    backdrop: Optional[str] = None,
) -> dict[str, Optional[float]]:
    auth = await _get_auth()
    tasks = [
        asyncio.create_task(
            _floor_for_market(search_key, collection, model, backdrop, auth=auth)
        )
        for search_key, _label, _hist in SAT_MARKETS
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out: dict[str, Optional[float]] = {}
    for (_search, label, _hist), res in zip(SAT_MARKETS, results):
        if isinstance(res, Exception):
            LOGS.info("Satellite floor %s failed: %s", label, res)
            out[label] = None
        else:
            out[label] = res
    return out


def _history_content(payload: Any) -> list[dict]:
    """Normalize POST /history/{collection} response → list of sale rows."""
    if isinstance(payload, dict):
        if isinstance(payload.get("content"), list):
            rows = payload["content"]
        else:
            data = payload.get("data")
            if isinstance(data, dict) and isinstance(data.get("content"), list):
                rows = data["content"]
            else:
                rows = _as_list(payload)
    else:
        rows = _as_list(payload)
    return [r for r in rows if isinstance(r, dict)]


def _sale_is_stars(row: dict) -> bool:
    """True when the sale is priced in Stars (Telegram market)."""
    cur = str(row.get("currency") or "").strip().upper()
    if cur in ("STARS", "STAR", "XTR"):
        return True
    if row.get("isStars") is True:
        return True
    # Mini app uses isTonOnly=False for stars listings/sales.
    if row.get("isTonOnly") is False:
        return True
    return False


def _sale_price_display(row: dict) -> str:
    """
    Human price for a sale row.
    Telegram Stars sales → star amount (not TON equivalent).
    """
    if _sale_is_stars(row):
        raw = row.get("originalPrice")
        if raw is None:
            raw = row.get("price")
        try:
            stars = float(raw)
            if stars > 1_000_000:
                stars = stars / 1_000_000_000.0
            if stars == int(stars):
                return f"{int(stars)} Stars"
            return f"{stars:.2f}".rstrip("0").rstrip(".") + " Stars"
        except Exception:
            pass
    price = _item_price(row)
    if price is None:
        return "—"
    return f"{_fmt_ton(price)} TON"


def _sale_row(row: dict, *, market_hint: Optional[str] = None) -> dict:
    slug = str(row.get("slug") or "").strip()
    number = row.get("number")
    if number is None and slug and "-" in slug:
        with contextlib.suppress(Exception):
            number = int(slug.rsplit("-", 1)[-1])
    return {
        "market": row.get("market") or market_hint or "?",
        "slug": slug,
        "number": number,
        "price": _item_price(row),
        "price_display": _sale_price_display(row),
        "is_stars": _sale_is_stars(row),
        "sold_at": row.get("soldAt") or row.get("date"),
        "nft_url": f"https://t.me/nft/{slug}" if slug else None,
        "raw": row,
    }


def _norm_market_key(value: Any) -> str:
    key = str(value or "").strip().lower()
    aliases = {
        "portal": "portals",
        "portals": "portals",
        "tonnel": "tonnel",
        "tg": "telegram",
        "telegram": "telegram",
        "mrkt": "mrkt",
        "getgem": "getgems",
        "getgems": "getgems",
    }
    return aliases.get(key, key)


def _sold_at_ts(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        if isinstance(value, (int, float)):
            ts = float(value)
            # ms vs s
            return ts / 1000.0 if ts > 1e12 else ts
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


def _fmt_sold_at(value: Any) -> str:
    """Format soldAt in Asia/Tehran local time."""
    if not value:
        return ""
    try:
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 1e12:
                ts /= 1000.0
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            text = str(value).replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(TEHRAN_TZ)
        return f"{local.month}/{local.day} {local.strftime('%H:%M')}"
    except Exception:
        return str(value)[:16]


async def _history_slot():
    """Serialize history POSTs (~1/s) to avoid Satellite 429s."""
    global _HISTORY_NEXT_AT
    async with _HISTORY_LOCK:
        now = time.monotonic()
        wait = _HISTORY_NEXT_AT - now
        if wait > 0:
            await asyncio.sleep(wait)
        _HISTORY_NEXT_AT = time.monotonic() + HISTORY_MIN_INTERVAL


async def _history_page(
    collection: str,
    *,
    model: Optional[str],
    backdrop: Optional[str],
    markets: Any,
    page: int,
    page_size: int = HISTORY_PAGE_SIZE,
    auth: Optional[str],
) -> list[dict]:
    page_size = min(max(1, int(page_size)), HISTORY_PAGE_SIZE)
    body: dict[str, Any] = {
        "models": [model] if model else [],
        "backdrops": [backdrop] if backdrop else [],
        "symbols": [],
        "number": "",
        "sortBy": "date",
        "page": page,
        "pageSize": page_size,
    }
    # Omit null markets — send string only when filtering one market.
    if markets:
        body["markets"] = markets
    await _history_slot()
    # Use raw collection path (spaces OK); matches Mini App encodeURIComponent.
    payload = await _sat_post(
        f"/history/{quote(collection, safe='')}",
        body,
        auth=auth,
    )
    rows = _history_content(payload)
    out = []
    for row in rows:
        if model and not _match_attr(row.get("modelName"), model):
            continue
        if backdrop and not _match_attr(row.get("backdropName"), backdrop):
            continue
        out.append(row)
    return out


def _trim_sales(rows: list[dict], limit: int) -> list[dict]:
    """Newest → oldest, unique, capped at limit."""
    rows = sorted(rows, key=lambda r: _sold_at_ts(r.get("sold_at")), reverse=True)
    seen = set()
    out = []
    for row in rows:
        key = (row.get("slug"), row.get("sold_at"), row.get("price"))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


async def _latest_sales_by_market(
    collection: str,
    model: Optional[str] = None,
    backdrop: Optional[str] = None,
    *,
    per_market: int = SALES_PER_MARKET,
) -> dict[str, list[dict]]:
    """
    4 latest sales for every market (newest first).

    History API: pageSize <= 20, ~1 req/s. Fetch each market sequentially
    with markets=<key>, then client-filter + sort.
    """
    auth = await _get_auth()
    buckets: dict[str, list[dict]] = {
        label: [] for _s, label, _h in SAT_MARKETS
    }

    for _search, label, hist_key in SAT_MARKETS:
        want = _norm_market_key(hist_key)
        matched: list[dict] = []
        # Up to 2 pages per market if the first page is thin after filtering.
        for page in range(0, 2):
            try:
                rows = await _history_page(
                    collection,
                    model=model,
                    backdrop=backdrop,
                    markets=hist_key,
                    page=page,
                    page_size=HISTORY_PAGE_SIZE,
                    auth=auth,
                )
            except Exception as e:
                LOGS.info(
                    "Satellite history %s/%s failed: %s", collection, hist_key, e,
                )
                break
            if not rows:
                break
            for row in rows:
                row_mkt = _norm_market_key(row.get("market"))
                if row_mkt and row_mkt != want:
                    continue
                matched.append(_sale_row(row, market_hint=hist_key))
            if len(matched) >= per_market:
                break
        buckets[label] = _trim_sales(matched, per_market)

    # If some markets are empty, one all-markets sweep to fill gaps.
    short = [
        (label, hist)
        for _s, label, hist in SAT_MARKETS
        if len(buckets.get(label) or []) < per_market
    ]
    if short:
        try:
            rows = await _history_page(
                collection,
                model=model,
                backdrop=backdrop,
                markets=None,
                page=0,
                page_size=HISTORY_PAGE_SIZE,
                auth=auth,
            )
        except Exception as e:
            LOGS.info("Satellite history gap-fill failed: %s", e)
            rows = []
        hist_to_label = {hist: label for _s, label, hist in SAT_MARKETS}
        for row in rows:
            hist_key = _norm_market_key(row.get("market"))
            label = hist_to_label.get(hist_key)
            if not label:
                continue
            if len(buckets[label]) >= per_market:
                continue
            buckets[label].append(_sale_row(row, market_hint=hist_key))
        for label, _hist in short:
            buckets[label] = _trim_sales(buckets[label], per_market)

    return buckets


def _sale_number_label(sale: dict) -> str:
    num = sale.get("number")
    if num is not None and str(num).strip() != "":
        return f"#{num}"
    slug = str(sale.get("slug") or "")
    if "-" in slug:
        with contextlib.suppress(Exception):
            return f"#{int(slug.rsplit('-', 1)[-1])}"
    return slug or "NFT"


def _nft_anchor(sale: dict) -> str:
    """HTML anchor showing #number (not full slug)."""
    title = _sale_number_label(sale)
    slug = sale.get("slug") or ""
    url = sale.get("nft_url") or (f"https://t.me/nft/{slug}" if slug else None)
    if url:
        return f'<a href="{_esc(url)}">{_esc(title)}</a>'
    return f"<code>{_esc(title)}</code>"


def _build_message(
    collection: str,
    model: Optional[str],
    backdrop: Optional[str],
    floors: dict[str, Optional[float]],
    sales_by_market: dict[str, list[dict]],
) -> str:
    lines = ["📡 <b>Gift Satellite</b>", ""]
    lines.append(f"🎁 <b>Collection:</b> <code>{_esc(collection)}</code>")
    if model:
        lines.append(f"🧩 <b>Model:</b> <code>{_esc(model)}</code>")
    if backdrop:
        lines.append(f"🎨 <b>Backdrop:</b> <code>{_esc(backdrop)}</code>")
    lines.append("")
    lines.append("💰 <b>Transferable floors</b>")
    for _search, label, _hist in SAT_MARKETS:
        price = floors.get(label)
        ton = f"{_fmt_ton(price)} TON" if price is not None else "—"
        lines.append(f"   <b>{_esc(label)}</b>: <code>{_esc(ton)}</code>")
    lines.append("")
    lines.append(f"🧾 <b>Latest sales</b> ({SALES_PER_MARKET} / market)")
    any_sales = False
    for _search, label, _hist in SAT_MARKETS:
        sales = sales_by_market.get(label) or []
        lines.append("")
        lines.append(f"<b>🏪 {SALES_PER_MARKET} Latest {_esc(label)} Sales</b>")
        if not sales:
            lines.append("   <b>No Sale Found -_-</b>")
            continue
        any_sales = True
        for i, sale in enumerate(sales, 1):
            price_txt = sale.get("price_display") or "—"
            when = _fmt_sold_at(sale.get("sold_at")) or "—"
            lines.append(
                f"   <b>{i}. {_nft_anchor(sale)} · "
                f"{_esc(price_txt)} · {_esc(when)}</b>"
            )
    if not any_sales:
        lines.append("")
        lines.append("<b>No Sale Found -_-</b>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Monochrome (Mini App — same data the backdrop picker shows)
# ---------------------------------------------------------------------------

_MONO_CACHE: dict[str, Any] = {}
_MONO_CACHE_TTL = 120.0


async def _fetch_monochromes(
    collection: str,
    model: Optional[str],
) -> list[dict]:
    """
    GET /match/backdrops-by-model — Gift Satellite Mini App monochrome list.

    Returns ``[{backdrop_name, type}, ...]`` with type high|medium|low.
    """
    if not collection or not model:
        return []
    cache_key = f"{_norm(collection)}|{_norm(model)}"
    row = _MONO_CACHE.get(cache_key)
    if row:
        expires, value = row
        if time.monotonic() < expires:
            return list(value)

    try:
        payload = await _sat_get(
            "/match/backdrops-by-model",
            params={
                "collectionName": collection,
                "modelName": model,
            },
        )
    except Exception as e:
        LOGS.warning(
            "Satellite monochrome failed (%s / %s): %s",
            collection,
            model,
            e,
        )
        return []

    rows = _as_list(payload)
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        rows = payload["data"]

    found: list[dict] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = (
            item.get("backdrop_name")
            or item.get("backdrop")
            or item.get("name")
        )
        if not name:
            continue
        level = str(item.get("type") or item.get("value") or "").strip()
        found.append({
            "backdrop_name": str(name).strip(),
            "type": level.upper() if level else "",
        })

    _MONO_CACHE[cache_key] = (
        time.monotonic() + _MONO_CACHE_TTL,
        found,
    )
    return found


def _format_sales_market_block(
    label: str,
    sales: list[dict],
    *,
    html_mode: bool = True,
    limit_note: int = 10,
) -> list[str]:
    """Format one market's sales lines (Tehran time, Stars-aware price)."""
    lines: list[str] = []
    header = f"🏪 {limit_note} Latest {label} Sales"
    if html_mode:
        lines.append(f"<b>{_esc(header)}</b>")
        if not sales:
            lines.append("   <b>No Sale Found -_-</b>")
            return lines
        for i, sale in enumerate(sales, 1):
            price_txt = sale.get("price_display") or "—"
            when = _fmt_sold_at(sale.get("sold_at")) or "—"
            lines.append(
                f"   <b>{i}. {_nft_anchor(sale)} · "
                f"{_esc(price_txt)} · {_esc(when)}</b>"
            )
    else:
        lines.append(f"**{header}**")
        if not sales:
            lines.append("   **No Sale Found -_-**")
            return lines
        for i, sale in enumerate(sales, 1):
            price_txt = sale.get("price_display") or "—"
            when = _fmt_sold_at(sale.get("sold_at")) or "—"
            slug = sale.get("slug") or ""
            url = sale.get("nft_url") or (
                f"https://t.me/nft/{slug}" if slug else None
            )
            title = _sale_number_label(sale)
            if url:
                link = f"[{title}]({url})"
            else:
                link = f"`{title}`"
            lines.append(f"   **{i}. {link} · {price_txt} · {when}**")
    return lines


async def _latest_sales_for_market(
    collection: str,
    market_hist_key: str,
    model: Optional[str] = None,
    backdrop: Optional[str] = None,
    *,
    limit: int = 10,
) -> list[dict]:
    """Latest ``limit`` sales for one history market key (portals/mrkt/…)."""
    auth = await _get_auth()
    want = _norm_market_key(market_hist_key)
    matched: list[dict] = []
    for page in range(0, 3):
        try:
            rows = await _history_page(
                collection,
                model=model,
                backdrop=backdrop,
                markets=market_hist_key,
                page=page,
                page_size=HISTORY_PAGE_SIZE,
                auth=auth,
            )
        except Exception as e:
            LOGS.info(
                "Satellite history %s/%s failed: %s",
                collection,
                market_hist_key,
                e,
            )
            break
        if not rows:
            break
        for row in rows:
            row_mkt = _norm_market_key(row.get("market"))
            if row_mkt and row_mkt != want:
                continue
            matched.append(_sale_row(row, market_hint=market_hist_key))
        if len(matched) >= limit:
            break
    return _trim_sales(matched, limit)

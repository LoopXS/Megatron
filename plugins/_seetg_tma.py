"""SeeTG (@seetgbot) Mini App client — NFT transfer history via TMA + GraphQL.

Auth path mirrors Gift Satellite: open the miniapp with Heartless DB creds
(``api_id`` / ``api_hash`` / ``SESSIONMRKT``) → initData → GraphQL.
A cached ``SEETG_WEB_TOKEN`` (Telegram Login web token) is used when present;
raw initData is never persisted as that token.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import parse_qs, quote, unquote, urlparse
from zoneinfo import ZoneInfo

import aiohttp
from telethon import TelegramClient, functions, utils
from telethon.sessions import StringSession
from telethon.tl.types import InputBotAppShortName

from . import LOGS, udB

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

SEETG_BOT = "seetgbot"
SEETG_APP_SHORT = "nft"
SEETG_WEBAPP = "https://see.tg/"
SEETG_GQL = "https://test-backend.see.tg/graphql"
SEETG_AUTH = "https://test-backend.see.tg/auth/web"
SEETG_BOT_ID = 8231963008

AUTH_TTL = 45 * 60
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=12)
HISTORY_LIMIT = 12

_AUTH_LOCK = asyncio.Lock()
_TG_LOCK = asyncio.Lock()
_TOKEN_CACHE: dict[str, Any] = {"token": None, "at": 0.0, "kind": None}
_INIT_CACHE: dict[str, Any] = {"init": None, "at": 0.0}

_GIFT_HISTORY_QUERY = """
query GiftHistory($giftId: String!, $first: Int!, $after: String, $sortDir: SortDirection, $kinds: [String!]) {
  giftHistory(giftId: $giftId, first: $first, after: $after, sortDir: $sortDir, kinds: $kinds) {
    items {
      id
      kind
      time
      hidden
      saleAction { market kind amount currency amountTon }
      giftAction {
        action
        direction
        from { username usernames title name telegramId address seeType }
        to { username usernames title name telegramId address seeType }
      }
    }
    pageInfo { endCursor hasNextPage }
  }
}
"""

_SEARCH_GIFTS_QUERY = """
query SearchGifts($filter: GiftFilter!, $first: Int!) {
  searchGifts(filter: $filter, first: $first) {
    items { id giftId title slug num }
  }
}
"""


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


def _db_web_token() -> Optional[str]:
    """Cached SeeTG web auth token (Telegram Login id_token exchange result)."""
    raw = udB.get_key("SEETG_WEB_TOKEN")
    tok = str(raw).strip() if raw else None
    if not tok:
        return None
    # Reject poisoned cache: raw Mini App initData must never be stored as web token.
    if "query_id=" in tok or "user=" in tok or "hash=" in tok:
        with contextlib.suppress(Exception):
            udB.del_key("SEETG_WEB_TOKEN")
        return None
    return tok


def _parse_nft_slug(value: str) -> Optional[tuple[str, int]]:
    text = str(value or "").strip()
    m = re.fullmatch(r"([A-Za-z][A-Za-z0-9]*)-(\d+)", text)
    if not m:
        m2 = re.search(r"(?:t\.me/nft/)?([A-Za-z][A-Za-z0-9]*)-(\d+)", text)
        if not m2:
            return None
        return m2.group(1), int(m2.group(2))
    return m.group(1), int(m.group(2))


def _peer_label(peer: Optional[dict], *, at_prefix: bool = True) -> str:
    if not isinstance(peer, dict):
        return "?"
    for key in ("username",):
        val = peer.get(key)
        if val:
            name = str(val).lstrip("@")
            return f"@{name}" if at_prefix else name
    names = peer.get("usernames") or []
    if isinstance(names, list) and names:
        name = str(names[0]).lstrip("@")
        return f"@{name}" if at_prefix else name
    for key in ("title", "name"):
        val = peer.get(key)
        if val:
            return str(val)
    tid = peer.get("telegramId")
    if tid:
        return f"id{tid}"
    addr = peer.get("address")
    if addr:
        a = str(addr)
        return a[:6] + "…" + a[-4:] if len(a) > 12 else a
    st = str(peer.get("seeType") or "").lower()
    if st == "hidden":
        return "Hidden"
    if st == "blockchain":
        return "On-chain"
    return "?"


def _fmt_history_time(raw: Any) -> str:
    if raw is None or raw == "":
        return "—"
    try:
        if isinstance(raw, (int, float)):
            ts = float(raw)
            if ts > 1e12:
                ts /= 1000.0
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            text = str(raw).replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(TEHRAN_TZ)
        return local.strftime("%-m/%-d %H:%M")
    except Exception:
        return str(raw)[:16]


def _history_ts(raw: Any) -> float:
    if raw is None or raw == "":
        return 0.0
    try:
        if isinstance(raw, (int, float)):
            ts = float(raw)
            return ts / 1000.0 if ts > 1e12 else ts
        text = str(raw).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


def _fmt_ton_amount(raw: Any) -> Optional[str]:
    """Format TON amount; auto-convert nanotons (≥1e6)."""
    try:
        amt = float(raw)
    except Exception:
        return None
    if amt <= 0:
        return None
    if amt >= 1_000_000:
        amt = amt / 1_000_000_000.0
    # Match gift UX: trim trailing zeros (4.182 → 4.18, 3.7 → 3.7)
    if amt >= 100:
        text = f"{amt:,.2f}"
    elif amt >= 10:
        text = f"{amt:.2f}"
    elif amt >= 1:
        text = f"{amt:.3f}".rstrip("0").rstrip(".")
    else:
        text = f"{amt:.4f}".rstrip("0").rstrip(".")
    if text.endswith(".00"):
        text = text[:-3]
    return f"{text} TON"


def _market_label(market: Any) -> str:
    key = str(market or "").strip().lower()
    aliases = {
        "telegram": "TG Market",
        "tg": "TG Market",
        "mrkt": "mrkt",
        "portals": "portals",
        "portal": "portals",
        "tonnel": "tonnel",
        "getgems": "getgems",
    }
    return aliases.get(key, str(market) if market else "")


def _decode_tg_auth_result(val: str) -> Optional[str]:
    """Decode oauth tgAuthResult blob → id_token / raw JSON string for auth/web."""
    text = unquote(str(val or "").strip())
    if not text:
        return None
    # Already a JWT
    if text.count(".") >= 2 and not text.startswith("{"):
        return text
    pad = "=" * (-len(text) % 4)
    for candidate in (text, text + pad):
        try:
            raw = base64.urlsafe_b64decode(candidate.encode("utf-8", "ignore"))
            decoded = raw.decode("utf-8", "ignore")
        except Exception:
            continue
        if decoded.count(".") >= 2:
            return decoded
        try:
            obj = json.loads(decoded)
        except Exception:
            continue
        if isinstance(obj, dict):
            for key in ("id_token", "token", "access_token"):
                if obj.get(key):
                    return str(obj[key])
            # Login-widget style payload — auth/web may accept the JSON body fields
            return decoded
    return text


async def _mint_init_data(start_param: Optional[str] = None) -> str:
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
                raise ValueError("SeeTG session is not authorized.")
            bot = await client.get_entity(SEETG_BOT)
            try:
                app = InputBotAppShortName(
                    bot_id=utils.get_input_user(bot),
                    short_name=SEETG_APP_SHORT,
                )
                web_view = await client(
                    functions.messages.RequestAppWebViewRequest(
                        peer=utils.get_input_peer(bot),
                        app=app,
                        platform="android",
                        write_allowed=True,
                        start_param=start_param or "",
                    )
                )
            except Exception:
                web_view = await client(
                    functions.messages.RequestWebViewRequest(
                        peer=utils.get_input_peer(bot),
                        bot=utils.get_input_user(bot),
                        platform="android",
                        url=SEETG_WEBAPP,
                        start_param=start_param or None,
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
        raise RuntimeError("SeeTG webview returned no tgWebAppData.")
    _INIT_CACHE["init"] = auth
    _INIT_CACHE["at"] = time.monotonic()
    return auth


async def _exchange_web_token(id_token: str) -> Optional[str]:
    """POST auth/web with Telegram Login id_token (or related body shapes)."""
    bodies = [
        {"id_token": id_token},
        {"initData": id_token},
        {"init_data": id_token},
        {"web_app_data": id_token},
        {"data": id_token},
        {"telegram_web_app": id_token},
    ]
    # If payload is Login-widget JSON, also try spreading fields + id_token alias
    with contextlib.suppress(Exception):
        obj = json.loads(id_token)
        if isinstance(obj, dict):
            bodies.insert(0, {"id_token": obj.get("id_token") or id_token})
            bodies.insert(0, obj)

    async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
        for body in bodies:
            if not isinstance(body, dict):
                continue
            try:
                async with session.post(
                    SEETG_AUTH,
                    json=body,
                    headers={
                        "Content-Type": "application/json",
                        "Origin": "https://see.tg",
                        "Referer": "https://see.tg/",
                        "User-Agent": "Heartless-SeeTG/1.0",
                    },
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
            except Exception:
                continue
            token = None
            if isinstance(data, dict):
                token = data.get("token") or (data.get("result") or {}).get("token")
            if token:
                return str(token)
    return None


async def _auth_via_oauth_webview() -> Optional[str]:
    """Open Telegram Login oauth URL inside a webview and scrape id_token if present."""
    api_id, api_hash, session = _api_id(), _api_hash(), _session_str()
    if not api_id or not api_hash or not session:
        return None
    oauth = (
        f"https://oauth.telegram.org/auth?bot_id={SEETG_BOT_ID}"
        f"&origin={quote('https://see.tg', safe='')}"
        f"&embed=1&request_access=write"
        f"&return_to={quote('https://see.tg/', safe='')}"
    )
    async with _TG_LOCK:
        client = TelegramClient(
            StringSession(session), api_id, api_hash,
            connection_retries=2, retry_delay=1, timeout=20,
        )
        try:
            await client.connect()
            if not await client.is_user_authorized():
                return None
            bot = await client.get_entity(SEETG_BOT)
            wv = await client(
                functions.messages.RequestWebViewRequest(
                    peer=utils.get_input_peer(bot),
                    bot=utils.get_input_user(bot),
                    platform="android",
                    url=oauth,
                )
            )
            url = wv.url or ""
        except Exception as e:
            LOGS.debug("SeeTG oauth webview failed: %s", e)
            return None
        finally:
            with contextlib.suppress(Exception):
                await client.disconnect()

    parsed = urlparse(url)
    blob = parse_qs(parsed.fragment, keep_blank_values=True)
    blob.update(parse_qs(parsed.query, keep_blank_values=True))
    for key in ("tgAuthResult", "id_token", "token", "tgWebAppData"):
        val = (blob.get(key) or [None])[0]
        if not val:
            continue
        decoded = _decode_tg_auth_result(val) if key == "tgAuthResult" else val
        if key == "id_token" and decoded:
            return await _exchange_web_token(decoded) or decoded
        if decoded:
            tok = await _exchange_web_token(decoded)
            if tok:
                return tok
    return None


async def _get_web_token(force: bool = False) -> Optional[str]:
    """Return a real web Login token if available. Never returns raw initData."""
    async with _AUTH_LOCK:
        now = time.monotonic()
        cached = _TOKEN_CACHE.get("token")
        if (
            not force
            and cached
            and _TOKEN_CACHE.get("kind") == "web"
            and now - float(_TOKEN_CACHE.get("at") or 0) < AUTH_TTL
        ):
            return cached

        db_tok = _db_web_token()
        if db_tok and not force:
            _TOKEN_CACHE["token"] = db_tok
            _TOKEN_CACHE["kind"] = "web"
            _TOKEN_CACHE["at"] = now
            return db_tok

        token = await _auth_via_oauth_webview()
        if not token:
            # Try exchanging fresh initData (some backends accept it as id_token).
            try:
                init = await _mint_init_data()
            except Exception as e:
                LOGS.debug("SeeTG initData mint failed: %s", e)
                init = None
            if init:
                token = await _exchange_web_token(init)

        if token:
            _TOKEN_CACHE["token"] = token
            _TOKEN_CACHE["kind"] = "web"
            _TOKEN_CACHE["at"] = now
            with contextlib.suppress(Exception):
                udB.set_key("SEETG_WEB_TOKEN", token)
            return token

        _TOKEN_CACHE["token"] = None
        _TOKEN_CACHE["kind"] = None
        _TOKEN_CACHE["at"] = 0.0
        return None


async def _get_init_data(force: bool = False) -> str:
    now = time.monotonic()
    cached = _INIT_CACHE.get("init")
    if (
        not force
        and cached
        and now - float(_INIT_CACHE.get("at") or 0) < AUTH_TTL
    ):
        return cached
    return await _mint_init_data()


def _auth_header_candidates(web_token: Optional[str], init_data: Optional[str]) -> list[str]:
    """Ordered Authorization values to try against SeeTG GraphQL."""
    out: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        if value and value not in seen:
            seen.add(value)
            out.append(value)

    if web_token:
        add(f"web {web_token}")
        add(f"Bearer {web_token}")
    if init_data:
        # Telegram Mini Apps common schemes + SeeTG web prefix with initData
        add(f"tma {init_data}")
        add(f"web {init_data}")
        add(init_data)
    return out


async def _gql(
    query: str,
    variables: Optional[dict] = None,
    *,
    web_token: Optional[str] = None,
    init_data: Optional[str] = None,
) -> dict:
    payload = {"query": query, "variables": variables or {}}
    headers_base = {
        "Content-Type": "application/json",
        "Origin": "https://see.tg",
        "Referer": "https://see.tg/",
        "User-Agent": "Heartless-SeeTG/1.0",
    }
    candidates = _auth_header_candidates(web_token, init_data)
    if not candidates:
        candidates = [""]  # guest / unauthenticated attempt

    last_err: Optional[Exception] = None
    async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
        for auth in candidates:
            headers = dict(headers_base)
            if auth:
                headers["Authorization"] = auth
            try:
                async with session.post(SEETG_GQL, json=payload, headers=headers) as resp:
                    text = await resp.text()
                    if resp.status == 401:
                        last_err = RuntimeError("SeeTG GraphQL HTTP 401")
                        continue
                    if resp.status >= 400:
                        last_err = RuntimeError(
                            f"SeeTG GraphQL HTTP {resp.status}: {text[:180]}"
                        )
                        continue
                    data = json.loads(text)
            except Exception as e:
                last_err = e
                continue
            if not isinstance(data, dict):
                last_err = RuntimeError("SeeTG GraphQL returned non-object.")
                continue
            if data.get("errors"):
                err = (
                    data["errors"][0]
                    if isinstance(data["errors"], list)
                    else data["errors"]
                )
                msg = err.get("message") if isinstance(err, dict) else str(err)
                # Auth errors → try next header scheme
                low = str(msg).lower()
                if any(x in low for x in ("auth", "unauthorized", "forbidden", "token")):
                    last_err = RuntimeError(f"SeeTG GraphQL: {msg}")
                    continue
                raise RuntimeError(f"SeeTG GraphQL: {msg}")
            return data.get("data") or {}

    if last_err:
        raise last_err
    raise RuntimeError("SeeTG GraphQL request failed.")


async def _resolve_gift(
    slug_num: str,
    *,
    web_token: Optional[str],
    init_data: Optional[str],
) -> Optional[dict]:
    parsed = _parse_nft_slug(slug_num)
    if not parsed:
        return None
    slug, num = parsed
    data = await _gql(
        _SEARCH_GIFTS_QUERY,
        {
            "filter": {
                "slug": slug,
                "numberFrom": num,
                "numberTo": num,
            },
            "first": 1,
        },
        web_token=web_token,
        init_data=init_data,
    )
    items = ((data.get("searchGifts") or {}).get("items")) or []
    return items[0] if items else None


def _history_event_label(item: dict) -> str:
    """Human event title matching SeeTG / user-facing copy."""
    kind = str(item.get("kind") or "").strip().lower()
    action = item.get("giftAction") if isinstance(item.get("giftAction"), dict) else {}
    sale = item.get("saleAction") if isinstance(item.get("saleAction"), dict) else {}
    act = str(action.get("action") or "").strip().lower()
    sale_kind = str(sale.get("kind") or "").strip().lower()

    # Prefer explicit kind when it's not the generic "gift" bucket.
    signal = kind if kind and kind not in ("gift", "event") else ""
    if not signal:
        signal = act or sale_kind

    labels = {
        "new": "Gift Upgraded",
        "mint": "Gift Upgraded",
        "upgrade": "Gift Upgraded",
        "upgraded": "Gift Upgraded",
        "transfer": "Gift Sent",
        "moved": "Gift Sent",
        "sent": "Gift Sent",
        "send": "Gift Sent",
        "sale": "Gift Sold",
        "sold": "Gift Sold",
        "buy": "Gift Sold",
        "listing": "Listed for Sale",
        "list": "Listed for Sale",
        "price": "Listed for Sale",
        "delisting": "Delisted",
        "burn": "Burned",
    }
    if signal in labels:
        return labels[signal]

    has_price = bool(
        sale
        and (
            sale.get("amount") is not None
            or sale.get("amountTon") is not None
        )
    )
    has_peers = bool(
        action
        and (action.get("from") or action.get("to"))
    )
    if has_price:
        if sale_kind in ("listing", "list", "price") or kind == "listing":
            return "Listed for Sale"
        return "Gift Sold"
    if has_peers:
        return "Gift Sent"
    if kind:
        return kind.replace("_", " ").title()
    return "Event"


def _sale_price_text(sale: dict) -> Optional[str]:
    if not isinstance(sale, dict):
        return None
    cur = str(sale.get("currency") or "").strip().upper()
    # Stars / XTR — amount is already in stars
    if cur in ("XTR", "STARS", "STAR"):
        raw = sale.get("amount")
        if raw is None:
            return None
        try:
            amt = float(raw)
            if amt == int(amt):
                return f"{int(amt)} Stars"
            return f"{amt:g} Stars"
        except Exception:
            return None
    # Prefer raw amount (gram/nanoton) then amountTon
    for key in ("amount", "amountTon"):
        if sale.get(key) is None:
            continue
        if key == "amount" and cur and cur not in ("GRAM", "TON", "NANOTON", ""):
            continue
        text = _fmt_ton_amount(sale.get(key))
        if text:
            return text
    return None


def _normalize_history_item(item: dict) -> dict:
    kind = str(item.get("kind") or "")
    action = item.get("giftAction") if isinstance(item.get("giftAction"), dict) else {}
    sale = item.get("saleAction") if isinstance(item.get("saleAction"), dict) else {}
    frm = _peer_label(action.get("from") if isinstance(action, dict) else None)
    to = _peer_label(action.get("to") if isinstance(action, dict) else None)
    label = _history_event_label(item)
    price = _sale_price_text(sale) if sale else None
    market_raw = sale.get("market") if sale else None
    return {
        "kind": kind,
        "kind_label": label,
        "show_peers": label == "Gift Sent",
        "show_price": label in ("Gift Sold", "Listed for Sale") and bool(price),
        "time": item.get("time"),
        "time_ts": _history_ts(item.get("time")),
        "time_display": _fmt_history_time(item.get("time")),
        "from": frm,
        "to": to,
        "price": price,
        "hidden": bool(item.get("hidden")),
        "market": market_raw,
        "market_label": _market_label(market_raw) if market_raw else None,
    }


async def fetch_transfer_history(
    slug_or_url: str,
    *,
    limit: int = HISTORY_LIMIT,
    sent_only: bool = True,
) -> list[dict]:
    """
    Fetch NFT history from SeeTG miniapp GraphQL for ``Slug-123`` / nft URL.

    By default returns only **Gift Sent** rows, oldest → newest.
    """
    parsed = _parse_nft_slug(slug_or_url)
    if not parsed:
        raise ValueError("Invalid NFT slug for SeeTG history.")
    slug, num = parsed
    start = f"{slug}-{num}"

    # Warm miniapp session (same startapp the bot uses).
    init_data: Optional[str] = None
    with contextlib.suppress(Exception):
        init_data = await _mint_init_data(start)
    if not init_data:
        with contextlib.suppress(Exception):
            init_data = await _get_init_data()

    web_token = await _get_web_token()

    gift = None
    with contextlib.suppress(Exception):
        gift = await _resolve_gift(
            start, web_token=web_token, init_data=init_data,
        )
    gift_id = None
    if gift:
        gift_id = gift.get("id") or gift.get("giftId")
    if not gift_id:
        gift_id = start

    want = max(int(limit or HISTORY_LIMIT), 1)
    # Pull a wider page so Gift Sent filtering still fills ``limit``.
    fetch_first = max(want * 5, 40) if sent_only else max(want * 2, 12)

    # Retry once with forced re-auth if the first attempt fails.
    last_err: Optional[Exception] = None
    for attempt in range(2):
        try:
            if attempt == 1:
                with contextlib.suppress(Exception):
                    udB.del_key("SEETG_WEB_TOKEN")
                web_token = await _get_web_token(force=True)
                init_data = await _get_init_data(force=True)
            # Prefer transfer/moved kinds when filtering to Gift Sent; fall back
            # to unfiltered if the enum rejects those values.
            kind_attempts: list[Optional[list[str]]] = (
                [["transfer", "moved"], None]
                if sent_only
                else [None]
            )
            items: list = []
            gql_err: Optional[Exception] = None
            for kinds in kind_attempts:
                try:
                    data = await _gql(
                        _GIFT_HISTORY_QUERY,
                        {
                            "giftId": str(gift_id),
                            "first": fetch_first,
                            "after": None,
                            "sortDir": "ASC",
                            "kinds": kinds,
                        },
                        web_token=web_token,
                        init_data=init_data,
                    )
                    items = ((data.get("giftHistory") or {}).get("items")) or []
                    gql_err = None
                    break
                except Exception as e:
                    gql_err = e
                    continue
            if gql_err and not items:
                raise gql_err

            out = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("hidden"):
                    continue
                row = _normalize_history_item(item)
                if sent_only and row.get("kind_label") != "Gift Sent":
                    continue
                out.append(row)
            # Ensure chronological order even if API ignores sortDir.
            out.sort(key=lambda r: float(r.get("time_ts") or 0.0))
            if len(out) > want:
                # Oldest → newest: keep the earliest N owner transfers.
                out = out[:want]
            return out
        except Exception as e:
            last_err = e
            LOGS.debug("SeeTG history attempt %s failed: %s", attempt + 1, e)

    if last_err:
        raise last_err
    return []


def format_history_md(rows: list[dict], *, nft_url: Optional[str] = None) -> list[str]:
    """Markdown lines for inline g Owner History (Gift Sent) block."""
    del nft_url  # reserved; panel no longer links out to SeeTG
    lines = ["📜 **Owner History**", ""]
    if not rows:
        lines.append("No History Found -_-")
        return lines
    for i, row in enumerate(rows, 1):
        kind = row.get("kind_label") or "Gift Sent"
        when = row.get("time_display") or "—"
        bit = f"**{i}. {kind}** · {when}"
        frm = row.get("from") or "?"
        to = row.get("to") or "?"
        bit += f"\n{frm} - > {to}"
        lines.append(bit)
    return lines

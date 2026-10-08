"""
Instagram downloader for userbot.

Command:
    {i}ig <Instagram link>

Inline:
    @AssistantBot ig <Instagram link>

Supported:
    - Posts
    - Reels
    - IGTV / TV
    - Stories
    - Story Highlights
    - Carousel posts

The command and inline layers share the same resolver/download service,
but they are otherwise independent.
"""

import asyncio
import glob
import hashlib
import html as html_lib
import json
import os
import re
import tempfile
import time
from base64 import urlsafe_b64decode
from urllib.parse import urlparse

from aiohttp import ClientSession, ClientTimeout, CookieJar
from telethon.errors.rpcerrorlist import (
    WebpageCurlFailedError,
    WebpageMediaEmptyError,
    YouBlockedUserError,
)

from . import (
    Button,
    LOGS,
    callback,
    eod,
    get_pstring,
    in_pattern,
    run_async,
    udB,
    heartless_cmd,
)

try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None


# ============================================================================
# CONSTANTS
# ============================================================================

IG_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?instagram\.com/"
    r"(?:"
    r"(?:p|reel|reels|tv)/[A-Za-z0-9._\-]+"
    r"|stories/highlights/[A-Za-z0-9._\-]+"
    r"|stories/[A-Za-z0-9._\-]+(?:/\d+)?"
    r")/?",
    re.I,
)

SHORTCODE_RE = re.compile(
    r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9._\-]+)",
    re.I,
)

STORY_RE = re.compile(
    r"instagram\.com/stories/"
    r"(?:(highlights)/)?"
    r"([^/]+)"
    r"(?:/(\d+))?/?",
    re.I,
)

HEX_ESC_RE = re.compile(
    r"\\x([0-9a-fA-F]{2})"
)

CDN_TOKEN_RE = re.compile(
    r"https://cdn\.downloadgram\.org/\?token=([^\"'&\s<>]+)"
)

SNAPCDN_RE = re.compile(
    r"https://(?:dl|i)\.snapcdn\.app/[^\"'\s<>]+",
    re.I,
)

MEDIA_URL_RE = re.compile(
    r"https://(?:scontent|instagram|cdn\.downloadgram\.org|"
    r"(?:dl|i)\.snapcdn\.app)"
    r"[^\"'\s<>]+",
    re.I,
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

IG_HEADERS = {
    "User-Agent": UA,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "X-IG-App-ID": "936619743392459",
    "X-ASBD-ID": "359341",
    "X-IG-WWW-Claim": "0",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.instagram.com/",
    "Origin": "https://www.instagram.com",
}

DOWNLOADGRAM = (
    "https://api.downloadgram.org/media"
)

SAVEINSTA = "https://saveinsta.to"

SAVEINSTA_HOME = (
    f"{SAVEINSTA}/en/highlights"
)

SAVEINSTA_SEARCH = (
    f"{SAVEINSTA}/api/ajaxSearch"
)

SAVEINSTA_VERIFY = (
    f"{SAVEINSTA}/api/userverify"
)

_IG_B64 = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789-_"
)

_SAVEINSTA_PAGE_TOKENS = {
    "k_exp": None,
    "k_token": None,
    "ts": 0,
}


# ============================================================================
# INLINE STATE
# ============================================================================

INLINE_STATE_TTL = 15 * 60
INLINE_MAX_MEDIA = 10

INLINE_TOKEN_RE = re.compile(
    r"^igdl:([A-Za-z0-9_-]{12,32})(?::(\d+))?$"
)

_INLINE_STATE = {}


# ============================================================================
# BASIC HELPERS
# ============================================================================

def _instagram_cookie_header():
    cookie_file = udB.get_key(
        "IG_COOKIES"
    )

    if (
        not cookie_file
        or not isinstance(cookie_file, str)
        or not os.path.isfile(cookie_file)
    ):
        return None

    cookies = []

    try:
        with open(
            cookie_file,
            "r",
            encoding="utf-8",
            errors="ignore",
        ) as fh:

            for line in fh:
                line = line.strip()

                if (
                    not line
                    or line.startswith("#")
                ):
                    continue

                parts = line.split("\t")

                if len(parts) < 7:
                    continue

                (
                    domain,
                    _flag,
                    _path,
                    _secure,
                    _expires,
                    name,
                    value,
                ) = parts[:7]

                if (
                    "instagram.com"
                    not in domain.lower()
                    or not name
                ):
                    continue

                cookies.append(
                    f"{name}={value}"
                )

    except OSError as er:
        LOGS.info(
            f"IG cookie file read failed: {er}"
        )
        return None

    return "; ".join(
        dict.fromkeys(cookies)
    ) or None


def _ig_request_headers(extra=None):
    headers = dict(
        IG_HEADERS
    )

    cookie = (
        _instagram_cookie_header()
    )

    if cookie:
        headers["Cookie"] = cookie

    if extra:
        headers.update(extra)

    return headers


def _dedupe_files(paths):
    seen = set()
    out = []

    for path in paths or []:

        try:
            size = os.path.getsize(
                path
            )

            digest = hashlib.sha256()

            with open(
                path,
                "rb",
            ) as fh:

                for chunk in iter(
                    lambda: fh.read(
                        1024 * 1024
                    ),
                    b"",
                ):
                    digest.update(
                        chunk
                    )

            key = (
                size,
                digest.hexdigest(),
            )

        except (
            OSError,
            IOError,
        ):
            continue

        if key in seen:

            try:
                os.remove(path)
            except OSError:
                pass

            continue

        seen.add(key)
        out.append(path)

    return out


def _normalize_url(url: str):
    url = (
        url.strip()
        .split()[0]
    )

    if not url.startswith(
        "http"
    ):
        url = (
            "https://"
            + url.lstrip("/")
        )

    parsed = urlparse(url)

    path = (
        parsed.path.rstrip("/")
        + "/"
    )

    return (
        "https://www.instagram.com"
        + path
    )


def _is_story(url: str):
    return (
        "/stories"
        in urlparse(url).path.lower()
    )


def _label_for(url: str):
    path = (
        urlparse(url)
        .path
        .lower()
    )

    if "/reel" in path:
        return f"[Reel]({url})"

    if "/stories" in path:
        return f"[Story]({url})"

    if "/tv/" in path:
        return f"[IGTV]({url})"

    if "/p/" in path:
        return f"[Post]({url})"

    return (
        f"[Instagram]({url})"
    )


def _shortcode(url: str):
    match = SHORTCODE_RE.search(
        url
    )

    return (
        match.group(1)
        if match
        else None
    )


def _shortcode_to_pk(
    shortcode: str,
):
    if len(shortcode) > 28:
        shortcode = shortcode[:-28]

    value = 0

    for char in shortcode:
        value = (
            value * 64
            + _IG_B64.index(char)
        )

    return str(value)


def _unique(urls):
    seen = set()
    out = []

    for url in urls:

        if not url or url in seen:
            continue

        seen.add(url)

        out.append(
            html_lib.unescape(
                url
            )
            .replace(
                "\\u0026",
                "&",
            )
            .replace(
                "\\/",
                "/",
            )
        )

    return out


def _decode_js_hex(text: str):
    return HEX_ESC_RE.sub(
        lambda m: chr(
            int(
                m.group(1),
                16,
            )
        ),
        text,
    )


def _jwt_payload(token: str):
    try:
        part = token.split(".")[1]

        part += "=" * (
            -len(part) % 4
        )

        return json.loads(
            urlsafe_b64decode(
                part.encode()
            )
        )

    except Exception:
        return {}


def _best_from_versions(
    versions,
):
    if not versions:
        return None

    try:
        return max(
            versions,
            key=lambda x: (
                x.get("width") or 0
            ) * (
                x.get("height") or 0
            ),
        ).get("url")

    except Exception:
        return (
            versions[0].get("url")
        )


# ============================================================================
# MEDIA URL EXTRACTION
# ============================================================================

def _urls_from_media_item(item):
    urls = []

    if not isinstance(
        item,
        dict,
    ):
        return urls

    if item.get(
        "video_versions"
    ):

        url = _best_from_versions(
            item[
                "video_versions"
            ]
        )

        if url:
            urls.append(url)

    elif item.get(
        "video_url"
    ):
        urls.append(
            item["video_url"]
        )

    elif item.get(
        "image_versions2",
        {},
    ).get(
        "candidates"
    ):

        url = _best_from_versions(
            item[
                "image_versions2"
            ][
                "candidates"
            ]
        )

        if url:
            urls.append(url)

    elif item.get(
        "display_url"
    ):
        urls.append(
            item["display_url"]
        )

    carousel = (
        item.get("carousel_media")
        or item.get(
            "edge_sidecar_to_children",
            {},
        ).get("edges")
    )

    if carousel:

        for part in carousel:

            node = (
                part.get(
                    "node",
                    part,
                )
                if isinstance(
                    part,
                    dict,
                )
                else part
            )

            urls.extend(
                _urls_from_media_item(
                    node
                )
            )

    return urls


def _urls_from_obj(
    obj,
    found=None,
):
    if found is None:
        found = []

    if isinstance(
        obj,
        dict,
    ):

        found.extend(
            _urls_from_media_item(
                obj
            )
        )

        for value in obj.values():
            _urls_from_obj(
                value,
                found,
            )

    elif isinstance(
        obj,
        list,
    ):

        for value in obj:
            _urls_from_obj(
                value,
                found,
            )

    return found


def _dedupe_media_urls(urls):
    urls = _unique(urls)

    seen = set()
    out = []

    for url in urls:

        key = None

        if (
            "token=" in url
            and (
                "cdn.downloadgram.org"
                in url
                or "snapcdn.app"
                in url.lower()
            )
        ):

            payload = _jwt_payload(
                url.split(
                    "token=",
                    1,
                )[1]
            )

            host = (
                "snapcdn"
                if "snapcdn.app"
                in url.lower()
                else "downloadgram"
            )

            key = (
                host,
                payload.get(
                    "filename"
                ),
                payload.get(
                    "filesize"
                )
                or payload.get("size"),
                payload.get("url"),
            )

            if (
                key[1] is None
                and key[3] is None
            ):
                key = None

        if key is None:
            key = (
                "direct",
                url.split(
                    "?",
                    1,
                )[0].rstrip("/"),
            )

        if key in seen:
            continue

        seen.add(key)
        out.append(url)

    snap_dl = [
        url
        for url in out
        if "dl.snapcdn.app"
        in url.lower()
    ]

    if snap_dl:
        return snap_dl

    return out


def _guess_ext(media: str):
    low = media.lower()

    if (
        "token=" in media
        and (
            "cdn.downloadgram.org"
            in low
            or "snapcdn.app"
            in low
        )
    ):

        payload = _jwt_payload(
            media.split(
                "token=",
                1,
            )[1]
        )

        filename = (
            payload.get(
                "filename"
            )
            or ""
        ).lower()

        source = (
            payload.get(
                "url"
            )
            or ""
        ).lower()

        if (
            filename.endswith(
                (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                )
            )
            or any(
                source.endswith(ext)
                for ext in (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                )
            )
        ):
            return ".jpg"

        if (
            filename.endswith(
                ".mp4"
            )
            or ".mp4" in source
        ):
            return ".mp4"

    path = low.split(
        "?",
        1,
    )[0]

    if any(
        path.endswith(ext)
        for ext in (
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        )
    ):
        return ".jpg"

    return ".mp4"


# ============================================================================
# YT-DLP
# ============================================================================

@run_async
def _ytdlp_download(
    url: str,
    outdir: str,
):
    if not YoutubeDL:
        return []

    outtmpl = os.path.join(
        outdir,
        "%(id)s.%(ext)s",
    )

    normalized = _normalize_url(
        url
    )

    is_story = _is_story(
        normalized
    )

    timeout = (
        30
        if is_story
        else 12
    )

    options = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": outtmpl,
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "socket_timeout": timeout,
        "retries": (
            2
            if is_story
            else 1
        ),
        "geo_bypass": True,
        "nocheckcertificate": True,
        "noplaylist": True,
    }

    cookie = (
        udB.get_key(
            "IG_COOKIES"
        )
        or (
            "cookies.txt"
            if os.path.exists(
                "cookies.txt"
            )
            else None
        )
    )

    if cookie:
        options[
            "cookiefile"
        ] = cookie

    try:

        with YoutubeDL(
            options
        ) as ydl:
            ydl.download(
                [url]
            )

    except Exception as er:

        LOGS.info(
            f"yt-dlp IG download failed: {er}"
        )

        return []

    files = [
        path
        for path in glob.glob(
            os.path.join(
                outdir,
                "*",
            )
        )
        if (
            os.path.isfile(path)
            and not path.endswith(
                (
                    ".part",
                    ".ytdl",
                    ".json",
                )
            )
        )
    ]

    files.sort(
        key=os.path.getmtime
    )

    return files


# ============================================================================
# INSTAGRAM SERVICE
# ============================================================================

class Instagram:

    def __init__(self):
        self.timeout = ClientTimeout(
            total=25,
            connect=8,
            sock_read=20,
        )

        self.story_timeout = ClientTimeout(
            total=45,
            connect=15,
            sock_read=30,
        )

    async def _get_json(
        self,
        session,
        url,
        **kwargs,
    ):
        async with session.get(
            url,
            **kwargs,
        ) as response:

            if response.status != 200:
                return None

            try:
                return await response.json(
                    content_type=None
                )

            except Exception:

                text = await response.text()

                try:
                    return json.loads(
                        text
                    )
                except Exception:
                    return None

    async def _from_downloadgram(
        self,
        session,
        url,
    ):
        try:

            async with session.post(
                DOWNLOADGRAM,
                json={
                    "url": url
                },
                headers={
                    "User-Agent": UA,
                    "Content-Type":
                        "application/json",
                    "Accept": "*/*",
                },
            ) as response:

                body = await response.text()

                if (
                    response.status != 200
                    or not body
                ):
                    LOGS.info(
                        "downloadgram "
                        f"status={response.status}"
                    )
                    return []

                return (
                    self._parse_downloadgram(
                        body
                    )
                )

        except Exception as er:

            LOGS.info(
                f"downloadgram miss: {er}"
            )

        return []

    def _parse_downloadgram(
        self,
        body,
    ):
        text = _decode_js_hex(
            body
        )

        tokens = CDN_TOKEN_RE.findall(
            text
        )

        if tokens:

            return _dedupe_media_urls(
                [
                    (
                        "https://cdn.downloadgram.org/"
                        f"?token={token}"
                    )
                    for token in tokens
                ]
            )

        return _dedupe_media_urls(
            MEDIA_URL_RE.findall(
                text
            )
        )

    async def _from_web_api(
        self,
        session,
        url,
    ):
        if _is_story(url):
            return []

        code = _shortcode(
            url
        )

        if not code:
            return []

        try:
            media_pk = (
                _shortcode_to_pk(
                    code
                )
            )
        except ValueError:
            media_pk = None

        endpoints = []

        if media_pk:

            endpoints.extend(
                [
                    (
                        "https://www.instagram.com/"
                        f"api/v1/media/{media_pk}/info/"
                    ),
                    (
                        "https://i.instagram.com/"
                        f"api/v1/media/{media_pk}/info/"
                    ),
                ]
            )

        endpoints.extend(
            [
                (
                    "https://www.instagram.com/"
                    f"p/{code}/?__a=1&__d=dis"
                ),
                (
                    "https://www.instagram.com/"
                    f"reel/{code}/?__a=1&__d=dis"
                ),
            ]
        )

        for endpoint in endpoints:

            try:

                data = await self._get_json(
                    session,
                    endpoint,
                    headers=_ig_request_headers(),
                )

                if not data:
                    continue

                items = (
                    data.get("items")
                    if isinstance(
                        data,
                        dict,
                    )
                    else None
                )

                if items:

                    urls = (
                        _dedupe_media_urls(
                            _urls_from_media_item(
                                items[0]
                            )
                        )
                    )

                else:

                    urls = (
                        _dedupe_media_urls(
                            _urls_from_obj(
                                data
                            )
                        )
                    )

                if urls:
                    return urls

            except Exception as er:

                LOGS.info(
                    "IG web api miss "
                    f"({endpoint}): {er}"
                )

        return []

    async def _saveinsta_page_tokens(
        self,
        session,
        force=False,
    ):
        now = time.time()

        if (
            not force
            and _SAVEINSTA_PAGE_TOKENS[
                "k_exp"
            ]
            and _SAVEINSTA_PAGE_TOKENS[
                "k_token"
            ]
            and (
                now
                - (
                    _SAVEINSTA_PAGE_TOKENS[
                        "ts"
                    ]
                    or 0
                )
                < 300
            )
        ):

            return (
                _SAVEINSTA_PAGE_TOKENS[
                    "k_exp"
                ],
                _SAVEINSTA_PAGE_TOKENS[
                    "k_token"
                ],
            )

        pages = (
            SAVEINSTA_HOME,
            f"{SAVEINSTA}/en/",
            f"{SAVEINSTA}/",
        )

        headers = {
            "User-Agent": UA,
            "Accept":
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language":
                "en-US,en;q=0.9",
        }

        for page in pages:

            try:

                async with session.get(
                    page,
                    headers=headers,
                    allow_redirects=True,
                ) as response:

                    if response.status != 200:
                        continue

                    text = await response.text()

            except Exception as er:

                LOGS.info(
                    f"saveinsta page miss: {er}"
                )

                continue

            exp = (
                re.search(
                    r'k_exp\s*=\s*["\']?([0-9]+)',
                    text,
                )
                or re.search(
                    r'k_exp["\'\s:=]+([0-9]+)',
                    text,
                )
            )

            token = (
                re.search(
                    r'k_token\s*=\s*["\']'
                    r'([A-Za-z0-9]+)',
                    text,
                )
                or re.search(
                    r'k_token["\'\s:=]+'
                    r'([A-Za-z0-9]+)',
                    text,
                )
            )

            if exp and token:

                _SAVEINSTA_PAGE_TOKENS[
                    "k_exp"
                ] = exp.group(1)

                _SAVEINSTA_PAGE_TOKENS[
                    "k_token"
                ] = token.group(1)

                _SAVEINSTA_PAGE_TOKENS[
                    "ts"
                ] = now

                return (
                    exp.group(1),
                    token.group(1),
                )

        return None, None

    def _parse_saveinsta_html(
        self,
        text,
    ):
        urls = SNAPCDN_RE.findall(
            text or ""
        )

        if not urls:
            urls = MEDIA_URL_RE.findall(
                text or ""
            )

        downloads = [
            url
            for url in urls
            if "dl.snapcdn.app"
            in url.lower()
        ]

        if downloads:

            videos = []

            for url in downloads:

                payload = _jwt_payload(
                    url.split(
                        "token=",
                        1,
                    )[-1]
                )

                filename = (
                    payload.get(
                        "filename"
                    )
                    or ""
                ).lower()

                source = (
                    payload.get(
                        "url"
                    )
                    or ""
                ).lower()

                if (
                    ".mp4" in filename
                    or ".mp4" in source
                ):
                    videos.append(
                        url
                    )

            return _dedupe_media_urls(
                videos
                or downloads
            )

        return _dedupe_media_urls(
            urls
        )

    async def _saveinsta_search_once(
        self,
        session,
        url,
        k_exp,
        k_token,
    ):
        headers = {
            "User-Agent": UA,
            "X-Requested-With":
                "XMLHttpRequest",
            "Origin": SAVEINSTA,
            "Referer": SAVEINSTA_HOME,
            "Content-Type":
                "application/x-www-form-urlencoded;"
                " charset=UTF-8",
            "Accept": "*/*",
            "Accept-Language":
                "en-US,en;q=0.9",
        }

        async with session.post(
            SAVEINSTA_VERIFY,
            data={
                "url": url
            },
            headers=headers,
        ) as response:

            raw = await response.text()

            if response.status >= 400:
                return []

            try:
                verify = json.loads(
                    raw
                )
            except Exception:
                return []

        cftoken = (
            (verify or {}).get(
                "token"
            )
            or ""
        )

        if not cftoken:
            return []

        async with session.post(
            SAVEINSTA_SEARCH,
            data={
                "k_exp": k_exp,
                "k_token": k_token,
                "q": url,
                "t": "media",
                "lang": "en",
                "v": "v2",
                "cftoken": cftoken,
            },
            headers=headers,
        ) as response:

            body = await response.text()

            if (
                response.status >= 400
                or not body
            ):
                return None

        try:
            data = json.loads(
                body
            )
        except Exception:
            return []

        message = str(
            data.get("mess")
            or data.get("message")
            or ""
        )

        status = (
            data.get("status")
            or ""
        ).lower()

        if (
            message
            and "token"
            in message.lower()
        ):
            return None

        if (
            status
            and status not in (
                "ok",
                "success",
            )
        ):
            return []

        html = (
            data.get("data")
            if isinstance(
                data.get("data"),
                str,
            )
            else ""
        )

        if not html:
            return []

        return self._parse_saveinsta_html(
            html
        )

    def _story_query_url(
        self,
        url,
    ):
        match = STORY_RE.search(
            url
        )

        if not match:
            return url

        is_highlight = (
            match.group(1)
        )

        part1 = match.group(2)
        part2 = match.group(3)

        if (
            is_highlight
            or part1.lower()
            == "highlights"
        ):

            highlight_id = (
                part2
                if part1.lower()
                == "highlights"
                else part1
            )

            if highlight_id:
                return (
                    "https://www.instagram.com/"
                    "stories/highlights/"
                    f"{highlight_id}/"
                )

            return url

        if part2:

            return (
                "https://www.instagram.com/"
                f"stories/{part1}/{part2}/"
            )

        return (
            "https://www.instagram.com/"
            f"stories/{part1}/"
        )

    async def _from_saveinsta_story(
        self,
        session,
        url,
    ):
        queries = []

        for query in (
            url,
            self._story_query_url(url),
        ):

            if (
                query
                and query not in queries
            ):
                queries.append(
                    query
                )

        match = STORY_RE.search(
            url
        )

        if match and not (
            match.group(1)
            or match.group(2).lower()
            == "highlights"
        ):

            username = match.group(2)

            for query in (
                (
                    "https://www.instagram.com/"
                    f"stories/{username}/"
                ),
                (
                    "https://instagram.com/"
                    f"stories/{username}/"
                ),
            ):

                if query not in queries:
                    queries.append(
                        query
                    )

        last_error = None

        for force in (
            False,
            True,
        ):

            k_exp, k_token = (
                await self._saveinsta_page_tokens(
                    session,
                    force=force,
                )
            )

            if not k_exp or not k_token:
                last_error = (
                    "missing page tokens"
                )
                continue

            for query in queries:

                try:

                    result = (
                        await self._saveinsta_search_once(
                            session,
                            query,
                            k_exp,
                            k_token,
                        )
                    )

                except Exception as er:

                    last_error = str(er)

                    _SAVEINSTA_PAGE_TOKENS[
                        "k_exp"
                    ] = None

                    _SAVEINSTA_PAGE_TOKENS[
                        "k_token"
                    ] = None

                    _SAVEINSTA_PAGE_TOKENS[
                        "ts"
                    ] = 0

                    break

                if result is None:

                    _SAVEINSTA_PAGE_TOKENS[
                        "k_exp"
                    ] = None

                    _SAVEINSTA_PAGE_TOKENS[
                        "k_token"
                    ] = None

                    _SAVEINSTA_PAGE_TOKENS[
                        "ts"
                    ] = 0

                    last_error = (
                        "invalid token"
                    )

                    break

                if result:
                    return result

            else:
                continue

        if last_error:
            LOGS.info(
                f"saveinsta story failed: {last_error}"
            )

        return []

    async def _from_story_api(
        self,
        session,
        url,
    ):
        return await self._from_saveinsta_story(
            session,
            url,
        )

    async def _from_embed(
        self,
        session,
        url,
    ):
        if _is_story(url):
            return []

        code = _shortcode(
            url
        )

        if not code:
            return []

        embed = (
            "https://www.instagram.com/"
            f"p/{code}/embed/captioned/"
        )

        try:

            async with session.get(
                embed,
                headers=_ig_request_headers(),
            ) as response:

                if response.status != 200:
                    return []

                text = await response.text()

        except Exception as er:

            LOGS.info(
                f"IG embed miss: {er}"
            )

            return []

        urls = []

        for key in (
            "video_url",
            "display_url",
            "contentUrl",
        ):

            pattern = (
                rf'{key}["\']?\s*[:=]\s*'
                rf'["\']([^"\']+)'
            )

            for match in re.finditer(
                pattern,
                text,
            ):
                urls.append(
                    match.group(1)
                )

        for match in re.finditer(
            r'property="og:(?:video|image)" '
            r'content="([^"]+)"',
            text,
        ):
            urls.append(
                match.group(1)
            )

        urls.extend(
            MEDIA_URL_RE.findall(
                text
            )
        )

        return _dedupe_media_urls(
            urls
        )

    async def _from_savers(
        self,
        session,
        url,
    ):
        payloads = [
            (
                "https://saveinsta.to/api/ajaxSearch",
                {
                    "q": url,
                    "t": "media",
                    "lang": "en",
                },
                {
                    "User-Agent": UA,
                    "X-Requested-With":
                        "XMLHttpRequest",
                    "Origin":
                        "https://saveinsta.to",
                    "Referer":
                        "https://saveinsta.to/",
                },
            ),
            (
                "https://gramsnap.com/api/ajaxSearch",
                {
                    "q": url,
                    "t": "media",
                    "lang": "en",
                },
                {
                    "User-Agent": UA,
                    "X-Requested-With":
                        "XMLHttpRequest",
                },
            ),
        ]

        if _is_story(url):

            payloads.append(
                (
                    "https://instanavigation.com/"
                    "api/ajaxSearch",
                    {
                        "q": url,
                        "t": "media",
                        "lang": "en",
                    },
                    {
                        "User-Agent": UA,
                        "X-Requested-With":
                            "XMLHttpRequest",
                    },
                )
            )

        for (
            endpoint,
            data,
            headers,
        ) in payloads:

            try:

                async with session.post(
                    endpoint,
                    data=data,
                    headers=headers,
                ) as response:

                    body = await response.text()

                if (
                    response.status >= 400
                    or not body
                ):
                    continue

                found = []

                try:

                    data = json.loads(
                        body
                    )

                    found.extend(
                        _urls_from_obj(
                            data
                        )
                    )

                    html = data.get(
                        "data"
                    )

                    if isinstance(
                        html,
                        str,
                    ):
                        found.extend(
                            re.findall(
                                r"https://[^\"'\s<>]+",
                                html,
                            )
                        )

                except Exception:

                    found.extend(
                        re.findall(
                            r"https://[^\"'\s<>]+",
                            body,
                        )
                    )

                media = [
                    url.replace(
                        "\\/",
                        "/",
                    )
                    for url in found
                    if any(
                        item in url.lower()
                        for item in (
                            ".mp4",
                            ".jpg",
                            "cdninstagram",
                            "scontent",
                            "downloadgram",
                        )
                    )
                ]

                media = (
                    _dedupe_media_urls(
                        media
                    )
                )

                if media:
                    return media

            except Exception as er:

                LOGS.info(
                    f"IG saver miss "
                    f"({endpoint}): {er}"
                )

        return []

    async def resolve(
        self,
        url,
    ):
        url = _normalize_url(
            url
        )

        story = _is_story(
            url
        )

        timeout = (
            ClientTimeout(
                total=90,
                connect=20,
                sock_read=60,
            )
            if story
            else self.timeout
        )

        jar = (
            CookieJar(
                unsafe=True
            )
            if story
            else None
        )

        async with ClientSession(
            timeout=timeout,
            cookie_jar=jar,
        ) as session:

            if story:

                urls = (
                    await self._from_story_api(
                        session,
                        url,
                    )
                )

                if urls:
                    return (
                        urls,
                        "saveinsta-story",
                    )

                return [], None

            urls = (
                await self._from_downloadgram(
                    session,
                    url,
                )
            )

            if urls:
                return (
                    urls,
                    "downloadgram",
                )

            urls = (
                await self._from_web_api(
                    session,
                    url,
                )
            )

            if urls:
                return (
                    urls,
                    "ig-api",
                )

            urls = (
                await self._from_embed(
                    session,
                    url,
                )
            )

            if urls:
                return (
                    urls,
                    "embed",
                )

            urls = (
                await self._from_savers(
                    session,
                    url,
                )
            )

            if urls:
                return (
                    urls,
                    "saver",
                )

        return [], None

    async def fetch_to_disk(
        self,
        media_urls,
        outdir,
    ):
        saved = []

        async with ClientSession(
            timeout=ClientTimeout(
                total=120,
                connect=10,
            )
        ) as session:

            for index, media in enumerate(
                media_urls
            ):

                ext = _guess_ext(
                    media
                )

                path = os.path.join(
                    outdir,
                    f"ig_{index}{ext}",
                )

                try:

                    headers = {
                        "User-Agent": UA
                    }

                    if (
                        "snapcdn.app"
                        in media.lower()
                    ):
                        headers[
                            "Referer"
                        ] = (
                            "https://saveinsta.to/"
                        )

                    elif (
                        "downloadgram"
                        in media.lower()
                    ):
                        headers[
                            "Referer"
                        ] = (
                            "https://downloadgram.org/"
                        )

                    async with session.get(
                        media,
                        headers=headers,
                    ) as response:

                        if response.status != 200:
                            continue

                        with open(
                            path,
                            "wb",
                        ) as file:

                            async for chunk in (
                                response.content.iter_chunked(
                                    64 * 1024
                                )
                            ):
                                file.write(
                                    chunk
                                )

                    if (
                        os.path.getsize(
                            path
                        ) > 0
                    ):
                        saved.append(
                            path
                        )

                except Exception as er:

                    LOGS.info(
                        f"IG media download failed: {er}"
                    )

        return saved

    async def download_files(
        self,
        url,
        outdir,
    ):
        url = _normalize_url(
            url
        )

        story = _is_story(
            url
        )

        media_urls, source = (
            await self.resolve(
                url
            )
        )

        if media_urls:

            files = _dedupe_files(
                await self.fetch_to_disk(
                    media_urls,
                    outdir,
                )
            )

            if files:
                return (
                    files,
                    source or "http",
                )

        if story:
            return [], None

        if not udB.get_key(
            "IG_SKIP_YTDLP"
        ):

            files = _dedupe_files(
                await _ytdlp_download(
                    url,
                    outdir,
                )
            )

            if files:
                return (
                    files,
                    "ytdlp",
                )

        return [], None


# ============================================================================
# TELEGRAM MEDIA HELPERS
# ============================================================================

async def _send_ig_media(
    client,
    chat_id,
    items,
    caption,
    reply_to=None,
):
    if not items:
        return False

    if all(
        isinstance(
            item,
            str,
        )
        for item in items
    ):

        if all(
            os.path.isfile(item)
            for item in items
        ):
            items = _dedupe_files(
                items
            )
        else:
            items = _dedupe_media_urls(
                items
            )

    else:

        unique = []
        seen = set()

        for item in items:

            key = getattr(
                item,
                "id",
                None,
            )

            if key is None:
                key = id(item)

            if key in seen:
                continue

            seen.add(key)
            unique.append(item)

        items = unique

    if not items:
        return False

    kwargs = {
        "caption": caption,
        "force_document": False,
        "supports_streaming": True,
        "reply_to": reply_to,
    }

    if len(items) == 1:

        await client.send_file(
            chat_id,
            items[0],
            **kwargs,
        )

    else:

        await client.send_file(
            chat_id,
            items,
            **kwargs,
        )

    return True


async def _download_remote_urls(
    urls,
    tmp,
):
    paths = []

    async with ClientSession(
        timeout=ClientTimeout(
            total=120
        )
    ) as session:

        for index, url in enumerate(
            urls
        ):

            path = os.path.join(
                tmp,
                (
                    f"ig_remote_{index}"
                    f"{_guess_ext(url)}"
                ),
            )

            try:

                headers = {
                    "User-Agent": UA
                }

                if (
                    "snapcdn.app"
                    in url.lower()
                ):
                    headers[
                        "Referer"
                    ] = (
                        "https://saveinsta.to/"
                    )

                elif (
                    "downloadgram"
                    in url.lower()
                ):
                    headers[
                        "Referer"
                    ] = (
                        "https://downloadgram.org/"
                    )

                async with session.get(
                    url,
                    headers=headers,
                ) as response:

                    if response.status != 200:
                        continue

                    with open(
                        path,
                        "wb",
                    ) as file:

                        async for chunk in (
                            response.content.iter_chunked(
                                64 * 1024
                            )
                        ):
                            file.write(
                                chunk
                            )

                if (
                    os.path.exists(path)
                    and os.path.getsize(path)
                    > 0
                ):
                    paths.append(
                        path
                    )

            except Exception as er:

                LOGS.info(
                    f"IG remote download failed: {er}"
                )

    return _dedupe_files(
        paths
    )


async def _via_telegram_bot(
    client,
    chat_id,
    url,
    caption,
    reply_to=None,
):
    bots = udB.get_key(
        "IG_SAVER_BOT"
    ) or [
        "@instasave_bot",
        "@TopSaverBot",
    ]

    if isinstance(
        bots,
        str,
    ):
        bots = [bots]

    for bot in bots:

        try:

            async with client.conversation(
                bot,
                timeout=60,
            ) as conv:

                request_msg = (
                    await conv.send_message(
                        url
                    )
                )

                responses = []

                try:
                    responses.append(
                        await conv.get_response()
                    )
                except asyncio.TimeoutError:
                    continue

                if not responses[-1].media:

                    try:

                        responses.append(
                            await conv.get_response(
                                timeout=25
                            )
                        )

                    except Exception:
                        pass

                media = [
                    message.media
                    for message in responses
                    if (
                        message
                        and message.media
                    )
                ]

                if not media:

                    await asyncio.sleep(2)

                    messages = (
                        await client.get_messages(
                            bot,
                            min_id=request_msg.id,
                            limit=10,
                        )
                    )

                    media = [
                        message.media
                        for message in reversed(
                            messages
                        )
                        if (
                            message
                            and message.media
                        )
                    ]

                if media:

                    await _send_ig_media(
                        client,
                        chat_id,
                        media,
                        caption,
                        reply_to,
                    )

                    return True

        except YouBlockedUserError:

            LOGS.info(
                f"Unblock {bot} to use Instagram fallback"
            )

        except Exception as er:

            LOGS.info(
                f"Telegram saver bot miss ({bot}): {er}"
            )

    return False


async def _download_via_telegram_bot(
    client,
    url,
    outdir,
):
    """
    Inline-safe Telegram saver fallback.

    The returned Telegram media is downloaded locally instead of being sent
    to a normal chat. This allows the inline callback to upload the media
    into the existing inline message.
    """
    bots = udB.get_key(
        "IG_SAVER_BOT"
    ) or [
        "@instasave_bot",
        "@TopSaverBot",
    ]

    if isinstance(
        bots,
        str,
    ):
        bots = [bots]

    for bot in bots:

        try:

            async with client.conversation(
                bot,
                timeout=70,
            ) as conv:

                request_msg = (
                    await conv.send_message(
                        url
                    )
                )

                responses = []

                try:

                    responses.append(
                        await conv.get_response()
                    )

                except asyncio.TimeoutError:
                    continue

                if not responses[-1].media:

                    try:

                        responses.append(
                            await conv.get_response(
                                timeout=30
                            )
                        )

                    except Exception:
                        pass

                media_messages = [
                    message
                    for message in responses
                    if (
                        message
                        and message.media
                    )
                ]

                if not media_messages:

                    try:

                        messages = (
                            await client.get_messages(
                                bot,
                                min_id=request_msg.id,
                                limit=12,
                            )
                        )

                        media_messages = [
                            message
                            for message in reversed(
                                messages
                            )
                            if (
                                message
                                and message.media
                            )
                        ]

                    except Exception:
                        media_messages = []

                if not media_messages:
                    continue

                files = []

                for index, message in enumerate(
                    media_messages[
                        :INLINE_MAX_MEDIA
                    ]
                ):

                    try:

                        path = (
                            await client.download_media(
                                message,
                                file=os.path.join(
                                    outdir,
                                    f"ig_bot_{index}",
                                ),
                            )
                        )

                        if (
                            path
                            and os.path.isfile(path)
                        ):
                            files.append(
                                path
                            )

                    except Exception as er:

                        LOGS.info(
                            "IG inline saver media "
                            f"download failed: {er}"
                        )

                files = _dedupe_files(
                    files
                )

                if files:

                    return (
                        files,
                        f"telegram:{bot}",
                    )

        except YouBlockedUserError:

            LOGS.info(
                f"Unblock {bot} to use Instagram inline fallback"
            )

        except Exception as er:

            LOGS.info(
                f"Instagram inline saver bot miss "
                f"({bot}): {er}"
            )

    return [], None


# ============================================================================
# INLINE STATE MANAGEMENT
# ============================================================================

def _remove_inline_tmp(
    tmpdir,
):
    if not tmpdir:
        return

    try:

        for path in glob.glob(
            os.path.join(
                tmpdir,
                "*",
            )
        ):

            try:
                os.remove(path)
            except OSError:
                pass

        os.rmdir(
            tmpdir
        )

    except OSError:
        pass


def _cleanup_inline_state():
    now = time.time()

    expired = []

    for token, state in list(
        _INLINE_STATE.items()
    ):

        if (
            now
            - state.get(
                "created",
                0,
            )
            > INLINE_STATE_TTL
        ):
            expired.append(
                token
            )

    for token in expired:

        state = _INLINE_STATE.pop(
            token,
            None,
        )

        if state:
            _remove_inline_tmp(
                state.get(
                    "tmpdir"
                )
            )


def _new_inline_token():
    return hashlib.sha256(
        (
            f"{time.time_ns()}:"
            f"{os.urandom(16).hex()}"
        ).encode()
    ).hexdigest()[:20]


def _inline_caption(
    url,
    source=None,
):
    label = _label_for(
        url
    )

    suffix = (
        f" • `{source}`"
        if source
        else ""
    )

    return (
        f"📸 **Instagram {label}**"
        f"{suffix}\n"
        f"🔗 {url}"
    )


def _inline_result_buttons(
    token,
):
    state = _INLINE_STATE[
        token
    ]

    return [
        [
            Button.inline(
                "⬇️ Download",
                data=(
                    f"igdl:{token}:0"
                ),
            ),
            Button.url(
                "🔗 Open",
                url=state["url"],
            ),
        ],
        [
            Button.inline(
                "✖️ Cancel",
                data=(
                    f"igclose:{token}"
                ),
            )
        ],
    ]


def _inline_page_buttons(
    token,
    index,
    total,
):
    state = _INLINE_STATE[
        token
    ]

    rows = []

    if total > 1:

        rows.append(
            [
                Button.inline(
                    "◀️",
                    data=(
                        f"igdl:{token}:"
                        f"{max(0, index - 1)}"
                    ),
                ),
                Button.inline(
                    f"{index + 1}/{total}",
                    data=(
                        f"igdl:{token}:"
                        f"{index}"
                    ),
                ),
                Button.inline(
                    "▶️",
                    data=(
                        f"igdl:{token}:"
                        f"{min(total - 1, index + 1)}"
                    ),
                ),
            ]
        )

    rows.append(
        [
            Button.url(
                "🔗 Open Instagram",
                url=state["url"],
            ),
            Button.inline(
                "🗑 Close",
                data=(
                    f"igclose:{token}"
                ),
            ),
        ]
    )

    return rows


def _inline_error(
    text,
):
    return (
        "❌ **Instagram**\n\n"
        f"{html_lib.escape(str(text)[:300])}"
    )


async def _inline_edit_media(
    event,
    token,
    index,
):
    state = _INLINE_STATE.get(
        token
    )

    if not state:

        return await event.answer(
            "This Instagram download has expired.",
            alert=True,
        )

    if (
        time.time()
        - state.get(
            "created",
            0,
        )
        > INLINE_STATE_TTL
    ):

        _INLINE_STATE.pop(
            token,
            None,
        )

        _remove_inline_tmp(
            state.get(
                "tmpdir"
            )
        )

        return await event.answer(
            "This Instagram download has expired.",
            alert=True,
        )

    files = (
        state.get(
            "files"
        )
        or []
    )

    if not files:

        return await event.answer(
            "No downloaded media is available.",
            alert=True,
        )

    index = max(
        0,
        min(
            index,
            len(files) - 1,
        ),
    )

    path = files[
        index
    ]

    if not os.path.isfile(
        path
    ):

        return await event.answer(
            "This media file is no longer available.",
            alert=True,
        )

    state["index"] = index
    state["updated"] = time.time()

    caption = (
        "📸 **Instagram**\n"
        f"`{index + 1}/{len(files)}`\n\n"
        f"{_label_for(state['url'])}\n"
        f"🔗 {state['url']}"
    )

    buttons = _inline_page_buttons(
        token,
        index,
        len(files),
    )

    try:

        await event.edit(
            caption,
            file=path,
            buttons=buttons,
            link_preview=False,
        )

    except Exception:

        await event.edit(
            file=path,
            text=caption,
            buttons=buttons,
            link_preview=False,
        )


# ============================================================================
# INLINE QUERY
# ============================================================================

@in_pattern(
    r"(?i)^ig(?:\s+(.+))?$"
)
async def instagram_inline(
    event,
):
    """
    Usage:

        @AssistantBot ig <Instagram link>
    """
    _cleanup_inline_state()

    raw = ""

    try:

        raw = (
            event.pattern_match.group(1)
            or ""
        ).strip()

    except Exception:
        raw = ""

    if not raw:

        result = (
            await event.builder.article(
                title=(
                    "📸 Instagram Downloader"
                ),
                description=(
                    "Download Instagram "
                    "posts, reels, stories "
                    "and highlights."
                ),
                text=(
                    "📸 **Instagram Downloader**\n\n"
                    "Send an Instagram link after `ig`.\n\n"
                    "Examples:\n"
                    "`@AssistantBot ig https://www.instagram.com/p/...`\n"
                    "`@AssistantBot ig https://www.instagram.com/reel/...`\n"
                    "`@AssistantBot ig https://www.instagram.com/stories/...`\n"
                    "`@AssistantBot ig https://www.instagram.com/stories/highlights/...`"
                ),
            )
        )

        return await event.answer(
            [result],
            cache_time=2,
        )

    match = IG_URL_RE.search(
        raw
    )

    if not match:

        result = (
            await event.builder.article(
                title=(
                    "❌ Invalid Instagram link"
                ),
                description=(
                    "The query does not contain "
                    "a supported Instagram URL."
                ),
                text=_inline_error(
                    "Please provide a valid Instagram post, reel, story, highlight or TV link."
                ),
            )
        )

        return await event.answer(
            [result],
            cache_time=2,
        )

    url = _normalize_url(
        match.group(0)
    )

    token = _new_inline_token()

    _INLINE_STATE[token] = {
        "created": time.time(),
        "updated": time.time(),
        "user_id": getattr(
            event,
            "sender_id",
            None,
        ),
        "url": url,
        "files": [],
        "tmpdir": None,
        "index": 0,
        "source": None,
        "lock": asyncio.Lock(),
    }

    kind = (
        "Story"
        if _is_story(url)
        else "Post / Reel"
    )

    result = (
        await event.builder.article(
            title=(
                f"📸 Instagram {kind}"
            ),
            description=(
                "Ready to download media "
                "from this Instagram link."
            ),
            text=(
                f"📸 **Instagram {kind}**\n\n"
                f"🔗 `{url}`\n\n"
                "Press **Download** to fetch the media.\n"
                "Carousel posts and stories can be "
                "browsed with Previous/Next."
            ),
            buttons=_inline_result_buttons(
                token
            ),
        )
    )

    return await event.answer(
        [result],
        cache_time=0,
        gallery=False,
    )


# ============================================================================
# INLINE DOWNLOAD CALLBACK
# ============================================================================

@callback(
    re.compile(
        r"^igdl:"
        r"([A-Za-z0-9_-]{12,32})"
        r"(?::(\d+))?$"
    )
)
async def instagram_inline_download(
    event,
):
    _cleanup_inline_state()

    try:

        token = event.data_match.group(
            1
        )

        if isinstance(
            token,
            bytes,
        ):
            token = token.decode()

        raw_index = (
            event.data_match.group(
                2
            )
        )

        if isinstance(
            raw_index,
            bytes,
        ):
            raw_index = (
                raw_index.decode()
            )

        index = int(
            raw_index or 0
        )

    except Exception:

        return await event.answer(
            "Invalid Instagram download request.",
            alert=True,
        )

    state = _INLINE_STATE.get(
        token
    )

    if not state:

        return await event.answer(
            "This Instagram request has expired.",
            alert=True,
        )

    async with state["lock"]:

        if state.get(
            "files"
        ):

            return await _inline_edit_media(
                event,
                token,
                index,
            )

        await event.answer(
            "Downloading Instagram media...",
            alert=False,
        )

        url = state["url"]

        tmp = None

        try:

            dl_root = (
                "resources/downloads"
            )

            try:

                os.makedirs(
                    dl_root,
                    exist_ok=True,
                )

                tmp = tempfile.mkdtemp(
                    prefix="ig_inline_",
                    dir=dl_root,
                )

            except OSError:

                tmp = tempfile.mkdtemp(
                    prefix="ig_inline_"
                )

            state[
                "tmpdir"
            ] = tmp

            insta = Instagram()

            files, source = (
                await insta.download_files(
                    url,
                    tmp,
                )
            )

            if not files:

                urls, resolve_source = (
                    await insta.resolve(
                        url
                    )
                )

                source = (
                    source
                    or resolve_source
                )

                if urls:

                    files = (
                        await _download_remote_urls(
                            urls,
                            tmp,
                        )
                    )

            files = _dedupe_files(
                files
            )

            files = files[
                :INLINE_MAX_MEDIA
            ]

            if (
                not files
                and not _is_story(url)
            ):

                files, saver_source = (
                    await _download_via_telegram_bot(
                        event.client,
                        url,
                        tmp,
                    )
                )

                source = (
                    source
                    or saver_source
                )

            files = _dedupe_files(
                files
            )

            if not files:

                if _is_story(url):

                    text = (
                        "❌ **No Instagram story media was found.**\n\n"
                        "The story may be private, expired, "
                        "or require an authenticated Instagram session."
                    )

                else:

                    text = (
                        "❌ **Instagram media could not be downloaded.**\n\n"
                        "No compatible resolver or saver source returned media."
                    )

                await event.edit(
                    text,
                    buttons=[
                        [
                            Button.url(
                                "🔗 Open Instagram",
                                url=url,
                            )
                        ]
                    ],
                    link_preview=False,
                )

                _INLINE_STATE.pop(
                    token,
                    None,
                )

                _remove_inline_tmp(
                    tmp
                )

                return

            state[
                "files"
            ] = files

            state[
                "source"
            ] = source

            state[
                "updated"
            ] = time.time()

            await _inline_edit_media(
                event,
                token,
                0,
            )

        except Exception as exc:

            LOGS.exception(
                "Instagram inline download failed: %s",
                exc,
            )

            try:

                await event.edit(
                    _inline_error(
                        f"Download failed: {exc}"
                    ),
                    buttons=[
                        [
                            Button.url(
                                "🔗 Open Instagram",
                                url=url,
                            )
                        ]
                    ],
                    link_preview=False,
                )

            except Exception:
                pass

            state = _INLINE_STATE.pop(
                token,
                None,
            )

            if state:
                _remove_inline_tmp(
                    state.get(
                        "tmpdir"
                    )
                )


# ============================================================================
# INLINE CLOSE
# ============================================================================

@callback(
    re.compile(
        r"^igclose:"
        r"([A-Za-z0-9_-]{12,32})$"
    )
)
async def instagram_inline_close(
    event,
):
    _cleanup_inline_state()

    try:

        token = event.data_match.group(
            1
        )

        if isinstance(
            token,
            bytes,
        ):
            token = token.decode()

    except Exception:

        return await event.answer(
            "Invalid request.",
            alert=True,
        )

    state = _INLINE_STATE.pop(
        token,
        None,
    )

    if state:
        _remove_inline_tmp(
            state.get(
                "tmpdir"
            )
        )

    try:

        await event.edit(
            (
                "📸 **Instagram**\n\n"
                "This download result has been closed."
            ),
            buttons=None,
        )

    except Exception:
        pass

    return await event.answer(
        "Closed.",
        alert=False,
    )


# ============================================================================
# COMMAND
# ============================================================================

@heartless_cmd(
    pattern="ig ?(.*)$",
    assistant=True,
    manager=True,
    allow_sudo=True,
)
async def instagram(
    e,
):
    inp = (
        e.pattern_match.group(1)
        or ""
    ).strip()

    if (
        not inp
        and e.is_reply
    ):

        reply = (
            await e.get_reply_message()
        )

        inp = (
            (
                reply.text
                or reply.message
                or ""
            )
            if reply
            else ""
        )

        match = (
            IG_URL_RE.search(inp)
            if inp
            else None
        )

        inp = (
            match.group(0)
            if match
            else ""
        )

    msg = await e.edit(
        get_pstring(
            "{p} **Please Wait...**",
            "load",
        )
    )

    if (
        not inp
        or not IG_URL_RE.search(inp)
    ):

        return await eod(
            msg,
            "❌ Invalid Instagram Link",
            time=3,
        )

    inp = _normalize_url(
        IG_URL_RE.search(
            inp
        ).group(0)
    )

    is_story = _is_story(
        inp
    )

    captions = (
        get_pstring(
            "instagram_1",
            "insta",
        ).format(
            _label_for(inp)
        )
    )

    insta = Instagram()

    dl_root = (
        "resources/downloads"
    )

    try:

        os.makedirs(
            dl_root,
            exist_ok=True,
        )

        tmp = tempfile.mkdtemp(
            prefix="ig_",
            dir=dl_root,
        )

    except OSError:

        tmp = tempfile.mkdtemp(
            prefix="ig_"
        )

    try:

        files, _source = (
            await insta.download_files(
                inp,
                tmp,
            )
        )

        if not files:

            urls, _ = (
                await insta.resolve(
                    inp
                )
            )

            if urls:

                sent = False

                try:

                    sent = (
                        await _send_ig_media(
                            e.client,
                            e.chat_id,
                            urls,
                            captions,
                            reply_to=(
                                e.reply_to_msg_id
                            ),
                        )
                    )

                except (
                    WebpageCurlFailedError,
                    WebpageMediaEmptyError,
                ):
                    sent = False

                if not sent:

                    files = (
                        await _download_remote_urls(
                            urls,
                            tmp,
                        )
                    )

                    if files:

                        sent = (
                            await _send_ig_media(
                                e.client,
                                e.chat_id,
                                files,
                                captions,
                                reply_to=(
                                    e.reply_to_msg_id
                                ),
                            )
                        )

                if sent:
                    return await msg.delete()

            if not is_story:

                ok = (
                    await _via_telegram_bot(
                        e.client,
                        e.chat_id,
                        inp,
                        captions,
                        reply_to=(
                            e.reply_to_msg_id
                        ),
                    )
                )

                if ok:
                    return await msg.delete()

            return await eod(
                msg,
                "❌ No media found",
                time=6,
            )

        await _send_ig_media(
            e.client,
            e.chat_id,
            files,
            captions,
            reply_to=(
                e.reply_to_msg_id
            ),
        )

        await msg.delete()

    except Exception as er:

        LOGS.exception(er)

        await eod(
            msg,
            f"❌ Download failed: `{er}`",
            time=8,
        )

    finally:

        for path in glob.glob(
            os.path.join(
                tmp,
                "*",
            )
        ):

            try:
                os.remove(path)
            except OSError:
                pass

        try:
            os.rmdir(tmp)
        except OSError:
            pass

"""
URL Tools — Inline-only URL intelligence toolkit.

Usage:
    @assistant urltools
    @assistant urltools https://example.com

Direct actions:
    @assistant urltools short https://example.com
    @assistant urltools qr https://example.com
    @assistant urltools screenshot https://example.com
    @assistant urltools whois example.com
    @assistant urltools info https://example.com
    @assistant urltools safe https://example.com

Features:
    • URL Shortener
    • QR Code Generator
    • URL Screenshot / Preview
    • WHOIS / RDAP
    • URL Information / Metadata
    • DNS Information
    • Malicious URL Checker
    • VirusTotal integration
    • URLhaus integration
    • SSRF protection
    • Redirect validation
    • Inline callback UI
    • Session expiration
    • Per-user callback protection

Optional database keys:

    URLTOOLS_VT_API_KEY
        VirusTotal API key

    URLTOOLS_URLHAUS_AUTH_KEY
        URLhaus Auth-Key
"""

import asyncio
import base64
import html
import ipaddress
import json
import re
import secrets
import socket
import time

from collections import OrderedDict
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import aiohttp
import dns.asyncresolver

from telethon import Button
from telethon.tl.types import InputWebDocument

from CythonX._misc._assistant import callback, in_pattern

from . import LOGS, udB


# ============================================================================
# CONFIGURATION
# ============================================================================

PLUGIN_NAME = "URL Tools"

REQUEST_TIMEOUT = 15
CONNECT_TIMEOUT = 7
DNS_TIMEOUT = 4

MAX_HTML_BYTES = 1_500_000
MAX_REDIRECTS = 6

MAX_TITLE_LENGTH = 180
MAX_DESCRIPTION_LENGTH = 320
MAX_STATE_ITEMS = 512
STATE_TTL = 15 * 60

USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; URLTools/1.0; +https://telegram.org)"
)

HTTP_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/json;q=0.9,*/*;q=0.5"
    ),
}

ACTION_ALIASES = {
    "short": "short",
    "shorten": "short",

    "qr": "qr",
    "qrcode": "qr",

    "screenshot": "screenshot",
    "shot": "screenshot",
    "preview": "screenshot",

    "whois": "whois",
    "rdap": "whois",

    "info": "info",
    "metadata": "info",
    "meta": "info",

    "safe": "safe",
    "security": "safe",
    "malicious": "safe",
    "check": "safe",
}


# ============================================================================
# SESSION STATE
# ============================================================================

# token -> {
#     "url": str,
#     "owner": int,
#     "created": float,
#     "expires": float,
# }
_STATE = OrderedDict()


def _state_cleanup():
    """Remove expired sessions and enforce the global state limit."""

    now = time.time()

    expired = []

    for token, state in _STATE.items():
        if state["expires"] <= now:
            expired.append(token)

    for token in expired:
        _STATE.pop(token, None)

    while len(_STATE) > MAX_STATE_ITEMS:
        _STATE.popitem(last=False)


def _state_create(url, owner_id):
    """Create a short-lived callback session."""

    _state_cleanup()

    token = (
        base64.urlsafe_b64encode(
            secrets.token_bytes(8)
        )
        .decode()
        .rstrip("=")
    )

    now = time.time()

    _STATE[token] = {
        "url": url,
        "owner": owner_id,
        "created": now,
        "expires": now + STATE_TTL,
    }

    _STATE.move_to_end(token)

    _state_cleanup()

    return token


def _state_get(token):
    """Get a valid callback session."""

    state = _STATE.get(token)

    if not state:
        return None

    if state["expires"] <= time.time():
        _STATE.pop(token, None)
        return None

    _STATE.move_to_end(token)

    return state


# ============================================================================
# TEXT / VALIDATION HELPERS
# ============================================================================

def _clean(value, limit=500):
    """
    Safely normalize text before putting it into Telegram markdown.
    """

    if value is None:
        return "—"

    value = str(value)

    value = re.sub(
        r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]",
        " ",
        value,
    )

    value = re.sub(r"\s+", " ", value).strip()

    if len(value) > limit:
        return value[:limit] + "…"

    return value


def _domain(url):
    """Extract normalized hostname."""

    try:
        return (urlsplit(url).hostname or "").lower().rstrip(".")
    except Exception:
        return ""


def _is_ip(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _is_private_ip(host):
    """
    Detect local/private/reserved destinations.

    Used for SSRF protection.
    """

    try:
        ip = ipaddress.ip_address(host)

        return any(
            (
                ip.is_private,
                ip.is_loopback,
                ip.is_link_local,
                ip.is_multicast,
                ip.is_reserved,
                ip.is_unspecified,
            )
        )

    except ValueError:
        return False


def normalize_url(raw, require_http=True):
    """
    Normalize and validate a URL.

    Examples:

        example.com
            -> https://example.com/

        https://example.com/test
            -> unchanged except normalization

    Blocked:

        file://
        ftp://
        javascript:
        data:
        URLs containing credentials
    """

    raw = (raw or "").strip()

    raw = raw.strip("<>")

    if not raw:
        raise ValueError("No URL was provided.")

    # Add default scheme.
    if not re.match(
        r"^[a-z][a-z0-9+.-]*://",
        raw,
        re.I,
    ):
        raw = "https://" + raw

    try:
        parts = urlsplit(raw)
    except Exception as exc:
        raise ValueError("Invalid URL format.") from exc

    scheme = parts.scheme.lower()

    if require_http and scheme not in {"http", "https"}:
        raise ValueError(
            "Only HTTP and HTTPS URLs are supported."
        )

    if not parts.hostname:
        raise ValueError(
            "The URL does not contain a valid hostname."
        )

    if parts.username or parts.password:
        raise ValueError(
            "URLs containing username/password are blocked."
        )

    try:
        host = parts.hostname.encode(
            "idna"
        ).decode("ascii").lower()
    except Exception as exc:
        raise ValueError(
            "Invalid hostname."
        ) from exc

    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError(
            "Invalid port number."
        ) from exc

    netloc = host

    if port:
        netloc += f":{port}"

    return urlunsplit(
        (
            scheme,
            netloc,
            parts.path or "/",
            parts.query,
            parts.fragment,
        )
    )


# ============================================================================
# SSRF PROTECTION
# ============================================================================

async def _resolve_public(host):
    """
    Resolve a hostname and reject private/local destinations.

    This is especially important because URL Tools performs
    server-side HTTP requests.
    """

    host = (host or "").strip().lower().rstrip(".")

    if not host:
        raise ValueError(
            "Hostname is empty."
        )

    # Direct IP.
    if _is_ip(host):

        if _is_private_ip(host):
            raise ValueError(
                "Local, private or reserved IP addresses "
                "are not allowed."
            )

        return {host}

    # Local/internal DNS suffixes.
    blocked_suffixes = (
        ".localhost",
        ".local",
        ".internal",
        ".home.arpa",
    )

    if host.endswith(blocked_suffixes):
        raise ValueError(
            "Local/internal hostnames are not allowed."
        )

    loop = asyncio.get_running_loop()

    try:
        infos = await loop.run_in_executor(
            None,
            lambda: socket.getaddrinfo(
                host,
                None,
                type=socket.SOCK_STREAM,
            ),
        )
    except socket.gaierror as exc:
        raise ValueError(
            "Hostname could not be resolved."
        ) from exc

    addresses = {
        item[4][0]
        for item in infos
        if item and item[4]
    }

    if not addresses:
        raise ValueError(
            "Hostname could not be resolved."
        )

    for address in addresses:

        if _is_private_ip(address):
            raise ValueError(
                "The hostname resolves to a "
                "local/private/reserved address."
            )

    return addresses


# ============================================================================
# TELEGRAM BUTTONS
# ============================================================================

def _home_buttons(token):

    return [
        [
            Button.inline(
                "✂️ Shorten",
                data=f"ut:{token}:short",
            ),
            Button.inline(
                "◈ QR Code",
                data=f"ut:{token}:qr",
            ),
        ],
        [
            Button.inline(
                "🖼 Screenshot",
                data=f"ut:{token}:screenshot",
            ),
            Button.inline(
                "🌐 Whois",
                data=f"ut:{token}:whois",
            ),
        ],
        [
            Button.inline(
                "ℹ️ URL Info",
                data=f"ut:{token}:info",
            ),
            Button.inline(
                "🛡 Security",
                data=f"ut:{token}:safe",
            ),
        ],
    ]


def _back_button(token):
    return [
        [
            Button.inline(
                "‹ Back to URL Tools",
                data=f"ut:{token}:home",
            )
        ]
    ]


def _web_document(url, mime="image/png"):
    """
    Create Telegram InputWebDocument.

    Used for inline image results.
    """

    return InputWebDocument(
        url=url,
        size=0,
        mime_type=mime,
        attributes=[],
    )


# ============================================================================
# HOME
# ============================================================================

def _home_text(url):

    return (
        "**🔗 URL Tools**\n\n"
        f"**Target:** `{_clean(url, 350)}`\n\n"
        "**Available tools:**\n"
        "• ✂️ URL Shortener\n"
        "• ◈ QR Code Generator\n"
        "• 🖼 URL Screenshot / Preview\n"
        "• 🌐 WHOIS / RDAP\n"
        "• ℹ️ URL Info & Metadata\n"
        "• 🛡 Malicious URL Checker\n\n"
        "_Select an operation below._"
    )


def _help_text():

    return (
        "**🔗 URL Tools**\n\n"
        "A complete inline URL intelligence toolkit.\n\n"
        "**Usage**\n"
        "`urltools https://example.com`\n\n"
        "**Direct actions**\n"
        "`urltools short https://example.com`\n"
        "`urltools qr https://example.com`\n"
        "`urltools screenshot https://example.com`\n"
        "`urltools whois example.com`\n"
        "`urltools info https://example.com`\n"
        "`urltools safe https://example.com`\n\n"
        "**Features**\n"
        "✂️ Shorten URLs\n"
        "◈ Generate QR codes\n"
        "🖼 Capture webpage screenshots\n"
        "🌐 RDAP domain lookup\n"
        "ℹ️ HTTP/HTML/DNS metadata\n"
        "🛡 VirusTotal + URLhaus checks"
    )


# ============================================================================
# HTTP
# ============================================================================

def _client_timeout():
    return aiohttp.ClientTimeout(
        total=REQUEST_TIMEOUT,
        connect=CONNECT_TIMEOUT,
        sock_read=REQUEST_TIMEOUT,
    )


async def _request_json(
    url,
    *,
    method="GET",
    headers=None,
    data=None,
):
    """
    Generic HTTP request helper.
    """

    timeout = _client_timeout()

    async with aiohttp.ClientSession(
        timeout=timeout,
        trust_env=False,
    ) as session:

        async with session.request(
            method,
            url,
            headers=headers,
            data=data,
        ) as response:

            body = await response.text(
                errors="replace"
            )

            if response.status >= 400:
                raise RuntimeError(
                    f"HTTP {response.status}: "
                    f"{_clean(body, 220)}"
                )

            return (
                response.status,
                body,
                dict(response.headers),
            )


# ============================================================================
# URL SHORTENER
# ============================================================================

async def shorten_url(url):
    """
    Shorten a URL using is.gd.

    No API key is required.
    """

    endpoint = (
        "https://is.gd/create.php"
        "?format=json&url="
        + quote(url, safe="")
    )

    _, body, _ = await _request_json(
        endpoint
    )

    try:
        data = json.loads(body)
    except Exception as exc:
        raise RuntimeError(
            "Shortener returned an invalid response."
        ) from exc

    short_url = data.get("shorturl")

    if short_url:
        return short_url

    error = data.get(
        "errormessage"
    ) or "Unable to shorten this URL."

    raise RuntimeError(error)


# ============================================================================
# QR CODE
# ============================================================================

def qr_url(url):
    """
    QRServer/goQR image endpoint.
    """

    return (
        "https://api.qrserver.com/"
        "v1/create-qr-code/"
        "?size=700x700"
        "&format=png"
        "&margin=12"
        "&ecc=H"
        "&data="
        + quote(url, safe="")
    )


# ============================================================================
# SCREENSHOT
# ============================================================================

def screenshot_url(url):
    """
    Thum.io screenshot endpoint.
    """

    return (
        "https://image.thum.io/"
        "get/width/1200/crop/1400/png/"
        + url
    )


# ============================================================================
# DNS
# ============================================================================

async def _dns_info(host):

    result = {}

    resolver = dns.asyncresolver.Resolver()

    resolver.timeout = DNS_TIMEOUT
    resolver.lifetime = DNS_TIMEOUT + 1

    records = (
        "A",
        "AAAA",
        "CNAME",
        "MX",
        "NS",
        "TXT",
    )

    for record_type in records:

        try:

            answers = await resolver.resolve(
                host,
                record_type,
            )

            values = []

            for answer in answers:

                value = str(answer)

                value = value.strip()
                value = value.strip('"')

                values.append(value)

            result[record_type] = values[:8]

        except Exception:

            result[record_type] = []

    return result


def _format_dns(dns_data):

    lines = []

    for record in (
        "A",
        "AAAA",
        "CNAME",
        "MX",
        "NS",
        "TXT",
    ):

        values = dns_data.get(
            record
        ) or []

        if not values:
            continue

        rendered = ", ".join(
            f"`{_clean(value, 180)}`"
            for value in values
        )

        lines.append(
            f"**{record}:** {rendered}"
        )

    if not lines:
        return "**DNS:** `No records returned`"

    return "\n".join(lines)


# ============================================================================
# HTML METADATA PARSER
# ============================================================================

def _meta_content(text, names):

    names_pattern = "|".join(
        re.escape(name)
        for name in names
    )

    patterns = [
        (
            rf'<meta[^>]+'
            rf'(?:name|property)\s*=\s*["\']'
            rf'(?:{names_pattern})'
            rf'["\'][^>]+'
            rf'content\s*=\s*["\']'
            rf'(.*?)["\']'
        ),
        (
            rf'<meta[^>]+'
            rf'content\s*=\s*["\']'
            rf'(.*?)["\'][^>]+'
            rf'(?:name|property)\s*=\s*["\']'
            rf'(?:{names_pattern})'
            rf'["\']'
        ),
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.I | re.S,
        )

        if match:
            return html.unescape(
                match.group(1).strip()
            )

    return None


async def fetch_metadata(url):
    """
    Fetch URL metadata while validating every redirect.

    This prevents a public URL from redirecting the
    userbot to localhost/private infrastructure.
    """

    current = url
    redirect_count = 0

    timeout = _client_timeout()

    async with aiohttp.ClientSession(
        timeout=timeout,
        trust_env=False,
        headers=HTTP_HEADERS,
    ) as session:

        while True:

            if redirect_count > MAX_REDIRECTS:
                raise RuntimeError(
                    "Too many redirects."
                )

            await _resolve_public(
                _domain(current)
            )

            async with session.get(
                current,
                allow_redirects=False,
            ) as response:

                location = response.headers.get(
                    "Location"
                )

                if (
                    300 <= response.status < 400
                    and location
                ):

                    current = urljoin(
                        current,
                        location,
                    )

                    current = normalize_url(
                        current
                    )

                    redirect_count += 1

                    continue

                chunks = []
                total = 0

                async for chunk in response.content.iter_chunked(
                    64 * 1024
                ):

                    chunks.append(chunk)
                    total += len(chunk)

                    if total >= MAX_HTML_BYTES:
                        break

                raw = b"".join(chunks)

                raw = raw[:MAX_HTML_BYTES]

                charset = (
                    response.charset
                    or "utf-8"
                )

                try:
                    text = raw.decode(
                        charset,
                        errors="replace",
                    )
                except LookupError:
                    charset = "utf-8"
                    text = raw.decode(
                        charset,
                        errors="replace",
                    )

                title_match = re.search(
                    r"<title[^>]*>(.*?)</title>",
                    text,
                    re.I | re.S,
                )

                title = None

                if title_match:
                    title = html.unescape(
                        _clean(
                            title_match.group(1),
                            MAX_TITLE_LENGTH,
                        )
                    )

                description = _meta_content(
                    text,
                    (
                        "description",
                        "og:description",
                        "twitter:description",
                    ),
                )

                if description:
                    description = _clean(
                        description,
                        MAX_DESCRIPTION_LENGTH,
                    )

                canonical_match = re.search(
                    r'<link[^>]+'
                    r'rel\s*=\s*["\'][^"\']*canonical[^"\']*["\']'
                    r'[^>]+href\s*=\s*["\'](.*?)["\']',
                    text,
                    re.I | re.S,
                )

                canonical = None

                if canonical_match:
                    canonical = urljoin(
                        str(response.url),
                        html.unescape(
                            canonical_match.group(1).strip()
                        ),
                    )

                og_image = _meta_content(
                    text,
                    ("og:image",),
                )

                if og_image:
                    og_image = urljoin(
                        str(response.url),
                        og_image,
                    )

                language_match = re.search(
                    r"<html[^>]+lang\s*=\s*"
                    r'["\']([^"\']+)["\']',
                    text,
                    re.I,
                )

                language = (
                    language_match.group(1)
                    if language_match
                    else None
                )

                final_url = str(
                    response.url
                )

                dns_data = await _dns_info(
                    _domain(final_url)
                )

                return {
                    "status": response.status,
                    "reason": response.reason,
                    "final_url": final_url,
                    "redirect_count": redirect_count,
                    "redirected": (
                        final_url != url
                    ),
                    "content_type": (
                        response.headers.get(
                            "Content-Type",
                            "",
                        ).split(
                            ";",
                            1,
                        )[0]
                    ),
                    "content_length": (
                        response.headers.get(
                            "Content-Length"
                        )
                        or str(total)
                    ),
                    "server": response.headers.get(
                        "Server"
                    ),
                    "powered_by": response.headers.get(
                        "X-Powered-By"
                    ),
                    "last_modified": response.headers.get(
                        "Last-Modified"
                    ),
                    "etag": response.headers.get(
                        "ETag"
                    ),
                    "title": title,
                    "description": description,
                    "canonical": canonical,
                    "og_image": og_image,
                    "language": language,
                    "charset": charset,
                    "bytes_read": total,
                    "dns": dns_data,
                }


# ============================================================================
# METADATA RENDERING
# ============================================================================

def metadata_text(meta):

    status = meta["status"]

    if 200 <= status < 300:
        status_icon = "🟢"
    elif status < 400:
        status_icon = "🟡"
    else:
        status_icon = "🔴"

    return (
        "**ℹ️ URL Information & Metadata**\n\n"

        f"{status_icon} **HTTP:** "
        f"`{status} {meta.get('reason') or ''}`\n"

        f"**Final URL:** "
        f"`{_clean(meta.get('final_url'), 500)}`\n"

        f"**Redirects:** "
        f"`{meta.get('redirect_count', 0)}`\n"

        f"**Content-Type:** "
        f"`{_clean(meta.get('content_type'), 100)}`\n"

        f"**Size:** "
        f"`{_clean(meta.get('content_length'), 60)} bytes`\n"

        f"**Server:** "
        f"`{_clean(meta.get('server'), 120)}`\n"

        f"**X-Powered-By:** "
        f"`{_clean(meta.get('powered_by'), 120)}`\n"

        f"**Title:** "
        f"`{_clean(meta.get('title'), 220)}`\n"

        f"**Description:** "
        f"`{_clean(meta.get('description'), 340)}`\n"

        f"**Canonical:** "
        f"`{_clean(meta.get('canonical'), 500)}`\n"

        f"**OG Image:** "
        f"`{_clean(meta.get('og_image'), 500)}`\n"

        f"**Language:** "
        f"`{_clean(meta.get('language'), 60)}`\n"

        f"**Charset:** "
        f"`{_clean(meta.get('charset'), 40)}`\n"

        f"**ETag:** "
        f"`{_clean(meta.get('etag'), 180)}`\n"

        f"**Last-Modified:** "
        f"`{_clean(meta.get('last_modified'), 120)}`\n\n"

        f"{_format_dns(meta.get('dns') or {})}"
    )

# ============================================================================
# RDAP / WHOIS
# ============================================================================

IANA_RDAP_BOOTSTRAP_URL = (
    "https://data.iana.org/rdap/dns.json"
)

RDAP_BOOTSTRAP_CACHE_TTL = 6 * 60 * 60

_RDAP_BOOTSTRAP_CACHE = None
_RDAP_BOOTSTRAP_CACHE_TIME = 0


async def _fetch_iana_rdap_bootstrap():
    """
    Download and cache the official IANA RDAP DNS bootstrap registry.

    This replaces the unreliable dependency on rdap.org.

    IANA publishes the authoritative RDAP service mapping for TLDs
    in this registry.
    """

    global _RDAP_BOOTSTRAP_CACHE
    global _RDAP_BOOTSTRAP_CACHE_TIME

    now = time.time()

    if (
        _RDAP_BOOTSTRAP_CACHE
        and now - _RDAP_BOOTSTRAP_CACHE_TIME
        < RDAP_BOOTSTRAP_CACHE_TTL
    ):
        return _RDAP_BOOTSTRAP_CACHE

    timeout = aiohttp.ClientTimeout(
        total=12,
        connect=6,
        sock_read=10,
    )

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "application/json,"
            "application/rdap+json"
        ),
    }

    async with aiohttp.ClientSession(
        timeout=timeout,
        trust_env=False,
    ) as session:

        async with session.get(
            IANA_RDAP_BOOTSTRAP_URL,
            headers=headers,
            allow_redirects=False,
        ) as response:

            if response.status != 200:
                raise RuntimeError(
                    "Unable to retrieve the official "
                    f"IANA RDAP bootstrap registry "
                    f"(HTTP {response.status})."
                )

            try:
                data = await response.json(
                    content_type=None
                )
            except Exception as exc:
                raise RuntimeError(
                    "IANA returned invalid RDAP "
                    "bootstrap data."
                ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            "Invalid IANA RDAP bootstrap structure."
        )

    services = data.get("services")

    if not isinstance(services, list):
        raise RuntimeError(
            "IANA RDAP bootstrap does not contain "
            "a valid services list."
        )

    _RDAP_BOOTSTRAP_CACHE = data
    _RDAP_BOOTSTRAP_CACHE_TIME = now

    return data


def _rdap_servers_for_tld(
    bootstrap,
    tld,
):
    """
    Return all RDAP servers registered by IANA
    for a specific TLD.

    Example:

        com -> https://rdap.verisign.com/com/v1/
    """

    tld = tld.lower().lstrip(".")

    services = (
        bootstrap.get("services")
        or []
    )

    servers = []

    for service in services:

        if (
            not isinstance(service, list)
            or len(service) < 2
        ):
            continue

        tlds = service[0]
        urls = service[1]

        if not isinstance(tlds, list):
            continue

        if tld not in {
            str(item).lower().lstrip(".")
            for item in tlds
        }:
            continue

        if not isinstance(urls, list):
            continue

        for base_url in urls:

            if not isinstance(
                base_url,
                str,
            ):
                continue

            base_url = base_url.strip()

            if not base_url:
                continue

            # RDAP bootstrap URLs must be HTTPS.
            parsed = urlsplit(base_url)

            if parsed.scheme.lower() != "https":
                continue

            if not parsed.hostname:
                continue

            servers.append(
                base_url.rstrip("/")
            )

    # Preserve order but remove duplicates.
    return list(
        dict.fromkeys(servers)
    )


def _extract_domain_for_rdap(raw):
    """
    Normalize input and extract an IDNA-safe domain.
    """

    normalized = normalize_url(
        raw
    )

    parts = urlsplit(
        normalized
    )

    hostname = (
        parts.hostname
        or ""
    ).strip().rstrip(".")

    if not hostname:
        raise ValueError(
            "A valid domain is required."
        )

    # WHOIS/RDAP domain lookup should not accept
    # an IP address through the domain endpoint.
    if _is_ip(hostname):
        raise ValueError(
            "WHOIS/RDAP domain lookup requires "
            "a domain name, not an IP address."
        )

    try:
        domain = hostname.encode(
            "idna"
        ).decode(
            "ascii"
        ).lower().rstrip(".")
    except Exception as exc:
        raise ValueError(
            "Unable to normalize the domain name."
        ) from exc

    # Basic domain validation.
    if (
        len(domain) > 253
        or "." not in domain
    ):
        raise ValueError(
            "Invalid domain name."
        )

    labels = domain.split(".")

    for label in labels:

        if not label:
            raise ValueError(
                "Invalid domain name."
            )

        if len(label) > 63:
            raise ValueError(
                "A domain label is too long."
            )

        if label.startswith("-"):
            raise ValueError(
                "Invalid domain label."
            )

        if label.endswith("-"):
            raise ValueError(
                "Invalid domain label."
            )

        if not re.match(
            r"^[a-z0-9-]+$",
            label,
            re.I,
        ):
            raise ValueError(
                "Invalid domain name."
            )

    return domain


async def _rdap_http_get(
    endpoint,
):
    """
    Perform a safe RDAP request.

    Redirects are handled manually so a malicious or
    compromised RDAP endpoint cannot redirect the userbot
    to localhost/private infrastructure.
    """

    current = endpoint

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "application/rdap+json,"
            "application/json;q=0.9"
        ),
    }

    timeout = aiohttp.ClientTimeout(
        total=15,
        connect=7,
        sock_read=12,
    )

    async with aiohttp.ClientSession(
        timeout=timeout,
        trust_env=False,
    ) as session:

        for _ in range(5):

            parsed = urlsplit(
                current
            )

            if parsed.scheme.lower() != "https":
                raise RuntimeError(
                    "RDAP server returned a "
                    "non-HTTPS endpoint."
                )

            hostname = (
                parsed.hostname
                or ""
            ).lower().rstrip(".")

            if not hostname:
                raise RuntimeError(
                    "RDAP endpoint has no hostname."
                )

            # Validate the destination before making
            # every RDAP request.
            await _resolve_public(
                hostname
            )

            async with session.get(
                current,
                headers=headers,
                allow_redirects=False,
            ) as response:

                if (
                    300
                    <= response.status
                    < 400
                ):

                    location = response.headers.get(
                        "Location"
                    )

                    if not location:
                        raise RuntimeError(
                            "RDAP server returned a "
                            "redirect without Location."
                        )

                    next_url = urljoin(
                        current,
                        location,
                    )

                    parsed_next = urlsplit(
                        next_url
                    )

                    if (
                        parsed_next.scheme.lower()
                        != "https"
                    ):
                        raise RuntimeError(
                            "RDAP redirect to a "
                            "non-HTTPS URL was blocked."
                        )

                    next_host = (
                        parsed_next.hostname
                        or ""
                    )

                    if not next_host:
                        raise RuntimeError(
                            "RDAP redirect has no hostname."
                        )

                    await _resolve_public(
                        next_host
                    )

                    current = next_url

                    continue

                body = await response.text(
                    errors="replace"
                )

                return (
                    response.status,
                    body,
                    dict(response.headers),
                    current,
                )

    raise RuntimeError(
        "Too many RDAP redirects."
    )


def _rdap_vcard_name(entity):
    """
    Extract the human-readable name from an RDAP
    vCard structure.
    """

    vcard = entity.get(
        "vcardArray"
    )

    if (
        not isinstance(vcard, list)
        or len(vcard) < 2
    ):
        return None

    properties = vcard[1]

    if not isinstance(
        properties,
        list,
    ):
        return None

    for item in properties:

        if (
            not isinstance(item, list)
            or len(item) < 4
        ):
            continue

        if item[0] == "fn":

            value = item[3]

            if isinstance(
                value,
                str,
            ):
                return value.strip()

    return None


def _rdap_extract_registrar(
    entities,
):
    """
    Extract registrar information from RDAP entities.

    Different registries return slightly different
    vCard/entity structures, so several formats are handled.
    """

    if not isinstance(
        entities,
        list,
    ):
        return None

    # Prefer an entity explicitly marked as registrar.
    for entity in entities:

        if not isinstance(
            entity,
            dict,
        ):
            continue

        roles = entity.get(
            "roles"
        ) or []

        roles = {
            str(role).lower()
            for role in roles
        }

        if "registrar" not in roles:
            continue

        name = _rdap_vcard_name(
            entity
        )

        if name:
            return name

        # Some RDAP responses include handle
        # even when no vCard FN is available.
        handle = entity.get(
            "handle"
        )

        if handle:
            return str(handle)

    # Fallback: search all entities for a useful FN.
    for entity in entities:

        if not isinstance(
            entity,
            dict,
        ):
            continue

        name = _rdap_vcard_name(
            entity
        )

        if name:
            return name

    return None


def _rdap_extract_nameservers(
    data,
):
    """
    Extract nameservers from an RDAP response.
    """

    result = []

    nameservers = (
        data.get("nameservers")
        or []
    )

    if not isinstance(
        nameservers,
        list,
    ):
        return result

    for nameserver in nameservers:

        if not isinstance(
            nameserver,
            dict,
        ):
            continue

        name = (
            nameserver.get("ldhName")
            or nameserver.get("unicodeName")
        )

        if not name:
            continue

        name = str(
            name
        ).strip().rstrip(".")

        if name and name not in result:
            result.append(name)

    return result[:12]


def _rdap_extract_events(
    data,
):
    """
    Normalize RDAP event dates.
    """

    events = {}

    raw_events = (
        data.get("events")
        or []
    )

    if not isinstance(
        raw_events,
        list,
    ):
        return events

    for event in raw_events:

        if not isinstance(
            event,
            dict,
        ):
            continue

        action = event.get(
            "eventAction"
        )

        date = event.get(
            "eventDate"
        )

        if not action or not date:
            continue

        events[
            str(action).lower()
        ] = str(date)

    return events


async def rdap_lookup(raw):
    """
    Perform a proper RDAP domain lookup using the
    official IANA bootstrap registry.

    This function DOES NOT use rdap.org.

    Flow:

        domain
          ↓
        IANA dns.json
          ↓
        authoritative TLD RDAP server
          ↓
        /domain/<domain>
    """

    domain = _extract_domain_for_rdap(
        raw
    )

    labels = domain.split(".")

    if len(labels) < 2:
        raise ValueError(
            "A fully-qualified domain name is required."
        )

    tld = labels[-1]

    bootstrap = (
        await _fetch_iana_rdap_bootstrap()
    )

    servers = _rdap_servers_for_tld(
        bootstrap,
        tld,
    )

    if not servers:

        raise RuntimeError(
            f"No authoritative RDAP service was "
            f"found in the IANA bootstrap registry "
            f"for .{tld}."
        )

    errors = []

    for base_url in servers:

        endpoint = (
            base_url.rstrip("/")
            + "/domain/"
            + quote(
                domain,
                safe="",
            )
        )

        try:

            status, body, headers, final_url = (
                await _rdap_http_get(
                    endpoint
                )
            )

            # Some RDAP services use 404 for
            # domains they don't know.
            if status == 404:

                errors.append(
                    f"{base_url}: HTTP 404"
                )

                continue

            if status == 429:

                errors.append(
                    f"{base_url}: HTTP 429 "
                    "(rate limited)"
                )

                continue

            if status >= 400:

                # Don't expose an entire HTML Cloudflare
                # page to Telegram.
                content_type = (
                    headers.get(
                        "Content-Type",
                        "",
                    )
                )

                errors.append(
                    f"{base_url}: HTTP {status}"
                    + (
                        f" ({_clean(content_type, 80)})"
                        if content_type
                        else ""
                    )
                )

                continue

            try:

                data = json.loads(
                    body
                )

            except Exception:

                errors.append(
                    f"{base_url}: invalid JSON"
                )

                continue

            if not isinstance(
                data,
                dict,
            ):

                errors.append(
                    f"{base_url}: invalid RDAP object"
                )

                continue

            # Validate that this really is a domain
            # RDAP object.
            object_class = (
                data.get(
                    "objectClassName"
                )
            )

            if (
                object_class
                and object_class.lower()
                != "domain"
            ):

                errors.append(
                    f"{base_url}: unexpected "
                    f"objectClassName"
                )

                continue

            registrar = (
                _rdap_extract_registrar(
                    data.get(
                        "entities"
                    )
                    or []
                )
            )

            nameservers = (
                _rdap_extract_nameservers(
                    data
                )
            )

            events = (
                _rdap_extract_events(
                    data
                )
            )

            statuses = []

            raw_statuses = (
                data.get("status")
                or []
            )

            if isinstance(
                raw_statuses,
                list,
            ):

                statuses = [
                    str(item)
                    for item in raw_statuses
                    if item
                ]

            domain_name = (
                data.get("ldhName")
                or data.get("unicodeName")
                or domain
            )

            handle = data.get(
                "handle"
            )

            # Some registries include a self link
            # which is preferable to our constructed URL.
            rdap_url = final_url

            links = (
                data.get("links")
                or []
            )

            if isinstance(
                links,
                list,
            ):

                for link in links:

                    if not isinstance(
                        link,
                        dict,
                    ):
                        continue

                    if (
                        link.get("rel")
                        == "self"
                        and link.get("href")
                    ):

                        candidate = str(
                            link["href"]
                        )

                        parsed_candidate = urlsplit(
                            candidate
                        )

                        if (
                            parsed_candidate.scheme.lower()
                            == "https"
                            and parsed_candidate.hostname
                        ):

                            rdap_url = candidate

                            break

            return {
                "domain": str(
                    domain_name
                ),
                "handle": (
                    str(handle)
                    if handle
                    else None
                ),
                "status": statuses,
                "registrar": registrar,
                "nameservers": nameservers,
                "events": events,
                "rdap": rdap_url,
                "server": base_url,
                "tld": tld,
            }

        except Exception as exc:

            errors.append(
                f"{base_url}: "
                f"{_clean(str(exc), 180)}"
            )

    # All authoritative providers failed.
    # Return a clean, useful error instead of the
    # giant Cloudflare HTML page.
    if errors:

        compact_errors = "\n".join(
            f"• `{_clean(error, 220)}`"
            for error in errors[:5]
        )

        raise RuntimeError(
            "Unable to retrieve authoritative "
            f"RDAP data for `{domain}`.\n\n"
            f"{compact_errors}"
        )

    raise RuntimeError(
        f"No RDAP server returned data for `{domain}`."
    )


def whois_text(data):
    """
    Render RDAP information for Telegram.
    """

    events = (
        data.get("events")
        or {}
    )

    statuses = (
        data.get("status")
        or []
    )

    nameservers = (
        data.get("nameservers")
        or []
    )

    if nameservers:

        ns_text = "\n".join(
            f"• `{_clean(ns, 150)}`"
            for ns in nameservers[:10]
        )

    else:

        ns_text = "• `Not disclosed / unavailable`"

    status_text = (
        ", ".join(statuses)
        if statuses
        else "Not disclosed / unavailable"
    )

    registered = (
        events.get(
            "registration"
        )
        or events.get(
            "registered"
        )
        or "—"
    )

    updated = (
        events.get(
            "last changed"
        )
        or events.get(
            "last update"
        )
        or events.get(
            "last changed"
        )
        or "—"
    )

    expires = (
        events.get(
            "expiration"
        )
        or events.get(
            "expiration date"
        )
        or "—"
    )

    return (
        "**🌐 WHOIS / RDAP**\n\n"

        f"**Domain:** "
        f"`{_clean(data.get('domain'), 180)}`\n"

        f"**TLD:** "
        f"`.{_clean(data.get('tld'), 30)}`\n"

        f"**Handle:** "
        f"`{_clean(data.get('handle'), 100)}`\n"

        f"**Registrar:** "
        f"`{_clean(data.get('registrar'), 220)}`\n"

        f"**Status:** "
        f"`{_clean(status_text, 400)}`\n"

        f"**Registered:** "
        f"`{_clean(registered, 100)}`\n"

        f"**Updated:** "
        f"`{_clean(updated, 100)}`\n"

        f"**Expires:** "
        f"`{_clean(expires, 100)}`\n\n"

        "**Nameservers:**\n"
        f"{ns_text}\n\n"

        f"**RDAP Server:** "
        f"`{_clean(data.get('server'), 240)}`\n\n"

        "_Data is retrieved from the "
        "authoritative RDAP registry._"
    )

# ============================================================================
# VIRUSTOTAL
# ============================================================================

def _get_db_key(key):
    """
    Safely retrieve a database key.

    Keeps the plugin compatible with the project's
    udB implementation.
    """

    try:
        return udB.get_key(key)
    except Exception:
        return None


async def _virustotal(url):

    api_key = _get_db_key(
        "URLTOOLS_VT_API_KEY"
    )

    if not api_key:

        return {
            "configured": False,
            "provider": "VirusTotal",
        }

    headers = {
        "x-apikey": str(api_key),
        "Accept": "application/json",
    }

    url_id = (
        base64.urlsafe_b64encode(
            url.encode()
        )
        .decode()
        .rstrip("=")
    )

    lookup_endpoint = (
        "https://www.virustotal.com/"
        f"api/v3/urls/{url_id}"
    )

    timeout = _client_timeout()

    async with aiohttp.ClientSession(
        timeout=timeout,
        trust_env=False,
        headers=headers,
    ) as session:

        # Try existing analysis first.
        async with session.get(
            lookup_endpoint
        ) as response:

            if response.status == 200:

                data = await response.json(
                    content_type=None
                )

                attrs = (
                    data.get("data", {})
                    .get("attributes", {})
                )

                return {
                    "configured": True,
                    "stats": (
                        attrs.get(
                            "last_analysis_stats"
                        )
                        or {}
                    ),
                    "reputation": attrs.get(
                        "reputation"
                    ),
                    "url": (
                        "https://www.virustotal.com/"
                        f"gui/url/{url_id}"
                    ),
                }

            if response.status not in (
                404,
                400,
            ):

                return {
                    "configured": True,
                    "error": (
                        f"HTTP {response.status}"
                    ),
                    "url": (
                        "https://www.virustotal.com/"
                        f"gui/url/{url_id}"
                    ),
                }

        # Submit URL for analysis.
        async with session.post(
            "https://www.virustotal.com/api/v3/urls",
            data={"url": url},
        ) as scan:

            if scan.status >= 400:

                return {
                    "configured": True,
                    "error": (
                        f"HTTP {scan.status}"
                    ),
                    "url": (
                        "https://www.virustotal.com/"
                        f"gui/url/{url_id}"
                    ),
                }

            data = await scan.json(
                content_type=None
            )

            analysis_id = (
                data.get("data", {})
                .get("id")
            )

            report_url = (
                "https://www.virustotal.com/"
                f"gui/url/{url_id}"
            )

            if not analysis_id:

                return {
                    "configured": True,
                    "status": "submitted",
                    "url": report_url,
                }

            # Give the analysis a short amount of time.
            await asyncio.sleep(1)

            async with session.get(
                "https://www.virustotal.com/"
                f"api/v3/analyses/{analysis_id}"
            ) as analysis_response:

                if analysis_response.status != 200:

                    return {
                        "configured": True,
                        "status": "submitted",
                        "url": report_url,
                    }

                analysis = (
                    await analysis_response.json(
                        content_type=None
                    )
                )

                attrs = (
                    analysis.get("data", {})
                    .get("attributes", {})
                )

                return {
                    "configured": True,
                    "stats": (
                        attrs.get("stats")
                        or {}
                    ),
                    "status": attrs.get(
                        "status"
                    ),
                    "url": report_url,
                }


# ============================================================================
# URLHAUS
# ============================================================================

async def _urlhaus(url):

    auth_key = _get_db_key(
        "URLTOOLS_URLHAUS_AUTH_KEY"
    )

    if not auth_key:

        return {
            "configured": False,
            "provider": "URLhaus",
        }

    endpoint = (
        "https://urlhaus-api.abuse.ch/"
        "v1/url/"
    )

    timeout = _client_timeout()

    async with aiohttp.ClientSession(
        timeout=timeout,
        trust_env=False,
    ) as session:

        async with session.post(
            endpoint,
            data={
                "url": url,
            },
            headers={
                "Auth-Key": str(auth_key),
            },
        ) as response:

            if response.status >= 400:

                return {
                    "configured": True,
                    "error": (
                        f"HTTP {response.status}"
                    ),
                }

            data = await response.json(
                content_type=None
            )

            return {
                "configured": True,
                "found": (
                    data.get("query_status")
                    == "ok"
                ),
                "status": data.get(
                    "url_status"
                ),
                "threat": data.get(
                    "threat"
                ),
                "tags": (
                    data.get("tags")
                    or []
                ),
                "reference": data.get(
                    "urlhaus_reference"
                ),
            }


# ============================================================================
# SECURITY CHECK
# ============================================================================

async def security_check(url):

    """
    Query configured threat intelligence providers.

    Important:
        We do NOT fetch the URL ourselves here.
        VirusTotal / URLhaus perform the intelligence lookup.
    """

    vt_task = _virustotal(url)
    uh_task = _urlhaus(url)

    vt, uh = await asyncio.gather(
        vt_task,
        uh_task,
        return_exceptions=True,
    )

    if isinstance(vt, Exception):

        vt = {
            "configured": bool(
                _get_db_key(
                    "URLTOOLS_VT_API_KEY"
                )
            ),
            "error": _clean(
                str(vt),
                250,
            ),
        }

    if isinstance(uh, Exception):

        uh = {
            "configured": bool(
                _get_db_key(
                    "URLTOOLS_URLHAUS_AUTH_KEY"
                )
            ),
            "error": _clean(
                str(uh),
                250,
            ),
        }

    return vt, uh


def security_text(vt, uh):

    lines = [
        "**🛡 Malicious URL Checker**",
        "",
    ]

    configured = 0
    dangerous = False

    # ------------------------------------------------------------------
    # VirusTotal
    # ------------------------------------------------------------------

    if vt.get("configured"):

        configured += 1

        stats = vt.get(
            "stats"
        ) or {}

        malicious = int(
            stats.get(
                "malicious",
                0,
            )
            or 0
        )

        suspicious = int(
            stats.get(
                "suspicious",
                0,
            )
            or 0
        )

        harmless = int(
            stats.get(
                "harmless",
                0,
            )
            or 0
        )

        undetected = int(
            stats.get(
                "undetected",
                0,
            )
            or 0
        )

        dangerous |= (
            malicious > 0
            or suspicious > 0
        )

        lines += [
            "**VirusTotal**",
            f"• 🔴 Malicious: `{malicious}`",
            f"• 🟠 Suspicious: `{suspicious}`",
            f"• 🟢 Harmless: `{harmless}`",
            f"• ⚪ Undetected: `{undetected}`",
        ]

        if vt.get("reputation") is not None:

            lines.append(
                "• Reputation: "
                f"`{vt['reputation']}`"
            )

        if vt.get("status"):

            lines.append(
                "• Scan status: "
                f"`{_clean(vt['status'], 100)}`"
            )

        if vt.get("error"):

            lines.append(
                "• Error: "
                f"`{_clean(vt['error'], 200)}`"
            )

    else:

        lines += [
            "**VirusTotal:** "
            "`API key not configured`"
        ]

    lines.append("")

    # ------------------------------------------------------------------
    # URLhaus
    # ------------------------------------------------------------------

    if uh.get("configured"):

        configured += 1

        if uh.get("found"):

            dangerous = True

            lines += [
                "**URLhaus**",
                "• Match: `KNOWN MALWARE URL`",
                (
                    "• Status: "
                    f"`{_clean(uh.get('status'), 100)}`"
                ),
                (
                    "• Threat: "
                    f"`{_clean(uh.get('threat'), 150)}`"
                ),
                (
                    "• Tags: "
                    f"`{_clean(', '.join(uh.get('tags') or []), 250)}`"
                ),
            ]

        elif uh.get("error"):

            lines.append(
                "**URLhaus:** "
                f"`{_clean(uh['error'], 200)}`"
            )

        else:

            lines.append(
                "**URLhaus:** "
                "`No matching URL record`"
            )

    else:

        lines.append(
            "**URLhaus:** "
            "`Auth-Key not configured`"
        )

    lines += [
        "",
    ]

    if dangerous:

        overall = (
            "⚠️ Potentially dangerous"
        )

    elif configured:

        overall = (
            "🟢 No configured provider "
            "reported a threat"
        )

    else:

        overall = (
            "⚪ No threat-intelligence "
            "API is configured"
        )

    lines += [
        f"**Overall:** `{overall}`",
        "",
        "_A clean result is not a guarantee of safety._",
    ]

    return "\n".join(lines)


# ============================================================================
# ACTION EXECUTORS
# ============================================================================

async def _execute_short(url):

    short = await shorten_url(
        url
    )

    return (
        "**✂️ URL Shortener**\n\n"
        f"**Original:**\n`{_clean(url, 600)}`\n\n"
        f"**Short URL:**\n`{short}`"
    ), short


async def _execute_whois(url):

    data = await rdap_lookup(
        url
    )

    return data


async def _execute_info(url):

    return await fetch_metadata(
        url
    )


async def _execute_security(url):

    return await security_check(
        url
    )


# ============================================================================
# DIRECT INLINE RESULT BUILDERS
# ============================================================================

async def _build_direct_result(
    event,
    url,
    action,
    token,
):
    """
    Build a complete inline result for direct commands.
    """

    try:

        # --------------------------------------------------------------
        # SHORTENER
        # --------------------------------------------------------------

        if action == "short":

            text, short = await _execute_short(
                url
            )

            return await event.builder.article(
                "✂️ URL Shortener",
                description=_clean(
                    short,
                    180,
                ),
                text=text,
                buttons=[
                    [
                        Button.url(
                            "🔗 Open Short URL",
                            short,
                        )
                    ],
                    [
                        Button.inline(
                            "‹ Back",
                            data=f"ut:{token}:home",
                        )
                    ],
                ],
                link_preview=False,
            )

        # --------------------------------------------------------------
        # QR
        # --------------------------------------------------------------

        if action == "qr":

            image = qr_url(
                url
            )

            return await event.builder.article(
                "◈ QR Code",
                description=_clean(
                    url,
                    180,
                ),
                text=(
                    "**◈ QR Code Generator**\n\n"
                    f"`{_clean(url, 600)}`"
                ),
                thumb=_web_document(
                    image
                ),
                content=_web_document(
                    image
                ),
                buttons=[
                    [
                        Button.url(
                            "🖼 Open QR Image",
                            image,
                        )
                    ],
                    [
                        Button.inline(
                            "‹ Back",
                            data=f"ut:{token}:home",
                        )
                    ],
                ],
                link_preview=False,
            )

        # --------------------------------------------------------------
        # SCREENSHOT
        # --------------------------------------------------------------

        if action == "screenshot":

            image = screenshot_url(
                url
            )

            return await event.builder.article(
                "🖼 URL Screenshot",
                description=_clean(
                    url,
                    180,
                ),
                text=(
                    "**🖼 URL Preview / Screenshot**\n\n"
                    f"`{_clean(url, 600)}`"
                ),
                thumb=_web_document(
                    image
                ),
                content=_web_document(
                    image
                ),
                buttons=[
                    [
                        Button.url(
                            "🌐 Open URL",
                            url,
                        )
                    ],
                    [
                        Button.inline(
                            "‹ Back",
                            data=f"ut:{token}:home",
                        )
                    ],
                ],
                link_preview=False,
            )

        # --------------------------------------------------------------
        # WHOIS
        # --------------------------------------------------------------

        if action == "whois":

            data = await _execute_whois(
                url
            )

            return await event.builder.article(
                "🌐 WHOIS / RDAP",
                description=_clean(
                    data.get("domain"),
                    180,
                ),
                text=whois_text(
                    data
                ),
                buttons=[
                    [
                        Button.url(
                            "🔎 Open RDAP",
                            data["rdap"],
                        )
                    ],
                    [
                        Button.inline(
                            "‹ Back",
                            data=f"ut:{token}:home",
                        )
                    ],
                ],
                link_preview=False,
            )

        # --------------------------------------------------------------
        # INFO
        # --------------------------------------------------------------

        if action == "info":

            data = await _execute_info(
                url
            )

            buttons = [
                [
                    Button.url(
                        "🌐 Open URL",
                        data["final_url"],
                    )
                ],
                [
                    Button.inline(
                        "🖼 Screenshot",
                        data=f"ut:{token}:screenshot",
                    ),
                    Button.inline(
                        "‹ Back",
                        data=f"ut:{token}:home",
                    ),
                ],
            ]

            return await event.builder.article(
                "ℹ️ URL Info",
                description=_clean(
                    data.get("title")
                    or data.get("final_url"),
                    180,
                ),
                text=metadata_text(
                    data
                ),
                buttons=buttons,
                link_preview=False,
            )

        # --------------------------------------------------------------
        # SECURITY
        # --------------------------------------------------------------

        if action == "safe":

            vt, uh = await _execute_security(
                url
            )

            buttons = []

            if vt.get("url"):

                buttons.append(
                    [
                        Button.url(
                            "🧪 VirusTotal",
                            vt["url"],
                        )
                    ]
                )

            if uh.get("reference"):

                buttons.append(
                    [
                        Button.url(
                            "🛡 URLhaus",
                            uh["reference"],
                        )
                    ]
                )

            buttons.append(
                [
                    Button.inline(
                        "‹ Back",
                        data=f"ut:{token}:home",
                    )
                ]
            )

            return await event.builder.article(
                "🛡 Security Check",
                description="VirusTotal + URLhaus",
                text=security_text(
                    vt,
                    uh,
                ),
                buttons=buttons,
                link_preview=False,
            )

        raise ValueError(
            "Unsupported URL Tools action."
        )

    except Exception as exc:

        LOGS.exception(
            "URL Tools direct action failed: %s",
            exc,
        )

        return await event.builder.article(
            "⚠️ URL Tools Error",
            description=_clean(
                str(exc),
                180,
            ),
            text=(
                "**⚠️ URL Tools failed**\n\n"
                f"`{_clean(str(exc), 600)}`"
            ),
            buttons=[
                [
                    Button.inline(
                        "‹ Back",
                        data=f"ut:{token}:home",
                    )
                ]
            ],
            link_preview=False,
        )


# ============================================================================
# INLINE ENTRY POINT
# ============================================================================

@in_pattern(
    re.compile(
        r"^(?:urltools(?:\s+(.*))?|((?:https?://)\S+))$",
        re.I,
    ),
    owner=True,
)
async def urltools_inline(event):

    try:

        raw_query = (
            event.text
            or ""
        ).strip()

        args = (
            event.pattern_match.group(1)
            or event.pattern_match.group(2)
            or ""
        )

        args = args.strip()

        action = None
        target = args

        # --------------------------------------------------------------
        # Detect direct action.
        # --------------------------------------------------------------

        if args:

            first, _, rest = (
                args.partition(" ")
            )

            first_lower = first.lower()

            if first_lower in ACTION_ALIASES:

                action = ACTION_ALIASES[
                    first_lower
                ]

                target = rest.strip()

        # --------------------------------------------------------------
        # No URL -> help result.
        # --------------------------------------------------------------

        if not target:

            result = await event.builder.article(
                "🔗 URL Tools",
                description=(
                    "Shorten • QR • Screenshot • "
                    "WHOIS • Metadata • Security"
                ),
                text=_help_text(),
                link_preview=False,
            )

            return await event.answer(
                [result],
                cache_time=0,
                private=True,
            )

        # --------------------------------------------------------------
        # Normalize URL.
        # --------------------------------------------------------------

        try:

            url = normalize_url(
                target
            )

        except Exception as exc:

            result = await event.builder.article(
                "❌ Invalid URL",
                description=_clean(
                    str(exc),
                    180,
                ),
                text=(
                    "**❌ Invalid URL**\n\n"
                    f"`{_clean(str(exc), 500)}`"
                ),
                link_preview=False,
            )

            return await event.answer(
                [result],
                cache_time=0,
                private=True,
            )

        # --------------------------------------------------------------
        # Create callback state.
        # --------------------------------------------------------------

        token = _state_create(
            url,
            event.sender_id,
        )

        # --------------------------------------------------------------
        # Direct action.
        # --------------------------------------------------------------

        if action:

            result = await _build_direct_result(
                event,
                url,
                action,
                token,
            )

            return await event.answer(
                [result],
                cache_time=0,
                private=True,
            )

        # --------------------------------------------------------------
        # Default interactive menu.
        # --------------------------------------------------------------

        result = await event.builder.article(
            "🔗 URL Tools",
            description=(
                "Shorten • QR • Screenshot • "
                "WHOIS • Metadata • Security"
            ),
            text=_home_text(
                url
            ),
            buttons=_home_buttons(
                token
            ),
            link_preview=False,
        )

        return await event.answer(
            [result],
            cache_time=0,
            private=True,
        )

    except Exception as exc:

        LOGS.exception(
            "URL Tools inline handler failed: %s",
            exc,
        )

        try:

            result = await event.builder.article(
                "⚠️ URL Tools Error",
                description=_clean(
                    str(exc),
                    180,
                ),
                text=(
                    "**⚠️ URL Tools encountered "
                    "an unexpected error.**\n\n"
                    f"`{_clean(str(exc), 500)}`"
                ),
                link_preview=False,
            )

            return await event.answer(
                [result],
                cache_time=0,
                private=True,
            )

        except Exception:

            return


# ============================================================================
# CALLBACK HANDLER
# ============================================================================

@callback(
    re.compile(
        r"^ut:"
        r"([A-Za-z0-9_-]+):"
        r"(home|short|qr|screenshot|whois|info|safe)$"
    ),
    owner=True,
)
async def urltools_callback(event):

    token = (
        event.data_match
        .group(1)
        .decode()
    )

    action = (
        event.data_match
        .group(2)
        .decode()
    )

    # --------------------------------------------------------------
    # Retrieve state.
    # --------------------------------------------------------------

    state = _state_get(
        token
    )

    if not state:

        return await event.answer(
            "This URL Tools session has expired. "
            "Run the inline query again.",
            alert=True,
        )

    url = state["url"]
    owner_id = state["owner"]

    # --------------------------------------------------------------
    # Prevent another user from using callback state.
    # --------------------------------------------------------------

    if event.sender_id != owner_id:

        return await event.answer(
            "This URL Tools session belongs to another user.",
            alert=True,
        )

    try:

        # ----------------------------------------------------------
        # HOME
        # ----------------------------------------------------------

        if action == "home":

            await event.answer(
                cache_time=0
            )

            return await event.edit(
                _home_text(url),
                buttons=_home_buttons(token),
                link_preview=False,
            )

        # ----------------------------------------------------------
        # Processing notification.
        # ----------------------------------------------------------

        await event.answer(
            "⏳ Processing…",
            cache_time=0,
        )

        # ----------------------------------------------------------
        # SHORTEN
        # ----------------------------------------------------------

        if action == "short":

            short = await shorten_url(
                url
            )

            return await event.edit(
                (
                    "**✂️ URL Shortener**\n\n"
                    f"**Original:**\n"
                    f"`{_clean(url, 600)}`\n\n"
                    f"**Short URL:**\n"
                    f"`{short}`"
                ),
                buttons=[
                    [
                        Button.url(
                            "🔗 Open Short URL",
                            short,
                        )
                    ],
                    [
                        Button.inline(
                            "‹ Back",
                            data=f"ut:{token}:home",
                        )
                    ],
                ],
                link_preview=False,
            )

        # ----------------------------------------------------------
        # QR CODE
        # ----------------------------------------------------------

        if action == "qr":

            image = qr_url(
                url
            )

            return await event.edit(
                (
                    "**◈ QR Code Generator**\n\n"
                    f"`{_clean(url, 600)}`"
                ),
                file=image,
                buttons=[
                    [
                        Button.url(
                            "🖼 Open QR Image",
                            image,
                        )
                    ],
                    [
                        Button.inline(
                            "‹ Back",
                            data=f"ut:{token}:home",
                        )
                    ],
                ],
                link_preview=False,
            )

        # ----------------------------------------------------------
        # SCREENSHOT
        # ----------------------------------------------------------

        if action == "screenshot":

            image = screenshot_url(
                url
            )

            return await event.edit(
                (
                    "**🖼 URL Preview / Screenshot**\n\n"
                    f"`{_clean(url, 600)}`"
                ),
                file=image,
                buttons=[
                    [
                        Button.url(
                            "🌐 Open URL",
                            url,
                        )
                    ],
                    [
                        Button.inline(
                            "‹ Back",
                            data=f"ut:{token}:home",
                        )
                    ],
                ],
                link_preview=False,
            )

        # ----------------------------------------------------------
        # WHOIS
        # ----------------------------------------------------------

        if action == "whois":

            data = await rdap_lookup(
                url
            )

            return await event.edit(
                whois_text(
                    data
                ),
                buttons=[
                    [
                        Button.url(
                            "🔎 Open RDAP",
                            data["rdap"],
                        )
                    ],
                    [
                        Button.inline(
                            "‹ Back",
                            data=f"ut:{token}:home",
                        )
                    ],
                ],
                link_preview=False,
            )

        # ----------------------------------------------------------
        # URL INFO
        # ----------------------------------------------------------

        if action == "info":

            data = await fetch_metadata(
                url
            )

            return await event.edit(
                metadata_text(
                    data
                ),
                buttons=[
                    [
                        Button.url(
                            "🌐 Open Final URL",
                            data["final_url"],
                        )
                    ],
                    [
                        Button.inline(
                            "🖼 Screenshot",
                            data=f"ut:{token}:screenshot",
                        ),
                        Button.inline(
                            "‹ Back",
                            data=f"ut:{token}:home",
                        ),
                    ],
                ],
                link_preview=False,
            )

        # ----------------------------------------------------------
        # SECURITY
        # ----------------------------------------------------------

        if action == "safe":

            vt, uh = await security_check(
                url
            )

            buttons = []

            if vt.get("url"):

                buttons.append(
                    [
                        Button.url(
                            "🧪 VirusTotal",
                            vt["url"],
                        )
                    ]
                )

            if uh.get("reference"):

                buttons.append(
                    [
                        Button.url(
                            "🛡 URLhaus",
                            uh["reference"],
                        )
                    ]
                )

            buttons.append(
                [
                    Button.inline(
                        "‹ Back",
                        data=f"ut:{token}:home",
                    )
                ]
            )

            return await event.edit(
                security_text(
                    vt,
                    uh,
                ),
                buttons=buttons,
                link_preview=False,
            )

        # ----------------------------------------------------------
        # Unknown action.
        # ----------------------------------------------------------

        return await event.edit(
            "**❌ Unknown URL Tools action.**",
            buttons=_back_button(token),
            link_preview=False,
        )

    except Exception as exc:

        LOGS.exception(
            "URL Tools callback failed: %s",
            exc,
        )

        return await event.edit(
            (
                "**⚠️ URL Tools Error**\n\n"
                f"`{_clean(str(exc), 600)}`"
            ),
            buttons=_back_button(token),
            link_preview=False,
)

"""
Translation Plugin

Command interface
-----------------
.tr en Hello
.tr en                  (reply to a message)
.tr fa>en سلام حالت چطوره؟
.tr auto>en text
.tr list
.tr help

Inline interface
----------------
@AssisXBot tr en Hello
@AssisXBot tr fa>en سلام حالت چطوره؟
@AssisXBot tr list

The plugin is intentionally self-contained and uses only aiohttp plus the
existing Megatron/CythonX interfaces. It does not require langdetect,
translate libraries, or a mandatory API key.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import io
import json
import os
import re
import time
from collections import OrderedDict
from typing import Optional
from urllib.parse import quote

import aiohttp
from telethon import Button, types

from . import HNDLR, LOGS, eor, in_pattern, heartless_cmd


# ---------------------------------------------------------------------------
# Language catalogue
# ---------------------------------------------------------------------------

LANGUAGES = {
    "af": "Afrikaans", "sq": "Albanian", "am": "Amharic", "ar": "Arabic",
    "hy": "Armenian", "az": "Azerbaijani", "eu": "Basque", "be": "Belarusian",
    "bn": "Bengali", "bs": "Bosnian", "bg": "Bulgarian", "ca": "Catalan",
    "ceb": "Cebuano", "zh-CN": "Chinese (Simplified)", "zh-TW": "Chinese (Traditional)",
    "co": "Corsican", "hr": "Croatian", "cs": "Czech", "da": "Danish",
    "nl": "Dutch", "en": "English", "eo": "Esperanto", "et": "Estonian",
    "fi": "Finnish", "fr": "French", "fy": "Frisian", "gl": "Galician",
    "ka": "Georgian", "de": "German", "el": "Greek", "gu": "Gujarati",
    "ht": "Haitian Creole", "ha": "Hausa", "haw": "Hawaiian", "he": "Hebrew",
    "hi": "Hindi", "hmn": "Hmong", "hu": "Hungarian", "is": "Icelandic",
    "ig": "Igbo", "id": "Indonesian", "ga": "Irish", "it": "Italian",
    "ja": "Japanese", "jv": "Javanese", "kn": "Kannada", "kk": "Kazakh",
    "km": "Khmer", "ko": "Korean", "ku": "Kurdish", "ky": "Kyrgyz",
    "lo": "Lao", "la": "Latin", "lv": "Latvian", "lt": "Lithuanian",
    "lb": "Luxembourgish", "mk": "Macedonian", "mg": "Malagasy", "ms": "Malay",
    "ml": "Malayalam", "mt": "Maltese", "mi": "Maori", "mr": "Marathi",
    "mn": "Mongolian", "my": "Myanmar (Burmese)", "ne": "Nepali", "no": "Norwegian",
    "ny": "Nyanja", "or": "Odia", "ps": "Pashto", "fa": "Persian",
    "pl": "Polish", "pt": "Portuguese", "pa": "Punjabi", "ro": "Romanian",
    "ru": "Russian", "sm": "Samoan", "gd": "Scots Gaelic", "sr": "Serbian",
    "st": "Sesotho", "sn": "Shona", "sd": "Sindhi", "si": "Sinhala",
    "sk": "Slovak", "sl": "Slovenian", "so": "Somali", "es": "Spanish",
    "su": "Sundanese", "sw": "Swahili", "sv": "Swedish", "tg": "Tajik",
    "ta": "Tamil", "tt": "Tatar", "te": "Telugu", "th": "Thai",
    "tr": "Turkish", "tk": "Turkmen", "uk": "Ukrainian", "ur": "Urdu",
    "ug": "Uyghur", "uz": "Uzbek", "vi": "Vietnamese", "cy": "Welsh",
    "xh": "Xhosa", "yi": "Yiddish", "yo": "Yoruba", "zu": "Zulu",
}


# Telegram UI flags. A language is not a country, so flags are only used where
# there is a sensible conventional representation; otherwise the globe is used.
LANGUAGE_FLAGS = {
    "fa": "🇮🇷", "en": "🇬🇧", "tr": "🇹🇷", "de": "🇩🇪", "fr": "🇫🇷",
    "es": "🇪🇸", "it": "🇮🇹", "pt": "🇵🇹", "ru": "🇷🇺", "uk": "🇺🇦",
    "ar": "🇸🇦", "he": "🇮🇱", "hi": "🇮🇳", "ur": "🇵🇰", "bn": "🇧🇩",
    "zh-CN": "🇨🇳", "zh-TW": "🇹🇼", "ja": "🇯🇵", "ko": "🇰🇷",
    "th": "🇹🇭", "vi": "🇻🇳", "id": "🇮🇩", "ms": "🇲🇾", "nl": "🇳🇱",
    "pl": "🇵🇱", "cs": "🇨🇿", "sk": "🇸🇰", "hu": "🇭🇺", "ro": "🇷🇴",
    "bg": "🇧🇬", "sr": "🇷🇸", "hr": "🇭🇷", "sl": "🇸🇮", "el": "🇬🇷",
    "sv": "🇸🇪", "no": "🇳🇴", "da": "🇩🇰", "fi": "🇫🇮", "et": "🇪🇪",
    "lv": "🇱🇻", "lt": "🇱🇹", "is": "🇮🇸", "ga": "🇮🇪", "sq": "🇦🇱",
    "hy": "🇦🇲", "az": "🇦🇿", "ka": "🇬🇪", "kk": "🇰🇿", "uz": "🇺🇿",
    "tk": "🇹🇲", "tg": "🇹🇯", "ky": "🇰🇬", "mn": "🇲🇳", "ne": "🇳🇵",
    "si": "🇱🇰", "my": "🇲🇲", "km": "🇰🇭", "lo": "🇱🇦", "ps": "🇦🇫",
    "sw": "🇹🇿", "am": "🇪🇹", "ha": "🇳🇬", "yo": "🇳🇬", "zu": "🇿🇦",
    "af": "🇿🇦", "ca": "🇪🇸", "eu": "🇪🇸", "gl": "🇪🇸", "cy": "🏴",
}

# Aliases are deliberately short and explicit. The canonical value is always
# a Google-compatible language code; "auto" is a source-only pseudo-code.
ALIASES = {
    "auto": "auto", "detect": "auto", "automatic": "auto",
    "persian": "fa", "farsi": "fa", "فارسی": "fa", "پارسی": "fa",
    "english": "en", "انگلیسی": "en", "arabic": "ar", "عربی": "ar",
    "turkish": "tr", "ترکی": "tr", "ترکی استانبولی": "tr",
    "russian": "ru", "روسی": "ru", "german": "de", "آلمانی": "de",
    "french": "fr", "فرانسوی": "fr", "spanish": "es", "اسپانیایی": "es",
    "italian": "it", "ایتالیایی": "it", "portuguese": "pt", "پرتغالی": "pt",
    "hindi": "hi", "هندی": "ur", "urdu": "ur", "اردو": "ur",
    "chinese": "zh-CN", "چینی": "zh-CN", "simplified chinese": "zh-CN",
    "traditional chinese": "zh-TW", "japanese": "ja", "ژاپنی": "ja",
    "korean": "ko", "کره ای": "ko", "کره‌ای": "ko", "dutch": "nl",
    "polish": "pl", "ukrainian": "uk", "اوکراینی": "uk", "bulgarian": "bg",
    "بلغاری": "bg", "greek": "el", "یونانی": "el", "armenian": "hy",
    "hebrew": "he", "عبری": "he", "indonesian": "id", "اندونزیایی": "id",
    "malay": "ms", "مالایی": "ms", "thai": "th", "تایلندی": "th",
    "vietnamese": "vi", "ویتنامی": "vi", "czech": "cs", "swedish": "sv",
    "norwegian": "no", "danish": "da", "finnish": "fi", "romanian": "ro",
    "persian (farsi)": "fa",
}

MAX_INPUT = 12000
MAX_INLINE_RESULT = 3800
MAX_COPY_TEXT = 256
MAX_SHARE_QUERY_BYTES = 256
MAX_TELEGRAM_TEXT = 3950
CACHE_SIZE = 256
CACHE_TTL = 15 * 60
REQUEST_TIMEOUT = 5.0
FAST_TIMEOUT = 4.5
SLOW_TIMEOUT = 7.0
CONCURRENCY = 8
TRANSLATION_DEADLINE = 7.5

_CACHE: OrderedDict[str, tuple[float, str, str]] = OrderedDict()
_SEMAPHORE = asyncio.Semaphore(CONCURRENCY)
_SESSION: Optional[aiohttp.ClientSession] = None
_SESSION_LOCK = asyncio.Lock()


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _escape(value: object) -> str:
    return html.escape(str(value), quote=False)


def _normalise_code(value: str | None) -> Optional[str]:
    if value is None:
        return None
    value = value.strip().replace("_", "-")
    if not value:
        return None
    low = value.casefold()
    if low in ALIASES:
        return ALIASES[low]
    for code in LANGUAGES:
        if low == code.casefold():
            return code
    return None


def _cache_key(text: str, source: str, target: str) -> str:
    raw = f"{source}\0{target}\0{text}".encode("utf-8", "ignore")
    return hashlib.sha256(raw).hexdigest()


def _cache_get(key: str):
    item = _CACHE.get(key)
    if not item:
        return None
    created, translated, detected = item
    if time.monotonic() - created >= CACHE_TTL:
        _CACHE.pop(key, None)
        return None
    _CACHE.move_to_end(key)
    return translated, detected


def _cache_put(key: str, translated: str, detected: str) -> None:
    _CACHE[key] = (time.monotonic(), translated, detected)
    _CACHE.move_to_end(key)
    while len(_CACHE) > CACHE_SIZE:
        _CACHE.popitem(last=False)


def _valid_translation(value: object, original: str) -> str:
    if value is None:
        raise ValueError("empty translation")
    result = html.unescape(str(value)).strip()
    if not result:
        raise ValueError("empty translation")
    # A backend occasionally returns the original query after an upstream
    # failure. Do not reject legitimate identical translations for very short
    # text, but reject suspicious exact echoes for longer input.
    if len(original) >= 32 and result == original.strip():
        raise ValueError("backend returned the original text")
    return result


async def _session() -> aiohttp.ClientSession:
    """Return one shared HTTP session.

    A single connector is substantially faster than creating a new TCP/TLS
    connection for every translation request, especially for inline queries.
    """
    global _SESSION
    if _SESSION is not None and not _SESSION.closed:
        return _SESSION
    async with _SESSION_LOCK:
        if _SESSION is None or _SESSION.closed:
            timeout = aiohttp.ClientTimeout(
                total=REQUEST_TIMEOUT,
                connect=2.5,
                sock_connect=2.5,
                sock_read=4.0,
            )
            connector = aiohttp.TCPConnector(
                limit=16,
                limit_per_host=8,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
            )
            _SESSION = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={
                    "Accept": "application/json,text/plain,text/html,*/*",
                    "Accept-Language": "en-US,en;q=0.8",
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
                },
            )
    return _SESSION


async def _close_session() -> None:
    global _SESSION
    if _SESSION is not None and not _SESSION.closed:
        await _SESSION.close()
    _SESSION = None


async def _request_text(method: str, url: str, *, timeout: float = FAST_TIMEOUT, **kwargs):
    """One bounded HTTP request.

    Translation latency is user-visible, particularly for Telegram inline
    queries. The previous implementation retried every HTTP error three times,
    which could make one failed provider block all subsequent providers for
    tens of seconds. Provider fallback now happens at the orchestration layer;
    individual requests deliberately have no retry loop.
    """
    session = await _session()
    request_timeout = aiohttp.ClientTimeout(
        total=timeout,
        connect=min(2.5, timeout),
        sock_connect=min(2.5, timeout),
        sock_read=min(max(timeout - 0.5, 1.0), 4.0),
    )
    try:
        async with session.request(method, url, timeout=request_timeout, **kwargs) as response:
            body = await response.text(errors="replace")
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
            return body
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise RuntimeError(type(exc).__name__) from exc


# ---------------------------------------------------------------------------
# Conservative local detection for fallback-only providers
# ---------------------------------------------------------------------------

_PERSIAN_WORDS = {
    "سلام", "حالت", "چطوری", "چطور", "خوبی", "هستی", "من", "تو", "شما",
    "این", "آن", "برای", "ممنون", "مرسی", "لطفا", "لطفاً", "چرا", "کجا",
    "چگونه", "خیلی", "امروز", "فردا", "دیروز", "دوست", "دارم", "داری", "دارید",
    "میخواهم", "میخوام", "نمیخواهم", "نمیخوام", "است", "هست", "بود", "باشد",
}

_ARABIC_WORDS = {
    "السلام", "عليكم", "عليکم", "كيف", "حالك", "ماذا", "أين", "لماذا", "أنا",
    "أنت", "نحن", "هذا", "هذه", "هناك", "مرحبا", "شكرا",
}


def _guess_source(text: str) -> str:
    """Return a conservative source code for providers that cannot auto-detect."""
    words = set(re.findall(r"[\u0600-\u06FF]+", text))

    # Persian has letters that are not used in standard Arabic. Check these
    # before the general Arabic-script test.
    if re.search(r"[پچژگک‌ی]", text) or words & _PERSIAN_WORDS:
        return "fa"
    if words & _ARABIC_WORDS:
        return "ar"
    if re.search(r"[\u0400-\u04FF]", text):
        return "ru"
    if re.search(r"[\u0370-\u03FF]", text):
        return "el"
    if re.search(r"[\u3040-\u30FF]", text):
        return "ja"
    if re.search(r"[\uAC00-\uD7AF]", text):
        return "ko"
    if re.search(r"[\u4E00-\u9FFF]", text):
        return "zh-CN"
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    if re.search(r"[\u0980-\u09FF]", text):
        return "bn"
    if re.search(r"[\u0B80-\u0BFF]", text):
        return "ta"
    if re.search(r"[\u0C00-\u0C7F]", text):
        return "te"
    if re.search(r"[\u0D00-\u0D7F]", text):
        return "ml"
    if re.search(r"[\u0E00-\u0E7F]", text):
        return "th"
    return "en"


# ---------------------------------------------------------------------------
# Translation backends
# ---------------------------------------------------------------------------


async def _google_cloud(text: str, target: str, source: str):
    api_key = os.getenv("GOOGLE_TRANSLATE_API_KEY")
    if not api_key:
        try:
            from . import udB
            api_key = udB.get_key("GOOGLE_TRANSLATE_API_KEY")
        except Exception:
            api_key = None
    if not api_key:
        raise RuntimeError("API key not configured")

    params = {"key": api_key, "target": target, "format": "text"}
    if source != "auto":
        params["source"] = source
    raw = await _request_text(
        "POST",
        "https://translation.googleapis.com/language/translate/v2",
        timeout=SLOW_TIMEOUT,
        params=params,
        json={"q": text},
    )
    payload = json.loads(raw)
    translations = payload.get("data", {}).get("translations", [])
    if not translations:
        raise ValueError("Google Cloud returned no translation")
    item = translations[0]
    translated = _valid_translation(item.get("translatedText"), text)
    detected = _normalise_code(item.get("detectedLanguageCode")) or source
    return translated, detected


async def _google_ajax(text: str, target: str, source: str):
    raw = await _request_text(
        "GET",
        "https://translate.googleapis.com/translate_a/single",
        timeout=FAST_TIMEOUT,
        params={
            "client": "gtx",
            "sl": source,
            "tl": target,
            "dt": "t",
            "q": text,
        },
    )
    payload = json.loads(raw)
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        raise ValueError("invalid Google response")
    translated = _valid_translation(
        "".join(str(item[0]) for item in payload[0] if isinstance(item, list) and item and item[0] is not None),
        text,
    )
    detected = source
    if len(payload) > 2 and isinstance(payload[2], str):
        detected = _normalise_code(payload[2]) or source
    return translated, detected


async def _google_web(text: str, target: str, source: str):
    raw = await _request_text(
        "GET",
        "https://translate.google.com/m",
        timeout=SLOW_TIMEOUT,
        params={"tl": target, "sl": source, "q": text},
    )
    matches = re.findall(
        r'class=["\'](?:result-container|t0)[^>]*>(.*?)<', raw, flags=re.I | re.S
    )
    if not matches:
        raise ValueError("Google web returned no translation")
    value = re.sub(r"<[^>]+>", "", matches[0])
    return _valid_translation(value, text), source


async def _lingva_one(text: str, target: str, source: str, instance: str):
    encoded = quote(text, safe="")
    raw = await _request_text(
        "GET",
        f"{instance}/api/v1/{source}/{target}/{encoded}",
        timeout=FAST_TIMEOUT,
    )
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("invalid Lingva response")
    return _valid_translation(payload.get("translation"), text), source


async def _lingva(text: str, target: str, source: str):
    instances = (
        "https://lingva.ml",
        "https://translate.plausibility.cloud",
        "https://translate.dr460nf1r3.org",
    )
    tasks = [asyncio.create_task(_lingva_one(text, target, source, x)) for x in instances]
    try:
        return await _first_success(tasks, timeout=FAST_TIMEOUT + 0.5)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()


async def _mymemory(text: str, target: str, source: str):
    source = source if source != "auto" else _guess_source(text)
    raw = await _request_text(
        "GET",
        "https://api.mymemory.translated.net/get",
        timeout=FAST_TIMEOUT,
        params={"q": text, "langpair": f"{source}|{target}"},
    )
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("invalid MyMemory response")
    response_data = payload.get("responseData") or {}
    status = response_data.get("responseStatus")
    if status not in (None, 200, "200"):
        raise RuntimeError(f"MyMemory status {status}")
    return _valid_translation(response_data.get("translatedText"), text), source


async def _legacy_core(text: str, target: str, source: str):
    from CythonX.fns.tools import translate as legacy_translate
    detected = source if source != "auto" else _guess_source(text)
    value = await asyncio.wait_for(
        asyncio.to_thread(legacy_translate, text, lang_tgt=target, lang_src=detected, timeout=5),
        timeout=6,
    )
    if isinstance(value, tuple):
        value = value[0]
    return _valid_translation(value, text), detected


async def _first_success(tasks, timeout: float):
    """Return the first successful translation and cancel the losers."""
    pending = set(tasks)
    errors = []
    deadline = asyncio.get_running_loop().time() + timeout
    try:
        while pending:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            done, pending = await asyncio.wait(
                pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
            )
            if not done:
                break
            for task in done:
                try:
                    result = task.result()
                    if result and result[0]:
                        return result
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    errors.append(str(exc))
    finally:
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    raise RuntimeError("; ".join(errors) or "translation timeout")


async def _translate(text: str, target: str, source: str = "auto", *, fast_only: bool = False):
    """Low-latency translation orchestration.

    Fast public providers are queried concurrently rather than sequentially.
    This is the key difference from the previous version: one dead/429
    provider can no longer add another full timeout to the user's request.
    """
    target = _normalise_code(target)
    source = _normalise_code(source) or "auto"
    if not target or target == "auto":
        raise ValueError("invalid target language")
    if source == target:
        return text, source

    key = _cache_key(text, source, target)
    cached = _cache_get(key)
    if cached:
        return cached

    detected = source if source != "auto" else _guess_source(text)

    async with _SEMAPHORE:
        # If a Cloud API key is configured, use it as one of the concurrent
        # candidates. Otherwise the public Google/MyMemory/Lingva race is fast.
        candidates = [
            ("Google AJAX", _google_ajax(text, target, source)),
            ("MyMemory", _mymemory(text, target, detected)),
            ("Lingva", _lingva(text, target, detected)),
        ]
        if os.getenv("GOOGLE_TRANSLATE_API_KEY"):
            candidates.insert(0, ("Google Cloud", _google_cloud(text, target, source)))

        tasks = [asyncio.create_task(coro) for _, coro in candidates]
        try:
            translated, actual_source = await _first_success(
                tasks, timeout=TRANSLATION_DEADLINE
            )
        except Exception as first_error:
            LOGS.debug("Fast translation race failed: %s", first_error)
            if fast_only:
                raise RuntimeError("fast translation providers unavailable") from first_error
            # Only after the fast race fails do we try the slower fallbacks.
            fallback_tasks = [
                asyncio.create_task(_google_web(text, target, detected)),
                asyncio.create_task(_legacy_core(text, target, detected)),
            ]
            try:
                translated, actual_source = await _first_success(
                    fallback_tasks, timeout=6.5
                )
            finally:
                for task in fallback_tasks:
                    if not task.done():
                        task.cancel()
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    actual_source = _normalise_code(actual_source) or detected
    translated = _valid_translation(translated, text)
    _cache_put(key, translated, actual_source)
    return translated, actual_source


# ---------------------------------------------------------------------------
# Request parsing / formatting
# ---------------------------------------------------------------------------


def _parse_request(raw: str, default_target: str = "en"):
    raw = raw.strip()
    if not raw:
        return default_target, "auto", ""

    pair = re.match(r"^([^\s:>]+)\s*(?:->|>|:)\s*([^\s]+)(?:\s+|$)(.*)$", raw, flags=re.S)
    if pair:
        source = _normalise_code(pair.group(1))
        target = _normalise_code(pair.group(2))
        if source and target:
            return target, source, pair.group(3).strip()

    parts = raw.split(maxsplit=1)
    target = _normalise_code(parts[0])
    if target:
        return target, "auto", parts[1].strip() if len(parts) == 2 else ""

    # Friendly shorthand: .tr Hello world -> English.
    return default_target, "auto", raw


def _display_name(code: str) -> str:
    return LANGUAGES.get(code, code.upper() if code else "AUTO")


def _flag(code: str) -> str:
    return LANGUAGE_FLAGS.get(code, "🌐")


def _language_label(code: str) -> str:
    return f"{_flag(code)} {_display_name(code)} ({code})"


def _format_result(original: str, translated: str, source: str, target: str, *, auto_detected: bool = False) -> str:
    detected_line = "\n⚡ Auto detected" if auto_detected else ""
    return (
        "<b>🌐 Translation</b>\n\n"
        f"{_flag(source)} <b>{_escape(_display_name(source))}</b> (<code>{source}</code>) "
        f"→ {_flag(target)} <b>{_escape(_display_name(target))}</b> (<code>{target}</code>)"
        f"<b>{detected_line}</b>\n\n"
        "<b>📝 Original Text</b>\n"
        f"{_escape(original)}\n\n"
        "<b>✨ Translation Result</b>\n"
        f"{_escape(translated)}"
    )


def _inline_plain_result(
    original: str,
    translated: str,
    source: str,
    target: str,
    *,
    auto_detected: bool = False,
) -> str:
    """Build the inline result as valid Telegram HTML.

    Inline articles are not parsed as HTML unless ``parse_mode`` is explicitly
    supplied to ``builder.article``.  More importantly, user/provider text
    must always be escaped before it is inserted into an HTML template.
    Keeping this function responsible for *only* content generation makes it
    much harder for a future caller to accidentally mix raw text and markup.
    """
    source_name = _escape(_display_name(source))
    target_name = _escape(_display_name(target))
    source_code = _escape(source)
    target_code = _escape(target)
    original_text = _escape(original)
    translated_text = _escape(translated)

    lines = [
        "<b>🌐 Translation</b>",
        "",
        (
            f"{_flag(source)} <b>{source_name}</b> (<code>{source_code}</code>) "
            f"→ {_flag(target)} <b>{target_name}</b> (<code>{target_code}</code>)"
        ),
    ]

    if auto_detected:
        lines.append("<b>⚡ Auto detected</b>")

    lines.extend(
        [
            "",
            "<b>📝 Original Text</b>",
            original_text,
            "",
            "<b>✨ Translation Result</b>",
            translated_text,
        ]
    )
    return "\n".join(lines)


def _truncate_inline_text(value: str, limit: int) -> str:
    """Truncate plain text without ever cutting an HTML entity."""
    value = str(value)
    if len(value) <= limit:
        return value
    if limit <= 1:
        return "…"[:limit]
    return value[: limit - 1] + "…"


def _fit_inline_result(
    original: str,
    translated: str,
    source: str,
    target: str,
    *,
    auto_detected: bool = False,
    limit: int = MAX_INLINE_RESULT,
) -> str:
    """Fit an inline result while preserving valid HTML markup.

    Never slice the final HTML string: doing so can cut ``</b>``/``</code>`` or
    an HTML entity and cause Telegram to render tags literally or reject the
    message. Instead, shorten the plain dynamic fields and rebuild the markup.
    """
    result = _inline_plain_result(
        original,
        translated,
        source,
        target,
        auto_detected=auto_detected,
    )
    if len(result) <= limit:
        return result

    # Keep both sections useful. The header/labels are fixed, so first reserve
    # enough room for them and then split the remaining budget between content.
    fixed = _inline_plain_result(
        "",
        "",
        source,
        target,
        auto_detected=auto_detected,
    )
    # Two empty-field placeholders account for the two dynamic text positions.
    available = max(2, limit - len(fixed))
    original_budget = available // 2
    translated_budget = available - original_budget

    for _ in range(8):
        candidate = _inline_plain_result(
            _truncate_inline_text(original, original_budget),
            _truncate_inline_text(translated, translated_budget),
            source,
            target,
            auto_detected=auto_detected,
        )
        if len(candidate) <= limit:
            return candidate

        # HTML escaping can expand the dynamic text. Reduce both budgets and
        # rebuild instead of ever slicing an already formatted HTML document.
        original_budget = max(1, int(original_budget * 0.85))
        translated_budget = max(1, int(translated_budget * 0.85))

    return _inline_plain_result(
        _truncate_inline_text(original, max(1, original_budget)),
        _truncate_inline_text(translated, max(1, translated_budget)),
        source,
        target,
        auto_detected=auto_detected,
    )


def _button_copy(text: str):
    """Create a real Telegram clipboard button when the installed Telethon
    layer exposes keyboardButtonCopy. Older Telethon builds did not expose
    this constructor through Button, so we use the raw TL type and patch the
    local inline-button classifier only when necessary.
    """
    if not text:
        return None
    if len(text) > MAX_COPY_TEXT:
        return None
    constructor = getattr(types, "KeyboardButtonCopy", None)
    if constructor is None:
        return None

    # Some Telethon 1.x builds know the Telegram constructor but their helper
    # classifier predates it. Make build_reply_markup treat it as inline.
    try:
        original = Button._is_inline
        if not getattr(Button, "_translation_pro_copy_patch", False):
            def _patched_is_inline(button):
                if isinstance(button, constructor):
                    return True
                return original(button)
            Button._is_inline = staticmethod(_patched_is_inline)
            Button._translation_pro_copy_patch = True
    except Exception:
        # If the local fork already handles KeyboardButtonCopy, no patch is
        # needed. If it does not, Telegram will reject the raw constructor;
        # callers simply omit the button rather than breaking translation.
        return None

    try:
        return constructor(text="📋 Copy Translation", copy_text=text)
    except TypeError:
        try:
            return constructor("📋 Copy Translation", text)
        except Exception:
            return None
    except Exception:
        return None


def _share_query(query: str) -> Optional[str]:
    """Return the exact inline query to prefill after chat selection.

    Telegram prepends the bot username automatically. The query itself must
    therefore contain the plugin switch (`tr`) as well as the user's original
    language/text arguments. Never reconstruct it from parsed fields: doing so
    can silently drop syntax such as `tr`, `fa>en`, or other future arguments.
    """
    query = query.strip()
    if not query:
        return None
    full_query = f"tr {query}"
    if len(full_query.encode("utf-8")) > MAX_SHARE_QUERY_BYTES:
        return None
    return full_query


def _translation_buttons(target: str, source: str, original: str, translated: str, *, inline: bool = False, share_query: Optional[str] = None):
    rows = []

    copy_button = _button_copy(translated)
    if share_query is not None:
        share_query = share_query.strip()
        if not share_query.startswith("tr "):
            share_query = f"tr {share_query}"
        if len(share_query.encode("utf-8")) > MAX_SHARE_QUERY_BYTES:
            share_query = None

    action_row = []
    if copy_button is not None:
        action_row.append(copy_button)
    if share_query is not None:
        # same_peer=False is intentional: Telegram opens the chat picker,
        # then places @BotUsername + this exact query in the selected chat's
        # input field.
        action_row.append(Button.switch_inline("📤 Share", query=share_query, same_peer=False))

    if action_row:
        rows.append(action_row)

    rows.append([
        Button.switch_inline("↻ Translate Again", query=f"tr {target} ", same_peer=True),
        Button.switch_inline("🌐 Change Language", query="tr ", same_peer=True),
    ])

    return rows


def _again_button(target: str):
    return [
        [Button.switch_inline("↻ Translate Again", query=f"tr {target} ", same_peer=True)],
        [Button.switch_inline("🌐 Change Language", query="tr ", same_peer=True)],
    ]


def _usage() -> str:
    return (
        "<b>🌐 Translation Pro</b>\n\n"
        f"<b>Command</b>\n<code>{HNDLR}tr en Hello, how are you?</code>\n"
        f"<code>{HNDLR}tr en</code> — reply to a message\n"
        f"<code>{HNDLR}tr fa&gt;en سلام حالت چطوره؟</code>\n"
        f"<code>{HNDLR}tr auto&gt;en text</code>\n\n"
        "<b>Inline</b>\n"
        "<code>@AssisXBot tr en سلام حالت چطوره؟</code>\n\n"
        "The source language is detected automatically unless you specify it explicitly.\n"
        f"Use <code>{HNDLR}tr list</code> to see all supported language codes."
    )


def _language_list() -> str:
    lines = ["<b>🌐 Language codes for Translation Plugin</b>", ""]
    for code, name in LANGUAGES.items():
        lines.append(f"≽ <code>{_escape(code)}</code> — {_escape(name)}")
    lines.extend(
        [
            "",
            "<b>Translation Usage</b>",
            f"<code>{HNDLR}tr &lt;language&gt; &lt;text&gt;</code>",
            f"<code>{HNDLR}tr &lt;language&gt;</code> + Reply",
            f"<code>{HNDLR}tr &lt;source&gt;&gt;&lt;target&gt; &lt;text&gt;</code>",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Command interface
# ---------------------------------------------------------------------------


@heartless_cmd(pattern=r"tr(?:\s+(.*)|$)")
async def translation_command(event):
    args = (event.pattern_match.group(1) or "").strip()

    if args.casefold() in {"help", "-h", "--help"}:
        return await eor(event, _usage(), parse_mode="html", time=18)
    if args.casefold() in {"list", "langs", "languages"}:
        return await eor(event, _language_list(), parse_mode="html", time=35)

    if not args and event.is_reply:
        args = "en"

    target, source, text = _parse_request(args)
    if not _normalise_code(target) or target == "auto":
        return await eor(
            event,
            "<b>❌ Invalid target language.</b>\n\n" + _usage(),
            parse_mode="html",
            time=12,
        )

    if not text and event.is_reply:
        replied = await event.get_reply_message()
        text = (replied.raw_text or "").strip() if replied else ""

    if not text:
        return await eor(event, _usage(), parse_mode="html", time=15)
    if len(text) > MAX_INPUT:
        return await eor(
            event,
            f"<b>⚠️ Text is too long.</b> Maximum: <code>{MAX_INPUT:,}</code> characters.",
            parse_mode="html",
            time=8,
        )

    status = await eor(
        event,
        f"🌐 <b>Translating to {_escape(_display_name(target))}...</b>",
        parse_mode="html",
    )

    try:
        translated, detected = await _translate(text, target, source)
        result = _format_result(text, translated, detected, target, auto_detected=(source == "auto"))
    except Exception:
        LOGS.exception("Translation Pro command failed")
        return await eor(
            status,
            "<b>❌ Translation failed.</b>\nAll available translation services were unavailable. Please try again.",
            parse_mode="html",
            time=10,
        )

    buttons = _translation_buttons(target, detected, text, translated, share_query=f"tr {target} {text}")
    if len(result) <= MAX_TELEGRAM_TEXT:
        return await eor(
            status,
            result,
            parse_mode="html",
            link_preview=False,
            buttons=buttons,
        )

    payload = (
        "Translation Pro\n\n"
        f"From: {_display_name(detected)} ({detected})\n"
        f"To: {_display_name(target)} ({target})\n\n"
        f"Original\n{text}\n\nTranslated\n{translated}\n"
    ).encode("utf-8")
    file = io.BytesIO(payload)
    file.name = f"translation_{target}.txt"
    return await eor(
        status,
        f"🌐 <b>Translation complete</b>\n{_escape(_display_name(detected))} → {_escape(_display_name(target))}",
        parse_mode="html",
        file=file,
        buttons=buttons,
    )


# ---------------------------------------------------------------------------
# Inline interface
# ---------------------------------------------------------------------------


@in_pattern(r"tr(?:\s+(.*)|$)")
async def translation_inline(event):
    query = (event.pattern_match.group(1) or "").strip()

    if not query:
        article = await event.builder.article(
            title="Translation Pro",
            description="Translate text to any supported language",
            text=_usage(),
            parse_mode="html",
            buttons=_again_button("en"),
        )
        return await event.answer([article], cache_time=0)

    command = query.casefold()
    if command == "help":
        article = await event.builder.article(
            title="Translation Pro — Help",
            description="Commands and inline usage",
            text=_usage(),
            parse_mode="html",
            buttons=_again_button("en"),
        )
        return await event.answer([article], cache_time=30)

    if command in {"list", "langs", "languages"}:
        article = await event.builder.article(
            title="Translation Languages",
            description=f"{len(LANGUAGES)} supported language codes",
            text=_language_list(),
            parse_mode="html",
            buttons=_again_button("en"),
        )
        return await event.answer([article], cache_time=60)

    target, source, text = _parse_request(query)
    target = _normalise_code(target)

    if not target or target == "auto":
        article = await event.builder.article(
            title="Invalid target language",
            description="Example: tr en Hello",
            text="<b>❌ Invalid target language.</b>\n\n" + _usage(),
            parse_mode="html",
            buttons=_again_button("en"),
        )
        return await event.answer([article], cache_time=0)

    if not text:
        article = await event.builder.article(
            title=f"Translate to {_display_name(target)}",
            description="Enter text after the language code",
            text=(
                f"<b>🌐 Translate to {_escape(_display_name(target))}</b>\n\n"
                f"Example:\n<code>tr {_escape(target)} Hello, how are you?</code>"
            ),
            parse_mode="html",
            buttons=_again_button(target),
        )
        return await event.answer([article], cache_time=0)

    if len(text) > MAX_INPUT:
        article = await event.builder.article(
            title="Text is too long",
            description=f"Maximum {MAX_INPUT:,} characters",
            text=f"<b>⚠️ Text is too long.</b> Maximum: <code>{MAX_INPUT:,}</code> characters.",
            parse_mode="html",
            buttons=_again_button(target),
        )
        return await event.answer([article], cache_time=0)

    try:
        translated, detected = await _translate(text, target, source, fast_only=True)
    except Exception:
        LOGS.exception("Translation Pro inline failed")
        article = await event.builder.article(
            title="Translation temporarily unavailable",
            description="All translation backends failed",
            text="<b>❌ Translation failed.</b>\nPlease try again in a few seconds.",
            parse_mode="html",
            buttons=_again_button(target),
        )
        return await event.answer([article], cache_time=0)

    output = _fit_inline_result(
        text,
        translated,
        detected,
        target,
        auto_detected=(source == "auto"),
    )

    article = await event.builder.article(
        title=f"{_display_name(target)} translation",
        description=re.sub(r"\s+", " ", translated)[:180],
        text=output,
        parse_mode="html",
        buttons=_translation_buttons(
            target,
            detected,
            text,
            translated,
            inline=True,
            share_query=query,
        ),
    )
    return await event.answer([article], cache_time=0)

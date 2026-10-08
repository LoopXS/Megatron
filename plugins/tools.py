"""
✘ Commands Available -

• {i}tempmail
   Generate Temporary Mail

• `{i}circle`
    Reply to a audio song or gif to get video note.

• `{i}ls`
    Get all the Files inside a Directory.

• `{i}bots`
    Shows the number of bots in the current chat with their perma-link.

• `{i}hl <a link> <text-optional>`
    Embeds the link with a whitespace as message.

• `{i}id`
    Reply a Sticker to Get Its Id
    Reply a User to Get His Id
    Without Replying You Will Get the Chat's Id

• `{i}sg <username>` or `{i}sgu <username>`
    Get Name History of the user.

• `{i}tr <dest lang code> <(reply to) a message>`
    Get translated message.

• `{i}webshot <url>`
    Get a screenshot of the webpage.

• `{i}shorturl <url> <id-optional>`
    shorten any url...
"""

import asyncio
import glob
import html
import io
import json
import os
import re

from requests import get

try:
    import cv2
except ImportError:
    cv2 = None

from telethon import events, types
from telethon.errors.rpcerrorlist import MessageTooLongError, YouBlockedUserError
from telethon.tl.types import (
    ChannelParticipantAdmin,
    ChannelParticipantsBots,
    DocumentAttributeVideo,
)

from CythonX.fns.tools import metadata, translate
from CythonX.fns.helper import async_searcher

from . import HNDLR, LOGS, ULTConfig, bash, con, eod, eor, get_string, get_pstring
from . import humanbytes as hb
from . import inline_mention, mediainfo, heartless_bot, heartless_cmd


def sanga_seperator(sanga_list):
    string = "".join(info[info.find("\n") + 1 :] for info in sanga_list)
    string = re.sub(r"^$\n", "", string, flags=re.MULTILINE)
    name, username = string.split("Usernames**")
    name = name.split("Names")[1]
    return name, username


def mentionuser(name, userid):
    return f"[{name}](tg://user?id={userid})"



# ---------------------------------------------------------------------------
# Professional translation support
# ---------------------------------------------------------------------------

# Google Translate's public web endpoint accepts the ISO language codes below.
# Aliases are intentionally kept local so the command works without an extra
# language-code package or database.
_TR_LANGUAGES = {
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

_TR_ALIASES = {
    "persian": "fa", "farsi": "fa", "فارسی": "fa",
    "english": "en", "انگلیسی": "en",
    "arabic": "ar", "عربی": "ar",
    "turkish": "tr", "ترکی": "tr",
    "russian": "ru", "روسی": "ru",
    "german": "de", "آلمانی": "de",
    "french": "fr", "فرانسوی": "fr",
    "spanish": "es", "اسپانیایی": "es",
    "italian": "it", "ایتالیایی": "it",
    "portuguese": "pt", "پرتغالی": "pt",
    "hindi": "hi", "هندی": "hi",
    "urdu": "ur", "اردو": "ur",
    "chinese": "zh-CN", "چینی": "zh-CN",
    "simplified chinese": "zh-CN", "traditional chinese": "zh-TW",
    "japanese": "ja", "ژاپنی": "ja",
    "korean": "ko", "کره ای": "ko", "کره‌ای": "ko",
    "dutch": "nl", "polish": "pl", "ukrainian": "uk",
    "bulgarian": "bg", "بلغاری": "bg",
}

def _tr_normalize_language(value):
    """Return a Google language code or None for an unknown language."""
    if not value:
        return None
    raw = value.strip().lower().replace("_", "-")
    if raw in _TR_ALIASES:
        return _TR_ALIASES[raw]
    for code in _TR_LANGUAGES:
        if raw == code.lower():
            return code
    return None


def _tr_language_help():
    common = (
        ("fa", "فارسی"), ("en", "English"), ("ar", "العربية"),
        ("de", "Deutsch"), ("fr", "Français"), ("es", "Español"),
        ("tr", "Türkçe"), ("ru", "Русский"), ("hi", "हिन्दी"),
        ("ur", "اردو"), ("it", "Italiano"), ("pt", "Português"),
        ("zh-CN", "简体中文"), ("zh-TW", "繁體中文"), ("ja", "日本語"),
        ("ko", "한국어"), ("nl", "Nederlands"), ("pl", "Polski"),
        ("uk", "Українська"), ("bg", "Български"),
    )
    return "\n".join(f"• <code>{code}</code> — {name}" for code, name in common)


async def _tr_google(text, target, source="auto"):
    """Translate through Google's public endpoint without assuming JSON.

    Some Google edge nodes return HTML (or another non-JSON response) for the
    /translate_a/single endpoint.  The previous implementation delegated JSON
    decoding to ``async_searcher(re_json=True)``, which made that normal HTTP
    response become an unhelpful JSONDecodeError.  We deliberately read the
    body as text first and validate the response ourselves.
    """
    import aiohttp

    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": source or "auto",
        "tl": target,
        "dt": "t",
        "q": text,
    }
    headers = {
        "Accept": "application/json,text/plain,*/*",
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "Chrome/128.0 Safari/537.36"
        ),
    }
    timeout = aiohttp.ClientTimeout(total=20, connect=8, sock_read=15)

    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        async with session.get(url, params=params) as response:
            body = await response.text(errors="replace")
            if response.status != 200:
                raise RuntimeError(
                    f"Google Translate HTTP {response.status}: {body[:120]!r}"
                )

    body = body.strip()
    if not body:
        raise ValueError("Google Translate returned an empty response")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Google Translate returned a non-JSON response "
            f"({body[:120]!r})"
        ) from exc

    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        raise ValueError("Unexpected Google Translate response")

    chunks = []
    for item in payload[0]:
        if isinstance(item, list) and item and item[0] is not None:
            chunks.append(str(item[0]))
    translated = "".join(chunks).strip()
    if not translated:
        raise ValueError("Google Translate returned an empty translation")

    detected = "auto"
    if len(payload) > 2 and isinstance(payload[2], str) and payload[2]:
        detected = payload[2]
    return translated, detected


async def _tr_google_web(text, target, source="auto"):
    """Fallback to Google's mobile/web translator endpoint.

    This endpoint returns HTML rather than JSON, so it is intentionally kept
    separate from ``_tr_google``.  It is useful when Google's JSON endpoint is
    blocked or served through an edge which returns an HTML page.
    """
    import aiohttp

    url = "https://translate.google.com/m"
    params = {"tl": target, "sl": source or "auto", "q": text}
    headers = {
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36",
    }
    timeout = aiohttp.ClientTimeout(total=20, connect=8, sock_read=15)

    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        async with session.get(url, params=params) as response:
            body = await response.text(errors="replace")
            if response.status != 200:
                raise RuntimeError(f"Google web HTTP {response.status}")

    # Google's mobile page has historically used both ``result-container``
    # and ``t0``.  Decode HTML entities after extracting the result.
    matches = re.findall(
        r'class=["\'](?:result-container|t0)["\'][^>]*>(.*?)<',
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not matches:
        # A second pattern handles minor markup changes where attributes are
        # ordered differently.
        matches = re.findall(
            r'<div[^>]+class=["\'][^"\']*result-container[^"\']*["\'][^>]*>(.*?)</div>',
            body,
            flags=re.IGNORECASE | re.DOTALL,
        )
    if not matches:
        raise ValueError("Google web translator returned no translation")

    translated = html.unescape(re.sub(r"<[^>]+>", "", matches[0])).strip()
    if not translated:
        raise ValueError("Google web translator returned an empty translation")
    return translated, source if source and source != "auto" else "auto"


def _tr_detect_source(text):
    """Detect source language reliably before translation.

    Statistical detectors can misclassify short Persian/Urdu messages because
    both languages share the Arabic script. We therefore use script-specific
    signals first and langdetect as a secondary detector.
    """
    text = str(text or "").strip()
    if not text:
        return "auto"

    # Persian-specific letters. These are strong signals even for very short
    # messages such as "سلام چطوری".
    if re.search(r"[پچژگ]", text):
        return "fa"

    # Urdu-specific letters, checked after Persian because Persian text can
    # contain characters shared with Urdu.
    if re.search(r"[ٹڈڑںھے]", text):
        return "ur"

    # Script-specific languages are more reliable than statistical detection.
    script_map = (
        (r"[\u0900-\u097F]", "hi"),
        (r"[\u0A80-\u0AFF]", "gu"),
        (r"[\u0B00-\u0B7F]", "or"),
        (r"[\u0B80-\u0BFF]", "ta"),
        (r"[\u0C00-\u0C7F]", "te"),
        (r"[\u0C80-\u0CFF]", "kn"),
        (r"[\u0D00-\u0D7F]", "ml"),
        (r"[\u0D80-\u0DFF]", "si"),
        (r"[\u0E00-\u0E7F]", "th"),
        (r"[\u0530-\u058F]", "hy"),
        (r"[\u0590-\u05FF]", "he"),
        (r"[\u10A0-\u10FF]", "ka"),
        (r"[\u3040-\u30FF]", "ja"),
        (r"[\uAC00-\uD7AF]", "ko"),
        (r"[\u4E00-\u9FFF]", "zh-CN"),
    )
    for pattern, code in script_map:
        if re.search(pattern, text):
            return code

    # Short Persian messages often contain no unique Persian letter. Use a
    # conservative lexical check before falling back to Arabic.
    words = set(re.findall(r"[\u0600-\u06FF]+", text.lower()))
    persian_words = {
        "سلام", "خوبی", "چطوری", "چطوره", "هستی", "هست", "نیستی",
        "من", "تو", "شما", "ما", "این", "آن", "برای", "ممنون",
        "مرسی", "لطفا", "لطفاً", "چرا", "کجا", "چگونه", "چطور",
        "چی", "چه", "خیلی", "امروز", "فردا", "دیروز", "دوست",
        "دارم", "داری", "دارید", "میخوام", "میخواهم", "نمی",
    }
    arabic_markers = {
        "السلام", "عليكم", "عليکم", "كيف", "حالك", "ماذا", "أين",
        "لماذا", "أنا", "أنت", "نحن", "هذا", "هذه", "هناك",
    }
    if words & persian_words and not (words & arabic_markers):
        return "fa"

    # Arabic script without Persian/Urdu-specific characters.
    if re.search(r"[\u0600-\u06FF\u0750-\u077F]", text):
        return "ar"

    try:
        from langdetect import detect as detect_language
        detected = detect_language(text)
        if detected:
            detected = detected.replace("_", "-").lower()
            if detected.startswith("zh"):
                return "zh-CN"
            if detected.startswith("ur"):
                return "ur"
            return detected.split("-")[0]
    except Exception as exc:
        LOGS.debug("Local language detection failed: %s", exc)

    return "auto"


async def _tr_lingva(text, target, source="auto"):
    """Translate through a public Lingva instance.

    Lingva exposes a REST API over a Google-Translate scraper. It is useful as
    a separate backend when Google's public endpoint rate-limits the bot.
    Multiple current instances are tried so one unavailable instance does not
    break translation.
    """
    import aiohttp
    from urllib.parse import quote

    source_code = source if source and source.lower() != "auto" else _tr_detect_source(text)
    if not source_code or source_code.lower() == "auto":
        source_code = "auto"

    instances = (
        "https://lingva.ml",
        "https://translate.plausibility.cloud",
        "https://translate.dr460nf1r3.org",
    )
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
    }
    timeout = aiohttp.ClientTimeout(total=18, connect=6, sock_read=12)
    encoded = quote(str(text), safe="")

    last_error = None
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        for instance in instances:
            url = f"{instance}/api/v1/{source_code}/{target}/{encoded}"
            try:
                async with session.get(url) as response:
                    body = await response.text(errors="replace")
                    if response.status != 200:
                        raise RuntimeError(f"HTTP {response.status}")
                payload = json.loads(body)
                if not isinstance(payload, dict):
                    raise ValueError("Unexpected Lingva response")
                translated = payload.get("translation")
                if not translated:
                    if payload.get("error"):
                        raise ValueError(str(payload["error"]))
                    raise ValueError("Lingva returned an empty translation")
                return str(translated).strip(), source_code
            except Exception as exc:
                last_error = exc
                LOGS.debug("Lingva instance failed (%s): %s", instance, exc)

    raise RuntimeError(f"Lingva unavailable: {last_error}")


async def _tr_mymemory(text, target, source="auto"):
    """Last-resort public backend using MyMemory's translation API.

    MyMemory does not accept ``AUTO`` as a source language.  Detect the
    language locally first and always send a concrete ISO language code.
    """
    import aiohttp

    url = "https://api.mymemory.translated.net/get"
    source_code = source if source and source.lower() != "auto" else _tr_detect_source(text)
    if not source_code or source_code.lower() == "auto":
        raise ValueError("Unable to determine source language for MyMemory")
    langpair = f"{source_code}|{target}"
    params = {"q": text, "langpair": langpair}
    headers = {"Accept": "application/json", "User-Agent": "CythonX-Translator/1.0"}
    timeout = aiohttp.ClientTimeout(total=20, connect=8, sock_read=15)

    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        async with session.get(url, params=params) as response:
            body = await response.text(errors="replace")
            if response.status != 200:
                raise RuntimeError(f"MyMemory HTTP {response.status}")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError("MyMemory returned a non-JSON response") from exc

    if not isinstance(payload, dict):
        raise ValueError("Unexpected MyMemory response")
    response_data = payload.get("responseData") or {}
    translated = response_data.get("translatedText") if isinstance(response_data, dict) else None
    if not translated:
        raise ValueError("MyMemory returned an empty translation")

    # The language used in langpair is authoritative. MyMemory's matches
    # metadata can report a regional or incorrect source for short text.
    detected = str(source_code).replace("_", "-").lower()
    return html.unescape(str(translated)).strip(), detected


async def _tr_translate(text, target, source="auto"):
    """Translate with several independent backends and clear diagnostics."""
    backends = (
        ("Google JSON", _tr_google),
        ("Google web", _tr_google_web),
        ("Lingva", _tr_lingva),
        ("MyMemory", _tr_mymemory),
    )
    errors = []

    detected_source = source
    if not detected_source or detected_source.lower() == "auto":
        detected_source = _tr_detect_source(text)

    for name, backend in backends:
        try:
            backend_source = source
            if name == "MyMemory":
                backend_source = detected_source
            translated, detected = await backend(text, target, backend_source)
            if translated:
                if name != "Google JSON":
                    LOGS.info("Translation backend used: %s", name)
                return translated, detected
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            LOGS.warning("Translation backend failed (%s): %s", name, exc)

    # Preserve compatibility with the project's original translator.  It is
    # synchronous, so it must never be awaited directly from the event loop.
    try:
        fallback = await asyncio.to_thread(
            translate,
            text,
            lang_tgt=target,
            lang_src=source,
            timeout=30,
        )
        if isinstance(fallback, tuple):
            fallback = fallback[0]
        if fallback:
            return str(fallback).strip(), source
        errors.append("Legacy Google translator: empty response")
    except Exception as exc:
        errors.append(f"Legacy Google translator: {exc}")
        LOGS.warning("Legacy translation backend failed: %s", exc)

    LOGS.error("All translation backends failed: %s", " | ".join(errors))
    raise RuntimeError("Translation service is temporarily unavailable.")


def _tr_escape(text):
    """Escape arbitrary user text for Telegram HTML parse mode."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _tr_usage():
    return (
        "<b>🌐 Translation</b>\n\n"
        "Usage:\n"
        "• <code>tr fa</code> — translate a replied message to Persian\n"
        "• <code>tr fa hello</code> — translate text directly\n"
        "• <code>tr english hello</code> — language names are supported\n"
        "• <code>tr list</code> — show common language codes\n\n"
        "The source language is detected automatically."
    )


@heartless_cmd(pattern="tempmail$")
async def demn(ult):
    chat = "@TempMailBot"
    msg = await eor(ult, "Generating Temporary Mail...")
    async with heartless_bot.conversation(chat) as conv:
        try:
            response = conv.wait_event(
                events.NewMessage(incoming=True, from_users=220112646)
            )
            await conv.send_message("/start")
            await asyncio.sleep(1)
            await conv.send_message("/create")
            response = await response
            data = response.reply_markup.rows[1].buttons[0].url
            link = data
            await heartless_bot.send_read_acknowledge(chat)
        except YouBlockedUserError:
            await msg.edit("Boss! Please Unblock @TempMailBot ")
            return
        await eor(
            ult,
            f"TEMPMAIL ~ {response.message.message}\n\n[CLICK TO VIEW INBOX]({link})",
        )


@heartless_cmd(pattern="id( (.*)|$)", manager=True, assistant=True)
async def _(event):
    ult = event
    match = event.pattern_match.group(1).strip()
    if match:
        try:
            ids = await event.client.parse_id(match)
        except Exception as er:
            return await event.eor(str(er))
        return await event.eor(
            f"**Chat ID:**  `{event.chat_id}`\n**User ID:**  `{ids}`"
        )
    data = f"**Current Chat ID:**  `{event.chat_id}`"
    if event.reply_to_msg_id:
        event = await event.get_reply_message()
        data += f"\n**From User ID:**  `{event.sender_id}`"
    if event.media:
        bot_api_file_id = event.file.id
        data += f"\n**Bot API File ID:**  `{bot_api_file_id}`"
    data += f"\n**Msg ID:**  `{event.id}`"
    await ult.eor(data)


@heartless_cmd(pattern="bots( (.*)|$)", groups_only=True, manager=True)
async def _(ult):
    mentions = "• **Bots in this Chat**: \n"
    if input_str := ult.pattern_match.group(1).strip():
        mentions = f"• **Bots in **{input_str}: \n"
        try:
            chat = await ult.client.parse_id(input_str)
        except Exception as e:
            return await ult.eor(str(e))
    else:
        chat = ult.chat_id
    try:
        async for x in ult.client.iter_participants(
            chat,
            filter=ChannelParticipantsBots,
        ):
            if isinstance(x.participant, ChannelParticipantAdmin):
                mentions += f"\n⚜️ {inline_mention(x)} `{x.id}`"
            else:
                mentions += f"\n• {inline_mention(x)} `{x.id}`"
    except Exception as e:
        mentions += f" {str(e)}" + "\n"
    await ult.eor(mentions)


@heartless_cmd(
    pattern="hl( (.*)|$)",
)
async def _(ult):
    input_ = ult.pattern_match.group(1).strip()
    if not input_:
        return await ult.eor("`Input some link`", time=5)
    text = None
    if len(input_.split()) > 1:
        spli_ = input_.split()
        input_ = spli_[0]
        text = spli_[1]
    if not text:
        text = "ㅤㅤㅤㅤㅤㅤㅤ"
    await ult.eor(f"[{text}]({input_})", link_preview=False)


@heartless_cmd(
    pattern="circle$",
)
async def _(e):
    reply = await e.get_reply_message()
    if not (reply and reply.media):
        return await e.eor("`Reply to a gif or audio file only.`")
    if "audio" in mediainfo(reply.media):
        msg = await e.eor("`Downloading...`")
        try:
            bbbb = await reply.download_media(thumb=-1)
        except TypeError:
            bbbb = ULTConfig.thumb
        im = cv2.imread(bbbb)
        dsize = (512, 512)
        output = cv2.resize(im, dsize, interpolation=cv2.INTER_AREA)
        cv2.imwrite("img.jpg", output)
        thumb = "img.jpg"
        audio, _ = await e.client.fast_downloader(reply.document)
        await msg.edit("`Creating video note...`")
        await bash(
            f'ffmpeg -i "{thumb}" -i "{audio.name}" -preset ultrafast -c:a libmp3lame -ab 64 circle.mp4 -y'
        )
        await msg.edit("`Uploading...`")
        data = await metadata("circle.mp4")
        file, _ = await e.client.fast_uploader("circle.mp4", to_delete=True)
        await e.client.send_file(
            e.chat_id,
            file,
            thumb=thumb,
            reply_to=reply,
            attributes=[
                DocumentAttributeVideo(
                    duration=min(data["duration"], 60),
                    w=512,
                    h=512,
                    round_message=True,
                )
            ],
        )

        await msg.delete()
        [os.remove(k) for k in [audio.name, thumb]]
    elif mediainfo(reply.media) == "gif" or mediainfo(reply.media).startswith("video"):
        msg = await e.eor("**Creating video note**")
        file = await reply.download_media("resources/downloads/")
        if file.endswith(".webm"):
            nfile = await con.ffmpeg_convert(file, "file.mp4")
            os.remove(file)
            file = nfile
        if file:
            await e.client.send_file(
                e.chat_id,
                file,
                video_note=True,
                thumb=ULTConfig.thumb,
                reply_to=reply,
            )
            os.remove(file)
        await msg.delete()

    else:
        await e.eor("`Reply to a gif or audio file only.`")


FilesEMOJI = {
    "py": "🐍",
    "json": "🔮",
    ("sh", "bat"): "⌨️",
    (".mkv", ".mp4", ".avi", ".gif", "webm"): "🎥",
    (".mp3", ".ogg", ".m4a", ".opus"): "🔊",
    (".jpg", ".jpeg", ".png", ".webp", ".ico"): "🖼",
    (".txt", ".text", ".log"): "📄",
    (".apk", ".xapk"): "📲",
    (".pdf", ".epub"): "📗",
    (".zip", ".rar"): "🗜",
    (".exe", ".iso"): "⚙",
}


@heartless_cmd(
    pattern="ls( (.*)|$)",
)
async def _(e):
    files = e.pattern_match.group(1).strip()
    if not files:
        files = "*"
    elif files.endswith("/"):
        files += "*"
    elif "*" not in files:
        files += "/*"
    files = glob.glob(files)
    if not files:
        return await e.eor("`Directory Empty or Incorrect.`", time=5)
    folders = []
    allfiles = []
    for file in sorted(files):
        if os.path.isdir(file):
            folders.append(f"📂 {file}")
        else:
            for ext in FilesEMOJI.keys():
                if file.endswith(ext):
                    allfiles.append(f"{FilesEMOJI[ext]} {file}")
                    break
            else:
                if "." in str(file)[1:]:
                    allfiles.append(f"🏷 {file}")
                else:
                    allfiles.append(f"📒 {file}")
    omk = [*sorted(folders), *sorted(allfiles)]
    text = ""
    fls, fos = 0, 0
    flc, foc = 0, 0
    for i in omk:
        try:
            emoji = i.split()[0]
            name = i.split(maxsplit=1)[1]
            nam = name.split("/")[-1]
            if os.path.isdir(name):
                size = 0
                for path, dirs, files in os.walk(name):
                    for f in files:
                        fp = os.path.join(path, f)
                        size += os.path.getsize(fp)
                if hb(size):
                    text += f"{emoji} `{nam}`  `{hb(size)}" + "`\n"
                    fos += size
                else:
                    text += f"{emoji} `{nam}`" + "\n"
                foc += 1
            else:
                if hb(int(os.path.getsize(name))):
                    text += (
                        emoji
                        + f" `{nam}`"
                        + "  `"
                        + hb(int(os.path.getsize(name)))
                        + "`\n"
                    )
                    fls += int(os.path.getsize(name))
                else:
                    text += f"{emoji} `{nam}`" + "\n"
                flc += 1
        except BaseException:
            pass
    tfos, tfls, ttol = hb(fos), hb(fls), hb(fos + fls)
    if not hb(fos):
        tfos = "0 B"
    if not hb(fls):
        tfls = "0 B"
    if not hb(fos + fls):
        ttol = "0 B"
    text += f"\n\n`Folders` :  `{foc}` :   `{tfos}`\n`Files` :       `{flc}` :   `{tfls}`\n`Total` :       `{flc+foc}` :   `{ttol}`"
    try:
        if (flc + foc) > 100:
            text = text.replace("`", "")
        await e.eor(text)
    except MessageTooLongError:
        with io.BytesIO(str.encode(text)) as out_file:
            out_file.name = "output.txt"
            await e.reply(f"`{e.text}`", file=out_file, thumb=ULTConfig.thumb)
        await e.delete()


@heartless_cmd(
    pattern="sg(|u)(?:\\s|$)([\\s\\S]*)",
    fullsudo=True,
)
async def sangmata(event):
    "To get name/username history."
    cmd = event.pattern_match.group(1)
    user = event.pattern_match.group(2)
    reply = await event.get_reply_message()
    if not user and reply:
        user = str(reply.sender_id)
    if not user:
        await event.edit(
            "`Reply to  user's text message to get name/username history or give userid/username`",
        )
        await asyncio.sleep(10)
        return await event.delete()

    try:
        if user.isdigit():
            userinfo = await heartless_bot.get_entity(int(user))
        else:
            userinfo = await heartless_bot.get_entity(user)
    except ValueError:
        userinfo = None
    if not isinstance(userinfo, types.User):
        await event.edit("`Can't fetch the user...`")
        await asyncio.sleep(10)
        return await event.delete()

    await event.edit("`Processing...`")
    async with event.client.conversation("@SangMata_beta_bot") as conv:
        try:
            await conv.send_message(f"{userinfo.id}")
        except YouBlockedUserError:
            return await ultevent.edit("Please unblock the bot and try again")
        responses = []
        while True:
            try:
                response = await conv.get_response(timeout=2)
            except asyncio.TimeoutError:
                break
            responses.append(response.text)
        await event.client.send_read_acknowledge(conv.chat_id)

    if not responses:
        await event.edit("`Bot can't fetch results`")
        await asyncio.sleep(10)
        await event.delete()
    if "No records found" in responses or "No data available" in responses:
        await event.edit("`The user doesn't have any record`")
        await asyncio.sleep(10)
        await event.delete()

    names, usernames = sanga_seperator(responses)
    check = (usernames, "Username") if cmd == "u" else (names, "Name")
    user_name = (
        f"{userinfo.first_name} {userinfo.last_name}"
        if userinfo.last_name
        else userinfo.first_name
    )
    output = f"**➜ User Info :**  {mentionuser(user_name, userinfo.id)}\n**➜ {check[1]} History :**\n{check[0]}"
    await event.edit(output)


@heartless_cmd(pattern="webshot( (.*)|$)")
async def webss(event):
    xx = await event.eor(get_pstring("com_1", "load"))
    xurl = event.pattern_match.group(1).strip()
    if xurl:
        x = get(f"https://mini.s-shot.ru/1920x1080/JpE6/1024/7100/?{xurl}")
        y = "shot.jpg"
        with open(y, "wb") as f:
            f.write(x.content)
        if (await heartless_bot.get_me()).premium:
            await heartless_bot.send_file(
                event.chat_id,
                y,
                caption=f"[📷](emoji/5258205968025525531) **WebShot Generated**\n[🔗](emoji/5983262173474853675) **URL** : {xurl}\n[✨](emoji/5244698746851173535) Ⲏⲉⲁʀⲧⳑⲉⲋⲋ Ⲉⲭⲥⳑυⲋⲓⳳⲉ Ⲃⲟⲧ [✨](emoji/5244698746851173535)",
                force_document=False,
            )
        else:
            await heartless_bot.send_file(
                event.chat_id,
                y,
                caption=f"📷 **WebShot Generated**\n🔗 **URL** : {xurl}\n✨ Ⲏⲉⲁʀⲧⳑⲉⲋⲋ Ⲉⲭⲥⳑυⲋⲓⳳⲉ Ⲃⲟⲧ",
                force_document=False,
            )
        os.remove(y)
    else:
        await eod(xx, f"Please provide me a URL...", time=5)
    await xx.delete()


@heartless_cmd(pattern="shorturl ?(.*)")
async def short_url(event):
    input_url = event.pattern_match.group(1)

    if not input_url:
        reply_msg = await event.get_reply_message()
        if reply_msg:
            input_url = reply_msg.text
        else:
            return await eor(event, "`Please provide a URL to shorten.`")

    try:
        s = pyshorteners.Shortener()
        if "http://tinyurl.com" in input_url.lower():
            shortened_url = s.tinyurl.expand(input_url)
            action = "Expanded"
        else:
            shortened_url = s.tinyurl.short(input_url)
            action = "Shortened"

        output_message = (
            f"**URL {action}**\n"
            f"**Given Link** ➠ **{input_url}**\n"
            f"**{action} Link** ➠ **[LINK]({shortened_url})**"
        )

        if event.reply_to_msg_id:
            await event.delete()
            await event.reply(output_message)
        else:
            await eor(event, output_message)

    except Exception as e:
        await eor(event, f"An error occurred: {e}")

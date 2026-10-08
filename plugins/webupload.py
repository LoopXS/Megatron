"""
Megatron WebUpload Pro
----------------------

A dependency-light, multi-provider file uploader for Telethon/Megatron.

Commands
--------
.webupload
    Reply to any Telegram media/file and upload it.

.webupload <path>
    Upload a local file.

.webupload <provider>
    Upload the replied file using a specific provider.

.webupload <provider> <path>
    Upload a local file using a specific provider.

Providers
---------
auto       Smart fallback chain (recommended)
gofile     Gofile
pixeldrain Pixeldrain
uguu       Uguu
tmpfiles   tmpfiles.org

Aliases:
    .wup
    .upload

The plugin does not inspect the file extension and does not reject formats.
Provider-specific size/retention limits still apply. In `auto` mode, failed
providers are skipped and the next compatible provider is attempted.
"""

from __future__ import annotations

import asyncio
import html
import json
import os
import re
import secrets
import shlex
import tempfile
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote, quote_plus

import aiohttp

from . import LOGS, Button, asst, callback, eod, eor, in_pattern, udB, heartless_cmd


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_TIMEOUT = aiohttp.ClientTimeout(
    total=None,
    connect=30,
    sock_connect=30,
    sock_read=None,
)

_CHUNK_SIZE = 1024 * 1024
_PROGRESS_INTERVAL = 2.0

# The order matters in auto mode.
# Gofile is the primary generic host; Pixeldrain is the large-file fallback.
_PROVIDER_ORDER = ("gofile", "pixeldrain", "uguu", "tmpfiles")

_PROVIDER_ALIASES = {
    "auto": "auto",
    "default": "auto",
    "gofile": "gofile",
    "go": "gofile",
    "pixeldrain": "pixeldrain",
    "pixel": "pixeldrain",
    "pd": "pixeldrain",
    "uguu": "uguu",
    "tmpfiles": "tmpfiles",
    "tmpfile": "tmpfiles",
    "tmp": "tmpfiles",
}

_HELP = """**☁️ WebUpload Pro**

Upload almost any file format to a public file host.

**Usage**
`{cmd}webupload` — reply to a file/media
`{cmd}webupload <path>` — upload a local file
`{cmd}webupload <provider>` — reply + choose provider
`{cmd}webupload <provider> <path>` — local file + provider
`{cmd}url <link>` — shorten a URL (da.gd)

**Providers**
• `auto` — automatic fallback
• `gofile` — Gofile
• `pixeldrain` — Pixeldrain *(DB key `PIXEL`)*
• `uguu` — Uguu
• `tmpfiles` — tmpfiles.org

**API keys (set in DB)**
• `PIXEL` — Pixeldrain API key

**Inline**
`@AssisXBot short <url>` — shorten with service picker
`@AssisXBot webupload` — upload tip / open picker after `.webupload`

**Aliases:** `{cmd}wup`, `{cmd}upload`

**Examples**
`{cmd}webupload`
`{cmd}webupload pixeldrain`
`{cmd}webupload "/home/user/My File.zip"`
`{cmd}url https://example.com`

The plugin does not care about the file extension. Provider limits and
retention policies still apply.
"""


# ---------------------------------------------------------------------------
# Formatting / parsing
# ---------------------------------------------------------------------------


def _human_bytes(value: int | float) -> str:
    value = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} PiB"


def _provider_name(value: str) -> Optional[str]:
    return _PROVIDER_ALIASES.get(value.strip().lower())


def _parse_args(raw: str) -> tuple[str, str]:
    """Return (provider, path). Provider defaults to auto."""
    if not raw:
        return "auto", ""

    try:
        tokens = shlex.split(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid arguments: {exc}") from exc

    if not tokens:
        return "auto", ""

    first = _provider_name(tokens[0])
    if first:
        return first, " ".join(tokens[1:]).strip()

    return "auto", " ".join(tokens).strip()


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------


async def _post_multipart(
    session: aiohttp.ClientSession,
    url: str,
    field: str,
    path: Path,
    extra: Optional[dict] = None,
) -> tuple[int, str, object]:
    """
    Generic multipart uploader.

    aiohttp can stream a regular file object without reading it all into RAM.
    """
    data = aiohttp.FormData()
    data.add_field(
        field,
        path.open("rb"),
        filename=path.name,
        content_type="application/octet-stream",
    )
    for key, value in (extra or {}).items():
        data.add_field(key, str(value))

    try:
        async with session.post(url, data=data) as response:
            body = await response.text(errors="replace")
            return response.status, response.headers.get("content-type", ""), body
    finally:
        # FormData does not reliably expose the opened file object, so the
        # upload field is rebuilt with a managed descriptor in the provider
        # implementations below. This helper is retained for compatibility.
        pass


async def _upload_gofile(path: Path) -> str:
    """
    Gofile current upload endpoint.

    The current API documentation specifies /uploadfile and supports guest
    uploads by omitting an account folder/token.
    """
    endpoint = "https://upload.gofile.io/uploadfile"

    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        with path.open("rb") as fp:
            form = aiohttp.FormData()
            form.add_field(
                "file",
                fp,
                filename=path.name,
                content_type="application/octet-stream",
            )
            async with session.post(endpoint, data=form) as response:
                body = await response.text(errors="replace")
                if response.status >= 400:
                    raise RuntimeError(
                        f"HTTP {response.status}: {body[:500]}"
                    )
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"Invalid Gofile response: {body[:500]}"
                    ) from exc

    if payload.get("status") != "ok":
        raise RuntimeError(str(payload)[:500])

    data = payload.get("data") or {}
    link = data.get("downloadPage")
    if not link:
        raise RuntimeError(f"Gofile returned no downloadPage: {payload}")

    return str(link)


async def _upload_pixeldrain(path: Path) -> str:
    api_key = udB.get_key("PIXEL")
    if not api_key:
        raise RuntimeError(
            "Pixeldrain requires API key. Set DB key `PIXEL` first."
        )

    endpoint = (
        "https://pixeldrain.com/api/file/"
        + quote(path.name, safe="")
    )
    auth = aiohttp.BasicAuth(login="", password=str(api_key))

    async with aiohttp.ClientSession(timeout=_TIMEOUT, auth=auth) as session:
        with path.open("rb") as fp:
            async with session.put(endpoint, data=fp) as response:
                body = await response.text(errors="replace")
                if response.status >= 400:
                    raise RuntimeError(
                        f"HTTP {response.status}: {body[:500]}"
                    )
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"Invalid Pixeldrain response: {body[:500]}"
                    ) from exc

    file_id = payload.get("id")
    if not file_id:
        raise RuntimeError(f"Pixeldrain returned no file id: {payload}")

    return f"https://pixeldrain.com/u/{file_id}"



async def _upload_uguu(path: Path) -> str:
    endpoint = "https://uguu.se/upload"

    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        with path.open("rb") as fp:
            form = aiohttp.FormData()
            form.add_field(
                "files[]",
                fp,
                filename=path.name,
                content_type="application/octet-stream",
            )
            async with session.post(endpoint, data=form) as response:
                body = await response.text(errors="replace")
                if response.status >= 400:
                    raise RuntimeError(
                        f"HTTP {response.status}: {body[:500]}"
                    )
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"Invalid Uguu response: {body[:500]}"
                    ) from exc

    # Uguu has used both `files` and `url`-like response structures.
    files = payload.get("files") or []
    if files and isinstance(files, list):
        item = files[0] if isinstance(files[0], dict) else {}
        link = item.get("url")
        if link:
            return str(link)

    if payload.get("url"):
        return str(payload["url"])

    raise RuntimeError(f"Uguu returned no URL: {payload}")


async def _upload_tmpfiles(path: Path) -> str:
    endpoint = "https://tmpfiles.org/api/v1/upload"

    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        with path.open("rb") as fp:
            form = aiohttp.FormData()
            form.add_field(
                "file",
                fp,
                filename=path.name,
                content_type="application/octet-stream",
            )
            async with session.post(endpoint, data=form) as response:
                body = await response.text(errors="replace")
                if response.status >= 400:
                    raise RuntimeError(
                        f"HTTP {response.status}: {body[:500]}"
                    )
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"Invalid tmpfiles response: {body[:500]}"
                    ) from exc

    data = payload.get("data") or {}
    link = data.get("url") or payload.get("url")
    if not link:
        raise RuntimeError(f"tmpfiles returned no URL: {payload}")

    return str(link)


_UPLOADERS = {
    "gofile": _upload_gofile,
    "pixeldrain": _upload_pixeldrain,
    "uguu": _upload_uguu,
    "tmpfiles": _upload_tmpfiles,
}

_PROVIDER_LABELS = (
    ("gofile", "Gofile"),
    ("pixeldrain", "Pixeldrain"),
    ("uguu", "Uguu"),
    ("tmpfiles", "tmpfiles"),
)

_UPLOAD_TTL = 30 * 60
_UPLOAD_SESSIONS: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Telegram / local-file acquisition
# ---------------------------------------------------------------------------


async def _download_reply(event, reply, destination: Path) -> Path:
    """
    Download any Telegram media type supported by Telethon.

    `download_media` handles documents, photos, videos, audio, voice notes,
    stickers and other Telegram media without relying on file extensions.
    """
    result = await event.client.download_media(
        reply,
        file=str(destination),
    )
    if not result:
        raise RuntimeError("Telegram could not download the replied media.")

    result_path = Path(result)
    if not result_path.is_file():
        raise RuntimeError("Telegram returned an invalid downloaded file.")

    return result_path


def _resolve_local_path(raw_path: str) -> Path:
    path = Path(os.path.expandvars(os.path.expanduser(raw_path))).resolve()
    if not path.exists():
        raise FileNotFoundError(f"File does not exist: {path}")
    if not path.is_file():
        raise IsADirectoryError(f"Not a file: {path}")
    if not os.access(path, os.R_OK):
        raise PermissionError(f"File is not readable: {path}")
    return path


# ---------------------------------------------------------------------------
# Upload session / picker (same UX as shortener)
# ---------------------------------------------------------------------------


def _upload_token() -> str:
    return secrets.token_urlsafe(8).replace("-", "_").replace("/", "_")[:12]


def _purge_upload_sessions() -> None:
    now = time.time()
    dead = [
        k
        for k, v in _UPLOAD_SESSIONS.items()
        if now - float(v.get("created", 0)) > _UPLOAD_TTL
    ]
    for key in dead:
        _cleanup_upload_session(key)


def _cleanup_upload_session(token: str) -> None:
    session = _UPLOAD_SESSIONS.pop(token, None)
    if not session:
        return
    temp_dir = session.get("temp_dir")
    if temp_dir is not None:
        try:
            temp_dir.cleanup()
        except Exception:
            pass


def _upload_panel_text(session: dict) -> str:
    name = html.escape(session["name"])
    size = html.escape(session["size_h"])
    selected = set(session.get("selected") or [])
    lines = [
        "☁️ <b>WebUpload Pro</b>",
        "",
        f"📄 <b>File:</b> <code>{name}</code>",
        f"📦 <b>Size:</b> <code>{size}</code>",
        "",
        "📍 <b>Where do you want to upload?</b>",
        "Tap hosts below (or All), then press <b>Upload</b>.",
        "",
    ]
    picked = [label for key, label in _PROVIDER_LABELS if key in selected]
    if picked:
        lines.append("✨ <b>Selected:</b> " + ", ".join(html.escape(x) for x in picked))
    else:
        lines.append("✨ <b>Selected:</b> <i>none</i>")
    return "\n".join(lines)


def _upload_buttons(token: str, session: dict):
    selected = set(session.get("selected") or [])
    rows = []
    row = []
    for key, name in _PROVIDER_LABELS:
        mark = "✅" if key in selected else "⬜"
        row.append(Button.inline(f"{mark} {name}", data=f"wuu:t:{token}:{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    all_on = len(selected) == len(_PROVIDER_LABELS)
    rows.append(
        [
            Button.inline(
                ("✅ All hosts" if all_on else "🌌 All hosts"),
                data=f"wuu:a:{token}",
            )
        ]
    )
    rows.append([Button.inline("🚀 Upload", data=f"wuu:g:{token}")])
    rows.append([Button.inline("✖️ Cancel", data=f"wuu:x:{token}")])
    return rows



def _upload_result_buttons(token: str):
    return [
        [
            Button.switch_inline(
                "🔄 Upload again",
                query="webupload",
                same_peer=True,
            ),
            Button.inline("✖️ Close", data=f"wuu:c:{token}"),
        ]
    ]

def _format_upload_results(
    name: str,
    size_h: str,
    results: list[tuple[str, str | None, str | None]],
) -> str:
    lines = [
        "☁️ <b>Upload Results</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"📄 <b>File:</b> <code>{html.escape(name)}</code>",
        f"📦 <b>Size:</b> <code>{html.escape(size_h)}</code>",
        "",
    ]
    ok = 0
    for host, link, error in results:
        if link:
            ok += 1
            lines.append(f"🟢 <b>{html.escape(host)}</b>\n{html.escape(link)}\n")
        else:
            lines.append(
                f"🔴 <b>{html.escape(host)}</b>\n{html.escape(error or 'failed')}\n"
            )
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(f"📊 <b>Success:</b> {ok}/{len(results)}")
    return "\n".join(lines)


async def _run_uploads(
    path: Path,
    selected: set[str],
    status_cb=None,
) -> list[tuple[str, str | None, str | None]]:
    size = path.stat().st_size
    results = []
    for key, label in _PROVIDER_LABELS:
        if key not in selected:
            continue
        if key == "uguu" and size > 128 * 1024 * 1024:
            results.append((label, None, "skipped (file exceeds 128 MiB)"))
            continue
        if status_cb:
            await status_cb(label)
        try:
            link = await _UPLOADERS[key](path)
            if not link.startswith(("http://", "https://")):
                raise RuntimeError("Provider returned an invalid URL.")
            results.append((label, link, None))
        except Exception as exc:
            LOGS.exception("webupload: %s failed for %s", key, path)
            results.append((label, None, f"{type(exc).__name__}: {str(exc)[:160]}"))
    return results


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------


@heartless_cmd(pattern=r"(?:webupload|wup|upload)(?:\s+(.+))?$")
async def webupload(event):
    raw = (event.pattern_match.group(1) or "").strip()

    if raw.lower() in {"help", "?"}:
        return await eor(event, _HELP.format(cmd=""))

    try:
        provider, path_arg = _parse_args(raw)
    except ValueError as exc:
        return await eod(event, f"❌ `{exc}`", time=8)

    reply = await event.get_reply_message()
    temp_dir = None
    keep_temp = False

    try:
        if path_arg:
            source = _resolve_local_path(path_arg)
        elif reply and getattr(reply, "media", None):
            temp_dir = tempfile.TemporaryDirectory(prefix="megatron-webupload-")
            original_name = (
                getattr(getattr(reply, "file", None), "name", None)
                or "telegram_file"
            )
            original_name = Path(str(original_name)).name or "telegram_file"
            temp_path = Path(temp_dir.name) / original_name
            status = await eor(event, "📥 **Downloading file from Telegram...**")
            source = await _download_reply(event, reply, temp_path)
            await eor(
                status,
                (
                    "📥 **Downloaded**\n"
                    f"• Name: `{source.name}`\n"
                    f"• Size: `{_human_bytes(source.stat().st_size)}`\n\n"
                    "☁️ **Preparing upload...**"
                ),
            )
        else:
            return await eod(event, _HELP.format(cmd=""), time=15)

        size = source.stat().st_size
        if size <= 0:
            return await eod(event, "❌ The selected file is empty.", time=8)

        display_name = source.name
        size_h = _human_bytes(size)

        # Specific provider: upload immediately (legacy / direct mode).
        if provider != "auto":
            msg = await eor(
                event,
                (
                    "☁️ **WebUpload Pro**\n\n"
                    f"**File:** `{display_name}`\n"
                    f"**Size:** `{size_h}`\n"
                    f"**Provider:** `{provider}`\n\n"
                    "⏳ **Uploading...**"
                ),
            )
            started = time.monotonic()
            try:
                uploaded_url = await _UPLOADERS[provider](source)
                if not uploaded_url.startswith(("http://", "https://")):
                    raise RuntimeError("Provider returned an invalid URL.")
            except Exception as exc:
                LOGS.exception("webupload: %s failed for %s", provider, source)
                return await eor(
                    msg,
                    (
                        "❌ **Upload failed.**\n\n"
                        f"**File:** `{display_name}`\n"
                        f"**Provider:** `{provider}`\n"
                        f"**Error:** `{type(exc).__name__}: {str(exc)[:220]}`"
                    ),
                )
            elapsed = time.monotonic() - started
            return await eor(
                msg,
                (
                    "✅ **Upload completed**\n\n"
                    f"**File:** `{display_name}`\n"
                    f"**Size:** `{size_h}`\n"
                    f"**Host:** `{provider}`\n"
                    f"**Time:** `{elapsed:.1f}s`\n\n"
                    f"🔗 **Link:**\n{uploaded_url}"
                ),
                link_preview=False,
            )

        # Auto / picker mode — same flow as the inline shortener.
        _purge_upload_sessions()
        token = _upload_token()
        session = {
            "path": str(source),
            "name": display_name,
            "size_h": size_h,
            "selected": {key for key, _ in _PROVIDER_LABELS},
            "owner": int(event.sender_id) if event.sender_id else 0,
            "created": time.time(),
            "temp_dir": temp_dir,
        }
        _UPLOAD_SESSIONS[token] = session
        keep_temp = True
        temp_dir = None

        # User accounts cannot attach inline keyboards — show the picker
        # through the assistant bot (same pattern as calc / pasta / short).
        panel_text = _upload_panel_text(session)
        panel_buttons = _upload_buttons(token, session)
        status = await eor(
            event,
            "☁️ **Opening upload picker...**",
        )
        try:
            if getattr(event.client, "_bot", False):
                await eor(
                    status,
                    panel_text,
                    buttons=panel_buttons,
                    parse_mode="html",
                    link_preview=False,
                )
            else:
                bot_username = asst.me.username
                results = await event.client.inline_query(
                    bot_username,
                    f"webupload {token}",
                )
                if not results:
                    raise RuntimeError("Assistant returned no inline results.")
                await results[0].click(
                    event.chat_id,
                    reply_to=event.reply_to_msg_id,
                    hide_via=True,
                )
                try:
                    await status.delete()
                except Exception:
                    pass
        except Exception as exc:
            LOGS.exception("webupload inline picker failed")
            # Last resort: try posting as the assistant bot itself.
            try:
                await asst.send_message(
                    event.chat_id,
                    panel_text,
                    buttons=panel_buttons,
                    parse_mode="html",
                    link_preview=False,
                    reply_to=event.reply_to_msg_id,
                )
                try:
                    await status.delete()
                except Exception:
                    pass
            except Exception:
                await eor(
                    status,
                    (
                        "❌ **Could not open the upload picker.**\n\n"
                        f"`{type(exc).__name__}: {str(exc)[:200]}`\n\n"
                        "Make sure the assistant bot is set up, then try again "
                        "or use a direct host:\n"
                        "` .webupload gofile `"
                    ),
                )

    except FileNotFoundError as exc:
        await eod(event, f"❌ `{exc}`", time=8)
    except IsADirectoryError as exc:
        await eod(event, f"❌ `{exc}`", time=8)
    except PermissionError as exc:
        await eod(event, f"❌ `{exc}`", time=8)
    except Exception as exc:
        LOGS.exception("webupload command failed")
        await eod(
            event,
            f"❌ **WebUpload error:** `{type(exc).__name__}: {str(exc)[:300]}`",
            time=10,
        )
    finally:
        if temp_dir is not None and not keep_temp:
            temp_dir.cleanup()


@in_pattern(re.compile(r"^(?:webupload|wup|upload)(?:\s+(.+))?$", re.I), owner=True)
async def webupload_inline(event):
    """Inline upload picker: @AssisXBot webupload [token]"""
    _purge_upload_sessions()
    raw = (event.pattern_match.group(1) or "").strip() if event.pattern_match else ""
    query = (getattr(event, "text", "") or "").strip()
    if not raw:
        for prefix in ("webupload", "wup", "upload"):
            if query.lower().startswith(prefix):
                raw = query[len(prefix) :].strip()
                break

    # Token from a prior .webupload download — open the same picker inline.
    if raw and raw in _UPLOAD_SESSIONS:
        session = _UPLOAD_SESSIONS[raw]
        result = await event.builder.article(
            title="☁️ WebUpload Pro",
            description=session.get("name", "Upload file")[:64],
            text=_upload_panel_text(session),
            parse_mode="html",
            buttons=_upload_buttons(raw, session),
            link_preview=False,
        )
        return await event.answer([result], cache_time=0, private=True)

    tip = await event.builder.article(
        title="☁️ WebUpload Pro",
        description="Reply to a file with .webupload",
        text=(
            "☁️ <b>WebUpload Pro</b>\n\n"
            "1. Reply to any file/media with <code>.webupload</code>\n"
            "2. Choose hosts with the buttons (or All)\n"
            "3. Press <b>Upload</b>\n\n"
            "Or name a host directly:\n"
            "<code>.webupload gofile</code>\n"
            "<code>.webupload pixeldrain</code>\n\n"
            "Same picker style as:\n"
            "<code>@AssisXBot short https://example.com</code>"
        ),
        parse_mode="html",
    )
    await event.answer([tip], cache_time=0, private=True)


@callback(data=re.compile(rb"wuu:([taxgc]):([A-Za-z0-9_]{8,16})(?::([a-z]+))?"))
async def webupload_callbacks(event):
    action = event.data_match.group(1).decode()
    token = event.data_match.group(2).decode()
    service = event.data_match.group(3).decode() if event.data_match.group(3) else None
    _purge_upload_sessions()
    session = _UPLOAD_SESSIONS.get(token)

    if action == "c":
        if session and session.get("owner") and int(event.sender_id) != int(session["owner"]):
            return await event.answer("This upload panel is not yours.", alert=True)
        _cleanup_upload_session(token)
        await event.edit(
            "✖️ <b>WebUpload closed.</b>",
            buttons=None,
            parse_mode="html",
        )
        return await event.answer("WebUpload closed")

    if not session:
        return await event.answer("Session expired. Run .webupload again.", alert=True)
    if session.get("owner") and int(event.sender_id) != int(session["owner"]):
        return await event.answer("This upload panel is not yours.", alert=True)

    if action == "x":
        _cleanup_upload_session(token)
        await event.edit(
            "✖️ <b>WebUpload cancelled.</b>",
            buttons=None,
            parse_mode="html",
        )
        return await event.answer("WebUpload cancelled")

    selected = set(session.get("selected") or [])
    if action == "t" and service:
        if service in selected:
            selected.discard(service)
        else:
            selected.add(service)
        session["selected"] = selected
        await event.edit(
            _upload_panel_text(session),
            buttons=_upload_buttons(token, session),
            parse_mode="html",
            link_preview=False,
        )
        return await event.answer("Updated")

    if action == "a":
        if len(selected) == len(_PROVIDER_LABELS):
            selected.clear()
        else:
            selected = {key for key, _ in _PROVIDER_LABELS}
        session["selected"] = selected
        await event.edit(
            _upload_panel_text(session),
            buttons=_upload_buttons(token, session),
            parse_mode="html",
            link_preview=False,
        )
        return await event.answer("All toggled")

    if action == "g":
        if not selected:
            return await event.answer("Select at least one host.", alert=True)
        path = Path(session["path"])
        if not path.is_file():
            _cleanup_upload_session(token)
            return await event.answer("File is gone. Run .webupload again.", alert=True)

        await event.answer("Uploading...")
        await event.edit(
            "☁️ <b>Uploading your file...</b>\n\nPlease wait a moment.",
            buttons=None,
            parse_mode="html",
        )

        async def _status(label: str):
            try:
                await event.edit(
                    (
                        "☁️ <b>Uploading your file...</b>\n\n"
                        f"⏳ <b>{html.escape(label)}</b>"
                    ),
                    buttons=None,
                    parse_mode="html",
                )
            except Exception:
                pass

        results = await _run_uploads(path, selected, status_cb=_status)
        text = _format_upload_results(session["name"], session["size_h"], results)
        # Free the temp file; keep a stub session so Close still works.
        temp_dir = session.get("temp_dir")
        if temp_dir is not None:
            try:
                temp_dir.cleanup()
            except Exception:
                pass
            session["temp_dir"] = None
        session["path"] = ""
        session["created"] = time.time()
        await event.edit(
            text,
            buttons=_upload_result_buttons(token),
            parse_mode="html",
            link_preview=False,
        )
        return


# ---------------------------------------------------------------------------
# URL shortener (command + inline)
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"^https?://\S+$", re.I)
_SHORT_TTL = 30 * 60
_SHORT_SESSIONS: dict[str, dict] = {}

# key -> (display name, async shortener)
_SHORT_SERVICES = (
    ("dagd", "da.gd"),
    ("isgd", "is.gd"),
    ("vgd", "v.gd"),
    ("tinyurl", "TinyURL"),
    ("clck", "clck.ru"),
)


def _short_token() -> str:
    return secrets.token_urlsafe(8).replace("-", "_").replace("/", "_")[:12]


def _purge_short_sessions() -> None:
    now = time.time()
    dead = [k for k, v in _SHORT_SESSIONS.items() if now - float(v.get("created", 0)) > _SHORT_TTL]
    for key in dead:
        _SHORT_SESSIONS.pop(key, None)


def _looks_like_url(value: str) -> bool:
    value = (value or "").strip()
    if not value:
        return False
    if _URL_RE.match(value):
        return True
    return value.startswith("www.") and " " not in value


def _normalize_url(value: str) -> str:
    value = (value or "").strip()
    if value.startswith("www."):
        value = "https://" + value
    return value


async def _http_text(url: str, *, method: str = "GET", data=None, headers=None) -> str:
    timeout = aiohttp.ClientTimeout(total=20, connect=10)
    async with aiohttp.ClientSession(timeout=timeout, headers=headers or {}) as session:
        if method.upper() == "POST":
            async with session.post(url, data=data) as response:
                body = (await response.text(errors="replace")).strip()
                if response.status >= 400:
                    raise RuntimeError(f"HTTP {response.status}: {body[:200]}")
                return body
        async with session.get(url) as response:
            body = (await response.text(errors="replace")).strip()
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}: {body[:200]}")
            return body


async def _shorten_dagd(url: str) -> str:
    return await _http_text(f"https://da.gd/s?url={quote_plus(url)}")


async def _shorten_isgd(url: str) -> str:
    return await _http_text(
        f"https://is.gd/create.php?format=simple&url={quote_plus(url)}"
    )


async def _shorten_vgd(url: str) -> str:
    return await _http_text(
        f"https://v.gd/create.php?format=simple&url={quote_plus(url)}"
    )


async def _shorten_tinyurl(url: str) -> str:
    return await _http_text(
        f"https://tinyurl.com/api-create.php?url={quote_plus(url)}"
    )


async def _shorten_clck(url: str) -> str:
    return await _http_text(f"https://clck.ru/--?url={quote_plus(url)}")


_SHORTENERS = {
    "dagd": _shorten_dagd,
    "isgd": _shorten_isgd,
    "vgd": _shorten_vgd,
    "tinyurl": _shorten_tinyurl,
    "clck": _shorten_clck,
}


def _short_panel_text(session: dict) -> str:
    url = html.escape(session["url"])
    selected = set(session.get("selected") or [])
    lines = [
        "✂️ <b>URL Shortener</b>",
        "",
        f"🔗 <b>Source</b>\n<code>{url}</code>",
        "",
        "📍 <b>Where do you want to shorten the link?</b>",
        "Tap services below (or All), then press <b>Shorten</b>.",
        "",
    ]
    picked = [name for key, name in _SHORT_SERVICES if key in selected]
    if picked:
        lines.append("✨ <b>Selected:</b> " + ", ".join(html.escape(x) for x in picked))
    else:
        lines.append("✨ <b>Selected:</b> <i>none</i>")
    return "\n".join(lines)


def _short_buttons(token: str, session: dict):
    selected = set(session.get("selected") or [])
    rows = []
    row = []
    for key, name in _SHORT_SERVICES:
        mark = "✅" if key in selected else "⬜"
        row.append(Button.inline(f"{mark} {name}", data=f"wus:t:{token}:{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    all_on = len(selected) == len(_SHORT_SERVICES)
    rows.append(
        [
            Button.inline(
                ("✅ All services" if all_on else "🌌 All services"),
                data=f"wus:a:{token}",
            )
        ]
    )
    rows.append([Button.inline("🚀 Shorten", data=f"wus:g:{token}")])
    rows.append([Button.inline("✖️ Cancel", data=f"wus:x:{token}")])
    return rows



def _short_result_buttons(token: str):
    return [
        [
            Button.switch_inline(
                "🔄 Short again",
                query="short ",
                same_peer=True,
            ),
            Button.inline("✖️ Close", data=f"wus:c:{token}"),
        ]
    ]

def _format_short_results(url: str, results: list[tuple[str, str | None, str | None]]) -> str:
    lines = [
        "✨ <b>Shortened Links</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"🔗 <b>Original</b>\n<code>{html.escape(url)}</code>",
        "",
    ]
    ok = 0
    for name, link, error in results:
        if link:
            ok += 1
            # Raw link (not monospaced) so it stays easy to copy/tap.
            lines.append(f"🟢 <b>{html.escape(name)}</b>\n{html.escape(link)}\n")
        else:
            lines.append(
                f"🔴 <b>{html.escape(name)}</b>\n{html.escape(error or 'failed')}\n"
            )
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(f"📊 <b>Success:</b> {ok}/{len(results)}")
    return "\n".join(lines)


@heartless_cmd(pattern=r"url(?:\s+(.*))?$")
async def url_short_cmd(event):
    """Quick da.gd shortener command."""
    raw = (event.pattern_match.group(1) or "").strip()
    if not raw:
        return await eod(event, "`Give some url`", time=6)
    if not _looks_like_url(raw):
        return await eod(event, "`Give a valid http(s) url`", time=6)
    url = _normalize_url(raw)
    status = await eor(event, "✂️ **Shortening...**")
    try:
        short = (await _shorten_dagd(url)).strip()
        if not short.startswith(("http://", "https://")):
            raise RuntimeError(short[:200] or "empty response")
        await eor(
            status,
            (
                f"**Shortened url** ==> {short}\n"
                f"**Given url** ==> {url}"
            ),
            link_preview=False,
        )
    except Exception as exc:
        LOGS.exception("url short command failed")
        await eod(
            status,
            f"`Something went wrong. Please try again Later.`\n`{type(exc).__name__}: {str(exc)[:120]}`",
            time=8,
        )


@in_pattern(re.compile(r"^short(?:\s+(.+))?$", re.I), owner=True)
async def short_inline(event):
    """Inline URL shortener picker: @AssisXBot short <url>"""
    _purge_short_sessions()
    raw = (event.pattern_match.group(1) or "").strip() if event.pattern_match else ""
    query = (getattr(event, "text", "") or "").strip()
    if not raw and query.lower().startswith("short"):
        raw = query[5:].strip()

    if not raw or not _looks_like_url(raw):
        tip = await event.builder.article(
            title="✂️ URL Shortener",
            description="Usage: short <url>",
            text=(
                "✂️ <b>URL Shortener</b>\n\n"
                "Send an inline query like:\n"
                "<code>@AssisXBot short https://example.com</code>\n\n"
                "Then choose shortening services and press <b>Shorten</b>."
            ),
            parse_mode="html",
        )
        return await event.answer([tip], cache_time=0, private=True)

    url = _normalize_url(raw)
    token = _short_token()
    session = {
        "url": url,
        "selected": {key for key, _ in _SHORT_SERVICES},
        "owner": int(event.sender_id) if event.sender_id else 0,
        "created": time.time(),
    }
    _SHORT_SESSIONS[token] = session

    result = await event.builder.article(
        title="✂️ URL Shortener",
        description=url[:64],
        text=_short_panel_text(session),
        parse_mode="html",
        buttons=_short_buttons(token, session),
        link_preview=False,
    )
    await event.answer([result], cache_time=0, private=True)


@callback(data=re.compile(rb"wus:([taxgc]):([A-Za-z0-9_]{8,16})(?::([a-z]+))?"))
async def short_callbacks(event):
    action = event.data_match.group(1).decode()
    token = event.data_match.group(2).decode()
    service = event.data_match.group(3).decode() if event.data_match.group(3) else None
    _purge_short_sessions()
    session = _SHORT_SESSIONS.get(token)

    if action == "c":
        if session and session.get("owner") and int(event.sender_id) != int(session["owner"]):
            return await event.answer("This shortener panel is not yours.", alert=True)
        _SHORT_SESSIONS.pop(token, None)
        await event.edit(
            "✖️ <b>URL Shortener closed.</b>",
            buttons=None,
            parse_mode="html",
        )
        return await event.answer("URL Shortener closed")

    if not session:
        return await event.answer("Session expired. Run the inline query again.", alert=True)
    if session.get("owner") and int(event.sender_id) != int(session["owner"]):
        return await event.answer("This shortener panel is not yours.", alert=True)

    if action == "x":
        _SHORT_SESSIONS.pop(token, None)
        await event.edit(
            "✖️ <b>URL Shortener cancelled.</b>",
            buttons=None,
            parse_mode="html",
        )
        return await event.answer("URL Shortener cancelled")

    selected = set(session.get("selected") or [])
    if action == "t" and service:
        if service in selected:
            selected.discard(service)
        else:
            selected.add(service)
        session["selected"] = selected
        await event.edit(
            _short_panel_text(session),
            buttons=_short_buttons(token, session),
            parse_mode="html",
            link_preview=False,
        )
        return await event.answer("Updated")

    if action == "a":
        if len(selected) == len(_SHORT_SERVICES):
            selected.clear()
        else:
            selected = {key for key, _ in _SHORT_SERVICES}
        session["selected"] = selected
        await event.edit(
            _short_panel_text(session),
            buttons=_short_buttons(token, session),
            parse_mode="html",
            link_preview=False,
        )
        return await event.answer("All toggled")

    if action == "g":
        if not selected:
            return await event.answer("Select at least one service.", alert=True)
        await event.answer("Shortening...")
        await event.edit(
            "✂️ <b>Shortening your link...</b>\n\nPlease wait a moment.",
            buttons=None,
            parse_mode="html",
        )
        url = session["url"]
        results = []
        for key, name in _SHORT_SERVICES:
            if key not in selected:
                continue
            func = _SHORTENERS[key]
            try:
                link = (await func(url)).splitlines()[0].strip()
                if not link.startswith(("http://", "https://")):
                    raise RuntimeError(link[:180] or "invalid response")
                results.append((name, link, None))
            except Exception as exc:
                LOGS.exception("shortener %s failed", key)
                results.append((name, None, f"{type(exc).__name__}: {str(exc)[:120]}"))
        session["created"] = time.time()
        await event.edit(
            _format_short_results(url, results),
            buttons=_short_result_buttons(token),
            parse_mode="html",
            link_preview=False,
        )
        return

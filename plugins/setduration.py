"""Spoof the duration Telegram displays for a playable file.

``.setdur`` (alias ``.fakedur``) replies to an audio, voice note, video,
video note or GIF and re-uploads the exact same bytes with only the
``DocumentAttributeAudio``/``DocumentAttributeVideo`` duration changed.
All the other attributes (waveform, title/performer, dimensions, round
and streaming flags, filename, animated marker) are preserved verbatim by
:mod:`CythonX.media_duration`.
"""

import os
import time
from mimetypes import guess_extension
from secrets import token_hex

from CythonX.media_duration import build_attributes, classify, parse_duration

from . import (
    LOGS,
    downloader,
    eod,
    get_help,
    get_string,
    heartless_cmd,
    stdr,
    uploader,
)

__doc__ = get_help("help_setduration")

_DOWNLOAD_DIR = "resources/downloads"


def _file_details(reply):
    """Return a best-effort ``(name, mime_type)`` for the replied document."""
    name, mime_type = "", None
    try:
        file = reply.file
    except Exception:
        file = None
    if file:
        name = file.name or ""
        mime_type = file.mime_type or None
    return name, mime_type


def _local_path(name, mime_type):
    """Pick a unique temp path that keeps the original extension.

    The extension matters because Telethon infers the mime type from the
    file name while uploading; the original *display* name is restored via
    the cloned ``DocumentAttributeFilename``.
    """
    _, ext = os.path.splitext(name or "")
    if not ext:
        ext = guess_extension(mime_type or "") or ""
    os.makedirs(_DOWNLOAD_DIR, exist_ok=True)
    return os.path.join(_DOWNLOAD_DIR, f"setdur_{token_hex(4)}{ext}")


@heartless_cmd(pattern=r"(?:setdur|fakedur)(?:\s+(.*))?$")
async def setdur(e):
    value = (e.pattern_match.group(1) or "").strip()

    if not e.reply_to:
        return await eod(e, get_string("setduration_1"))

    reply = await e.get_reply_message()
    document = getattr(reply, "document", None) if reply else None
    if document is None or classify(document.attributes) is None:
        return await eod(e, get_string("setduration_2"))

    try:
        duration = parse_duration(value)
    except ValueError:
        return await eod(e, get_string("setduration_3"))

    name, mime_type = _file_details(reply)
    path = _local_path(name, mime_type)
    attributes = build_attributes(document.attributes, duration)
    display = os.path.basename(name) or os.path.basename(path)

    status = await e.eor(get_string("setduration_4"))
    start = time.time()
    try:
        await downloader(path, document, status, start, get_string("setduration_5"))
        await status.edit(get_string("setduration_6"))
        uploaded = await uploader(
            path, display, start, status, get_string("setduration_6")
        )
        await e.client.send_file(
            e.chat_id,
            uploaded,
            attributes=attributes,
            mime_type=mime_type,
            force_document=False,
            reply_to=e.reply_to_msg_id,
        )
    except Exception as er:
        LOGS.exception(er)
        return await status.edit(get_string("setduration_7"))
    finally:
        if os.path.exists(path):
            os.remove(path)

    await status.edit(get_string("setduration_done").format(stdr(duration)))

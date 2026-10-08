"""
✘ Commands Available -

• `{i}igm <Instagram link>`
  Send an Instagram post/reel to @VoiceShazamBot, press "Recognize Music",
  and send the recognized audio back to the current chat.
"""

import asyncio
import os
import re
import shutil
import tempfile
from urllib.parse import urlparse

from telethon import functions
from telethon.errors import YouBlockedUserError

from . import LOGS, eod, eor, heartless_cmd


SHAZAM_BOT = "@VoiceShazamBot"
BUTTON_RE = re.compile(r"recognize\s+music", re.IGNORECASE)
_SHAZAM_LOCK = asyncio.Lock()
RECOGNITION_TIMEOUT = 60
AUDIO_TIMEOUT = 90


def _clean_instagram_url(value):
    value = value.strip().strip("<>[](){}")
    value = value.rstrip(".,;!?\"'")

    if not value:
        return None

    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower().rstrip(".")

    if parsed.scheme not in {"http", "https"}:
        return None

    if hostname not in {"instagram.com", "www.instagram.com"}:
        return None

    if not parsed.path or parsed.path == "/":
        return None

    return value


def _find_recognize_button(message):
    for row in message.buttons or []:
        for button in row:
            text = getattr(button, "text", None) or ""

            if BUTTON_RE.search(text):
                return button

    return None


def _is_audio_message(message):
    if not message or not message.media:
        return False

    if getattr(message, "audio", None):
        return True

    file_obj = getattr(message, "file", None)

    mime_type = (
        getattr(file_obj, "mime_type", None)
        if file_obj
        else None
    )

    if mime_type and mime_type.lower().startswith("audio/"):
        return True

    name = getattr(file_obj, "name", None) if file_obj else None

    return bool(
        name
        and os.path.splitext(name)[1].lower()
        in {
            ".mp3",
            ".m4a",
            ".aac",
            ".flac",
            ".wav",
            ".ogg",
            ".opus",
        }
    )


async def _wait_for_message_with_button(conv, timeout):
    deadline = asyncio.get_running_loop().time() + timeout

    while True:
        remaining = (
            deadline
            - asyncio.get_running_loop().time()
        )

        if remaining <= 0:
            raise asyncio.TimeoutError(
                "Recognition button timeout"
            )

        message = await asyncio.wait_for(
            conv.get_response(),
            timeout=remaining,
        )

        if _find_recognize_button(message):
            return message


async def _wait_for_audio(conv, timeout):
    deadline = asyncio.get_running_loop().time() + timeout

    while True:
        remaining = (
            deadline
            - asyncio.get_running_loop().time()
        )

        if remaining <= 0:
            raise asyncio.TimeoutError(
                "Audio response timeout"
            )

        message = await asyncio.wait_for(
            conv.get_response(),
            timeout=remaining,
        )

        if _is_audio_message(message):
            return message


async def _send_audio_to_origin(
    event,
    audio_message,
    caption=None,
):
  
    try:
        return await event.client.send_file(
            event.chat_id,
            file=audio_message.media,
            caption=None,
            parse_mode=None,
            reply_to=event.id,
        )

    except Exception as direct_error:
        LOGS.warning(
            "Direct media copy failed: %s",
            direct_error,
        )

    temp_dir = tempfile.mkdtemp(
        prefix="voice_shazam_"
    )

    try:
        downloaded = await audio_message.download_media(
            file=temp_dir
        )

        if not downloaded or not os.path.exists(downloaded):
            raise RuntimeError(
                "The recognized audio could not be downloaded."
            )

        return await event.client.send_file(
            event.chat_id,
            file=downloaded,
            caption=None,
            parse_mode=None,
            reply_to=event.id,
        )

    finally:
        shutil.rmtree(
            temp_dir,
            ignore_errors=True,
        )


@heartless_cmd(pattern="igm ?(.*)$", allow_sudo=True)
async def instagram_shazam(event):
    instagram_url = _clean_instagram_url(
        event.pattern_match.group(1)
    )

    if not instagram_url:
        return await eod(
            event,
            "❌ **Usage:** `.igm <Instagram post/reel link>`",
            time=8,
        )

    if _SHAZAM_LOCK.locked():
        return await eod(
            event,
            "⏳ Another `.igm` request is already being processed. "
            "Please try again shortly.",
            time=8,
        )

    status = await eor(
        event,
        "🎵 `Please Wait...`",
    )

    async with _SHAZAM_LOCK:
        try:
            bot = await event.client.get_entity(
                SHAZAM_BOT
            )

            async with event.client.conversation(
                bot,
                timeout=AUDIO_TIMEOUT,
                exclusive=True,
            ) as conv:

                try:
                    await conv.send_message(
                        instagram_url
                    )

                except YouBlockedUserError:
                    LOGS.info(
                        "Unblocking %s for .igm",
                        SHAZAM_BOT,
                    )

                    await event.client(
                        functions.contacts.UnblockRequest(
                            bot
                        )
                    )

                    await conv.send_message(
                        instagram_url
                    )

                await event.client.send_read_acknowledge(
                    bot
                )

                await status.edit(
                    "🔎 `Recognizing Music...`"
                )

                recognition_message = (
                    await _wait_for_message_with_button(
                        conv,
                        RECOGNITION_TIMEOUT,
                    )
                )

                button = _find_recognize_button(
                    recognition_message
                )

                if button is None:
                    raise RuntimeError(
                        "The 'Recognize Music' button "
                        "was not found."
                    )

                await status.edit(
                    "🎧 `Recognized. Requesting "
                    "the audio file...`"
                )

                await button.click()

                audio_message = await _wait_for_audio(
                    conv,
                    AUDIO_TIMEOUT,
                )

                # The bot normally edits the recognition
                # message with the final title/artist after
                # the button is pressed. Fetch the fresh copy.
                try:
                    recognition_message = (
                        await event.client.get_messages(
                            bot,
                            ids=recognition_message.id,
                        )
                    )

                except Exception:
                    pass

                title = (
                    recognition_message.raw_text
                    or ""
                ).strip()

                if len(title) > 300:
                    title = title[:297] + "..."

                caption = title or None

                await status.edit(
                    "📤 `Sending the recognized song...`"
                )

                await _send_audio_to_origin(
                    event,
                    audio_message,
                    caption=None,
                )

                if title:
                    await status.edit(
                        f"{title}",
                        parse_mode=None,
                    )

                else:
                    await status.edit(
                        "Music recognized successfully...",
                        parse_mode=None,
                    )

        except asyncio.TimeoutError:
            await eod(
                status,
                "❌ `Bot did not respond "
                "in time.`",
                time=10,
            )

        except YouBlockedUserError:
            await eod(
                status,
                f"❌ `Please unblock {SHAZAM_BOT} "
                "and try again.`",
                time=10,
            )

        except Exception as exc:
            LOGS.exception(
                "VoiceShazam .igm command failed"
            )

            await eod(
                status,
                f"❌ **VoiceShazam error:** "
                f"`{type(exc).__name__}: {exc}`",
                time=12,
   )

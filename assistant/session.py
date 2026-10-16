"""``/session`` — generate a Telethon StringSession from the Assistant bot.

Any user can PM the assistant and run ``/session``.  The bot asks for the
user's own API ID / API Hash (from my.telegram.org), phone number and the
login code Telegram sends, then returns the session as a message and a
``.txt`` file.  ``/cancel`` aborts at any step.

The framework-free login logic lives in ``assistant/_session_core.py``; this
module only wires it to the Telethon event layer.
"""

import asyncio
import secrets
from io import BytesIO

from . import *

from telethon import Button, TelegramClient, events
from telethon.sessions import StringSession
from telethon.utils import get_display_name

from ._session_core import (
    SESSION_FILE_NAME,
    Cooldown,
    SessionCancelled,
    SessionError,
    ask_validated,
    build_session_document,
    format_wait,
    generate_session,
    parse_api_hash,
    parse_api_id,
    parse_phone,
)

SESSION_COOLDOWN_SECONDS = 300
MAX_CONCURRENT_SESSIONS = 5
STEP_TIMEOUT = 300
TOTAL_TIMEOUT = 3600

# Prompts whose answers should be scrubbed from the chat where possible.
_SENSITIVE_PROMPTS = frozenset(
    {
        "session_ask_api_hash",
        "session_ask_phone",
        "session_ask_code",
        "session_ask_password",
    }
)

_cooldown = Cooldown(SESSION_COOLDOWN_SECONDS)


def _render(key, kwargs=None):
    text = get_string(key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


class _Chat:
    """Adapter that turns a Telethon conversation into the core's ``interact``."""

    def __init__(self, conv, user_id):
        self.conv = conv
        self.user_id = user_id

    async def notify(self, key, **kwargs):
        return await self.conv.send_message(_render(key, kwargs))

    async def ask(self, key, sensitive=False, **kwargs):
        await self.notify(key, **kwargs)
        try:
            response = await self.conv.get_response(timeout=STEP_TIMEOUT)
        except asyncio.TimeoutError:
            raise SessionError("session_err_timeout") from None
        text = (response.raw_text or "").strip()
        if text.lower() == "/cancel":
            raise SessionCancelled()
        if sensitive or key in _SENSITIVE_PROMPTS:
            try:
                await response.delete()
            except Exception as er:
                LOGS.debug("Could not delete sensitive reply: %s", er)
        return text

    async def confirm(self, token):
        await self.conv.send_message(
            get_string("session_intro"),
            buttons=[
                [
                    Button.inline(
                        get_string("session_btn_generate"), data=f"ssgen_y_{token}"
                    ),
                    Button.inline(
                        get_string("session_btn_cancel"), data=f"ssgen_n_{token}"
                    ),
                ]
            ],
            link_preview=False,
        )
        while True:
            try:
                event = await self.conv.wait_event(
                    events.CallbackQuery(chats=self.user_id), timeout=STEP_TIMEOUT
                )
            except asyncio.TimeoutError:
                raise SessionError("session_err_timeout") from None
            try:
                await event.answer()
            except Exception as er:
                LOGS.debug("Could not answer session callback: %s", er)
            raw = event.data
            data = raw.decode() if isinstance(raw, bytes) else str(raw)
            if data == f"ssgen_y_{token}":
                try:
                    await event.delete()
                except Exception as er:
                    LOGS.debug("Could not delete session prompt: %s", er)
                return True
            if data == f"ssgen_n_{token}":
                try:
                    await event.delete()
                except Exception as er:
                    LOGS.debug("Could not delete session prompt: %s", er)
                return False


def _make_client(api_id, api_hash):
    return TelegramClient(StringSession(), api_id, api_hash)


async def _deliver(chat, session_string, me):
    try:
        name = get_display_name(me) if me is not None else "Unknown"
    except Exception:
        name = "Unknown"
    uid = getattr(me, "id", "?")
    await chat.conv.send_message(
        _render(
            "session_result",
            {"name": name, "uid": uid, "session": session_string},
        ),
        link_preview=False,
    )
    document = BytesIO(build_session_document(session_string))
    document.name = SESSION_FILE_NAME
    await chat.conv.send_file(document)
    await chat.conv.send_message(get_string("session_warning"), link_preview=False)


async def _safe_reply(event, key, **kwargs):
    try:
        await event.reply(_render(key, kwargs))
    except Exception as er:
        LOGS.exception(er)


@asst_cmd(pattern="session( (.*)|$)", func=lambda x: x.is_private)
async def session_command(event):
    user_id = event.sender_id

    remaining = _cooldown.remaining(user_id)
    if remaining > 0:
        return await event.reply(
            _render("session_cooldown", {"wait": format_wait(remaining)})
        )
    if _cooldown.active_count() >= MAX_CONCURRENT_SESSIONS:
        return await event.reply(get_string("session_busy"))

    token = secrets.token_hex(4)
    _cooldown.start(user_id)
    try:
        async with event.client.conversation(user_id, timeout=TOTAL_TIMEOUT) as conv:
            chat = _Chat(conv, user_id)
            if not await chat.confirm(token):
                return await chat.notify("session_cancelled")
            api_id = await ask_validated(
                chat, "session_ask_api_id", parse_api_id, "session_bad_api_id"
            )
            api_hash = await ask_validated(
                chat, "session_ask_api_hash", parse_api_hash, "session_bad_api_hash"
            )
            phone = await ask_validated(
                chat, "session_ask_phone", parse_phone, "session_bad_phone"
            )
            await chat.notify("session_working")
            session_string, me = await generate_session(
                api_id, api_hash, phone, _make_client, chat
            )
            await _deliver(chat, session_string, me)
    except SessionCancelled:
        await _safe_reply(event, "session_cancelled")
    except SessionError as er:
        await _safe_reply(event, er.key, **er.kwargs)
    except Exception as er:
        LOGS.exception(er)
        await _safe_reply(event, "session_err_generic")
    finally:
        _cooldown.finish(user_id)

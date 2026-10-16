"""``/api`` — obtain Telegram API credentials via the Assistant bot.

Any user can PM the assistant and run ``/api``.  The bot walks them through
logging in to **my.telegram.org** (there is no official API for this), then
either reads the account's existing application or creates one, and returns
the ``api_id`` / ``api_hash``.  ``/cancel`` aborts at any step, and a manual
fallback guide is offered whenever the automated flow cannot finish.

The framework-free web logic lives in ``assistant/_api_core.py``; this
module only wires it to the Telethon event layer.  Everything is in-memory:
nothing about the user is stored or logged.
"""

import asyncio
import secrets

from . import *

import requests
from telethon import Button, events

from ._api_core import (
    WEB_USER_AGENT,
    ApiCredsError,
    complete_credentials,
    request_login_code,
)
from ._session_core import (
    Cooldown,
    format_wait,
    normalize_code,
    parse_phone,
)

API_COOLDOWN_SECONDS = 300
MAX_CONCURRENT_API = 5
STEP_TIMEOUT = 300
TOTAL_TIMEOUT = 900
NETWORK_TIMEOUT = 30
CODE_ATTEMPTS = 3
INPUT_ATTEMPTS = 3
FALLBACK_DATA = "apifallback"

_cooldown = Cooldown(API_COOLDOWN_SECONDS)


class _Cancelled(Exception):
    """Raised when the user cancels (``/cancel``) or a step times out."""


def _render(key, kwargs=None):
    text = get_string(key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def _new_http_session():
    """A cookie-holding session whose browser User-Agent satisfies the site."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": WEB_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


async def _run(func, *args):
    """Run a blocking HTTP helper in a worker thread, mapping transport errors."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(func, *args), timeout=NETWORK_TIMEOUT
        )
    except asyncio.TimeoutError:
        raise ApiCredsError("api_err_timeout") from None
    except requests.RequestException:
        raise ApiCredsError("api_err_network") from None


class _Chat:
    """Adapter that turns a Telethon conversation into the prompts we need."""

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
            raise ApiCredsError("api_err_timeout") from None
        text = (response.raw_text or "").strip()
        if text.lower() == "/cancel":
            raise _Cancelled()
        if sensitive:
            try:
                await response.delete()
            except Exception as er:
                LOGS.debug("Could not delete sensitive reply: %s", er)
        return text

    async def confirm(self, token):
        await self.conv.send_message(
            get_string("api_intro"),
            buttons=[
                [
                    Button.inline(get_string("api_btn_get"), data=f"api_y_{token}"),
                    Button.inline(get_string("api_btn_manual"), data=f"api_m_{token}"),
                ],
                [Button.inline(get_string("api_btn_cancel"), data=f"api_n_{token}")],
            ],
            link_preview=False,
        )
        while True:
            try:
                event = await self.conv.wait_event(
                    events.CallbackQuery(chats=self.user_id), timeout=STEP_TIMEOUT
                )
            except asyncio.TimeoutError:
                raise ApiCredsError("api_err_timeout") from None
            try:
                await event.answer()
            except Exception as er:
                LOGS.debug("Could not answer api callback: %s", er)
            raw = event.data
            data = raw.decode() if isinstance(raw, bytes) else str(raw)
            if data == f"api_y_{token}":
                await self._drop(event)
                return "go"
            if data == f"api_m_{token}":
                await self._drop(event)
                return "manual"
            if data == f"api_n_{token}":
                await self._drop(event)
                return "no"

    @staticmethod
    async def _drop(event):
        try:
            await event.delete()
        except Exception as er:
            LOGS.debug("Could not delete api prompt: %s", er)


async def _ask_validated(chat, prompt_key, parser, bad_key, sensitive=False):
    """Re-prompt until ``parser`` accepts the answer, else raise."""
    for _ in range(INPUT_ATTEMPTS):
        raw = await chat.ask(prompt_key, sensitive=sensitive)
        value = parser(raw)
        if value is not None:
            return value
        await chat.notify(bad_key)
    raise ApiCredsError("api_err_invalid")


async def _deliver(chat, api_id, api_hash):
    await chat.conv.send_message(
        _render("api_result", {"api_id": api_id, "api_hash": api_hash}),
        link_preview=False,
    )
    await chat.conv.send_message(get_string("api_result_warning"), link_preview=False)
    await chat.conv.send_message(get_string("api_result_next"), link_preview=False)


async def _safe_reply(event, key, fallback=False, **kwargs):
    try:
        buttons = None
        if fallback:
            buttons = [[Button.inline(get_string("api_btn_manual"), data=FALLBACK_DATA)]]
        await event.reply(_render(key, kwargs), buttons=buttons, link_preview=False)
    except Exception as er:
        LOGS.exception(er)


@asst_cmd(pattern="api( (.*)|$)", func=lambda x: x.is_private)
async def api_command(event):
    user_id = event.sender_id

    remaining = _cooldown.remaining(user_id)
    if remaining > 0:
        return await event.reply(
            _render("api_cooldown", {"wait": format_wait(remaining)})
        )
    if _cooldown.active_count() >= MAX_CONCURRENT_API:
        return await event.reply(get_string("api_busy"))

    token = secrets.token_hex(4)
    http = None
    _cooldown.start(user_id)
    try:
        async with event.client.conversation(user_id, timeout=TOTAL_TIMEOUT) as conv:
            chat = _Chat(conv, user_id)
            choice = await chat.confirm(token)
            if choice == "manual":
                await chat.conv.send_message(
                    get_string("api_manual"), link_preview=False
                )
                return
            if choice == "no":
                return await chat.notify("api_cancelled")

            phone = await _ask_validated(
                chat, "api_ask_phone", parse_phone, "api_bad_phone", sensitive=True
            )
            http = _new_http_session()
            await chat.notify("api_working")
            random_hash = await _run(request_login_code, http, phone)
            await chat.notify("api_code_sent")

            for _ in range(CODE_ATTEMPTS):
                code = normalize_code(await chat.ask("api_ask_code", sensitive=True))
                if not code:
                    await chat.notify("api_bad_code")
                    continue
                try:
                    api_id, api_hash = await _run(
                        complete_credentials, http, phone, random_hash, code
                    )
                except ApiCredsError as er:
                    if er.key == "api_err_bad_code":
                        await chat.notify("api_bad_code")
                        continue
                    raise
                await _deliver(chat, api_id, api_hash)
                return
            raise ApiCredsError("api_err_bad_code")
    except _Cancelled:
        await _safe_reply(event, "api_cancelled")
    except ApiCredsError as er:
        await _safe_reply(event, er.key, fallback=True, **er.kwargs)
    except Exception as er:
        LOGS.exception(er)
        await _safe_reply(event, "api_err_generic", fallback=True)
    finally:
        _cooldown.finish(user_id)
        if http is not None:
            try:
                http.close()
            except Exception:
                pass


@callback(FALLBACK_DATA)
async def api_manual_callback(event):
    try:
        await event.answer()
    except Exception as er:
        LOGS.debug("Could not answer api fallback: %s", er)
    try:
        await event.reply(get_string("api_manual"), link_preview=False)
    except Exception as er:
        LOGS.exception(er)

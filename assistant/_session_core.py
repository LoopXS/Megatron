"""Pure, framework-free core for the Assistant bot's ``/session`` command.

This module deliberately imports *nothing* from CythonX/assistant so it can be
loaded and unit-tested in isolation (see ``tests/test_session_core.py``).  The
Telethon/runtime glue — the actual command handler and chat adapter — lives in
``assistant/session.py``.

The interactive part is expressed against two small duck-typed collaborators:

* ``make_client(api_id, api_hash)`` -> a connected-capable TelegramClient-like
  object exposing ``connect``, ``disconnect``, ``send_code_request``,
  ``sign_in`` and ``session.save``.
* ``interact`` -> ``await interact.ask(key, **kwargs)`` and
  ``await interact.notify(key, **kwargs)``.
"""

import math
import string
import time

from telethon.errors.rpcerrorlist import (
    ApiIdInvalidError,
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberBannedError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from telethon.tl import types

MAX_CODE_ATTEMPTS = 3
MAX_PASSWORD_ATTEMPTS = 3
DEFAULT_INPUT_ATTEMPTS = 3
SESSION_FILE_NAME = "string_session.txt"


class SessionError(Exception):
    """A failure the user should see, carrying a language-string key."""

    def __init__(self, key, **kwargs):
        super().__init__(key)
        self.key = key
        self.kwargs = kwargs


class SessionCancelled(Exception):
    """Raised when the user cancels (``/cancel``) or a step times out."""


def normalize_code(text):
    """Extract a login code, tolerating spaces/dashes.

    Telegram codes may be numeric (``"12345"``) or alphanumeric
    (``"M0YcbckTMdA"``) and users often paste them with spaces or dashes, so
    keep every letter and digit and drop everything else.
    """
    if not text:
        return ""
    return "".join(ch for ch in str(text) if ch.isascii() and ch.isalnum())


def parse_api_id(text):
    text = (text or "").strip()
    if not text.isdigit():
        return None
    value = int(text)
    return value if value > 0 else None


def parse_api_hash(text):
    text = (text or "").strip()
    if len(text) != 32:
        return None
    if any(ch not in string.hexdigits for ch in text):
        return None
    return text


def parse_phone(text):
    text = (text or "").strip().replace(" ", "").replace("-", "")
    if not text.startswith("+"):
        return None
    digits = text[1:]
    if not digits.isdigit():
        return None
    if not 7 <= len(digits) <= 15:
        return None
    return text


class Cooldown:
    """Per-user rate limit plus a count of in-progress generations."""

    def __init__(self, seconds, clock=time.monotonic):
        self.seconds = seconds
        self._clock = clock
        self._last = {}
        self._active = set()

    def remaining(self, user_id):
        last = self._last.get(user_id)
        if last is None:
            return 0.0
        rem = self.seconds - (self._clock() - last)
        return rem if rem > 0 else 0.0

    def is_active(self, user_id):
        return user_id in self._active

    def active_count(self):
        return len(self._active)

    def start(self, user_id):
        self._active.add(user_id)
        self._last[user_id] = self._clock()

    def finish(self, user_id):
        self._active.discard(user_id)


def format_wait(seconds):
    total = int(math.ceil(seconds))
    minutes, secs = divmod(total, 60)
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def build_session_document(session_string):
    """The ``.txt`` backup handed to the user alongside the chat message."""
    body = (
        "Telethon StringSession\n"
        "======================\n\n"
        f"{session_string}\n\n"
        "Do not share this string with anyone. Anyone who has it can log in "
        "to your Telegram account and take it over completely.\n"
    )
    return body.encode("utf-8")


async def ask_validated(
    interact, prompt_key, parser, bad_key, attempts=DEFAULT_INPUT_ATTEMPTS
):
    """Re-prompt until ``parser`` accepts the answer, else raise ``SessionError``."""
    for _ in range(attempts):
        raw = await interact.ask(prompt_key)
        value = parser(raw)
        if value is not None:
            return value
        await interact.notify(bad_key)
    raise SessionError("session_err_invalid")


async def generate_session(api_id, api_hash, phone, make_client, interact):
    """Run the full login and return ``(session_string, user)``."""
    client = make_client(api_id, api_hash)
    try:
        await client.connect()
        sent = await _send_code(client, phone)
        code_hash = getattr(sent, "phone_code_hash", None)
        user = await _submit_code(client, phone, code_hash, interact)
        return client.session.save(), user
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def _send_code(client, phone):
    try:
        return await client.send_code_request(phone)
    except FloodWaitError as er:
        raise SessionError(
            "session_err_flood", seconds=int(getattr(er, "seconds", 0) or 0)
        )
    except ApiIdInvalidError:
        raise SessionError("session_err_api_id")
    except PhoneNumberInvalidError:
        raise SessionError("session_err_phone")
    except PhoneNumberBannedError:
        raise SessionError("session_err_phone_banned")


async def _submit_code(client, phone, code_hash, interact):
    for _ in range(MAX_CODE_ATTEMPTS):
        code = normalize_code(await interact.ask("session_ask_code"))
        if len(code) < 3:
            await interact.notify("session_bad_code")
            continue
        try:
            result = await client.sign_in(
                phone=phone, code=code, phone_code_hash=code_hash
            )
        except SessionPasswordNeededError:
            return await _submit_password(client, interact)
        except PhoneCodeInvalidError:
            await interact.notify("session_bad_code")
            continue
        except PhoneCodeExpiredError:
            raise SessionError("session_err_code_expired")
        if isinstance(result, types.auth.SentCode):
            raise SessionError("session_err_signup")
        return result
    raise SessionError("session_err_code_max")


async def _submit_password(client, interact):
    for _ in range(MAX_PASSWORD_ATTEMPTS):
        password = await interact.ask("session_ask_password", sensitive=True)
        if not password:
            await interact.notify("session_bad_password")
            continue
        try:
            return await client.sign_in(password=password)
        except PasswordHashInvalidError:
            await interact.notify("session_bad_password")
            continue
    raise SessionError("session_err_password_max")

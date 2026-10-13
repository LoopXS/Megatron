"""
Tehran Time Automation
======================

Commands
--------

tbio
    Automatically update the account biography with Tehran time.

tname
    Automatically update the account first name with Tehran time.

tcbio
    Automatically update the current channel description with Tehran time.

tgbio
    Automatically update the current group description with Tehran time.

tclock
    Show the current Tehran date and time.

Every automatic command supports:

    <command>
    <command> off

Templates are configured through the project's existing setdb system:

    setdb BIOTEXT "Hello World"
    setdb NAMETEXT "My Account"
    setdb CHANNELBIOTEXT "My Channel"
    setdb GROUPBIOTEXT "My Group"

Supported placeholders:

    {time}
    {hour}
    {minute}
    {second}
    {date}
    {datetime}

If a template contains no time placeholder, {time} is automatically
appended to the template.

Examples:

    setdb BIOTEXT "Hello World"
    setdb BIOTEXT "Hello World • {time}"
    setdb BIOTEXT "Tehran {hour}:{minute}"

The scheduler does NOT sleep for a fixed 60 seconds.

Instead, after every successful update it calculates the exact amount
of time remaining until the next Tehran minute boundary. This prevents
scheduler drift.

The plugin also avoids sending an identical Telegram update twice.
"""

from . import get_help

__doc__ = get_help("help_timebio")


import asyncio
import contextlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telethon import functions, types
from telethon.errors import FloodWaitError
from telethon.errors.rpcerrorlist import (
    ChatAboutTooLongError,
    ChatAdminRequiredError,
    ChatIdInvalidError,
    ChatNotModifiedError,
    FloodWaitError as RpcFloodWaitError,
)

from . import LOGS, udB, heartless_bot, heartless_cmd


# ============================================================================
# CONFIGURATION
# ============================================================================

TEHRAN = ZoneInfo("Asia/Tehran")

# Database keys.
BIO_TEXT_KEY = "BIOTEXT"
NAME_TEXT_KEY = "NAMETEXT"
CHANNEL_BIO_TEXT_KEY = "CHANNELBIOTEXT"
GROUP_BIO_TEXT_KEY = "GROUPBIOTEXT"

BIO_ACTIVE_KEY = "TBIO_ACTIVE"
NAME_ACTIVE_KEY = "TNAME_ACTIVE"
CHANNEL_ACTIVE_KEY = "TCBIO_ACTIVE"
GROUP_ACTIVE_KEY = "TGBIO_ACTIVE"

CHANNEL_CHAT_KEY = "TCBIO_CHAT"
GROUP_CHAT_KEY = "TGBIO_CHAT"


# Telegram limits.
#
# Telegram's limits can change over time. These conservative limits keep
# generated values inside the commonly supported boundaries.
PROFILE_NAME_LIMIT = 64
PROFILE_BIO_LIMIT = 70
CHAT_ABOUT_LIMIT = 255


# One asyncio task per automatic feature.
_TASKS = {
    "tbio": None,
    "tname": None,
    "tcbio": None,
    "tgbio": None,
}


# ============================================================================
# GENERAL HELPERS
# ============================================================================


def _db_get(key, default=None):
    """
    Read a value from the project's existing database safely.
    """
    try:
        value = udB.get_key(key)

        if value is None:
            return default

        return value

    except Exception as exc:
        LOGS.exception(
            "timebio: unable to read DB key %s: %s",
            key,
            exc,
        )
        return default


def _db_set(key, value):
    """
    Write a value using the project's real DB abstraction.
    """
    try:
        return udB.set_key(key, value)

    except Exception as exc:
        LOGS.exception(
            "timebio: unable to write DB key %s: %s",
            key,
            exc,
        )
        return False


def _db_delete(key):
    """
    Delete a DB key safely.
    """
    try:
        return udB.del_key(key)

    except Exception as exc:
        LOGS.exception(
            "timebio: unable to delete DB key %s: %s",
            key,
            exc,
        )
        return False


def _as_bool(value):
    """
    Convert database values to bool.

    Supports values such as:

        True
        False
        "True"
        "False"
        "1"
        "0"
        "yes"
        "no"
    """
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    if isinstance(value, int):
        return bool(value)

    value = str(value).strip().lower()

    return value in {
        "1",
        "true",
        "yes",
        "on",
        "enabled",
    }


def _clean_template(value):
    """
    Normalize a template loaded from setdb.

    Existing setdb syntax allows:

        setdb BIOTEXT "Hello World"

    Depending on the DB/parser, quotation marks may be stored literally.

    This helper removes only one matching pair of surrounding quotes.
    """
    if value is None:
        return None

    value = str(value).strip()

    if len(value) >= 2:

        if (
            value.startswith('"')
            and value.endswith('"')
        ):
            return value[1:-1]

        if (
            value.startswith("'")
            and value.endswith("'")
        ):
            return value[1:-1]

    return value


def _truncate(text, limit):
    """
    Safely limit generated text.

    Telegram limits are expressed in characters for these fields in the
    common API usage. Keeping the truncation here centralized also prevents
    one bad template from killing the scheduler.
    """
    if not text:
        return ""

    text = str(text)

    if len(text) <= limit:
        return text

    return text[:limit]


# ============================================================================
# TEHRAN CLOCK
# ============================================================================


def _tehran_now():
    """
    Return the current timezone-aware Tehran datetime.
    """
    return datetime.now(TEHRAN)


def _clock_values(now=None):
    """
    Return all supported template values.
    """
    now = now or _tehran_now()

    return {
        "time": now.strftime("%H:%M"),
        "hour": now.strftime("%H"),
        "minute": now.strftime("%M"),
        "second": now.strftime("%S"),
        "date": now.strftime("%Y-%m-%d"),
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _render_template(template, now=None):
    """
    Render a configured database template.

    Supported:

        {time}
        {hour}
        {minute}
        {second}
        {date}
        {datetime}

    If none of the placeholders are present, the time is automatically
    appended to the text.

    Example:

        Hello World

    becomes:

        Hello World • 14:37
    """

    now = now or _tehran_now()

    template = _clean_template(template)

    if not template:
        template = ""

    values = _clock_values(now)

    placeholder_found = False

    for key, value in values.items():

        placeholder = "{" + key + "}"

        if placeholder in template:
            placeholder_found = True

        template = template.replace(
            placeholder,
            value,
        )

    if not placeholder_found:

        if template:
            template = f"{template} • {values['time']}"

        else:
            template = values["time"]

    return template.strip()


def _seconds_until_next_minute(now=None):
    """
    Calculate the exact delay until the next Tehran minute.

    IMPORTANT:

    We do not use:

        sleep(60)

    because that introduces cumulative scheduler drift.

    Instead, we calculate the real next minute boundary.

    Example:

        14:37:59.900

    results in approximately:

        0.100 seconds

    of sleep.
    """

    now = now or _tehran_now()

    next_minute = (
        now + timedelta(minutes=1)
    ).replace(
        second=0,
        microsecond=0,
    )

    delay = (
        next_minute - now
    ).total_seconds()

    # Protect against extremely small / negative values.
    return max(
        0.001,
        delay,
    )


# ============================================================================
# ASYNCIO TASK MANAGEMENT
# ============================================================================


async def _cancel_task(name):
    """
    Cancel one running automation task.
    """

    task = _TASKS.get(name)

    if task is None:
        return

    _TASKS[name] = None

    if task.done():
        with contextlib.suppress(Exception):
            task.exception()
        return

    task.cancel()

    with contextlib.suppress(
        asyncio.CancelledError,
        Exception,
    ):
        await task


def _task_done_callback(name, task):
    """
    Prevent 'Task exception was never retrieved' messages.
    """

    current = _TASKS.get(name)

    if current is task:
        _TASKS[name] = None

    if task.cancelled():
        return

    with contextlib.suppress(
        asyncio.CancelledError,
        Exception,
    ):
        error = task.exception()

        if error:
            LOGS.error(
                "timebio: %s task stopped unexpectedly: %s",
                name,
                error,
                exc_info=(
                    type(error),
                    error,
                    error.__traceback__,
                ),
            )


async def _start_task(name, coroutine):
    """
    Start exactly one task for a feature.

    Any previous task is cancelled before the new one starts.
    """

    await _cancel_task(name)

    task = asyncio.create_task(
        coroutine,
        name=f"timebio:{name}",
    )

    _TASKS[name] = task

    task.add_done_callback(
        lambda completed: _task_done_callback(
            name,
            completed,
        )
    )

    return task


# ============================================================================
# TELEGRAM UPDATE HELPERS
# ============================================================================


async def _update_profile_bio(client, text):
    """
    Update the account biography.

    Telegram may return CHAT_ABOUT_NOT_MODIFIED-equivalent RPC errors
    when the value is unchanged. Such cases are intentionally ignored.
    """

    text = _truncate(
        text,
        PROFILE_BIO_LIMIT,
    )

    try:

        await client(
            functions.account.UpdateProfileRequest(
                about=text,
            )
        )

        return True

    except Exception as exc:

        name = type(exc).__name__

        if "NotModified" in name:
            return True

        raise


async def _update_profile_name(client, text):
    """
    Update the account first name.

    The time is placed into first_name rather than last_name because
    the user specifically requested automatic time in the account name.
    """

    text = _truncate(
        text,
        PROFILE_NAME_LIMIT,
    )

    try:

        await client(
            functions.account.UpdateProfileRequest(
                first_name=text,
            )
        )

        return True

    except Exception as exc:

        name = type(exc).__name__

        if "NotModified" in name:
            return True

        raise


async def _update_chat_about(client, chat_id, text):
    """
    Update group/channel description.

    Telegram exposes messages.editChatAbout for group/supergroup/channel
    descriptions.
    """

    text = _truncate(
        text,
        CHAT_ABOUT_LIMIT,
    )

    await client(
        functions.messages.EditChatAboutRequest(
            peer=chat_id,
            about=text,
        )
    )

    return True


# ============================================================================
# FLOOD WAIT / NETWORK RETRY
# ============================================================================


async def _call_with_floodwait(
    operation,
    operation_name,
):
    """
    Execute a Telegram operation while handling FloodWait safely.

    FloodWait cannot be eliminated by code. Telegram decides the required
    waiting time. The important point is that the scheduler remains alive
    and retries after the exact server-provided delay.
    """

    while True:

        try:
            return await operation()

        except (
            FloodWaitError,
            RpcFloodWaitError,
        ) as exc:

            seconds = int(
                getattr(
                    exc,
                    "seconds",
                    1,
                )
            )

            LOGS.warning(
                "timebio: FloodWait during %s; "
                "sleeping %s seconds.",
                operation_name,
                seconds,
            )

            await asyncio.sleep(
                max(
                    1,
                    seconds,
                )
            )

        except (
            ChatNotModifiedError,
        ):
            return True

        except Exception:

            raise


# ============================================================================
# AUTOMATION LOOPS
# ============================================================================


async def _profile_bio_loop():
    """
    Continuous account biography updater.
    """

    last_value = None

    while _as_bool(
        _db_get(
            BIO_ACTIVE_KEY,
            False,
        )
    ):

        now = _tehran_now()

        template = _db_get(
            BIO_TEXT_KEY,
            "Tehran Time",
        )

        value = _render_template(
            template,
            now,
        )

        value = _truncate(
            value,
            PROFILE_BIO_LIMIT,
        )

        # Avoid duplicate Telegram requests.
        if value != last_value:

            try:

                await _call_with_floodwait(
                    lambda: _update_profile_bio(
                        heartless_bot,
                        value,
                    ),
                    "tbio",
                )

                last_value = value

            except asyncio.CancelledError:
                raise

            except Exception as exc:

                LOGS.exception(
                    "timebio: tbio update failed: %s",
                    exc,
                )

                # Do not hammer Telegram if an RPC/network error occurs.
                await asyncio.sleep(3)

        await asyncio.sleep(
            _seconds_until_next_minute()
        )


async def _profile_name_loop():
    """
    Continuous account name updater.
    """

    last_value = None

    while _as_bool(
        _db_get(
            NAME_ACTIVE_KEY,
            False,
        )
    ):

        now = _tehran_now()

        template = _db_get(
            NAME_TEXT_KEY,
            "Tehran Time",
        )

        value = _render_template(
            template,
            now,
        )

        value = _truncate(
            value,
            PROFILE_NAME_LIMIT,
        )

        if value != last_value:

            try:

                await _call_with_floodwait(
                    lambda: _update_profile_name(
                        heartless_bot,
                        value,
                    ),
                    "tname",
                )

                last_value = value

            except asyncio.CancelledError:
                raise

            except Exception as exc:

                LOGS.exception(
                    "timebio: tname update failed: %s",
                    exc,
                )

                await asyncio.sleep(3)

        await asyncio.sleep(
            _seconds_until_next_minute()
        )


async def _channel_bio_loop(chat_id):
    """
    Continuous channel description updater.
    """

    last_value = None

    while _as_bool(
        _db_get(
            CHANNEL_ACTIVE_KEY,
            False,
        )
    ):

        stored_chat = _db_get(
            CHANNEL_CHAT_KEY,
        )

        if stored_chat is None:
            LOGS.warning(
                "timebio: channel chat ID disappeared from DB."
            )
            break

        try:
            stored_chat = int(stored_chat)
        except (
            TypeError,
            ValueError,
        ):
            LOGS.error(
                "timebio: invalid channel chat ID: %r",
                stored_chat,
            )
            break

        if stored_chat != chat_id:
            break

        now = _tehran_now()

        template = _db_get(
            CHANNEL_BIO_TEXT_KEY,
            "Tehran Channel",
        )

        value = _render_template(
            template,
            now,
        )

        value = _truncate(
            value,
            CHAT_ABOUT_LIMIT,
        )

        if value != last_value:

            try:

                await _call_with_floodwait(
                    lambda: _update_chat_about(
                        heartless_bot,
                        chat_id,
                        value,
                    ),
                    "tcbio",
                )

                last_value = value

            except asyncio.CancelledError:
                raise

            except Exception as exc:

                LOGS.exception(
                    "timebio: tcbio update failed: %s",
                    exc,
                )

                await asyncio.sleep(5)

        await asyncio.sleep(
            _seconds_until_next_minute()
        )


async def _group_bio_loop(chat_id):
    """
    Continuous group/supergroup description updater.
    """

    last_value = None

    while _as_bool(
        _db_get(
            GROUP_ACTIVE_KEY,
            False,
        )
    ):

        stored_chat = _db_get(
            GROUP_CHAT_KEY,
        )

        if stored_chat is None:
            LOGS.warning(
                "timebio: group chat ID disappeared from DB."
            )
            break

        try:
            stored_chat = int(stored_chat)
        except (
            TypeError,
            ValueError,
        ):
            LOGS.error(
                "timebio: invalid group chat ID: %r",
                stored_chat,
            )
            break

        if stored_chat != chat_id:
            break

        now = _tehran_now()

        template = _db_get(
            GROUP_BIO_TEXT_KEY,
            "Tehran Group",
        )

        value = _render_template(
            template,
            now,
        )

        value = _truncate(
            value,
            CHAT_ABOUT_LIMIT,
        )

        if value != last_value:

            try:

                await _call_with_floodwait(
                    lambda: _update_chat_about(
                        heartless_bot,
                        chat_id,
                        value,
                    ),
                    "tgbio",
                )

                last_value = value

            except asyncio.CancelledError:
                raise

            except Exception as exc:

                LOGS.exception(
                    "timebio: tgbio update failed: %s",
                    exc,
                )

                await asyncio.sleep(5)

        await asyncio.sleep(
            _seconds_until_next_minute()
        )


# ============================================================================
# CHAT VALIDATION
# ============================================================================


async def _get_current_chat(event):
    """
    Resolve the current chat.
    """

    if event.chat_id is None:
        raise ValueError(
            "This command must be used inside a Telegram chat."
        )

    try:

        return await event.client.get_entity(
            event.chat_id
        )

    except Exception as exc:

        raise ValueError(
            "Unable to resolve the current chat."
        ) from exc


async def _validate_channel(event):
    """
    Ensure current chat is a Telegram broadcast channel.
    """

    chat = await _get_current_chat(event)

    if not isinstance(
        chat,
        types.Channel,
    ):
        raise ValueError(
            "tcbio must be used inside a channel."
        )

    if getattr(
        chat,
        "megagroup",
        False,
    ):
        raise ValueError(
            "This chat is a group/supergroup, not a channel. "
            "Use tgbio instead."
        )

    if getattr(
        chat,
        "gigagroup",
        False,
    ):
        raise ValueError(
            "This chat is not a normal broadcast channel."
        )

    return chat


async def _validate_group(event):
    """
    Ensure current chat is a group/supergroup.

    Both old Telegram groups and migrated supergroups are supported.
    """

    chat = await _get_current_chat(event)

    if isinstance(
        chat,
        types.Chat,
    ):
        return chat

    if isinstance(
        chat,
        types.Channel,
    ) and getattr(
        chat,
        "megagroup",
        False,
    ):
        return chat

    raise ValueError(
        "tgbio must be used inside a group or supergroup."
    )


# ============================================================================
# STOP HELPERS
# ============================================================================


async def _stop_bio():
    """
    Stop account biography automation.
    """

    _db_set(
        BIO_ACTIVE_KEY,
        False,
    )

    await _cancel_task(
        "tbio"
    )


async def _stop_name():
    """
    Stop account name automation.
    """

    _db_set(
        NAME_ACTIVE_KEY,
        False,
    )

    await _cancel_task(
        "tname"
    )


async def _stop_channel():
    """
    Stop channel description automation.
    """

    _db_set(
        CHANNEL_ACTIVE_KEY,
        False,
    )

    _db_delete(
        CHANNEL_CHAT_KEY
    )

    await _cancel_task(
        "tcbio"
    )


async def _stop_group():
    """
    Stop group description automation.
    """

    _db_set(
        GROUP_ACTIVE_KEY,
        False,
    )

    _db_delete(
        GROUP_CHAT_KEY
    )

    await _cancel_task(
        "tgbio"
    )


# ============================================================================
# CLOCK COMMAND
# ============================================================================


@heartless_cmd(
    pattern=r"tclock$"
)
async def tclock(event):
    """
    Show current Tehran time.
    """

    now = _tehran_now()

    values = _clock_values(
        now
    )

    text = (
        "**Tehran Time**\n\n"
        f"📅 `{values['date']}`\n"
        f"🕐 `{values['time']}`\n"
        f"🕒 `{values['datetime']}`"
    )

    await event.eor(
        text,
        time=8,
    )


# ============================================================================
# ACCOUNT BIO
# ============================================================================


@heartless_cmd(
    pattern=r"tbio(?:\s+(.*)|$)"
)
async def tbio(event):
    """
    Start/stop automatic account biography updates.
    """

    raw = (
        event.pattern_match.group(1)
        or ""
    ).strip()

    if raw.lower() == "off":

        await _stop_bio()

        return await event.eor(
            "`Automatic Tehran time in account bio stopped.`",
            time=5,
        )

    template = _clean_template(
        _db_get(
            BIO_TEXT_KEY,
            "Tehran Time",
        )
    )

    if not template:

        return await event.eor(
            "`BIOTEXT is empty. Set it first with:`\n"
            "`setdb BIOTEXT \"Hello World\"`",
            time=7,
        )

    _db_set(
        BIO_ACTIVE_KEY,
        True,
    )

    await _start_task(
        "tbio",
        _profile_bio_loop(),
    )

    # Force the first update immediately rather than waiting for the next
    # minute boundary.
    now = _tehran_now()

    value = _truncate(
        _render_template(
            template,
            now,
        ),
        PROFILE_BIO_LIMIT,
    )

    try:

        await _call_with_floodwait(
            lambda: _update_profile_bio(
                event.client,
                value,
            ),
            "tbio-initial",
        )

    except Exception as exc:

        LOGS.exception(
            "timebio: initial tbio update failed: %s",
            exc,
        )

    return await event.eor(
        "`Tehran time auto-bio started.`\n\n"
        f"Template: `{template}`\n"
        f"Current: `{value}`",
        time=7,
    )


# ============================================================================
# ACCOUNT NAME
# ============================================================================


@heartless_cmd(
    pattern=r"tname(?:\s+(.*)|$)"
)
async def tname(event):
    """
    Start/stop automatic account name updates.
    """

    raw = (
        event.pattern_match.group(1)
        or ""
    ).strip()

    if raw.lower() == "off":

        await _stop_name()

        return await event.eor(
            "`Automatic Tehran time in account name stopped.`",
            time=5,
        )

    template = _clean_template(
        _db_get(
            NAME_TEXT_KEY,
            "Tehran Time",
        )
    )

    if not template:

        return await event.eor(
            "`NAMETEXT is empty. Set it first with:`\n"
            "`setdb NAMETEXT \"My Account\"`",
            time=7,
        )

    _db_set(
        NAME_ACTIVE_KEY,
        True,
    )

    await _start_task(
        "tname",
        _profile_name_loop(),
    )

    now = _tehran_now()

    value = _truncate(
        _render_template(
            template,
            now,
        ),
        PROFILE_NAME_LIMIT,
    )

    try:

        await _call_with_floodwait(
            lambda: _update_profile_name(
                event.client,
                value,
            ),
            "tname-initial",
        )

    except Exception as exc:

        LOGS.exception(
            "timebio: initial tname update failed: %s",
            exc,
        )

    return await event.eor(
        "`Tehran time auto-name started.`\n\n"
        f"Template: `{template}`\n"
        f"Current: `{value}`",
        time=7,
    )


# ============================================================================
# CHANNEL BIO
# ============================================================================


@heartless_cmd(
    pattern=r"tcbio(?:\s+(.*)|$)"
)
async def tcbio(event):
    """
    Start/stop automatic channel description updates.
    """

    raw = (
        event.pattern_match.group(1)
        or ""
    ).strip()

    if raw.lower() == "off":

        await _stop_channel()

        return await event.eor(
            "`Automatic Tehran time in channel bio stopped.`",
            time=5,
        )

    try:

        channel = await _validate_channel(
            event
        )

    except ValueError as exc:

        return await event.eor(
            f"`{exc}`",
            time=7,
        )

    template = _clean_template(
        _db_get(
            CHANNEL_BIO_TEXT_KEY,
            "Tehran Channel",
        )
    )

    if not template:

        return await event.eor(
            "`CHANNELBIOTEXT is empty. Set it first with:`\n"
            "`setdb CHANNELBIOTEXT \"My Channel\"`",
            time=7,
        )

    chat_id = int(
        channel.id
    )

    _db_set(
        CHANNEL_CHAT_KEY,
        chat_id,
    )

    _db_set(
        CHANNEL_ACTIVE_KEY,
        True,
    )

    await _start_task(
        "tcbio",
        _channel_bio_loop(
            chat_id
        ),
    )

    now = _tehran_now()

    value = _truncate(
        _render_template(
            template,
            now,
        ),
        CHAT_ABOUT_LIMIT,
    )

    try:

        await _call_with_floodwait(
            lambda: _update_chat_about(
                event.client,
                chat_id,
                value,
            ),
            "tcbio-initial",
        )

    except Exception as exc:

        LOGS.exception(
            "timebio: initial tcbio update failed: %s",
            exc,
        )

        return await event.eor(
            "`Unable to update channel description.`\n"
            f"`{type(exc).__name__}: {exc}`",
            time=8,
        )

    return await event.eor(
        "`Tehran time auto-channel-bio started.`\n\n"
        f"Template: `{template}`\n"
        f"Current: `{value}`",
        time=7,
    )


# ============================================================================
# GROUP BIO
# ============================================================================


@heartless_cmd(
    pattern=r"tgbio(?:\s+(.*)|$)"
)
async def tgbio(event):
    """
    Start/stop automatic group/supergroup description updates.
    """

    raw = (
        event.pattern_match.group(1)
        or ""
    ).strip()

    if raw.lower() == "off":

        await _stop_group()

        return await event.eor(
            "`Automatic Tehran time in group bio stopped.`",
            time=5,
        )

    try:

        group = await _validate_group(
            event
        )

    except ValueError as exc:

        return await event.eor(
            f"`{exc}`",
            time=7,
        )

    template = _clean_template(
        _db_get(
            GROUP_BIO_TEXT_KEY,
            "Tehran Group",
        )
    )

    if not template:

        return await event.eor(
            "`GROUPBIOTEXT is empty. Set it first with:`\n"
            "`setdb GROUPBIOTEXT \"My Group\"`",
            time=7,
        )

    chat_id = int(
        group.id
    )

    _db_set(
        GROUP_CHAT_KEY,
        chat_id,
    )

    _db_set(
        GROUP_ACTIVE_KEY,
        True,
    )

    await _start_task(
        "tgbio",
        _group_bio_loop(
            chat_id
        ),
    )

    now = _tehran_now()

    value = _truncate(
        _render_template(
            template,
            now,
        ),
        CHAT_ABOUT_LIMIT,
    )

    try:

        await _call_with_floodwait(
            lambda: _update_chat_about(
                event.client,
                chat_id,
                value,
            ),
            "tgbio-initial",
        )

    except Exception as exc:

        LOGS.exception(
            "timebio: initial tgbio update failed: %s",
            exc,
        )

        return await event.eor(
            "`Unable to update group description.`\n"
            f"`{type(exc).__name__}: {exc}`",
            time=8,
        )

    return await event.eor(
        "`Tehran time auto-group-bio started.`\n\n"
        f"Template: `{template}`\n"
        f"Current: `{value}`",
        time=7,
    )


# ============================================================================
# RESTORE AUTOMATIONS AFTER RESTART
# ============================================================================


async def _restore_saved_tasks():
    """
    Restore previously enabled automations after plugin loading.

    This is intentionally conservative:

    - tbio/tname have no external target and can always be restored.
    - tcbio/tgbio require their saved chat IDs.
    - Invalid/missing targets are disabled instead of creating a permanent
      failing background task.
    """

    try:

        if _as_bool(
            _db_get(
                BIO_ACTIVE_KEY,
                False,
            )
        ):

            await _start_task(
                "tbio",
                _profile_bio_loop(),
            )

    except Exception as exc:

        LOGS.exception(
            "timebio: failed to restore tbio: %s",
            exc,
        )

    try:

        if _as_bool(
            _db_get(
                NAME_ACTIVE_KEY,
                False,
            )
        ):

            await _start_task(
                "tname",
                _profile_name_loop(),
            )

    except Exception as exc:

        LOGS.exception(
            "timebio: failed to restore tname: %s",
            exc,
        )

    try:

        if _as_bool(
            _db_get(
                CHANNEL_ACTIVE_KEY,
                False,
            )
        ):

            chat_id = _db_get(
                CHANNEL_CHAT_KEY
            )

            if chat_id is not None:

                chat_id = int(
                    chat_id
                )

                await _start_task(
                    "tcbio",
                    _channel_bio_loop(
                        chat_id
                    ),
                )

            else:

                _db_set(
                    CHANNEL_ACTIVE_KEY,
                    False,
                )

    except Exception as exc:

        LOGS.exception(
            "timebio: failed to restore tcbio: %s",
            exc,
        )

    try:

        if _as_bool(
            _db_get(
                GROUP_ACTIVE_KEY,
                False,
            )
        ):

            chat_id = _db_get(
                GROUP_CHAT_KEY
            )

            if chat_id is not None:

                chat_id = int(
                    chat_id
                )

                await _start_task(
                    "tgbio",
                    _group_bio_loop(
                        chat_id
                    ),
                )

            else:

                _db_set(
                    GROUP_ACTIVE_KEY,
                    False,
                )

    except Exception as exc:

        LOGS.exception(
            "timebio: failed to restore tgbio: %s",
            exc,
        )


# ============================================================================
# PLUGIN STARTUP
# ============================================================================


try:

    # Do not block plugin import.
    #
    # The project already has an active asyncio loop when plugins are loaded.
    _loop = asyncio.get_running_loop()

except RuntimeError:
    # Happens only if the plugin is imported before an event loop exists.
    # The commands themselves remain fully functional.
    LOGS.debug("timebio: asyncio loop not ready during plugin import.")

else:
    # Build the coroutine only once a running loop is available so that it is
    # always wrapped in a task and never left un-awaited.
    _restore_task = _loop.create_task(
        _restore_saved_tasks(),
        name="timebio:restore",
    )

    _restore_task.add_done_callback(
        lambda task: (
            None
            if task.cancelled()
            else (
                LOGS.error(
                    "timebio: restore task failed: %s",
                    task.exception(),
                    exc_info=(
                        type(task.exception()),
                        task.exception(),
                        task.exception().__traceback__,
                    ),
                )
                if task.exception()
                else None
            )
        )
    )

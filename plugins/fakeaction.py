from . import get_help

__doc__ = get_help("help_fakeaction")

import asyncio
import contextlib
import re
import time

from telethon import events
from telethon.errors.rpcerrorlist import (
    PeerIdInvalidError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)

from . import get_string, heartless_bot, heartless_cmd


# ============================================================================
# Configuration
# ============================================================================

DEFAULT_DURATION = 1800
MIN_DURATION = 1

ACTIONS = {
    "typing": "typing",
    "audio": "record-audio",
    "contact": "contact",
    "document": "document",
    "game": "game",
    "location": "location",
    "sticker": "sticker",
    "photo": "photo",
    "round": "record-round",
    "video": "record-video",
}

DURATION_RE = re.compile(r"^(\d+)([smhdSMHD]?)$")


# ============================================================================
# Runtime State
# ============================================================================

# ---------------------------------------------------------------------------
# ALL Fake Action watchers
#
# {
#     "typing": {
#         "handler": ...,
#         "builder": ...,
#         "duration": 1800,
#         "target_id": None,
#     }
# }
# ---------------------------------------------------------------------------

_ALL_WATCHERS = {}


# ---------------------------------------------------------------------------
# Action tasks created by ALL mode.
#
# Key:
#     (action_name, chat_id)
#
# Value:
#     asyncio.Task
#
# This allows every action to be cancelled independently.
# ---------------------------------------------------------------------------

_ALL_ACTION_TASKS = {}


# ---------------------------------------------------------------------------
# Normal/manual action tasks.
#
# Key:
#     (action_name, destination_id)
#
# Value:
#     asyncio.Task
#
# This is what makes:
#
#     ftyping 10h
#
# followed by:
#
#     ftyping off
#
# possible.
# ---------------------------------------------------------------------------

_ACTION_TASKS = {}


# ---------------------------------------------------------------------------
# Normal FSeen watchers.
#
# Key:
#     target user ID
#
# Value:
#     {
#         "handler": ...,
#         "builder": ...,
#         "entity": ...,
#     }
# ---------------------------------------------------------------------------

_SEEN_WATCHERS = {}


# ---------------------------------------------------------------------------
# ALL FSeen watcher.
#
# Only one global all-fseen watcher is maintained.
#
# {
#     "handler": ...,
#     "builder": ...,
#     "target_id": None,
# }
# ---------------------------------------------------------------------------

_ALL_SEEN_WATCHER = None


# ============================================================================
# Generic Helpers
# ============================================================================


def _parse_duration(value):
    """
    Convert duration string to seconds.

    Supported:

        10
        10s
        10m
        10h
        10d
    """

    if not value:
        return None

    value = value.strip()

    match = DURATION_RE.fullmatch(value)

    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2).lower()

    if amount < MIN_DURATION:
        return None

    multiplier = {
        "": 1,
        "s": 1,
        "m": 60,
        "h": 60 * 60,
        "d": 24 * 60 * 60,
    }[unit]

    return amount * multiplier


def _normalize_target(value):
    """
    Normalize username or numeric Telegram ID.

    Examples:

        username
        @username
        123456789
        -1001234567890
    """

    value = (value or "").strip()

    if not value:
        return None

    if value.lstrip("-").isdigit():
        return int(value)

    if not value.startswith("@"):
        return f"@{value}"

    return value


async def _resolve_entity(client, target):
    """
    Resolve username/numeric ID into a Telethon entity.
    """

    target = _normalize_target(target)

    if target is None:
        raise ValueError("Invalid target.")

    try:
        return await client.get_entity(target)

    except (
        UsernameInvalidError,
        UsernameNotOccupiedError,
        PeerIdInvalidError,
        ValueError,
    ) as exc:

        raise ValueError(
            f"Unable to resolve `{target}`. "
            "Check the username/ID and make sure this account "
            "can access that entity."
        ) from exc


def _parse_action_args(raw):
    """
    Parse fake-action arguments.

    Supported:

        ftyping
        ftyping 10
        ftyping 10s
        ftyping 5m
        ftyping 2h

        ftyping @username
        ftyping @username 10
        ftyping @username 10s

        ftyping 123456789 10
        ftyping 10 @username
        ftyping 10 123456789
    """

    raw = (raw or "").strip()

    # No arguments.
    if not raw:
        return None, DEFAULT_DURATION, None

    parts = raw.split()

    if len(parts) > 2:
        return None, None, "Too many arguments."

    # -----------------------------------------------------------------------
    # One argument
    # -----------------------------------------------------------------------

    if len(parts) == 1:

        value = parts[0]

        duration = _parse_duration(value)

        # Example:
        #
        # ftyping 10
        # ftyping 10h
        #
        if duration is not None:
            return None, duration, None

        # Username.
        if not value.lstrip("-").isdigit():
            return _normalize_target(value), DEFAULT_DURATION, None

        # A numeric target without duration is ambiguous because:
        #
        # ftyping 123456789
        #
        # is interpreted as a duration by the command syntax.
        return (
            None,
            None,
            "A numeric target ID must be followed by a duration.\n"
            "Example: `ftyping 123456789 10`",
        )

    first, second = parts

    first_duration = _parse_duration(first)
    second_duration = _parse_duration(second)

    # duration + target
    #
    # ftyping 10 @username
    if first_duration is not None and second_duration is None:

        return (
            _normalize_target(second),
            first_duration,
            None,
        )

    # target + duration
    #
    # ftyping @username 10
    if first_duration is None and second_duration is not None:

        return (
            _normalize_target(first),
            second_duration,
            None,
        )

    # Two durations.
    if first_duration is not None and second_duration is not None:

        return (
            None,
            None,
            "Only one duration can be specified.",
        )

    return (
        None,
        None,
        "A valid duration is required.",
    )


def _target_label(entity):
    """
    Return readable target name.
    """

    username = getattr(entity, "username", None)

    if username:
        return f"@{username}"

    entity_id = getattr(entity, "id", None)

    if entity_id is not None:
        return str(entity_id)

    return "unknown"


async def _cancel_task(task):
    """
    Safely cancel an asyncio task.
    """

    if task is None:
        return

    if task.done():
        with contextlib.suppress(Exception):
            task.result()
        return

    task.cancel()

    with contextlib.suppress(
        asyncio.CancelledError,
        Exception,
    ):
        await task


def _cancel_task_callback(task):
    """
    Consume task exceptions so asyncio does not report:

        Task exception was never retrieved
    """

    if task.cancelled():
        return

    with contextlib.suppress(Exception):
        task.exception()


async def _run_action(
    client,
    destination,
    action,
    duration,
):
    """
    Execute one fake Telegram action.
    """

    try:

        async with client.action(
            destination,
            action,
        ):

            await asyncio.sleep(duration)

    except asyncio.CancelledError:
        raise

    except Exception:
        return False

    return True


# ============================================================================
# Manual / Normal Action Task Management
# ============================================================================


def _destination_id(destination):
    """
    Get a stable ID for an action destination.
    """

    if isinstance(destination, int):
        return destination

    entity_id = getattr(
        destination,
        "id",
        None,
    )

    if entity_id is not None:
        return entity_id

    return None


async def _stop_action(
    action_name,
    destination_id,
):
    """
    Stop one normal/manual fake action.
    """

    key = (
        action_name,
        destination_id,
    )

    task = _ACTION_TASKS.pop(
        key,
        None,
    )

    if task is None:
        return False

    await _cancel_task(task)

    return True


async def _stop_all_manual_actions():
    """
    Stop all currently running normal/manual fake actions.
    """

    for key, task in list(
        _ACTION_TASKS.items()
    ):

        _ACTION_TASKS.pop(
            key,
            None,
        )

        await _cancel_task(task)


async def _start_manual_action(
    client,
    destination,
    action_name,
    duration,
):
    """
    Start a normal fake action.

    If an action of the same type is already running for the same
    destination, the previous task is replaced.
    """

    destination_id = _destination_id(
        destination
    )

    if destination_id is None:
        raise ValueError(
            "Unable to determine target ID."
        )

    key = (
        action_name,
        destination_id,
    )

    # Replace previous task.
    old_task = _ACTION_TASKS.pop(
        key,
        None,
    )

    if old_task:
        await _cancel_task(old_task)

    task = asyncio.create_task(
        _run_action(
            client,
            destination,
            ACTIONS[action_name],
            duration,
        )
    )

    task.add_done_callback(
        _cancel_task_callback
    )

    def cleanup(done_task):

        current = _ACTION_TASKS.get(key)

        if current is done_task:
            _ACTION_TASKS.pop(
                key,
                None,
            )

    task.add_done_callback(
        cleanup
    )

    _ACTION_TASKS[key] = task

    return task


# ============================================================================
# ALL MODE - Fake Actions
# ============================================================================


async def _stop_all_watcher(action_name):
    """
    Stop one ALL fake-action watcher and all tasks created by it.
    """

    watcher = _ALL_WATCHERS.pop(
        action_name,
        None,
    )

    if watcher:

        handler = watcher.get(
            "handler"
        )

        if handler:

            with contextlib.suppress(
                Exception
            ):

                heartless_bot.remove_event_handler(
                    handler
                )

    # Cancel all action tasks belonging to this action.
    for key, task in list(
        _ALL_ACTION_TASKS.items()
    ):

        task_action, chat_id = key

        if task_action != action_name:
            continue

        _ALL_ACTION_TASKS.pop(
            key,
            None,
        )

        await _cancel_task(task)


async def _stop_all_modes():
    """
    Stop every ALL fake-action watcher.
    """

    for action_name in list(
        _ALL_WATCHERS
    ):

        await _stop_all_watcher(
            action_name
        )


async def _start_all_watcher(
    action_name,
    duration,
    target=None,
):
    """
    Start ALL mode for a fake action.

    Examples:

        all ftyping 10

        all ftyping 10h

        all ftyping @username 10
    """

    # Remove existing watcher first.
    await _stop_all_watcher(
        action_name
    )

    # Important:
    # Only updates arriving after this timestamp are processed.
    activated_at = time.time()

    target_id = (
        getattr(target, "id", None)
        if target is not None
        else None
    )

    async def all_handler(event):

        try:

            # Only incoming messages.
            if not event.incoming:
                return

            message = event.message

            if not message:
                return

            if not message.date:
                return

            # Ignore messages that existed before activation.
            if (
                message.date.timestamp()
                <= activated_at
            ):
                return

            sender = await event.get_sender()

            if sender is None:
                return

            sender_id = getattr(
                sender,
                "id",
                None,
            )

            if sender_id is None:
                return

            # Ignore bots.
            if getattr(
                sender,
                "bot",
                False,
            ):
                return

            # Optional user filter.
            if (
                target_id is not None
                and sender_id != target_id
            ):
                return

            chat_id = event.chat_id

            if chat_id is None:
                return

            key = (
                action_name,
                chat_id,
            )

            # Telegram fake actions are chat-wide.
            # Newest message replaces previous task.
            old_task = _ALL_ACTION_TASKS.pop(
                key,
                None,
            )

            if old_task:
                await _cancel_task(
                    old_task
                )

            task = asyncio.create_task(
                _run_action(
                    event.client,
                    chat_id,
                    ACTIONS[action_name],
                    duration,
                )
            )

            task.add_done_callback(
                _cancel_task_callback
            )

            _ALL_ACTION_TASKS[key] = task

            def cleanup(done_task):

                current = _ALL_ACTION_TASKS.get(
                    key
                )

                if current is done_task:
                    _ALL_ACTION_TASKS.pop(
                        key,
                        None,
                    )

            task.add_done_callback(
                cleanup
            )

        except asyncio.CancelledError:
            raise

        except Exception:
            # Never allow an event handler exception to kill ALL mode.
            return

    builder = events.NewMessage(
        incoming=True,
    )

    heartless_bot.add_event_handler(
        all_handler,
        builder,
    )

    _ALL_WATCHERS[action_name] = {
        "handler": all_handler,
        "builder": builder,
        "duration": duration,
        "target_id": target_id,
        "activated_at": activated_at,
    }


# ============================================================================
# FSEEN - Normal Mode
# ============================================================================


async def _stop_seen_watcher(
    target_id,
):
    """
    Stop normal FSeen watcher for one user.
    """

    watcher = _SEEN_WATCHERS.pop(
        target_id,
        None,
    )

    if not watcher:
        return False

    handler = watcher.get(
        "handler"
    )

    if handler:

        with contextlib.suppress(
            Exception
        ):

            heartless_bot.remove_event_handler(
                handler
            )

    return True


async def _stop_all_seen_watchers():
    """
    Stop all normal FSeen watchers.
    """

    for target_id in list(
        _SEEN_WATCHERS
    ):

        await _stop_seen_watcher(
            target_id
        )


async def _start_seen_watcher(
    target_entity,
):
    """
    Start normal FSeen watcher for one user.
    """

    target_id = getattr(
        target_entity,
        "id",
        None,
    )

    if target_id is None:
        raise ValueError(
            "The selected entity does not have a valid user ID."
        )

    # Replace duplicate watcher.
    await _stop_seen_watcher(
        target_id
    )

    async def seen_handler(event):

        try:

            if not event.incoming:
                return

            if not event.message:
                return

            sender = await event.get_sender()

            if getattr(
                sender,
                "id",
                None,
            ) != target_id:
                return

            chat_id = event.chat_id

            if chat_id is None:
                return

            await event.client.send_read_acknowledge(
                chat_id,
                max_id=event.id,
            )

        except asyncio.CancelledError:
            raise

        except Exception:
            # Network/RPC failure should not kill watcher.
            return

    builder = events.NewMessage(
        incoming=True,
        from_users=target_id,
    )

    heartless_bot.add_event_handler(
        seen_handler,
        builder,
    )

    _SEEN_WATCHERS[target_id] = {
        "handler": seen_handler,
        "builder": builder,
        "entity": target_entity,
    }

    return seen_handler


# ============================================================================
# FSEEN - ALL Mode
# ============================================================================


async def _stop_all_seen_watcher():
    """
    Stop ALL FSeen watcher.
    """

    global _ALL_SEEN_WATCHER

    watcher = _ALL_SEEN_WATCHER

    _ALL_SEEN_WATCHER = None

    if not watcher:
        return False

    handler = watcher.get(
        "handler"
    )

    if handler:

        with contextlib.suppress(
            Exception
        ):

            heartless_bot.remove_event_handler(
                handler
            )

    return True


async def _start_all_seen_watcher(
    target=None,
):
    """
    Start ALL FSeen.

    Without target:

        all fseen

    Every new incoming message is acknowledged.

    With target:

        all fseen @username
        all fseen 123456789

    Only messages from that user are acknowledged.
    """

    global _ALL_SEEN_WATCHER

    await _stop_all_seen_watcher()

    activated_at = time.time()

    target_id = (
        getattr(target, "id", None)
        if target is not None
        else None
    )

    async def all_seen_handler(event):

        try:

            if not event.incoming:
                return

            message = event.message

            if not message:
                return

            if not message.date:
                return

            # Only new messages after activation.
            if (
                message.date.timestamp()
                <= activated_at
            ):
                return

            sender = await event.get_sender()

            if sender is None:
                return

            sender_id = getattr(
                sender,
                "id",
                None,
            )

            if sender_id is None:
                return

            # Ignore our own messages.
            if (
                sender_id
                == getattr(
                    event.client,
                    "uid",
                    None,
                )
            ):
                return

            # Ignore bots.
            if getattr(
                sender,
                "bot",
                False,
            ):
                return

            # Optional target filter.
            if (
                target_id is not None
                and sender_id != target_id
            ):
                return

            chat_id = event.chat_id

            if chat_id is None:
                return

            await event.client.send_read_acknowledge(
                chat_id,
                max_id=event.id,
            )

        except asyncio.CancelledError:
            raise

        except Exception:
            # Never kill global FSeen watcher.
            return

    builder = events.NewMessage(
        incoming=True,
    )

    heartless_bot.add_event_handler(
        all_seen_handler,
        builder,
    )

    _ALL_SEEN_WATCHER = {
        "handler": all_seen_handler,
        "builder": builder,
        "target_id": target_id,
        "activated_at": activated_at,
    }


# ============================================================================
# FSEEN Target Resolver
# ============================================================================


async def _get_seen_target(
    event,
    raw,
):
    """
    Resolve FSeen target in this priority:

    1. Explicit username / numeric ID.
    2. Replied message sender.
    3. Current private-chat user.
    """

    raw = (raw or "").strip()

    # -----------------------------------------------------------------------
    # Explicit target
    # -----------------------------------------------------------------------

    if raw:

        parts = raw.split()

        if len(parts) > 1:
            raise ValueError(
                "fseen accepts only one username or numeric ID."
            )

        return await _resolve_entity(
            event.client,
            parts[0],
        )

    # -----------------------------------------------------------------------
    # Reply target
    # -----------------------------------------------------------------------

    if event.is_reply:

        reply = await event.get_reply_message()

        if reply:

            sender = await reply.get_sender()

            if sender is not None:
                return sender

    # -----------------------------------------------------------------------
    # Private chat
    # -----------------------------------------------------------------------

    if event.is_private:

        chat = await event.get_chat()

        if getattr(
            chat,
            "id",
            None,
        ) == getattr(
            event.client,
            "uid",
            None,
        ):

            raise ValueError(
                "You cannot use fseen on yourself."
            )

        if getattr(
            chat,
            "bot",
            False,
        ):

            raise ValueError(
                "The target chat is a bot, not a normal user."
            )

        return chat

    # -----------------------------------------------------------------------
    # Group/channel
    # -----------------------------------------------------------------------

    raise ValueError(
        "In a group, use fseen as a reply to the person's "
        "message or provide their @username / numeric ID."
    )


# ============================================================================
# Fake Action Commands
# ============================================================================


@heartless_cmd(
    pattern=(
        r"(all\s+)?"
        r"f(typing|audio|contact|document|game|location|sticker|photo|round|video)"
        r"(?:\s+(.*)|$)"
    )
)
async def fake_action(event):
    """
    Fake Telegram actions.

    Normal:

        ftyping
        ftyping 10
        ftyping 10h
        ftyping @username 10
        ftyping 123456789 10

    Stop:

        ftyping off
        ftyping off @username

    ALL:

        all ftyping 10
        all ftyping 10h
        all ftyping @username 10

    Stop ALL:

        all ftyping off
    """

    all_prefix = event.pattern_match.group(1)

    action_name = event.pattern_match.group(2)

    raw = (
        event.pattern_match.group(3)
        or ""
    ).strip()

    all_mode = bool(all_prefix)

    action = ACTIONS[action_name]

    # ========================================================================
    # ALL OFF
    # ========================================================================

    if all_mode and raw:

        parts = raw.split()

        if parts[0].lower() == "off":

            # all ftyping off
            if len(parts) == 1:

                stopped = await _stop_all_watcher(
                    action_name
                )

                if stopped:

                    return await event.eor(
                        f"`All {action_name} mode stopped.`",
                        time=4,
                    )

                return await event.eor(
                    f"`All {action_name} mode was not active.`",
                    time=4,
                )

            # Currently ALL action's target filter is controlled by
            # the watcher itself. Therefore:
            #
            # all ftyping off @username
            #
            # is treated as stopping the action's ALL watcher.
            #
            # This is intentional because only one ALL watcher per action
            # is maintained.
            if len(parts) == 2:

                stopped = await _stop_all_watcher(
                    action_name
                )

                if stopped:

                    return await event.eor(
                        f"`All {action_name} mode stopped.`",
                        time=4,
                    )

                return await event.eor(
                    f"`All {action_name} mode was not active.`",
                    time=4,
                )

            return await event.eor(
                "`Invalid ALL off syntax.`",
                time=5,
            )

    # ========================================================================
    # ALL MODE
    # ========================================================================

    if all_mode:

        target_raw, duration, error = (
            _parse_action_args(raw)
        )

        if error:

            return await event.eor(
                f"`{error}`",
                time=6,
            )

        target = None

        if target_raw is not None:

            try:

                target = await _resolve_entity(
                    event.client,
                    target_raw,
                )

            except ValueError as exc:

                return await event.eor(
                    f"`{exc}`",
                    time=7,
                )

            if not hasattr(
                target,
                "id",
            ):

                return await event.eor(
                    "`The selected target is invalid.`",
                    time=5,
                )

        await _start_all_watcher(
            action_name,
            duration,
            target=target,
        )

        if target is not None:

            label = _target_label(
                target
            )

            text = (
                f"`All {action_name} mode enabled "
                f"for {label}. Each new message from "
                f"this user triggers it for {duration}s.`"
            )

        else:

            text = (
                f"`All {action_name} mode enabled. "
                f"Each new incoming message triggers "
                f"it for {duration}s.`"
            )

        return await event.eor(
            text,
            time=7,
        )

    # ========================================================================
    # NORMAL OFF
    # ========================================================================

    if raw:

        parts = raw.split()

        if parts[0].lower() == "off":

            # ---------------------------------------------------------------
            # ftyping off
            #
            # Stop current action in current chat.
            # ---------------------------------------------------------------

            if len(parts) == 1:

                destination_id = event.chat_id

                if destination_id is None:

                    return await event.eor(
                        "`Unable to determine current chat.`",
                        time=5,
                    )

                stopped = await _stop_action(
                    action_name,
                    destination_id,
                )

                if stopped:

                    return await event.eor(
                        f"`{action_name} stopped.`",
                        time=4,
                    )

                return await event.eor(
                    f"`No active {action_name} action found.`",
                    time=4,
                )

            # ---------------------------------------------------------------
            # ftyping off @username
            # ftyping off 123456789
            # ---------------------------------------------------------------

            if len(parts) == 2:

                target_raw = parts[1]

                try:

                    target = await _resolve_entity(
                        event.client,
                        target_raw,
                    )

                except ValueError as exc:

                    return await event.eor(
                        f"`{exc}`",
                        time=7,
                    )

                destination_id = _destination_id(
                    target
                )

                if destination_id is None:

                    return await event.eor(
                        "`Invalid target.`",
                        time=5,
                    )

                stopped = await _stop_action(
                    action_name,
                    destination_id,
                )

                if stopped:

                    return await event.eor(
                        f"`{action_name} stopped for "
                        f"{_target_label(target)}.`",
                        time=5,
                    )

                return await event.eor(
                    f"`No active {action_name} action found "
                    f"for {_target_label(target)}.`",
                    time=5,
                )

            return await event.eor(
                "`Invalid off syntax.`",
                time=5,
            )

    # ========================================================================
    # NORMAL ACTION
    # ========================================================================

    target_raw, duration, error = (
        _parse_action_args(raw)
    )

    if error:

        return await event.eor(
            f"`{error}`",
            time=6,
        )

    destination = event.chat_id

    # Explicit target.
    if target_raw is not None:

        try:

            destination = await _resolve_entity(
                event.client,
                target_raw,
            )

        except ValueError as exc:

            return await event.eor(
                f"`{exc}`",
                time=7,
            )

    destination_id = _destination_id(
        destination
    )

    if destination_id is None:

        return await event.eor(
            "`Unable to determine target chat.`",
            time=5,
        )

    # Start asynchronously.
    try:

        await _start_manual_action(
            event.client,
            destination,
            action_name,
            duration,
        )

    except Exception:

        return await event.eor(
            "`Unable to start fake action.`",
            time=6,
        )

    # Existing project string, if available.
    try:

        text = get_string(
            "fka_1"
        ).format(
            str(duration)
        )

    except Exception:

        if target_raw is not None:

            text = (
                f"`{action_name} started for "
                f"{_target_label(destination)} "
                f"for {duration}s.`"
            )

        else:

            text = (
                f"`{action_name} started for "
                f"{duration}s.`"
            )

    return await event.eor(
        text,
        time=5,
    )


# ============================================================================
# FSEEN COMMAND
# ============================================================================


@heartless_cmd(
    pattern=r"(all\s+)?fseen(?:\s+(.*)|$)"
)
async def fseen(event):
    """
    FSeen normal and ALL modes.

    Normal:

        fseen
        fseen @username
        fseen 123456789

    Stop:

        fseen off
        fseen off @username
        fseen off 123456789

    ALL:

        all fseen
        all fseen @username
        all fseen 123456789

    Stop ALL:

        all fseen off
        all fseen off @username
        all fseen off 123456789
    """

    all_prefix = event.pattern_match.group(1)

    raw = (
        event.pattern_match.group(2)
        or ""
    ).strip()

    all_mode = bool(all_prefix)

    # ========================================================================
    # ALL FSEEN
    # ========================================================================

    if all_mode:

        parts = raw.split()

        # ---------------------------------------------------------------
        # all fseen off
        # all fseen off @username
        # all fseen off 123456789
        # ---------------------------------------------------------------

        if parts and parts[0].lower() == "off":

            if len(parts) > 2:

                return await event.eor(
                    "`Invalid ALL FSeen off syntax.`",
                    time=5,
                )

            stopped = await _stop_all_seen_watcher()

            if stopped:

                return await event.eor(
                    "`All FSeen mode stopped.`",
                    time=5,
                )

            return await event.eor(
                "`All FSeen mode was not active.`",
                time=5,
            )

        # ---------------------------------------------------------------
        # all fseen
        #
        # Every new incoming message.
        # ---------------------------------------------------------------

        target = None

        if raw:

            if len(parts) != 1:

                return await event.eor(
                    "`all fseen accepts only one username "
                    "or numeric ID.`",
                    time=5,
                )

            try:

                target = await _resolve_entity(
                    event.client,
                    parts[0],
                )

            except ValueError as exc:

                return await event.eor(
                    f"`{exc}`",
                    time=7,
                )

        # Do not monitor ourselves.
        if (
            target is not None
            and getattr(
                target,
                "id",
                None,
            )
            == getattr(
                event.client,
                "uid",
                None,
            )
        ):

            return await event.eor(
                "`You cannot use FSeen on yourself.`",
                time=5,
            )

        try:

            await _start_all_seen_watcher(
                target=target
            )

        except Exception as exc:

            return await event.eor(
                f"`Unable to start All FSeen: {exc}`",
                time=7,
            )

        if target is not None:

            return await event.eor(
                f"`All FSeen enabled for "
                f"{_target_label(target)}. New messages "
                "from this user will be marked as read.`",
                time=7,
            )

        return await event.eor(
            "`All FSeen enabled. Every new incoming "
            "message will be marked as read.`",
            time=7,
        )

    # ========================================================================
    # NORMAL FSEEN OFF
    # ========================================================================

    parts = raw.split()

    if parts and parts[0].lower() == "off":

        if len(parts) > 2:

            return await event.eor(
                "`Invalid FSeen off syntax.`",
                time=5,
            )

        target_raw = (
            parts[1]
            if len(parts) == 2
            else ""
        )

        try:

            target = await _get_seen_target(
                event,
                target_raw,
            )

        except ValueError as exc:

            return await event.eor(
                f"`{exc}`",
                time=7,
            )

        target_id = getattr(
            target,
            "id",
            None,
        )

        if target_id is None:

            return await event.eor(
                "`Invalid target.`",
                time=5,
            )

        stopped = await _stop_seen_watcher(
            target_id
        )

        if stopped:

            return await event.eor(
                f"`FSeen stopped for "
                f"{_target_label(target)}.`",
                time=5,
            )

        return await event.eor(
            f"`FSeen was not active for "
            f"{_target_label(target)}.`",
            time=5,
        )

    # ========================================================================
    # NORMAL FSEEN START
    # ========================================================================

    if len(parts) > 1:

        return await event.eor(
            "`fseen accepts only one username or numeric ID.`",
            time=5,
        )

    try:

        target = await _get_seen_target(
            event,
            raw,
        )

    except ValueError as exc:

        return await event.eor(
            f"`{exc}`",
            time=7,
        )

    target_id = getattr(
        target,
        "id",
        None,
    )

    if target_id is None:

        return await event.eor(
            "`The selected target does not have a valid user ID.`",
            time=5,
        )

    # Do not monitor ourselves.
    if (
        target_id
        == getattr(
            event.client,
            "uid",
            None,
        )
    ):

        return await event.eor(
            "`fseen cannot be enabled for your own messages.`",
            time=5,
        )

    # ------------------------------------------------------------------------
    # Immediately acknowledge the latest existing message from target
    # in current chat, if possible.
    # ------------------------------------------------------------------------

    with contextlib.suppress(
        Exception
    ):

        latest = await event.client.get_messages(
            event.chat_id,
            limit=1,
            from_user=target,
        )

        if latest:

            await event.client.send_read_acknowledge(
                event.chat_id,
                max_id=latest[0].id,
            )

    # ------------------------------------------------------------------------
    # Start watcher.
    # ------------------------------------------------------------------------

    try:

        await _start_seen_watcher(
            target
        )

    except ValueError as exc:

        return await event.eor(
            f"`{exc}`",
            time=7,
        )

    except Exception as exc:

        return await event.eor(
            f"`Unable to start FSeen: {exc}`",
            time=7,
        )

    return await event.eor(
        f"`FSeen enabled for {_target_label(target)}. "
        "New messages from this user will be marked "
        "as read automatically.`",
        time=7,
    )

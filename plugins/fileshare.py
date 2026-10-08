from . import get_help

__doc__ = get_help("help_fileshare")

import asyncio
import contextlib
import math
import os
import re
import time
from collections import Counter

from telethon import Button, events

from CythonX.dB.filestore_db import (
    del_stored,
    get_stored_msg,
    list_all_stored_msgs,
)
from CythonX.fns.tools import get_file_link

from . import (
    HNDLR,
    asst,
    callback,
    get_string,
    in_pattern,
    udB,
    heartless_bot,
    heartless_cmd,
)


# ============================================================================
# Configuration
# ============================================================================

PAGE_SIZE = 10
MAX_INLINE_RESULTS = 50
MAX_NAME_LENGTH = 80
MAX_SEARCH_LENGTH = 100

META_KEY = "FILE_STORE_META"

# Used to prevent simultaneous modifications of FILE_STORE / FILE_STORE_META.
_STORE_LOCK = asyncio.Lock()

# Small in-process cache for inline browsing.
#
# The database remains the source of truth. This cache only reduces repeated
# work during a single burst of inline queries/callbacks.
_INLINE_CACHE = {
    "time": 0.0,
    "items": None,
}

CACHE_TTL = 2.0


# ============================================================================
# Generic helpers
# ============================================================================


def _bot_username():
    """
    Return assistant bot username without @.
    """
    username = getattr(getattr(asst, "me", None), "username", None)
    return username or ""


def _share_link(name):
    """
    Build the permanent assistant deep-link for a stored item.
    """
    username = _bot_username()

    if not username:
        return None

    return f"https://t.me/{username}?start={name}"


def _normalize_name(value):
    """
    Normalize a user supplied FileStore name.

    The name is intentionally kept human readable while removing characters
    that are problematic inside a Telegram start parameter.
    """
    value = (value or "").strip()

    if not value:
        return None

    value = re.sub(r"\s+", "_", value)

    # Telegram deep-link parameters are safer with a restricted character set.
    value = re.sub(r"[^A-Za-z0-9_.@+\-]", "_", value)

    value = re.sub(r"_+", "_", value)

    value = value.strip("_")

    if not value:
        return None

    return value[:MAX_NAME_LENGTH]


def _display_name(name):
    """
    Human-readable representation of a stored name.
    """
    return str(name).replace("_", " ")


def _get_meta():
    """
    Get optional metadata without breaking old installations.
    """
    meta = udB.get_key(META_KEY)

    if not isinstance(meta, dict):
        return {}

    return meta


def _set_meta(meta):
    """
    Save metadata.
    """
    return udB.set_key(META_KEY, meta)


def _get_store_names():
    """
    Return all stored names.

    The original project database remains authoritative.
    """
    try:
        names = list_all_stored_msgs()
    except Exception:
        return []

    if not names:
        return []

    return list(dict.fromkeys(str(x) for x in names))


def _invalidate_cache():
    """
    Invalidate inline cache.
    """
    _INLINE_CACHE["time"] = 0.0
    _INLINE_CACHE["items"] = None


def _get_cached_names():
    """
    Get names with a very short cache.

    This is intentionally tiny because FileStore can be modified at any time.
    """
    now = time.monotonic()

    if (
        _INLINE_CACHE["items"] is not None
        and now - _INLINE_CACHE["time"] < CACHE_TTL
    ):
        return list(_INLINE_CACHE["items"])

    names = _get_store_names()

    _INLINE_CACHE["items"] = list(names)
    _INLINE_CACHE["time"] = now

    return names


def _sort_names(names, meta=None):
    """
    Sort files using stored creation timestamp where available.

    Older installations without metadata are sorted alphabetically.
    """
    meta = meta or _get_meta()

    def key(name):
        info = meta.get(name, {})

        if isinstance(info, dict):
            created = info.get("created_at", 0)

            try:
                return float(created)
            except Exception:
                pass

        return 0

    # Newest first.
    return sorted(
        names,
        key=key,
        reverse=True,
    )


def _format_size(size):
    """
    Convert bytes into a readable size.
    """
    if size is None:
        return "Unknown"

    try:
        size = int(size)
    except Exception:
        return "Unknown"

    units = (
        "B",
        "KB",
        "MB",
        "GB",
        "TB",
    )

    value = float(size)

    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"

            return f"{value:.2f} {unit}"

        value /= 1024

    return "Unknown"


def _message_info(message):
    """
    Extract safe metadata from a Telegram message.
    """
    if not message:
        return {}

    media = getattr(message, "media", None)

    document = getattr(message, "document", None)

    photo = getattr(message, "photo", None)

    size = None

    if document:
        size = getattr(document, "size", None)

    elif photo:
        # Telegram Photo does not always expose a direct size.
        size = None

    mime = None

    if document:
        mime = getattr(document, "mime_type", None)

    return {
        "message_id": getattr(message, "id", None),
        "date": (
            message.date.timestamp()
            if getattr(message, "date", None)
            else None
        ),
        "size": size,
        "mime": mime,
        "has_media": bool(media),
        "text": bool(getattr(message, "text", None)),
    }


def _short_text(text, limit=80):
    """
    Safely shorten text for Inline descriptions.
    """
    text = str(text or "")
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) <= limit:
        return text

    return text[: limit - 3] + "..."


def _file_description(name, message=None, meta=None):
    """
    Build Inline description.
    """
    meta = meta or {}

    parts = []

    info = meta.get(name, {})

    if isinstance(info, dict):
        kind = info.get("kind")

        if kind:
            parts.append(str(kind))

    if message:
        m_info = _message_info(message)

        if m_info.get("size") is not None:
            parts.append(
                _format_size(m_info["size"])
            )

        if m_info.get("mime"):
            parts.append(
                str(m_info["mime"])
            )

    if not parts:
        parts.append("Stored File")

    return " • ".join(parts)[:255]


async def _get_stored_message(name):
    """
    Retrieve the original stored message from LOG_CHANNEL.
    """
    msg_id = get_stored_msg(name)

    if not msg_id:
        return None

    log_channel = udB.get_key("LOG_CHANNEL")

    if not log_channel:
        return None

    try:
        message = await asst.get_messages(
            log_channel,
            ids=int(msg_id),
        )
    except Exception:
        return None

    if not message:
        return None

    if not getattr(message, "id", None):
        return None

    return message


async def _ensure_meta(name, message=None):
    """
    Lazily create metadata for old FileStore entries.
    """
    async with _STORE_LOCK:
        meta = _get_meta()

        if name in meta:
            return meta.get(name) or {}

        info = {
            "created_at": time.time(),
            "kind": "media" if message and message.media else "text",
        }

        if message:
            info.update(
                _message_info(message)
            )

        meta[name] = info

        _set_meta(meta)

        return info


async def _remove_stored(name):
    """
    Remove a FileStore entry and its metadata.
    """
    async with _STORE_LOCK:

        msg_id = get_stored_msg(name)

        if not msg_id:
            return False, None

        try:
            del_stored(name)
        except Exception:
            return False, msg_id

        meta = _get_meta()

        if name in meta:
            meta.pop(name, None)
            _set_meta(meta)

        _invalidate_cache()

        return True, msg_id


async def _rename_stored(old_name, new_name):
    """
    Rename a stored entry while preserving its Telegram message ID and
    metadata.
    """
    new_name = _normalize_name(new_name)

    if not new_name:
        raise ValueError("Invalid new name.")

    if old_name == new_name:
        raise ValueError(
            "The new name is identical to the current name."
        )

    async with _STORE_LOCK:

        current_id = get_stored_msg(old_name)

        if not current_id:
            raise ValueError(
                "The stored file does not exist."
            )

        if get_stored_msg(new_name):
            raise ValueError(
                "A file with the new name already exists."
            )

        # We intentionally use the project's existing DB helper API.
        from CythonX.dB.filestore_db import store_msg

        store_msg(
            new_name,
            current_id,
        )

        del_stored(old_name)

        meta = _get_meta()

        if old_name in meta:
            meta[new_name] = meta.pop(old_name)
            _set_meta(meta)

        _invalidate_cache()

    return True


async def _delete_log_message(msg_id):
    """
    Delete the physical stored message from LOG_CHANNEL.
    """
    if not msg_id:
        return False

    log_channel = udB.get_key("LOG_CHANNEL")

    if not log_channel:
        return False

    try:
        await heartless_bot.delete_messages(
            log_channel,
            int(msg_id),
        )
        return True
    except Exception:
        return False


def _paginate(items, page):
    """
    Return page slice and pagination information.
    """
    total = len(items)

    pages = max(
        1,
        math.ceil(total / PAGE_SIZE),
    )

    page = max(
        0,
        min(page, pages - 1),
    )

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE

    return (
        items[start:end],
        page,
        pages,
    )


def _page_buttons(page, pages):
    """
    Pagination keyboard.
    """
    buttons = []

    row = []

    if page > 0:
        row.append(
            Button.inline(
                "‹ Previous",
                data=f"fs_page:{page - 1}",
            )
        )

    if page < pages - 1:
        row.append(
            Button.inline(
                "Next ›",
                data=f"fs_page:{page + 1}",
            )
        )

    if row:
        buttons.append(row)

    buttons.append(
        [
            Button.inline(
                "↻ Refresh",
                data=f"fs_refresh:{page}",
            ),
            Button.inline(
                "Stats",
                data="fs_stats",
            ),
        ]
    )

    return buttons


# ============================================================================
# Inline rendering
# ============================================================================


async def _build_inline_results(event, names, page=0):
    """
    Build InlineQueryResult objects.

    Invalid/deleted stored messages are skipped rather than crashing the
    entire Inline query.
    """
    meta = _get_meta()

    page_items, page, pages = _paginate(
        names,
        page,
    )

    results = []

    for name in page_items:

        message = await _get_stored_message(name)

        if not message:
            continue

        await _ensure_meta(
            name,
            message,
        )

        info = meta.get(name, {})

        description = _file_description(
            name,
            message,
            meta,
        )

        title = _display_name(name)

        share = _share_link(name)

        buttons = []

        if share:
            buttons.append(
                [
                    Button.url(
                        "🔗 Open",
                        share,
                    )
                ]
            )

        # --------------------------------------------------------------------
        # Media result
        # --------------------------------------------------------------------

        if message.media:

            try:
                result = await event.builder.document(
                    title=title,
                    description=description,
                    file=message.media,
                    text=(
                        f"**{title}**\n\n"
                        f"Stored File\n"
                        f"Size: {_format_size(info.get('size'))}"
                    ),
                    buttons=buttons or None,
                )

                results.append(result)

            except Exception:
                continue

        # --------------------------------------------------------------------
        # Text result
        # --------------------------------------------------------------------

        elif message.text:

            text = message.text

            result = await event.builder.article(
                title=title,
                description=_short_text(text),
                text=text,
                buttons=buttons or None,
            )

            results.append(result)

    return results, page, pages


# ============================================================================
# STORE
# ============================================================================


@heartless_cmd(
    pattern=r"store(?:\s+(.*))?$"
)
async def filestore(event):
    """
    Store a replied message/media.
    """

    reply = await event.get_reply_message()

    if not reply:
        return await event.eor(
            get_string("fsh_3"),
            time=5,
        )

    raw_name = event.pattern_match.group(1)

    if not raw_name:
        return await event.eor(
            "Give me a name for the stored file.",
            time=5,
        )

    name = _normalize_name(raw_name)

    if not name:
        return await event.eor(
            "Invalid file name.",
            time=5,
        )

    if get_stored_msg(name):
        return await event.eor(
            f"`{name}` is already stored. "
            "Use another name or rename the existing item.",
            time=6,
        )

    try:
        # Keep using the project's established storage mechanism.
        stored_name = await get_file_link(
            reply,
            name,
        )

    except Exception as exc:
        return await event.eor(
            f"`Unable to store this message: {exc}`",
            time=7,
        )

    message = await _get_stored_message(
        stored_name
    )

    await _ensure_meta(
        stored_name,
        message,
    )

    link = _share_link(stored_name)

    if not link:
        return await event.eor(
            "File stored, but assistant bot username is unavailable.",
            time=7,
        )

    await event.eor(
        get_string("fsh_2").format(link),
        link_preview=False,
    )


# ============================================================================
# DELETE
# ============================================================================


@heartless_cmd(
    pattern=r"delstored(?:\s+(.*))?$"
)
async def delstored(event):
    """
    Delete a stored file.

    Accepts either:
        delstored NAME
        delstored https://t.me/BOT?start=NAME
    """

    raw = (
        event.pattern_match.group(1)
        or ""
    ).strip()

    if not raw:
        return await event.eor(
            "`Give a stored file name or its shareable link.`",
            time=5,
        )

    name = raw

    # Extract deep-link name.
    if "?start=" in raw:
        try:
            bot_part, name = raw.split(
                "?start=",
                1,
            )

            bot_username = (
                bot_part.rstrip("/")
                .split("/")[-1]
                .lstrip("@")
            )

            if (
                bot_username.lower()
                != _bot_username().lower()
            ):
                return await event.eor(
                    "`This file was not stored by this assistant bot.`",
                    time=6,
                )

        except Exception:
            return await event.eor(
                "`Invalid stored-file link.`",
                time=5,
            )

    name = name.strip()

    msg_id = get_stored_msg(name)

    if not msg_id:
        return await event.eor(
            "`Stored file was not found or was already deleted.`",
            time=6,
        )

    removed, msg_id = await _remove_stored(
        name
    )

    if not removed:
        return await event.eor(
            "`Unable to remove the stored entry.`",
            time=6,
        )

    await _delete_log_message(
        msg_id
    )

    await event.eor(
        f"`Deleted: {name}`",
        time=5,
    )


# ============================================================================
# RENAME
# ============================================================================


@heartless_cmd(
    pattern=r"renamestored(?:\s+(\S+)\s+(\S.*))?$"
)
async def renamestored(event):
    """
    Rename:

        renamestored old new
    """

    old_name = event.pattern_match.group(1)
    new_name = event.pattern_match.group(2)

    if not old_name or not new_name:
        return await event.eor(
            "`Usage: renamestored <old_name> <new_name>`",
            time=6,
        )

    old_name = old_name.strip()
    new_name = _normalize_name(
        new_name
    )

    if not new_name:
        return await event.eor(
            "`Invalid new name.`",
            time=5,
        )

    if not get_stored_msg(old_name):
        return await event.eor(
            "`The original stored file does not exist.`",
            time=6,
        )

    try:
        await _rename_stored(
            old_name,
            new_name,
        )

    except ValueError as exc:
        return await event.eor(
            f"`{exc}`",
            time=6,
        )

    link = _share_link(new_name)

    text = (
        f"`Renamed successfully.`\n\n"
        f"`Old:` {old_name}\n"
        f"`New:` {new_name}"
    )

    if link:
        text += f"\n\n{link}"

    await event.eor(
        text,
        link_preview=False,
    )


# ============================================================================
# LIST
# ============================================================================


@heartless_cmd(
    pattern=r"liststored$"
)
async def liststored(event):
    """
    List all stored files.
    """

    names = _sort_names(
        _get_store_names()
    )

    if not names:
        return await event.eor(
            get_string("fsh_4"),
            time=5,
        )

    total = len(names)

    # Telegram message limit.
    lines = [
        "**Stored Files:**",
        "",
    ]

    for index, name in enumerate(
        names,
        start=1,
    ):
        link = _share_link(name)

        if link:
            lines.append(
                f"`{index}`. [{_display_name(name)}]({link})"
            )
        else:
            lines.append(
                f"`{index}`. `{name}`"
            )

    text = "\n".join(lines)

    if len(text) <= 4095:
        return await event.eor(
            text,
            link_preview=False,
        )

    # Fall back to a file.
    path = "filestore_list.txt"

    try:
        with open(
            path,
            "w",
            encoding="utf-8",
        ) as fp:
            fp.write(
                "\n".join(
                    f"{i}. {_display_name(name)}"
                    + (
                        f" - {_share_link(name)}"
                        if _share_link(name)
                        else ""
                    )
                    for i, name in enumerate(
                        names,
                        start=1,
                    )
                )
            )

        await event.reply(
            get_string("fsh_1"),
            file=path,
        )

    finally:
        with contextlib.suppress(Exception):
            os.remove(path)


# ============================================================================
# INFO
# ============================================================================


@heartless_cmd(
    pattern=r"(?:fileinfo|storedinfo)(?:\s+(.*))?$"
)
async def storedinfo(event):
    """
    Show detailed information about a stored item.
    """

    name = (
        event.pattern_match.group(1)
        or ""
    ).strip()

    if not name:
        return await event.eor(
            "`Usage: fileinfo <stored_name>`",
            time=5,
        )

    msg_id = get_stored_msg(name)

    if not msg_id:
        return await event.eor(
            "`Stored file not found.`",
            time=5,
        )

    message = await _get_stored_message(
        name
    )

    if not message:
        return await event.eor(
            "`The stored Telegram message no longer exists.`",
            time=6,
        )

    info = await _ensure_meta(
        name,
        message,
    )

    created = info.get(
        "created_at"
    )

    if created:
        created_text = time.strftime(
            "%Y-%m-%d %H:%M:%S UTC",
            time.gmtime(created),
        )
    else:
        created_text = "Unknown"

    share = _share_link(name)

    text = (
        f"**File Information**\n\n"
        f"• **Name:** `{name}`\n"
        f"• **Message ID:** `{msg_id}`\n"
        f"• **Type:** `{info.get('kind', 'unknown')}`\n"
        f"• **MIME:** `{info.get('mime') or 'Unknown'}`\n"
        f"• **Size:** `{_format_size(info.get('size'))}`\n"
        f"• **Stored:** `{created_text}`"
    )

    if share:
        text += (
            f"\n\n**Share Link:**\n{share}"
        )

    await event.eor(
        text,
        link_preview=False,
    )


# ============================================================================
# STATS
# ============================================================================


@heartless_cmd(
    pattern=r"filestats$"
)
async def filestats(event):
    """
    Show FileStore statistics.
    """

    names = _get_store_names()

    if not names:
        return await event.eor(
            "`FileStore is empty.`",
            time=5,
        )

    meta = _get_meta()

    media_count = 0
    text_count = 0
    known_size = 0

    for name in names:

        info = meta.get(
            name,
            {},
        )

        if not isinstance(info, dict):
            continue

        if info.get("kind") == "media":
            media_count += 1

        elif info.get("kind") == "text":
            text_count += 1

        size = info.get("size")

        if isinstance(size, (int, float)):
            known_size += int(size)

    text = (
        "**FileStore Statistics**\n\n"
        f"• **Total:** `{len(names)}`\n"
        f"• **Media:** `{media_count}`\n"
        f"• **Text:** `{text_count}`\n"
        f"• **Known Size:** `{_format_size(known_size)}`\n"
        f"• **Inline Limit/Page:** `{PAGE_SIZE}`"
    )

    await event.eor(
        text,
        time=7,
    )


# ============================================================================
# CLEAR ALL
# ============================================================================


@heartless_cmd(
    pattern=r"clearstored$"
)
async def clearstored(event):
    """
    Delete all FileStore entries and physical log messages.
    """

    names = _get_store_names()

    if not names:
        return await event.eor(
            "`FileStore is already empty.`",
            time=5,
        )

    status = await event.eor(
        f"`Deleting {len(names)} stored item(s)...`",
        time=5,
    )

    deleted = 0
    failed = 0

    for name in names:

        msg_id = get_stored_msg(
            name
        )

        removed, msg_id = await _remove_stored(
            name
        )

        if not removed:
            failed += 1
            continue

        deleted += 1

        await _delete_log_message(
            msg_id
        )

        # Avoid hammering Telegram on very large stores.
        await asyncio.sleep(0)

    await status.eor(
        f"`FileStore cleanup finished.`\n\n"
        f"`Deleted:` {deleted}\n"
        f"`Failed:` {failed}",
        time=7,
    )


# ============================================================================
# INLINE FILESTORE
# ============================================================================


@in_pattern(
    "fs",
    owner=True,
)
async def file_short(event):
    """
    Inline FileStore browser.

    Supported:

        @assistant fs
        @assistant fs filename
        @assistant fs keyword
    """

    # Remove command itself.
    query = (
        getattr(event, "text", "")
        or ""
    ).strip()

    if query.lower().startswith("fs"):
        query = query[2:].strip()

    query = query[:MAX_SEARCH_LENGTH]

    names = _get_cached_names()

    if query:
        needle = query.casefold()

        names = [
            name
            for name in names
            if needle in str(name).casefold()
        ]

    meta = _get_meta()

    names = _sort_names(
        names,
        meta,
    )

    if not names:

        title = (
            "No stored files"
            if query
            else "FileStore is empty"
        )

        description = (
            f"No files matched: {query}"
            if query
            else "No files have been stored yet."
        )

        result = await event.builder.article(
            title=title,
            description=description,
            text=(
                "**FileStore**\n\n"
                + description
                + f"\n\nUse `{HNDLR}store <name>` "
                  "as a reply to store a file."
            ),
        )

        return await event.answer(
            [result],
            cache_time=0,
        )

    results, page, pages = await _build_inline_results(
        event,
        names,
        page=0,
    )

    if not results:
        result = await event.builder.article(
            title="No valid stored files",
            description="Stored messages may have been deleted.",
            text=(
                "**FileStore**\n\n"
                "No valid stored Telegram messages were found."
            ),
        )

        return await event.answer(
            [result],
            cache_time=0,
        )

    # ------------------------------------------------------------------------
    # Add a management/info result at the beginning.
    # ------------------------------------------------------------------------

    search_text = (
        f"\n\nSearch: `{query}`"
        if query
        else ""
    )

    management = await event.builder.article(
        title="FileStore",
        description=(
            f"{len(names)} matching file(s) • "
            f"Page {page + 1}/{pages}"
        ),
        text=(
            "**FileStore**\n\n"
            f"**Files:** `{len(names)}`"
            f"{search_text}\n\n"
            "Select a file below to send it."
        ),
        buttons=_page_buttons(
            page,
            pages,
        ),
    )

    results.insert(
        0,
        management,
    )

    await event.answer(
        results[:MAX_INLINE_RESULTS],
        cache_time=0,
    )


# ============================================================================
# INLINE PAGINATION
# ============================================================================


@callback(
    re.compile(r"fs_page:(\d+)$"),
    owner=True,
)
async def fileshare_page(event):
    """
    Inline pagination callback.

    Note:
    Telegram callback data does not carry the original query itself, so the
    page button is intentionally designed for the currently displayed
    FileStore browser. Telegram re-runs the inline query context internally.
    """

    try:
        page = int(
            event.data_match.group(1)
        )
    except Exception:
        return await event.answer(
            "Invalid page.",
            alert=True,
        )

    # For callback-based inline results, edit the current result using the
    # current FileStore state.
    names = _sort_names(
        _get_store_names()
    )

    if not names:
        return await event.edit(
            "**FileStore**\n\n"
            "No stored files are available."
        )

    # This callback is mainly useful for messages generated by the browser.
    # Reconstruct a compact management page.
    page_items, page, pages = _paginate(
        names,
        page,
    )

    lines = [
        "**FileStore**",
        "",
        f"Page `{page + 1}/{pages}`",
        "",
    ]

    for index, name in enumerate(
        page_items,
        start=page * PAGE_SIZE + 1,
    ):
        link = _share_link(name)

        if link:
            lines.append(
                f"`{index}`. [{_display_name(name)}]({link})"
            )
        else:
            lines.append(
                f"`{index}`. `{name}`"
            )

    await event.edit(
        "\n".join(lines),
        buttons=_page_buttons(
            page,
            pages,
        ),
        link_preview=False,
    )


@callback(
    re.compile(r"fs_refresh:(\d+)$"),
    owner=True,
)
async def fileshare_refresh(event):
    """
    Refresh FileStore inline management page.
    """

    _invalidate_cache()

    try:
        page = int(
            event.data_match.group(1)
        )
    except Exception:
        page = 0

    names = _sort_names(
        _get_store_names()
    )

    if not names:
        return await event.edit(
            "**FileStore**\n\n"
            "No stored files are available."
        )

    page_items, page, pages = _paginate(
        names,
        page,
    )

    lines = [
        "**FileStore**",
        "",
        f"Page `{page + 1}/{pages}`",
        "",
    ]

    for index, name in enumerate(
        page_items,
        start=page * PAGE_SIZE + 1,
    ):
        link = _share_link(name)

        if link:
            lines.append(
                f"`{index}`. [{_display_name(name)}]({link})"
            )
        else:
            lines.append(
                f"`{index}`. `{name}`"
            )

    await event.edit(
        "\n".join(lines),
        buttons=_page_buttons(
            page,
            pages,
        ),
        link_preview=False,
    )


# ============================================================================
# INLINE STATS
# ============================================================================


@callback(
    "fs_stats",
    owner=True,
)
async def fileshare_inline_stats(event):
    """
    Inline statistics.
    """

    names = _get_store_names()
    meta = _get_meta()

    media = 0
    text = 0
    total_size = 0

    for name in names:

        info = meta.get(
            name,
            {},
        )

        if not isinstance(info, dict):
            continue

        if info.get("kind") == "media":
            media += 1

        elif info.get("kind") == "text":
            text += 1

        size = info.get("size")

        if isinstance(size, (int, float)):
            total_size += int(size)

    await event.edit(
        "**FileStore Statistics**\n\n"
        f"• **Total:** `{len(names)}`\n"
        f"• **Media:** `{media}`\n"
        f"• **Text:** `{text}`\n"
        f"• **Known Size:** `{_format_size(total_size)}`",
        buttons=[
            [
                Button.inline(
                    "‹ Back",
                    data="fs_refresh:0",
                )
            ]
        ],
    )


# ============================================================================
# OPTIONAL INLINE MANAGEMENT COMMANDS
# ============================================================================


@in_pattern(
    "filestore",
    owner=True,
)
async def filestore_inline_alias(event):
    """
    Alias:

        @assistant filestore
        @assistant filestore keyword

    This intentionally uses the same renderer as `fs`.
    """

    query = (
        getattr(event, "text", "")
        or ""
    ).strip()

    if query.lower().startswith(
        "filestore"
    ):
        query = query[
            len("filestore"):
        ].strip()

    names = _get_cached_names()

    if query:
        needle = query.casefold()

        names = [
            name
            for name in names
            if needle in str(name).casefold()
        ]

    names = _sort_names(
        names,
        _get_meta(),
    )

    if not names:

        result = await event.builder.article(
            title="No stored files",
            description="No matching FileStore item was found.",
            text=(
                "**FileStore**\n\n"
                "No matching stored file was found."
            ),
        )

        return await event.answer(
            [result],
            cache_time=0,
        )

    results, page, pages = await _build_inline_results(
        event,
        names,
        0,
    )

    management = await event.builder.article(
        title="FileStore",
        description=f"{len(names)} file(s)",
        text=(
            "**FileStore**\n\n"
            f"Available: `{len(names)}`"
        ),
        buttons=_page_buttons(
            page,
            pages,
        ),
    )

    results.insert(
        0,
        management,
    )

    await event.answer(
        results[:MAX_INLINE_RESULTS],
        cache_time=0,
)

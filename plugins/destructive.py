"""
✘ Commands Available -

• Auto (no command)
   Saves view-once / TTL media received in PMs to Saved Messages.
"""

import os

from telethon import events

from . import *


@heartless_bot.on(events.NewMessage(incoming=True))
async def destructive(e):
    """Save view-once / TTL media from PMs to Saved Messages.

    Only photo/document media expose ``ttl_seconds``. WebPage previews and
    other media types must be ignored — accessing the attribute raises.
    """
    if not e.is_private or not e.media:
        return
    ttl = getattr(e.media, "ttl_seconds", None)
    if ttl is None:
        return
    try:
        download = await e.client.download_media(e.media, "resources/")
        if not download:
            return
        await e.client.send_message(
            "me", "✨ T.me/DarkPentester", file=download
        )
        os.remove(download)
    except Exception as ex:
        log_chat = udB.get_key("PMLOGGROUP")
        if log_chat:
            try:
                await e.client.send_message(int(log_chat), f"Error:\n\n{ex}")
            except Exception:
                LOGS.debug("destructive log failed", exc_info=True)
        else:
            LOGS.debug("destructive save failed: %s", ex)

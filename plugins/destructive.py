import asyncio
import os

from telethon import events
from telethon.errors import FloodWaitError
from telethon.tl import functions
from telethon.tl.types import MessageMediaPhoto

from . import *

@heartless_bot.on(events.NewMessage(incoming=True))
async def destructive(e):
    if not e.is_private:
        return
    if e.media and not hasattr(e.media, "value") and e.media.ttl_seconds is not None:
        try:
            download = await e.client.download_media(e.media, "resources/")
            await e.client.send_message("me", "✨ T.me/DarkPentester", file=download)
            os.remove(download)
        except Exception as ex:
            await e.client.send_message(
                int(udB.get_key("PMLOGGROUP")), f"Error:\n\n{ex}"
            )

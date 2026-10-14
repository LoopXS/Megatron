import asyncio
import re
import time

from telethon import functions
from telethon.errors import YouBlockedUserError

from . import eod, eor, get_pstring, heartless_bot, heartless_cmd, LOGS

ext = re.compile(r'https?://[^\s]+')

@heartless_cmd(pattern="link")
async def f2l(event):
    xx = await event.edit(get_pstring("{p} **Please Wait...**", "load"))
    r = await event.get_reply_message()
    async with heartless_bot.conversation("@GrayFile2LinkBot", timeout=20) as conv:
        try:
            await conv.send_file(r.media)
        except YouBlockedUserError:
            LOGS.info("Unblocking Bot...")
            await heartless_bot(functions.contacts.UnblockRequest("GrayFile2LinkBot"))
            await conv.send_file(r.media)
        links = []
        msg = await conv.get_response()
        await heartless_bot.send_read_acknowledge(conv.chat_id)
        first_link = ext.search(msg.raw_text or "")
        if not first_link:
            await xx.edit("❌ No direct link found.")
            return
        links.append(first_link.group(0))
        reply_text = f"**[✨ Direct Link]**({links[0]})\n✨ T.me/DarkPentester"
        await xx.edit(reply_text)
        # Prefer monotonic clock — avoids asyncio.get_event_loop() on Python 3.14.
        end_time = time.monotonic() + 60
        while time.monotonic() < end_time and len(links) < 3:
            try:
                msg = await asyncio.wait_for(
                    conv.get_response(),
                    timeout=max(0.1, end_time - time.monotonic()),
                )
            except asyncio.TimeoutError:
                break
            await heartless_bot.send_read_acknowledge(conv.chat_id)
            found = ext.search(msg.raw_text or "")
            if found and found.group(0) not in links:
                links.append(found.group(0))
                txt = f"**[✨ Direct Link]**({links[0]})"
                if len(links) >= 2:
                    txt += f"\n**[✨ Nim-Baha-1]**({links[1]})"
                if len(links) >= 3:
                    txt += f"\n**[✨ Nim-Baha-2]**({links[2]})"
                txt += "\n✨ T.me/DarkPentester"
                await xx.edit(txt)

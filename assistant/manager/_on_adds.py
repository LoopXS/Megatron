from . import *
from telethon import events


@asst.on(events.ChatAction(func= lambda x: x.user_added))
async def dueha(e):
    user = await e.get_user()
    if not user.is_self:
        return
    sm = udB.get("ON_MNGR_ADD")
    if sm == "OFF":
        return
    if not sm:
        sm = "Thanks For Adding Me :)"
    await e.reply(sm, link_preview=False)

import time
from datetime import datetime
from pytz import timezone as tz

from cython.dB.asst_fns import *
from cython.dB.sudos import is_fullsudo
from cython.functions.helper import inline_mention
from cython.misc import owner_and_sudos

from telethon import Button, events
from telethon.utils import get_display_name

from strings.strings import get_string
from assistant.manager._help import *
from . import *


_settings = [
    [
        Button.inline("API Kᴇʏs", data="apiset"),
        Button.inline("Pᴍ Bᴏᴛ", data="chatbot"),
    ],
    [
        Button.inline("Aʟɪᴠᴇ", data="alvcstm"),
        Button.inline("PᴍPᴇʀᴍɪᴛ", data="ppmset"),
    ],
    [Button.inline("Fᴇᴀᴛᴜʀᴇs", data="otvars")],
    [Button.inline("VC Sᴏɴɢ Bᴏᴛ", data="vcb")],
    [Button.inline("« Bᴀᴄᴋ", data="mainmenu")],
]

_start = [
    [
        Button.inline("Lᴀɴɢᴜᴀɢᴇ 🌐", data="lang"),
        Button.inline("Sᴇᴛᴛɪɴɢs ⚙️", data="setter"),
    ],
    [
        Button.inline("Sᴛᴀᴛs ✨", data="stat"),
        Button.inline("Bʀᴏᴀᴅᴄᴀsᴛ 📻", data="bcast"),
    ],
    [Button.inline("TɪᴍᴇZᴏɴᴇ 🌎", data="tz")],
]

@asst_cmd(pattern="start ?(.*)", forwards=False, func=lambda x: not x.is_group)
async def ultroid(event):
    if not is_added(event.sender_id) and str(event.sender_id) not in owner_and_sudos():
        add_user(event.sender_id)
        kak_uiw = udB.get("OFF_START_LOG")
        if not kak_uiw or kak_uiw != "True":
            msg = f"{inline_mention(event.sender)} `[{event.sender_id}]` Started Your [Assistant Bot](@{asst.me.username})."
            buttons = [[Button.inline("Info", "itkkstyo")]]
            if event.sender.username:
                buttons[0].append(Button.url("User", "t.me/" + event.sender.username))
            await event.client.send_message(
                int(udB["OWNER_ID"]), msg, buttons=buttons
            )
    if not is_fullsudo(event.sender_id): 
        ok = ""
        u = await event.client.get_entity(event.chat_id)
        if not udB.get("STARTMSG"):
            if udB.get("PMBOT") == "True":
                ok = "✵✵✵✵✵✵✵✵✵✵✵✵✵✵✵✵"
            await event.reply(
                f"Ⲏⲉⲩ [{get_display_name(u)}](tg://user?id={u.id}), Ⲓ'ⲙ Ⲁⲋⲋⲓⲋⲧⲁⲛⲧ ⲟϝ {ultroid_bot.me.first_name}!\n\n",
                file=udB.get("STARTMEDIA"),
                buttons=[
                    [
                        Button.inline("✘ ᴄʜᴀᴛ ᴡɪᴛʜ ʜᴇᴀʀᴛʟᴇꜱꜱ ✘", data="chat"),
                    ],
                    [
                        Button.inline("✘ ɢʀᴏᴜᴘ/ᴄʜᴀɴɴᴇʟ ᴍᴀɴᴀɢᴇʀ ʜᴇʟᴘ ✘", data="group"),
                    ],
                    [
                        Button.inline("✘ ꜱᴇʀᴠᴇʀ ᴘɪɴɢ ✘", data="ping"),
                    ],
                    [
                        Button.inline("✘ ᴛᴇxᴛ ᴛʀᴀɴꜱʟᴀᴛᴏʀ ✘", data="tlans"),
                    ],
                ],
            )
        else:
            me = f"[{ultroid_bot.me.first_name}](tg://user?id={ultroid_bot.uid})"
            mention = f"[{get_display_name(u)}](tg://user?id={u.id})"
            await event.reply(
                udB.get("STARTMSG").format(me=me, mention=mention),
                file=udB.get("STARTMEDIA"),
                buttons=[
                    [
                        Button.inline("✘ ᴄʜᴀᴛ ᴡɪᴛʜ ʜᴇᴀʀᴛʟᴇꜱꜱ ✘", data="chat"),
                    ],
                    [
                        Button.inline("✘ ɢʀᴏᴜᴘ/ᴄʜᴀɴɴᴇʟ ᴍᴀɴᴀɢᴇʀ ʜᴇʟᴘ ✘", data="group"),
                    ],
                    [
                        Button.inline("✘ ꜱᴇʀᴠᴇʀ ᴘɪɴɢ ✘", data="ping"),
                    ],
                    [
                        Button.inline("✘ ᴛᴇxᴛ ᴛʀᴀɴꜱʟᴀᴛᴏʀ ✘", data="tlans"),
                    ],
                ],
            )
    else:
        name = get_display_name(event.sender_id)
        if event.pattern_match.group(1) == "set":
            await event.reply(
                "Choose from the below options -",
                buttons=_settings,
            )
        else:
            await event.reply(
                get_string("ast_3").format(name),
                buttons=_start,
            )
            
                
@callback("itkkstyo", owner=True)
async def ekekdhdb(e):
    text = f"When New Visitor will visit your Assistant Bot. You will get this log message!\n\nTo Disable : {HNDLR}setredis OFF_START_LOG True"
    await e.answer(text, alert=True)
    
    
@callback("tlans")
async def tlans(event):
    await event.delete()
    await asst.send_message(event.chat_id, "✨ How to use:\n✘ `/tr LangaugeCode text` \n✘ `/tr Language Code` as reply to a message \n\nHere is the list of [Language Codes](https://telegra.ph/𝒉𝒆𝒂𝒓𝒕𝒍𝒆𝒔𝒔-06-19)", link_preview=False)

    
    
@callback("chat")
async def chat(event):
    await event.delete()
    await asst.send_message(event.chat_id, "Send your message please. I'll see and answer you whenever get online\n\n✨ CɪᴘʜᴇʀX Ⲉⲭⲥⳑυⲋⲓⳳⲉ Ⲃⲟⲧ✨")


@callback("ping")
async def _(event):
    await event.delete()
    start = time.time()
    x = await event.respond("𝙿𝙸𝙽𝙶")
    end = round((time.time() - start) * 1000)
    uptime = time_formatter((time.time() - start_time) * 1000)
    await x.edit(get_string("ping").format(end, uptime))

    
@callback("group")
async def users(event):
    await event.delete()
    #grabon = "🎆 Here Are Some Commands for group/channel management\n➤ /start ~ Check if I'm Alive \n➤ /ping ~ Ping CɪᴘʜᴇʀX Server Response Time\n➤ /tr <lang-code>\n➤ /id ~ Shows ID of User/Media/Chat\n➤ /ban ~ Works in Group , Bans a User \n➤ /unban ~ Works in Group , Unbans a User\n➤ /promote ~ Promotes A User \n➤ /demote ~ Demotes A User \n➤ /gpin ~ Pins a Message\n(c)✨ CɪᴘʜᴇʀX Ⲃⲟⲧ Ⲉⲭⲥⳑυⲋⲓⳳⲉ ✨"
    await asst.send_message(event.chat_id, START, buttons=get_buttons())


@callback("mainmenu", owner=True, func=lambda x: not x.is_group)
async def ultroid(event):
    await event.edit(
        get_string("ast_3").format(OWNER_NAME),
        buttons=_start,
    )

    
@callback("stat", owner=True)
async def botstat(event):
    ok = len(get_all_users())
    msg = """Assistant - Stats
Total Users - {}""".format(
        ok,
    )
    await event.answer(msg, cache_time=0, alert=True)


@callback("bcast", owner=True)
async def bdcast(event):
    ok = get_all_users()
    await event.edit(f"• Broadcast to {len(ok)} users.")
    async with event.client.conversation(OWNER_ID) as conv:
        await conv.send_message(
            "Enter your broadcast message.\nUse /cancel to stop the broadcast.",
        )
        response = await conv.get_response()
        if response.message == "/cancel":
            return await conv.send_message("Cancelled!!")
        success = 0
        fail = 0
        await conv.send_message(f"Starting a broadcast to {len(ok)} users...")
        start = datetime.now()
        for i in ok:
            try:
                await asst.send_message(int(i), response.message)
                success += 1
            except BaseException:
                fail += 1
        end = datetime.now()
        time_taken = (end - start).seconds
        await conv.send_message(
            f"""
**Broadcast completed in {time_taken} seconds.**
Total Users in Bot - {len(ok)}
**Sent to** : `{success} users.`
**Failed for** : `{fail} user(s).`""",
        )


@callback("setter", owner=True)
async def setting(event):
    await event.edit(
        "Choose from the below options -",
        buttons=_settings,
    )


@callback("tz", owner=True)
async def timezone_(event):
    await event.delete()
    pru = event.sender_id
    var = "TIMEZONE"
    name = "Timezone"
    async with event.client.conversation(pru) as conv:
        await conv.send_message(
            "Send Your TimeZone From This List [Check From Here](http://www.timezoneconverter.com/cgi-bin/findzone.tzc)"
        )
        response = conv.wait_event(events.NewMessage(chats=pru))
        response = await response
        themssg = response.message.message
        if themssg == "/cancel":
            return await conv.send_message(
                "Cancelled!!",
                buttons=get_back_button("mainmenu"),
            )
        try:
            tz(themssg)
            await setit(event, var, themssg)
            await conv.send_message(
                f"{name} changed to {themssg}\n",
                buttons=get_back_button("mainmenu"),
            )
        except BaseException:
            await conv.send_message(
                "Wrong TimeZone, Try again",
                buttons=get_back_button("mainmenu"),
            )

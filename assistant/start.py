from datetime import datetime

try:
    from pytz import timezone as tz
except ImportError:
    tz = None
from telethon import Button, events
from telethon.errors.rpcerrorlist import MessageDeleteForbiddenError
from telethon.utils import get_display_name

from assistant.manager._help import *
from CythonX._misc import SUDO_M, owner_and_sudos
from CythonX.dB.base import KeyManager
from CythonX.fns.helper import inline_mention
from strings import get_string

from . import *

Owner_info_msg = udB.get_key("BOT_INFO_START")
custom_info = True
if Owner_info_msg is None:
    custom_info = False
    Owner_info_msg = f"""
**Owner** - {OWNER_NAME}
**OwnerID** - `{OWNER_ID}`

**Message Forwards** - {udB.get_key("PMBOT")}

**UserBot v{heartless_version}, Powered By @DarkPentester**
"""


_settings = [
    [
        Button.inline("API Kᴇʏs", data="cbs_apiset"),
        Button.inline("Pᴍ Bᴏᴛ", data="cbs_chatbot"),
    ],
    [
        Button.inline("Aʟɪᴠᴇ", data="cbs_alvcstm"),
        Button.inline("PᴍPᴇʀᴍɪᴛ", data="cbs_ppmset"),
    ],
    [
        Button.inline("Fᴇᴀᴛᴜʀᴇs", data="cbs_otvars"),
        Button.inline("VC Sᴏɴɢ Bᴏᴛ", data="cbs_vcb"),
    ],
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


@callback("closeit")
async def closet(lol):
    try:
        await lol.delete()
    except MessageDeleteForbiddenError:
        await lol.answer("MESSAGE_TOO_OLD", alert=True)


@asst_cmd(pattern="start( (.*)|$)", forwards=False, func=lambda x: not x.is_group)
async def heartless(event):
    args = event.pattern_match.group(1).strip()
    keym = KeyManager("BOT_USERS", cast=list)
    if not keym.contains(event.sender_id) and event.sender_id not in owner_and_sudos():
        keym.add(event.sender_id)
        kak_uiw = udB.get_key("OFF_START_LOG")
        if not kak_uiw or kak_uiw != True:
            msg = f"{inline_mention(event.sender)} `[{event.sender_id}]` started your [Assistant bot](@{asst.me.username})."
            buttons = [[Button.inline("Info", "itkkstyo")]]
            if event.sender.username:
                buttons[0].append(
                    Button.mention(
                        "User", await event.client.get_input_entity(event.sender_id)
                    )
                )
            await event.client.send_message(
                udB.get_key("LOG_CHANNEL"), msg, buttons=buttons
            )
    if event.sender_id not in SUDO_M.fullsudos:
        me = inline_mention(heartless_bot.me)
        mention = inline_mention(event.sender)
        if args and args != "set":
            await get_stored_file(event, args)
        if not udB.get_key("STARTMSG"):
            if udB.get_key("PMBOT"):
                pass
            await event.reply(
                f"Ⲏⲉⲩ {mention}, Ⲓ'ⲙ Ⲁⲋⲋⲓⲋⲧⲁⲛⲧ ⲟϝ {heartless_bot.me.first_name}!",
                file=udB.get_key("STARTMEDIA"),
                buttons=[
                    [
                        Button.inline("✗ ᴄʜᴀᴛ ᴡɪᴛʜ ʜᴇᴀʀᴛʟᴇꜱꜱ ✗", data="chat"),
                    ],
                    [
                        Button.inline("✗ ɢʀᴏᴜᴘ/ᴄʜᴀɴɴᴇʟ ᴍᴀɴᴀɢᴇʀ ʜᴇʟᴘ ✗", data="group"),
                    ],
                    [
                        Button.inline("✗ ꜱᴇʀᴠᴇʀ ᴘɪɴɢ ✗", data="ping"),
                    ],
                    [
                        Button.inline("✗ ᴛᴇxᴛ ᴛʀᴀɴꜱʟᴀᴛᴏʀ ✗", data="tlans"),
                    ],
                ],
            )
        else:
            await event.reply(
                udB.get_key("STARTMSG").format(me=me, mention=mention),
                file=udB.get_key("STARTMEDIA"),
                buttons=(
                    [
                        [
                            Button.inline("✗ ᴄʜᴀᴛ ᴡɪᴛʜ ʜᴇᴀʀᴛʟᴇꜱꜱ ✗", data="chat"),
                        ],
                        [
                            Button.inline(
                                "✗ ɢʀᴏᴜᴘ/ᴄʜᴀɴɴᴇʟ ᴍᴀɴᴀɢᴇʀ ʜᴇʟᴘ ✗", data="group"
                            ),
                        ],
                        [
                            Button.inline("✗ ꜱᴇʀᴠᴇʀ ᴘɪɴɢ ✗", data="ping"),
                        ],
                        [
                            Button.inline("✗ ᴛᴇxᴛ ᴛʀᴀɴꜱʟᴀᴛᴏʀ ✗", data="tlans"),
                        ],
                    ]
                    if Owner_info_msg
                    else None
                ),
            )
    else:
        name = get_display_name(event.sender)
        if args == "set":
            await event.reply(
                "Choose from the below options -",
                buttons=_settings,
            )
        elif args:
            await get_stored_file(event, args)
        else:
            await event.reply(
                get_string("ast_3").format(name),
                buttons=_start,
            )


@callback("itkkstyo", owner=True)
async def ekekdhdb(e):
    text = f"When New Visitor will visit your Assistant Bot. You will get this log message!\n\nTo Disable : {HNDLR}setdb OFF_START_LOG True"
    await e.answer(text, alert=True)


@callback("tlans")
async def tlans(event):
    await event.delete()
    await asst.send_message(
        event.chat_id,
        "✨ How to use:\n1⃣ `/tr LangaugeCode text` \n2⃣ `/tr Language Code` as reply to a message \n\nHere is the list of [Language Codes](https://telegra.ph/𝒉𝒆𝒂𝒓𝒕𝒍𝒆𝒔𝒔-06-19)",
        link_preview=False,
    )


@callback("chat")
async def chat(event):
    await event.delete()
    await asst.send_message(
        event.chat_id,
        "Send your message please. I'll see and answer you whenever get online\n\n✨ Ⲏⲉⲁʀⲧⳑⲉⲋⲋ Ⲉⲭⲥⳑυⲋⲓⳳⲉ Ⲃⲟⲧ ✨",
    )


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
    # grabon = "🎆 Here Are Some Commands for group/channel management\n➤ /start ~ Check if I'm Alive \n➤ /ping ~ Ping Server Response Time\n➤ /tr <lang-code>\n➤ /id ~ Shows ID of User/Media/Chat\n➤ /ban ~ Works in Group , Bans a User \n➤ /unban ~ Works in Group , Unbans a User\n➤ /promote ~ Promotes A User \n➤ /demote ~ Demotes A User \n➤ /gpin ~ Pins a Message"
    await asst.send_message(event.chat_id, START, buttons=get_buttons())


@callback("mainmenu", owner=True, func=lambda x: not x.is_group)
async def heartless(event):
    await event.edit(
        get_string("ast_3").format(OWNER_NAME),
        buttons=_start,
    )


@callback("stat", owner=True)
async def botstat(event):
    ok = len(udB.get_key("BOT_USERS") or [])
    msg = """Assistant - Stats
Total Users - {}""".format(
        ok,
    )
    await event.answer(msg, cache_time=0, alert=True)


@callback("bcast", owner=True)
async def bdcast(event):
    keym = KeyManager("BOT_USERS", cast=list)
    total = keym.count()
    await event.edit(f"• Broadcast to {total} users.")
    async with event.client.conversation(OWNER_ID) as conv:
        await conv.send_message(
            "Enter your broadcast message.\nUse /cancel to stop the broadcast.",
        )
        response = await conv.get_response()
        if response.message == "/cancel":
            return await conv.send_message("Cancelled!!")
        success = 0
        fail = 0
        await conv.send_message(f"Starting a broadcast to {total} users...")
        start = datetime.now()
        for i in keym.get():
            try:
                await asst.send_message(int(i), response)
                success += 1
            except BaseException:
                fail += 1
        end = datetime.now()
        time_taken = (end - start).seconds
        await conv.send_message(
            f"""
**Broadcast completed in {time_taken} seconds.**
Total Users in Bot - {total}
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
    if tz is None:
        return await event.client.send_message(
            event.sender_id,
            f"`pytz` is not installed, TimeZone feature is unavailable.\n\nInstall it via `{HNDLR}update` or `{HNDLR}bash pip install pytz`.",
        )
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

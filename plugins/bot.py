"""
✘ Commands Available

• `{i}alive` | `{i}ialive`
    Check if bot is working.

• `{i}ping`
    Check server response time.

• `{i}cmds`
    View all plugin names.

• `{i}restart`
    To restart your bot.

• `{i}logs (sys)`
    Get the full terminal logs.

• `{i}logs carbon`
    Get the carbonized sys logs.

• `{i}logs heroku`
   Get the latest 100 lines of heroku logs.

• `{i}shutdown`
    Turn off your bot.
"""
import os
import sys
import time
from platform import python_version as pyver
from random import choice

from git import Repo
from cython.version import __version__ as UltVer
from telethon import __version__
from telethon.errors.rpcerrorlist import ChatSendMediaForbiddenError
from telethon.utils import resolve_bot_file_id

try:
    from carbonnow import Carbon
except ImportError:
    Carbon = None

from . import (
    ATRA_COL,
    LOGS,
    OWNER_NAME,
    Button,
    Telegraph,
    Var,
    allcmds,
    asst,
    bash,
    call_back,
    callback,
    def_logs,
    eor,
    eod, 
    get_string,
    heroku_logs,
    in_pattern,
    restart,
    shutdown,
    start_time,
    time_formatter,
    udB,
    ultroid_cmd,
    ultroid_version,
)

# Will move to strings
alive_txt = """
**ɦᥱᥲrᴛᥣᥱss ᥱ᥊ᥴᥣᥙsi᥎ᥱ ᥙsᥱrδ᧐ᴛ**
✵✵✵✵✵✵✵✵✵✵✵✵✵✵✵✵✵✵✵✵
╔════❰ Ⲃⲟⲧ Ⲓⲛϝⲟʀⲙⲁⲧⲓⲟⲛ ❱═❍⊱❁۪۪۪
║╭━━━━━━━━━━━━━━━➣ 
║┣⪼ **Ⲃⲟⲧ Ⳳⲉʀⲋⲓⲟⲛ** - `{}`
║┣⪼ **Ⳑⲓⲃʀⲁʀⲩ Ⳳⲉʀⲋⲓⲟⲛ** - `{}`  
║┣⪼ **Ⲧⲉⳑⲉⲧⲏⲟⲛ** - `{}` 
║┣⪼ **✨ ⲏⲉⲁʀⲧⳑⲉⲋⲋ ⲓⲋ ⲧⲏⲉ ⲃⲉⲋⲧ ✨**
║╰━━━━━━━━━━━━━━━➣ ╚══════════════════❍⊱❁۪۪۪
"""


@callback("alive")
async def alive(event):
    text = alive_txt.format(ultroid_version, UltVer, __version__)
    await event.answer(text, alert=True)


@ultroid_cmd(
    pattern="alive$",
)
async def lol(ult):
    pic = udB.get("ALIVE_PIC")
    uptime = time_formatter((time.time() - start_time) * 1000)
    y = Repo().active_branch
    xx = Repo().remotes[0].config_reader.get("url")
    rep = xx.replace(".git", f"/tree/{y}")
    kk = f" `[{y}]({rep})` "
    als = (get_string("alive_1")).format(
        OWNER_NAME,
        ultroid_version,
        UltVer,
        uptime,
        pyver(),
        __version__,
        kk,
    )
    if pic is None:
        await eor(ult, als)
    elif "telegra" in pic:
        try:
            await ult.reply(als, file=pic, link_preview=False)
            await ult.delete()
        except ChatSendMediaForbiddenError:
            await eor(ult, als, link_preview=False)
    else:
        try:
            await ult.reply(file=pic)
            await ult.reply(als, link_preview=False)
            await ult.delete()
        except ChatSendMediaForbiddenError:
            await eor(ult, als, link_preview=False)


@ultroid_cmd(
    pattern="ialive$",
)
async def is_on(ult):
    if not ult.client._bot:
        await ult.delete()
        try:
            res = await ult.client.inline_query(asst.me.username, "alive")
            await res[0].click(ult.chat_id)
        except Exception as er:
            LOGS.info(er)
        return
    pic = udB.get("ALIVE_PIC")
    uptime = time_formatter((time.time() - start_time) * 1000)
    y = Repo().active_branch
    xx = Repo().remotes[0].config_reader.get("url")
    rep = xx.replace(".git", f"/tree/{y}")
    kk = f" `[{y}]({rep})` "
    als = (get_string("alive_1")).format(
        OWNER_NAME,
        ultroid_version,
        UltVer,
        uptime,
        pyver(),
        __version__,
        kk,
    )
    buttons = [
        [Button.inline(get_string("bot_2"), "alive")],
        [
            Button.url(get_string("bot_3"), "https://xhamsterlive.com"),
            Button.url(get_string("bot_4"), "t.me/FutureTechnologyOfficial"),
        ],
    ]
    await ult.client.send_message(
        ult.chat_id, als, file=pic, buttons=buttons, link_preview=False
    )


@ultroid_cmd(pattern="ping$", chats=[], type=["official", "assistant", "manager"])
async def _(event):
    if event.out:
        await event.delete()
    start = time.time()
    x = await event.respond("𝙿𝙸𝙽𝙶")
    end = round((time.time() - start) * 1000)
    uptime = time_formatter((time.time() - start_time) * 1000)
    await x.edit(get_string("ping").format(end, uptime))


@ultroid_cmd(
    pattern="cmds$",
)
async def cmds(event):
    await allcmds(event, Telegraph)


heroku_api = Var.HEROKU_API


@ultroid_cmd(
    pattern="restart$",
    fullsudo=True,
)
async def restartbt(ult):
    ok = await eod(ult, get_string("bot_5"), time=5)
    call_back()
    if heroku_api:
        return await restart(ok)
    await bash("git pull && pip3 install -r requirements.txt")
    os.execl(sys.executable, sys.executable, "-m", "cython")


@ultroid_cmd(
    pattern="shutdown$",
    fullsudo=True,
)
async def shutdownbot(ult):
    await shutdown(ult)


@ultroid_cmd(
    pattern="logs ?(.*)",
    chats=[],
)
async def _(event):
    opt = event.pattern_match.group(1)
    if opt == "heroku":
        await heroku_logs(event)
    elif opt == "carbon" and Carbon:
        event = await eor(event, get_string("com_1"))
        code = open("heartless.log", "r").read()[-2500:]
        file = await Carbon(
            base_url="https://carbonara.vercel.app/api/cook",
            code=code,
            background=choice(ATRA_COL),
        ).memorize("heartless-logs")
        await event.reply("**~ Logs**", file=file)
    else:
        await def_logs(event)
    await event.delete()


@in_pattern("alive", owner=True)
async def inline_alive(ult):
    pic = udB.get("ALIVE_PIC")
    uptime = time_formatter((time.time() - start_time) * 1000)
    y = Repo().active_branch
    xx = Repo().remotes[0].config_reader.get("url")
    rep = xx.replace(".git", f"/tree/{y}")
    kk = f" `[{y}]({rep})` "
    als = (get_string("alive_1")).format(
        OWNER_NAME,
        ultroid_version,
        UltVer,
        uptime,
        pyver(),
        __version__,
        kk,
    )
    buttons = [
        [
            Button.url(get_string("bot_3"), "https://xhamsterlive.com"),
            Button.url(get_string("bot_4"), "t.me/DarkPentesterX"),
        ]
    ]
    builder = ult.builder
    if pic:
        try:
            if ".jpg" in pic:
                results = [await builder.photo(pic, text=als, buttons=buttons)]
            else:
                _pic = resolve_bot_file_id(pic)
                if _pic:
                    pic = _pic
                    buttons.insert(
                        0, [Button.inline(get_string("bot_2"), data="alive")]
                    )
                results = [
                    await builder.document(
                        pic,
                        title="Inline Alive",
                        description="(c) CɪᴘʜᴇʀX Ⲉⲭⲥⳑυⲋⲓⳳⲉ Ⲃⲟⲧ",
                        buttons=buttons,
                    )
                ]
            return await ult.answer(results)
        except BaseException as er:
            LOGS.info(er)
    result = [
        await builder.article("Alive", text=als, link_preview=False, buttons=buttons)
    ]
    await ult.answer(result)

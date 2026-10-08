import inspect
import re
from traceback import format_exc

from telethon import Button
from telethon.errors import QueryIdInvalidError
from telethon.events import CallbackQuery, InlineQuery, NewMessage
from telethon.tl.types import InputWebDocument, User, Channel

from .. import LOGS, asst, udB, heartless_bot
from ..fns.admins import admin_check
from . import append_or_update, owner_and_sudos

OWNER = heartless_bot.full_name

MSG = f"ᥴᥣiᥴκ ᴛɦᥱ δᥙᴛᴛ᧐ᥒ δᥱᥣ᧐ᥕ ᴛ᧐ ᥴ᧐ᥒᴛᥲᥴᴛ !"

IN_BTTS = [
    [
        Button.url(
            "✗ ᴅᴇᴠ ✗",
            url="T.me/DarkPentester",
        ),
    ]
]


# decorator for assistant


async def button_clicked(event):
    chat_id = event.chat_id
    chat = await event.client.get_entity(chat_id)
    if isinstance(chat, User):
        user_id = chat.id
        udB.set_key("CLICKED", user_id)
        return user_id
    elif isinstance(chat, Channel):
        chat_id = event.chat_id
        return chat_id
    else:
        user1_id = chat.participants[0].id
        user2_id = chat.participants[1].id
        return chat


def asst_cmd(pattern=None, load=None, owner=False, **kwargs):
    """Decorator for assistant's command"""
    name = inspect.stack()[1].filename.split("/")[-1].replace(".py", "")
    kwargs["forwards"] = False

    def ult(func):
        if pattern:
            kwargs["pattern"] = re.compile(f"^/{pattern}")

        async def handler(event):
            if owner and event.sender_id not in owner_and_sudos():
                return
            try:
                await func(event)
            except Exception as er:
                LOGS.exception(er)

        asst.add_event_handler(handler, NewMessage(**kwargs))
        if load is not None:
            append_or_update(load, func, name, kwargs)

    return ult


def callback(data=None, from_users=None, admins=False, owner=False, **kwargs):
    """Assistant's callback decorator"""
    if from_users is None:
        from_users = []
    if "me" in from_users:
        from_users.remove("me")
        from_users.append(heartless_bot.uid)

    def ultr(func):
        async def wrapper(event):
            if admins and not await admin_check(event):
                return
            if from_users and event.sender_id not in from_users:
                return await event.answer(f"This Is {OWNER} Bot!", alert=True)
            if owner and event.sender_id not in owner_and_sudos():
                return await event.answer(f"This Is {OWNER} Bot!")
            try:
                await func(event)
            except Exception as er:
                LOGS.exception(er)

        asst.add_event_handler(wrapper, CallbackQuery(data=data, **kwargs))

    return ultr


def in_pattern(pattern=None, owner=False, **kwargs):
    """Assistant's inline decorator."""

    def don(func):
        async def wrapper(event):
            if owner and event.sender_id not in owner_and_sudos():
                res = [
                    await event.builder.article(
                        title="𝒉𝒆𝒂𝒓𝒕𝒍𝒆𝒔𝒔",
                        # url="T.me/DarkPentester",
                        description="℘ he/she (or anything you like; I don't care)",
                        text=MSG,
                        thumb=InputWebDocument(
                            "https://graph.org/file/5eee0c3b21849601906ea.mp4",
                            0,
                            "video/mp4",
                            [],
                        ),
                        buttons=IN_BTTS,
                    )
                ]
                return await event.answer(
                    res,
                    switch_pm=f"👨🏻‍💻: 𝒂𝒔𝒔𝒊𝒔𝒕𝒂𝒏𝒕 𝒐𝒇 {OWNER}",
                    switch_pm_param="start",
                )
            try:
                await func(event)
            except QueryIdInvalidError:
                pass
            except Exception as er:
                err = format_exc()

                def error_text():
                    return f"**#ERROR #INLINE**\n\nQuery: `{asst.me.username} {pattern}`\n\n**Traceback:**\n`{format_exc()}`"

                LOGS.exception(er)
                try:
                    await event.answer(
                        [
                            await event.builder.article(
                                title="Unhandled Exception has Occured!",
                                text=error_text(),
                                buttons=Button.url("Report", "T.me/DarkPentesterBot"),
                            )
                        ]
                    )
                except QueryIdInvalidError:
                    LOGS.exception(err)
                except Exception as er:
                    LOGS.exception(er)
                    await asst.send_message(udB.get_key("LOG_CHANNEL"), error_text())

        asst.add_event_handler(wrapper, InlineQuery(pattern=pattern, **kwargs))

    return don

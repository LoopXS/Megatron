from telethon import Button, custom

from CythonX import *
from CythonX import _ult_cache
from CythonX._misc import owner_and_sudos
from CythonX._misc._assistant import asst_cmd, callback, in_pattern
from CythonX.fns.helper import *
from CythonX.fns.tools import get_stored_file
from plugins import ATRA_COL, InlinePlugin
from strings import get_languages, get_string

OWNER_NAME = heartless_bot.full_name
OWNER_ID = heartless_bot.uid

AST_PLUGINS = {}


async def setit(event, name, value):
    try:
        udB.set_key(name, value)
    except BaseException as er:
        LOGS.exception(er)
        return await event.edit("`Something Went Wrong`")


def get_back_button(name):
    return [Button.inline("« Bᴀᴄᴋ", data=f"{name}")]


async def deliver_inline_apk(event, file_obj, caption, buttons=None):
    """
    Put an APK into the chat where the inline Download button was pressed.

    For inline messages the bot never gets a normal chat id for send_file
    (that is why files were landing in the assistant PM). Editing the
    inline message with the document updates it in-place in that chat.
    """
    if isinstance(file_obj, tuple):
        file_obj = file_obj[0]

    try:
        return await event.edit(
            caption,
            file=file_obj,
            buttons=buttons,
            force_document=True,
            link_preview=False,
        )
    except Exception as er:
        LOGS.exception("Inline APK edit failed: %s", er)
        raise RuntimeError(
            "Could not attach APK to this chat message. "
            f"Try sending the inline result again, then press Download. ({er})"
        ) from er

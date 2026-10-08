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

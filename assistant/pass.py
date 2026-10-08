import secrets
import string

from . import *


@asst_cmd(pattern="gen")
async def _(event):
    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for i in range(8))
    await event.client.send_message(event.chat_id, f"`{password}`")

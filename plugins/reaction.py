"""
✘ Commands Available -

• `{i}react` <custom emoji name in database> <reply to message>
     Reacts to a Message with Saved Custom Emoji in Database
     (**For Non-Premium Users:** This plugin automatically converts the saved custom emoji in database to a non-premium reaction emoji. In case of a not allowed reaction in chat, the list of that chat allowed reaction will be returned.
"""

from telethon import types
from telethon.errors import ReactionInvalidError
from telethon.tl.functions.messages import (
    GetAvailableReactionsRequest,
    SendReactionRequest,
)

from CythonX.dB.premium_db import get_emp

from . import LOGS, prememoji, heartless_bot, heartless_cmd


@heartless_cmd(
    pattern="react(?:\\s+(.*))?$",
)
async def react_handler(event):
    reply = await event.get_reply_message()
    if not reply:
        return await event.eor("Reply to a message please...", time=4)
    reaction = event.pattern_match.group(1).strip()
    try:
        await send_reaction(event, reply, event.chat_id, reaction=reaction)
    except ReactionInvalidError:
        await event.eor(
            "Invalid reaction. Maybe it's a custom emoji you don't have?", time=4
        )
    except Exception as e:
        LOGS.info(f"Unexpected error during reaction: {str(e)}")
        await event.eor("Oops! Something went wrong, try again later.", time=4)


@prememoji
async def send_reaction(event, message, chat, reaction, result=None):
    if get_emp(reaction) is None:
        return await event.eor("Invalid reaction name...", time=3)
    reaction_id = get_emp(reaction)
    if not reaction_id:
        return await event.eor(
            "The reaction name doesn't exist in database. You can add by replying `.addemoji <name>` on your desired custom emoji",
            time=8,
        )

    try:
        if (await heartless_bot.get_me()).premium:
            await heartless_bot(
                SendReactionRequest(
                    peer=event.chat_id,
                    msg_id=message.id,
                    reaction=[types.ReactionCustomEmoji(document_id=reaction_id)],
                )
            )
        else:
            try:
                await heartless_bot(
                    SendReactionRequest(
                        peer=event.chat_id,
                        msg_id=message.id,
                        reaction=[types.ReactionEmoji(emoticon=result)],
                    )
                )
            except ReactionInvalidError:
                reactions = (
                    await event.client(GetAvailableReactionsRequest(event.chat_id))
                ).reactions
                x = []
                for i in reactions:
                    x.append(i.reaction)
                    r = "".join(x)
                exceptmsg = await event.respond(
                    f"**You're only allowed to use these reactions in this chat :** `{r}`"
                )
    except Exception as e:
        LOGS.info(f"Unexpected error during reaction: {str(e)}")
        await event.eor("An error occurred while sending the reaction.", time=3)
    await event.delete()

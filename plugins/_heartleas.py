from telethon.errors import (
    BotMethodInvalidError,
    ChatSendInlineForbiddenError,
    ChatSendMediaForbiddenError,
)

from . import LOG_CHANNEL, LOGS, Button, asst, eor, get_string, inline_pic, heartless_cmd

REPOMSG = """
• Ⲏⲉⲁʀⲧⳑⲉⲋⲋ Ⲉⲭⲥⳑυⲋⲓⳳⲉ Ⲃⲟⲧ •
"""

RP_BUTTONS = [
    [Button.url(get_string("bot_3"), "https://xhamsterlive.com")],
    [Button.url("• Ⲋυⲣⲣⲟʀⲧ •", "t.me/PentesterX")],
]


ULTSTRING = """🎇 **Thanks for Deploying UserBot**

• Here, are the Some Basic stuff from, where you can Know, about its Usage."""


@heartless_cmd(pattern="repo$", manager=True, assistant=True)
async def repify(e):
    try:
        await e.reply(
            REPOMSG,
            file=inline_pic(),
            buttons=RP_BUTTONS,
        )
    except (
        ChatSendInlineForbiddenError,
        ChatSendMediaForbiddenError,
        BotMethodInvalidError,
    ):
        pass
    except Exception as er:
        LOGS.info(f"Error while repo command : {str(er)}")


@heartless_cmd(pattern="heartless$")
async def useheartless(rs):
    Button.inline("Start >>", "initft_2")
    msg = await asst.send_message(
        LOG_CHANNEL,
        ULTSTRING,
        file="https://graph.org/file/07158d91e452d53e2d42c.png",
        buttons=RP_BUTTONS,
    )
    if not (rs.chat_id == LOG_CHANNEL and rs.client._bot):
        await eor(rs, f"**[Click Here]({msg.message_link})**")

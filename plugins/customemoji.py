"""
✘ Commands Available -

• `{i}addemoji` <custom emoji name> <reply to a custom emoji>
    Saves Custom Emoji to Database with Desired Name

• `{i}rememoji` <reply to a custom emoji>
    Deletes Custom Emoji from Database

• `{i}listemoji`
    Get Custom Emoji Database List
"""

from telethon.tl.types import MessageEntityCustomEmoji

from . import heartless_bot, heartless_cmd, cusmo, udB, add_emp, is_emp, list_emp, rem_emp


@heartless_cmd(pattern="addemoji( (.*)|$)")
async def add(e):
    reply = await e.get_reply_message()
    if not reply:
        return await e.eor("`Reply to a custom emoji!`", time=4)
    for i in reply.entities:
        if not isinstance(i, MessageEntityCustomEmoji):
            return await e.eor("`Reply to a custom emoji!`", time=4)
    inp = e.pattern_match.group(1).strip()
    if not inp:
        return await e.eor("`Give a name for the replied emoji!`", time=4)
    for i in reply.entities:
        add_emp(inp, i.document_id)
    await heartless_bot.send_message(
        e.chat_id,
        f"[🔄](emoji/5971944878815317190)** Custom Emoji** ([🫨](emoji/{i.document_id})) **Added to Database**\n[➡️](emoji/5971895400792067820)** Name:** `{inp}`\n[🔱](emoji/5972022360025336988)** Doc ID:** `{i.document_id}`",
        reply_to=reply.id,
    )
    await e.delete()


@heartless_cmd(pattern="rememoji( (.*)|$)")
async def rem(e):
    reply = await e.get_reply_message()
    if not reply:
        return await e.eor("`Reply to a custom emoji!`", time=5)
    for i in reply.entities:
        if not isinstance(i, MessageEntityCustomEmoji):
            return await e.eor("`Reply to a custom emoji!`", time=5)
    e.pattern_match.group(1).strip()
    for i in reply.entities:
        if is_emp(i.document_id) is None:
            return await e.eor(
                "This emoji doesn't exist in custom emoji database", time=5
            )
        else:
            rem_emp(is_emp(i.document_id), i.document_id)
            await heartless_bot.send_message(
                e.chat_id,
                f"[🔄](emoji/5971944878815317190)** Custom Emoji** ([🫨](emoji/{i.document_id})) **Removed from Database**\n[🔱](emoji/5972022360025336988)** Doc ID:** `{i.document_id}`",
                reply_to=reply.id,
            )
    await e.delete()

@heartless_cmd(pattern="listemoji( (.*)|$)")
async def list(e):
    x = await e.eor(f"{cusmo('load')} **Processing...**")
    message = "**Custom Emoji Database List :**\n\n"
    redis_dict = udB.get_key("EMP")
    for key, value in redis_dict.items():
        message += f'**Emojis for** `"{key}"`:\n'
        emojis = []
        for number in value:
            emoji = cusmo(int(number))
            emojis.append(f"{emoji} : [`{number}`]")
        message += ", ".join(emojis) + "\n"
    await x.edit(f"\n{message}\n")

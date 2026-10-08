"""
✘ Commands Available -

• `{i}dart 1-6`
• `{i}dice 1-6`
• `{i}bb 1-5` (Basketball)
• `{i}fb 1-5` (Football)
• `{i}jp 1-64` (Slot)

For Guessing Dart and Dice Value Automatically, Do `{i}setdb GUESS True`
"""

from telethon import events
from telethon.tl.types import InputMediaDice

from . import LOGS, udB, heartless_bot, heartless_cmd

DART_E_MOJI = "🎯"
DICE_E_MOJI = "🎲"
BALL_E_MOJI = "🏀"
FOOT_E_MOJI = "⚽️"
SLOT_E_MOJI = "🎰"


@heartless_bot.on(events.NewMessage)
async def Dice(event):
    if (
        event.media
        and hasattr(event.media, "value")
        and udB.get_key("GUESS")
        and event.media.emoticon == "🎲"
    ):
        try:
            await event.eor(f"Dice number is {event.media.value}")
        except Exception as e:
            LOGS.info(str(e))


@heartless_bot.on(events.NewMessage)
async def Dart(event):
    if (
        event.media
        and hasattr(event.media, "value")
        and udB.get_key("GUESS")
        and event.media.emoticon == "🎯"
    ):
        try:
            await event.eor(f"Dart sybl number is {event.media.value}")
        except Exception as e:
            LOGS.info(str(e))


@heartless_cmd(pattern=f"({DART_E_MOJI}|dart)( ([1-6])|$)")
async def _(event):
    if event.fwd_from:
        return
    reply_message = event
    if event.reply_to_msg_id:
        reply_message = await event.get_reply_message()
    emoticon = event.pattern_match.group(1)
    input_str = event.pattern_match.group(2)
    await event.delete()
    if emoticon == "dart":
        emoticon = "🎯"
    r = await reply_message.reply(file=InputMediaDice(emoticon=emoticon))
    if input_str:
        try:
            required_number = int(input_str)
            while r.media.value != required_number:
                await r.delete()
                r = await reply_message.reply(file=InputMediaDice(emoticon=emoticon))
        except BaseException:
            pass
    else:
        if event.sender_id == event.client.uid:
            await event.edit(file=InputMediaDice(emoticon=emoticon))
        else:
            await event.reply(file=InputMediaDice(emoticon=emoticon))


@heartless_cmd(pattern=f"({DICE_E_MOJI}|dice)( ([1-6])|$)")
async def _(event):
    if event.fwd_from:
        return
    reply_message = event
    if event.reply_to_msg_id:
        reply_message = await event.get_reply_message()
    emoticon = event.pattern_match.group(1)
    input_str = event.pattern_match.group(2)
    await event.delete()
    if emoticon == "dice":
        emoticon = "🎲"
    r = await reply_message.reply(file=InputMediaDice(emoticon=emoticon))
    if input_str:
        try:
            required_number = int(input_str)
            while r.media.value != required_number:
                await r.delete()
                r = await reply_message.reply(file=InputMediaDice(emoticon=emoticon))
        except BaseException:
            pass
    else:
        if event.sender_id == event.client.uid:
            await event.edit(file=InputMediaDice(emoticon=emoticon))
        else:
            await event.reply(file=InputMediaDice(emoticon=emoticon))


@heartless_cmd(pattern=f"({BALL_E_MOJI}|bb)( ([1-5])|$)")
async def _(event):
    if event.fwd_from:
        return
    reply_message = event
    if event.reply_to_msg_id:
        reply_message = await event.get_reply_message()
    emoticon = event.pattern_match.group(1)
    input_str = event.pattern_match.group(2)
    await event.delete()
    if emoticon == "bb":
        emoticon = "🏀"
    r = await reply_message.reply(file=InputMediaDice(emoticon=emoticon))
    if input_str:
        try:
            required_number = int(input_str)
            while r.media.value != required_number:
                await r.delete()
                r = await reply_message.reply(file=InputMediaDice(emoticon=emoticon))
        except BaseException:
            pass
    else:
        if event.sender_id == event.client.uid:
            await event.edit(file=InputMediaDice(emoticon=emoticon))
        else:
            await event.reply(file=InputMediaDice(emoticon=emoticon))


@heartless_cmd(pattern=f"({FOOT_E_MOJI}|fb)( ([1-5])|$)")
async def _(event):
    if event.fwd_from:
        return
    reply_message = event
    if event.reply_to_msg_id:
        reply_message = await event.get_reply_message()
    emoticon = event.pattern_match.group(1)
    input_str = event.pattern_match.group(2)
    await event.delete()
    if emoticon == "fb":
        emoticon = "⚽️"
    r = await reply_message.reply(file=InputMediaDice(emoticon=emoticon))
    if input_str:
        try:
            required_number = int(input_str)
            while r.media.value != required_number:
                await r.delete()
                r = await reply_message.reply(file=InputMediaDice(emoticon=emoticon))
        except BaseException:
            pass
    else:
        if event.sender_id == event.client.uid:
            await event.edit(file=InputMediaDice(emoticon=emoticon))
        else:
            await event.reply(file=InputMediaDice(emoticon=emoticon))


@heartless_cmd(pattern=f"({SLOT_E_MOJI}|jp)( ([1-64])|$)")
async def _(event):
    if event.fwd_from:
        return
    reply_message = event
    if event.reply_to_msg_id:
        reply_message = await event.get_reply_message()
    emoticon = event.pattern_match.group(1)
    input_str = event.pattern_match.group(2)
    await event.delete()
    if emoticon == "jp":
        emoticon = "🎰"
    r = await reply_message.reply(file=InputMediaDice(emoticon=emoticon))
    if input_str:
        try:
            required_number = int(input_str)
            while r.media.value != required_number:
                await r.delete()
                r = await reply_message.reply(file=InputMediaDice(emoticon=emoticon))
        except BaseException:
            pass
    else:
        if event.sender_id == event.client.uid:
            await event.edit(file=InputMediaDice(emoticon=emoticon))
        else:
            await event.reply(file=InputMediaDice(emoticon=emoticon))

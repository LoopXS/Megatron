import os
import re

import pytz
from telethon.errors.rpcerrorlist import (
    ButtonUserInvalidError,
    ChannelPrivateError,
    ChatWriteForbiddenError,
    MediaCaptionTooLongError,
    MediaEmptyError,
    MessageTooLongError,
    PeerIdInvalidError,
    UserNotParticipantError,
)
from telethon.tl.types import MessageEntityMention, MessageEntityMentionName, User
from telethon.utils import get_display_name

from CythonX.dB.botchat_db import tag_add, who_tag

from . import (
    LOG_CHANNEL,
    LOGS,
    Button,
    asst,
    callback,
    events,
    get_string,
    inline_mention,
    udB,
    heartless_bot,
)

CACHE_SPAM = {}
TAG_EDITS = {}


@heartless_bot.on(
    events.NewMessage(
        incoming=True,
        func=lambda e: (e.mentioned),
    ),
)
async def all_messages_catcher(e):
    x = await e.get_sender()
    if isinstance(x, User) and (x.bot or x.verified):
        return
    if not udB.get_key("TAG_LOG"):
        return
    NEEDTOLOG = udB.get_key("TAG_LOG")
    buttons = await parse_buttons(e)
    try:
        try:
            sent = await asst.send_message(NEEDTOLOG, e.message, buttons=buttons)
        except ButtonUserInvalidError:
            LOGS.debug("TAG_LOG ButtonUserInvalidError; retrying without mention")
            buttons = await parse_buttons(e, allow_mention=False)
            sent = await asst.send_message(NEEDTOLOG, e.message, buttons=buttons)
        if TAG_EDITS.get(e.chat_id):
            TAG_EDITS[e.chat_id].update({e.id: {"id": sent.id, "msg": e}})
        else:
            TAG_EDITS.update({e.chat_id: {e.id: {"id": sent.id, "msg": e}}})
        tag_add(sent.id, e.chat_id, e.id)
    except MediaEmptyError as er:
        LOGS.debug(f"handling {er}.")
        try:
            msg = await asst.get_messages(e.chat_id, ids=e.id)
            try:
                sent = await asst.send_message(NEEDTOLOG, msg, buttons=buttons)
            except ButtonUserInvalidError:
                buttons = await parse_buttons(e, allow_mention=False)
                sent = await asst.send_message(NEEDTOLOG, msg, buttons=buttons)
            if TAG_EDITS.get(e.chat_id):
                TAG_EDITS[e.chat_id].update({e.id: {"id": sent.id, "msg": e}})
            else:
                TAG_EDITS.update({e.chat_id: {e.id: {"id": sent.id, "msg": e}}})
            tag_add(sent.id, e.chat_id, e.id)
        except Exception as me:
            if not isinstance(me, (PeerIdInvalidError, ValueError)):
                LOGS.exception(me)
            if e.photo or e.sticker or e.gif:
                try:
                    media = await e.download_media()
                    try:
                        sent = await asst.send_message(
                            NEEDTOLOG, e.message.text, file=media, buttons=buttons
                        )
                    except ButtonUserInvalidError:
                        buttons = await parse_buttons(e, allow_mention=False)
                        sent = await asst.send_message(
                            NEEDTOLOG, e.message.text, file=media, buttons=buttons
                        )
                    if TAG_EDITS.get(e.chat_id):
                        TAG_EDITS[e.chat_id].update({e.id: {"id": sent.id, "msg": e}})
                    else:
                        TAG_EDITS.update({e.chat_id: {e.id: {"id": sent.id, "msg": e}}})
                    return os.remove(media)
                except Exception as er:
                    LOGS.exception(er)
            try:
                await asst.send_message(NEEDTOLOG, get_string("com_4"), buttons=buttons)
            except ButtonUserInvalidError:
                buttons = await parse_buttons(e, allow_mention=False)
                await asst.send_message(NEEDTOLOG, get_string("com_4"), buttons=buttons)
    except (PeerIdInvalidError, ValueError) as er:
        LOGS.exception(er)
        try:
            CACHE_SPAM[NEEDTOLOG]
        except KeyError:
            await asst.send_message(
                udB.get_key("LOG_CHANNEL"), get_string("userlogs_1")
            )
            CACHE_SPAM.update({NEEDTOLOG: True})
    except ChatWriteForbiddenError:
        try:
            await asst.get_permissions(NEEDTOLOG, "me")
            MSG = get_string("userlogs_4")
        except UserNotParticipantError:
            MSG = get_string("userlogs_2")
        try:
            CACHE_SPAM[NEEDTOLOG]
        except KeyError:
            await asst.send_message(LOG_CHANNEL, MSG)
            CACHE_SPAM.update({NEEDTOLOG: True})
    except Exception as er:
        LOGS.exception(er)


if udB.get_key("TAG_LOG"):

    @heartless_bot.on(events.MessageEdited(func=lambda x: not x.out))
    async def upd_edits(event):
        x = event.sender
        if isinstance(x, User) and (x.bot or x.verified):
            return
        if event.chat_id not in TAG_EDITS:
            if event.sender_id == udB.get_key("TAG_LOG"):
                return
            if event.is_private:
                return
            if entities := event.get_entities_text():
                is_self = False
                username = event.client.me.username
                if username:
                    username = username.lower()
                for ent, text in entities:
                    if isinstance(ent, MessageEntityMention):
                        is_self = text[1:].lower() == username
                    elif isinstance(ent, MessageEntityMentionName):
                        is_self = ent.user_id == event.client.me.id
                if is_self:
                    text = f"**#Edited & #Mentioned**\n\n{event.text}"
                    try:
                        sent = await asst.send_message(
                            udB.get_key("TAG_LOG"),
                            text,
                            buttons=await parse_buttons(event),
                        )
                    except Exception as er:
                        return LOGS.exception(er)
                    if TAG_EDITS.get(event.chat_id):
                        TAG_EDITS[event.chat_id].update({event.id: {"id": sent.id}})
                    else:
                        TAG_EDITS.update({event.chat_id: {event.id: {"id": sent.id}}})
            return
        d_ = TAG_EDITS[event.chat_id]
        if not d_.get(event.id):
            return
        d_ = d_[event.id]
        if d_["msg"].text == event.text:
            return
        msg = None
        if d_.get("count"):
            d_["count"] += 1
        else:
            msg = True
            d_.update({"count": 1})
        if d_["count"] > 10:
            return  # some limit to take edits
        try:
            MSG = await asst.get_messages(udB.get_key("TAG_LOG"), ids=d_["id"])
        except Exception as er:
            return LOGS.exception(er)
        TEXT = MSG.text
        if msg:
            TEXT += "\n\n🖋 **Edited to :**"
        md = pytz.timezone("Asia/Tehran")
        strf = event.edit_date.astimezone(md).strftime("%H:%M:%S")
        if "\n" not in event.text:
            TEXT += f"\n• `{strf}` : {event.text}"
        else:
            TEXT += f"\n• `{strf}` :\n-> {event.text}"
        if d_["count"] == 10:
            TEXT += "\n\n• __Only the first 10 Edits are shown.__"
        try:
            msg = await MSG.edit(TEXT, buttons=await parse_buttons(event))
            d_["msg"] = msg
        except (MessageTooLongError, MediaCaptionTooLongError):
            del TAG_EDITS[event.chat_id][event.id]
        except Exception as er:
            LOGS.exception(er)

    @heartless_bot.on(
        events.NewMessage(
            outgoing=True,
            chats=[udB.get_key("TAG_LOG")],
            func=lambda e: e.reply_to,
        )
    )
    async def idk(e):
        id = e.reply_to_msg_id
        chat, msg = who_tag(id)
        if chat and msg:
            try:
                await heartless_bot.send_message(chat, e.message, reply_to=msg)
            except BaseException as er:
                LOGS.exception(er)


# log for assistant/user joins/add


async def when_added_or_joined(event):
    user = await event.get_user()
    chat = await event.get_chat()
    if not (user and user.is_self):
        return
    action_msg = getattr(event, "action_message", None)
    msg_id = getattr(action_msg, "id", None) or getattr(event, "id", None)
    title = getattr(chat, "title", None) or "Chat"
    username = getattr(chat, "username", None)
    chat_id = getattr(chat, "id", None)
    if username and msg_id:
        chat = f"[{title}](https://t.me/{username}/{msg_id})"
    elif chat_id and msg_id:
        # strip -100 prefix for t.me/c/ links when present
        cid = str(chat_id)
        if cid.startswith("-100"):
            cid = cid[4:]
        chat = f"[{title}](https://t.me/c/{cid}/{msg_id})"
    elif username:
        chat = f"[{title}](https://t.me/{username})"
    else:
        chat = f"**{title}**"
    key = "bot" if event.client._bot else "user"
    buttons = Button.inline(
        get_string("userlogs_3"), data=f"leave_ch_{event.chat_id}|{key}"
    )
    if event.user_added:
        tmp = event.added_by
        text = f"#ADD_LOG\n\n{inline_mention(tmp)} just added {inline_mention(user)} to {chat}."
    elif event.from_request:
        text = f"#APPROVAL_LOG\n\n{inline_mention(user)} just got Chat Join Approval to {chat}."
    else:
        text = f"#JOIN_LOG\n\n{inline_mention(user)} just joined {chat}."
    await asst.send_message(udB.get_key("LOG_CHANNEL"), text, buttons=buttons)


asst.add_event_handler(
    when_added_or_joined, events.ChatAction(func=lambda x: x.user_added)
)
heartless_bot.add_event_handler(
    when_added_or_joined,
    events.ChatAction(func=lambda x: x.user_added or x.user_joined),
)
_client = {"bot": asst, "user": heartless_bot}


@callback(
    re.compile(
        "leave_ch_(.*)",
    ),
    from_users=[heartless_bot.uid],
)
async def leave_ch_at(event):
    cht = event.data_match.group(1).decode("UTF-8")
    ch_id, client = cht.split("|")
    try:
        client = _client[client]
    except KeyError:
        return
    try:
        name = (await client.get_entity(int(ch_id))).title
        await client.delete_dialog(int(ch_id))
    except UserNotParticipantError:
        pass
    except ChannelPrivateError:
        return await event.edit(
            "`[CANT_ACCESS_CHAT]` `Maybe already left or got banned.`"
        )
    except Exception as er:
        LOGS.exception(er)
        return await event.answer(str(er))
    await event.edit(get_string("userlogs_5").format(name))


@callback("do_nothing")
async def _(event):
    await event.answer()


async def parse_buttons(event, *, allow_mention=True):
    y, x = event.chat, event.sender
    where_n, who_n = get_display_name(y), get_display_name(x)
    where_l = event.message_link
    buttons = [[Button.url(where_n, where_l)]]

    def _who_url():
        if getattr(x, "username", None):
            return Button.url(who_n, f"t.me/{x.username}")
        return Button.url(who_n, where_l)

    # Layer 230 profile buttons need an InputUser the *assistant* knows.
    # Prefer asst.get_input_entity; otherwise fall back to a t.me URL so
    # SendMessageRequest does not raise ButtonUserInvalidError.
    if isinstance(x, User) and allow_mention:
        peer = None
        try:
            peer = await asst.get_input_entity(x)
        except Exception:
            try:
                peer = await asst.get_input_entity(int(x.id))
            except Exception as er:
                LOGS.debug("TAG_LOG asst cannot resolve mention peer: %s", er)
        if peer is not None:
            try:
                buttons.append([Button.mention(who_n, peer)])
            except Exception as er:
                LOGS.debug("TAG_LOG mention button build failed: %s", er)
                buttons.append([_who_url()])
        else:
            buttons.append([_who_url()])
    else:
        buttons.append([_who_url()])

    replied = await event.get_reply_message()
    if replied and replied.out:
        button = Button.url("Replied to", replied.message_link)
        if len(who_n) > 7:
            buttons.append([button])
        else:
            buttons[-1].append(button)
    return buttons

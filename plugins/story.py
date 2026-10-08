"""
✘ Commands Available -

• `{i}addstory` <reply to a video/image>
    Sets the Video/Image as Your Account Story

• `{i}dlstory` <telegram story link>
    Downloads the Telegram Story by Link

• `{i}remstory` <telegram story link>
    Deletes the Telegram Story by Link

• `{i}views`
    Shows All Views of Your Active Stories
    ~ `{i}viewsu` - List via Username
"""

import os
import re
import time
import pytz

from telethon.errors.rpcerrorlist import MessageEmptyError
from telethon.tl.functions.stories import (
    DeleteStoriesRequest,
    GetPeerStoriesRequest,
    GetStoriesByIDRequest,
    GetStoryViewsListRequest,
    SendStoryRequest,
)
from telethon.tl.types import (
    DocumentAttributeFilename,
    InputPrivacyValueAllowAll,
    ReactionCustomEmoji,
    ReactionEmoji,
)
from telethon.utils import get_input_media

from . import eor, downloader, mediainfo, heartless_bot, heartless_cmd


@heartless_cmd(pattern="addstory( (.*)|$)", fullsudo=True)
async def addstory(e):
    inp = int(e.pattern_match.group(1).strip())
    if inp not in [6, 12, 24, 48]:
        return await e.eor("**Give time : 6, 12, 24, 48**", time=4)
    if inp <= 12:
        inp = inp * 3600
    elif inp == 24:
        inp = 86400
    elif inp == 48:
        inp = 2 * 86400
    else:
        inp = 86400  # Default value for non-premium users
    reply = await e.get_reply_message()
    if "video" in mediainfo(reply.media):
        file_path = reply.media.document
        for attribute in file_path.attributes:
            if isinstance(attribute, DocumentAttributeFilename):
                file_name = attribute.file_name
                break
    else:
        file_path = reply.media.photo
    if not reply or not reply.media:
        return await e.eor("`Reply to a video/image file please...`", time=4)
    if "pic" not in mediainfo(reply.media) and "video" not in mediainfo(reply.media):
        return await e.eor("`Reply to a video/image only please...`", time=4)
    msg = await e.eor("`Downloading` [🔄](emoji/5971944878815317190)")
    dwntime = time.time()
    try:
        file_path = await downloader(file_name, file_path, e, dwntime, f"Downloading")
    except Exception:
        file_name = await heartless_bot.download_media(reply.media)
    y, _ = await heartless_bot.fast_uploader(
        file_name,
        show_progress=True,
        event=e,
        to_delete=True,
    )
    if "pic" in mediainfo(reply.media):
        story = await heartless_bot(
            SendStoryRequest(
                peer="me",
                period=inp, 
                media=(await heartless_bot._file_to_media(y))[1],
                privacy_rules=[InputPrivacyValueAllowAll()],
            )
        )
    if "video" in mediainfo(reply.media):
        if reply.media.document.size > 10000000:
            return await e.eor("The video/image size can't be upper than 10Mb", time=4)
        else:
            story = await heartless_bot(
                SendStoryRequest(
                    peer="me",
                    period=inp,
                    media=get_input_media(y), 
                    privacy_rules=[InputPrivacyValueAllowAll()],
                )
            )
    await msg.edit(
        f"[📸](emoji/5467868941223214483)** [Story Uploaded Successfully]**(https://t.me/{(await heartless_bot.get_me()).username}/s/{story.updates[1].id})"
    )


async def download_story(user_id, story_id):
    stories = (await heartless_bot(GetStoriesByIDRequest(user_id, [story_id]))).stories
    if stories:
        return await heartless_bot.download_media(stories[0].media)


@heartless_cmd(pattern="dlstory( (.*)|$)", assistant=True, manager=True)
async def dlstory(e):
    inp = e.pattern_match.group(1).strip()
    if not inp:
        return await e.eor("`Give a telegram story link!`", time=4)
    msg = await e.eor("[🔄](emoji/5971944878815317190) `Fetching Story Info...`")
    pattern = r"https://t.me/(\w+)/s/(\d+)"
    match = re.match(pattern, inp)
    if match:
        peer = match.group(1)
        id = match.group(2)
        story_file = await download_story(peer, int(id))
        if story_file:
            await e.client.send_file(
                e.chat_id,
                story_file,
                caption=f"[✨](emoji/5929393980683848892)** [Story Downloaded Successfully]**({inp})",
                force_document=False,
            )
            os.remove(story_file)
        else:
            return await e.eor("`Story unavailable!`", time=4)
    else:
        return await e.eor("`Invalid telegram story link!`", time=4)
    await msg.delete()


@heartless_cmd(pattern="remstory( (.*)|$)", fullsudo=True)
async def remstory(e):
    inp = e.pattern_match.group(1).strip()
    if not inp:
        return await e.eor("`Give a telegram story link!`", time=4)
    pattern = r"https://t.me/(\w+)/s/(\d+)"
    match = re.match(pattern, inp)
    if match:
        id = match.group(2)
        await heartless_bot(DeleteStoriesRequest(peer="me", id=[int(id)]))
        await e.eor("[✅](emoji/5474411305991415885) **Story Deleted Successfully**")
    else:
        return await e.eor("`Invalid telegram story link!`", time=4)


@heartless_cmd(pattern="views(|u)$", fullsudo=True)
async def storyviews(e):
    try:
        x = await heartless_bot(GetPeerStoriesRequest(peer="me"))
        txt = ""
        userN = None
        if e.pattern_match.group(1) == "u":
            userN = "u"
        for story in x.stories.stories:
            I = int(story.id)
            t = await heartless_bot(
                GetStoryViewsListRequest(peer="me", id=I, offset="ok", limit=100)
            )
            m = {user.first_name: i.reaction for user, i in zip(t.users, t.views)}
            txt += f"\n\n[👁](emoji/5032776298733240935) **[Details of Story {story.id}]**(https://t.me/{(await heartless_bot.get_me()).username}/s/{story.id}):\n\n**Total Views** ➪ {t.views_count}\n"
            reactions = []
            for user, reaction in m.items():
                if reaction is not None:
                    if isinstance(reaction, ReactionEmoji):
                        reactions.append((user, reaction.emoticon))
                    if isinstance(reaction, ReactionCustomEmoji):
                        reactions.append((user, f"[♥️](emoji/{reaction.document_id})"))
                else:
                    reactions.append((user, ""))
            converted_times = [
                i.date.replace(tzinfo=pytz.utc)
                .astimezone(pytz.timezone("Asia/Tehran"))
                .strftime("%H:%M:%S")
                for i in t.views
            ]
            if userN != "u":
                for (user, reaction), converted_time in zip(reactions, converted_times):
                    txt += f"\n⌬ {user} {reaction}\n**╰ ᴠɪᴇᴡᴇᴅ ᴀᴛ** {converted_time}\n"
            if userN == "u":
                for user, converted_time in zip(t.users, converted_times):
                    txt += f"\n⌬ {converted_time} "
                    txt += f"@{user.username}" if user.username else user.first_name
        await e.edit(txt)
    except MessageEmptyError:
        await e.eor(f"[🤯](emoji/5382347178763106071) Set a story first", time=5)

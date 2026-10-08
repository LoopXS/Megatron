import os
import re

try:
    from PIL import Image
except ImportError:
    Image = None
from telethon import Button
from telethon.errors.rpcerrorlist import FilePartLengthInvalidError, MediaEmptyError
from telethon.tl.types import DocumentAttributeAudio, DocumentAttributeVideo
from telethon.tl.types import InputWebDocument as wb

from CythonX.fns.helper import (
    bash,
    fast_download,
    humanbytes,
    numerize,
    time_formatter,
)
from CythonX.fns.ytdl import dler, get_buttons, get_formats, _inline_download

from . import LOGS, asst, callback, in_pattern, udB

try:
    from youtubesearchpython import VideosSearch
except ImportError:
    LOGS.info("'youtubesearchpython' not installed!")
    VideosSearch = None


ytt = "https://graph.org/file/afd04510c13914a06dd03.jpg"
_yt_base_url = "https://www.youtube.com/watch?v="
BACK_BUTTON = {}


@in_pattern("yt", owner=True)
async def _(event):
    try:
        string = event.text.split(" ", maxsplit=1)[1]
    except IndexError:
        fuk = event.builder.article(
            title="Search Something",
            thumb=wb(ytt, 0, "image/jpeg", []),
            text="**YᴏᴜTᴜʙᴇ Sᴇᴀʀᴄʜ**\n\nYou didn't search anything",
            buttons=Button.switch_inline(
                "Sᴇᴀʀᴄʜ Aɢᴀɪɴ",
                query="yt ",
                same_peer=True,
            ),
        )
        await event.answer([fuk])
        return
    results = []
    search = VideosSearch(string, limit=50)
    nub = search.result()
    nibba = nub["result"]
    for v in nibba:
        ids = v["id"]
        link = _yt_base_url + ids
        title = v["title"]
        duration = v["duration"]
        views = v["viewCount"]["short"]
        publisher = v["channel"]["name"]
        published_on = v["publishedTime"]
        description = (
            v["descriptionSnippet"][0]["text"]
            if v.get("descriptionSnippet")
            and len(v["descriptionSnippet"][0]["text"]) < 500
            else "None"
        )
        thumb = f"https://i.ytimg.com/vi/{ids}/hqdefault.jpg"
        text = f"**Title: [{title}]({link})**\n\n"
        text += f"`Description: {description}\n\n"
        text += f"「 Duration: {duration} 」\n"
        text += f"「 Views: {views} 」\n"
        text += f"「 Publisher: {publisher} 」\n"
        text += f"「 Published on: {published_on} 」`"
        desc = f"{title}\n{duration}"
        file = wb(thumb, 0, "image/jpeg", [])
        buttons = [
            [
                Button.inline("Audio", data=f"ytdl:audio:{ids}"),
                Button.inline("Video", data=f"ytdl:video:{ids}"),
            ],
            [
                Button.switch_inline(
                    "Sᴇᴀʀᴄʜ Aɢᴀɪɴ",
                    query="yt ",
                    same_peer=True,
                ),
                Button.switch_inline(
                    "Sʜᴀʀᴇ",
                    query=f"yt {string}",
                    same_peer=False,
                ),
            ],
        ]
        BACK_BUTTON.update({ids: {"text": text, "buttons": buttons}})
        results.append(
            await event.builder.article(
                type="photo",
                title=title,
                description=desc,
                thumb=file,
                content=file,
                text=text,
                include_media=True,
                buttons=buttons,
            ),
        )
    await event.answer(results[:50])


@callback(
    re.compile(
        "ytdl:(.*)",
    ),
    owner=True,
)
async def _(e):
    _e = e.pattern_match.group(1).strip().decode("UTF-8")
    _lets_split = _e.split(":")
    _ytdl_data = await dler(e, _yt_base_url + _lets_split[1])
    _data = get_formats(_lets_split[0], _lets_split[1], _ytdl_data)
    _buttons = get_buttons(_data)
    _text = (
        "`Select Your Format.`"
        if _buttons
        else "`Error downloading from YouTube.\nTry Restarting your bot.`"
    )
    await e.edit(_text, buttons=_buttons)


@callback(
    re.compile(
        "ytdownload:(.*)",
    ),
    owner=True,
)
async def _(event):
    """
    Handle a selected inline format.

    The previous implementation hard-coded YouTube format 251 for audio,
    guessed the output extension and relied on a handful of filename fallbacks.
    The new path delegates the actual download to the EGM-style yt-dlp engine
    in CythonX.fns.ytdl._inline_download.
    """
    raw = event.pattern_match.group(1).strip().decode("UTF-8")
    parts = raw.split(":")
    if len(parts) < 3:
        return await event.answer("Invalid download request.", alert=True)

    media_type, format_id, video_id = parts[:3]
    ext = parts[3] if len(parts) >= 4 else ("mp3" if media_type == "audio" else "mp4")

    if media_type not in ("audio", "video"):
        return await event.answer("Unsupported media type.", alert=True)

    if not re.fullmatch(r"[A-Za-z0-9_.-]+", video_id):
        return await event.answer("Invalid YouTube video ID.", alert=True)

    if media_type == "video" and not re.fullmatch(r"[A-Za-z0-9_.-]+", format_id):
        return await event.answer("Invalid video format.", alert=True)

    if media_type == "audio" and format_id not in {"128", "192", "320"}:
        return await event.answer("Invalid audio quality.", alert=True)

    await event.answer("Starting download…")

    await _inline_download(
        event,
        video_id=video_id,
        media_type=media_type,
        format_id=format_id,
        quality=format_id if media_type == "audio" else "0",
        ext=ext,
    )


@callback(re.compile("ytdl_back:(.*)"), owner=True)
async def ytdl_back(event):
    id_ = event.data_match.group(1).decode("utf-8")
    if not BACK_BUTTON.get(id_):
        return await event.answer("Query Expired! Search again 🔍")
    await event.edit(**BACK_BUTTON[id_])

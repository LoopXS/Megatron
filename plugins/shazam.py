"""
✘ Commands Available -

• `{i}shazam`
  Identify a song by replying to an audio, voice, or video message.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
import aiohttp

from . import *


ACR_HOST = "identify-ap-southeast-1.acrcloud.com"
ACR_KEY = "b050a13ce81ce1019e1e4b25281f45cd"
ACR_SECRET = "dkmrEDd2w8McSy920qKUXzGdBLp35uxgX4Lfpwtd"


def generate_acr_signature(http_method, uri, access_key, secret_key, data_type, signature_version, timestamp):
    string_to_sign = f"{http_method}\n{uri}\n{access_key}\n{data_type}\n{signature_version}\n{timestamp}"
    hmac_res = hmac.new(
        secret_key.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha1
    ).digest()
    return base64.b64encode(hmac_res).decode("utf-8")


@heartless_cmd(pattern="shazam$", assistant=True, manager=True, allow_sudo=True)
async def _(event):
    if not event.is_reply:
        return await eor(event, "`Reply to an audio, voice, or video file!`")

    reply = await event.get_reply_message()
    if not reply or not reply.media:
        return await eor(event, "`Replied message doesn't contain media.`")

    msg = await eor(event, "`Downloading media...`")
    file_path = None
    trimmed_path = None

    try:
        file_path = await event.client.download_media(reply)
        await msg.edit("`Trimming audio snippet (12s)...`")

        trimmed_path = f"{file_path}_snippet.mp3"
        ffmpeg_cmd = f"ffmpeg -y -i '{file_path}' -ss 00:00:00 -t 12 -vn -map 0:a: -acodec libmp3lame '{trimmed_path}'"
        
        process = await asyncio.create_subprocess_shell(
            ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        if process.returncode != 0 or not os.path.exists(trimmed_path):
            return await msg.edit(f"❌ `ffmpeg error:` `{stderr.decode().strip()}`")

        await msg.edit("`Analyzing audio sample with ACRCloud...`")

        with open(trimmed_path, "rb") as f:
            sample_data = f.read()

        sample_bytes = len(sample_data)
        timestamp = str(int(time.time()))
        req_url = f"https://{ACR_HOST}/v1/identify"

        signature = generate_acr_signature(
            "POST",
            "/v1/identify",
            ACR_KEY,
            ACR_SECRET,
            "audio",
            "1",
            timestamp
        )

        data = aiohttp.FormData()
        data.add_field("sample", sample_data, filename="sample.mp3", content_type="audio/mpeg")
        data.add_field("sample_bytes", str(sample_bytes))
        data.add_field("access_key", ACR_KEY)
        data.add_field("data_type", "audio")
        data.add_field("signature_version", "1")
        data.add_field("signature", signature)
        data.add_field("timestamp", timestamp)

        async with aiohttp.ClientSession() as session:
            async with session.post(req_url, data=data) as resp:
                res = await resp.json(content_type=None)

        status = res.get("status", {})
        if status.get("code") != 0:
            msg_text = status.get("msg", "No match found.")
            return await msg.edit(f"❌ `{msg_text}`")

        metadata = res.get("metadata", {})
        music = metadata.get("music", [])

        if not music:
            return await msg.edit("❌ `No matching track found.`")

        track_info = music[0]
        title = track_info.get("title", "Unknown Title")
        
        artists = [a.get("name", "") for a in track_info.get("artists", [])]
        artist_str = ", ".join(artists) if artists else "Unknown Artist"

        album = track_info.get("album", {}).get("name", "Single / Unknown")
        duration_ms = track_info.get("duration_ms", 0)
        minutes, seconds = divmod(int(duration_ms / 1000), 60)
        time_str = f"{minutes}:{seconds:02d}"

        output_text = (
            "🎵 **Match Found!**\n"
            "```\n"
            f"Track:    {title}\n"
            f"Artist:   {artist_str}\n"
            f"Album:    {album}\n"
            f"Duration: {time_str}\n"
            "```"
        )
        await msg.edit(output_text)

    except Exception as err:
        await msg.edit(f"❌ **Error:** `{str(err)}`")

    finally:
        for p in (file_path, trimmed_path):
            if p and os.path.exists(p):
                os.remove(p)

"""
✘ Commands Available -

• `{i}yta <(youtube/any) link>`
   Download audio from the link.

• `{i}ytv <(youtube/any) link>`
   Download video from the link.

• `{i}ytsa <(youtube) search query>`
   Search and download audio from youtube.

• `{i}ytsv <(youtube) search query>`
   Search and download video from youtube.

• `{i}ytsc <soundcloud link>`
   Download audio from SoundCloud.

• `{i}ytsp <spotify link>`
   Download audio from Spotify
"""

import os
import glob
import subprocess
from bs4 import BeautifulSoup

from CythonX.fns.ytdl import download_yt, get_yt_link

from . import get_string, get_pstring, requests, heartless_cmd


def thumb(spotify_link):
    try:
        response = requests.get(spotify_link)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        thumbnail_element = soup.select_one("meta[property='og:image']")
        if thumbnail_element:
            thumbnail_url = thumbnail_element["content"]
            response = requests.get(thumbnail_url, stream=True)
            response.raise_for_status()
            save_path = "thumb.jpg"
            with open(save_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
        else:
            LOGS.info("Thumbnail not found for the given Spotify link.")
    except requests.exceptions.RequestException as e:
        LOGS.info(f"Error: {e}")


@heartless_cmd(
    pattern="yt(a|v|sa|sv|sc|sp) ?(.*)",
)
async def download_from_youtube_(event):
    ytd = {
        "prefer_ffmpeg": True,
        "addmetadata": True,
        "geo-bypass": True,
        "nocheckcertificate": True,
    }
    opt = event.pattern_match.group(1).strip()
    xx = await event.eor(get_pstring("com_1", "load"))
    if opt == "a":
        ytd["format"] = "bestaudio"
        ytd["outtmpl"] = "%(id)s.m4a"
        url = event.pattern_match.group(2)
        if not url:
            return await xx.eor(get_string("youtube_1"))
        try:
            requests.get(url)
        except BaseException:
            return await xx.eor(get_string("youtube_2"))
    elif opt == "v":
        ytd["format"] = "best"
        ytd["outtmpl"] = "%(id)s.mp4"
        ytd["postprocessors"] = [{"key": "FFmpegMetadata"}]
        url = event.pattern_match.group(2)
        if not url:
            return await xx.eor(get_string("youtube_3"))
        try:
            requests.get(url)
        except BaseException:
            return await xx.eor(get_string("youtube_4"))
    elif opt == "sa":
        ytd["format"] = "bestaudio"
        ytd["outtmpl"] = "%(id)s.m4a"
        try:
            query = event.text.split(" ", 1)[1]
        except IndexError:
            return await xx.eor(get_string("youtube_5"))
        url = get_yt_link(query)
        if not url:
            return await xx.edit(get_string("unspl_1"))
        await xx.eor(get_string("youtube_6"))
    elif opt == "sv":
        ytd["format"] = "best"
        ytd["outtmpl"] = "%(id)s.mp4"
        ytd["postprocessors"] = [{"key": "FFmpegMetadata"}]
        try:
            query = event.text.split(" ", 1)[1]
        except IndexError:
            return await xx.eor(get_string("youtube_7"))
        url = get_yt_link(query)
        if not url:
            return await xx.edit(get_string("unspl_1"))
        await xx.eor(get_string("youtube_8"))
    elif opt == "sc":
        ytd["format"] = "bestaudio"
        ytd["outtmpl"] = "%(id)s.mp3"
        url = event.pattern_match.group(2)
        if not url:
            return await xx.eor("Please provide a SoundCloud link.")
        try:
            requests.get(url)
        except BaseException:
            return await xx.eor("Invalid SoundCloud link.")
    elif opt == "sp":
        ytd["format"] = "bestaudio"
        ytd["outtmpl"] = "%(id)s.mp3"
        url = event.pattern_match.group(2)
        if not url:
            return await xx.eor("Please provide a Spotify link.")
        try:
            subprocess.run(["spotdl", url], check=True, capture_output=True)
            files = os.listdir(".")
            mp3_files = [file for file in files if file.endswith(".mp3")]
            thumbnail = thumb(url)
            if mp3_files:
                file_path = mp3_files[0]
                file, _ = await event.client.fast_uploader(file_path, show_progress=True, event=event, to_delete=True)
                await event.client.send_file(event.chat_id, file, thumb="thumb.jpg")
            else:
                return await xx.eor("No MP3 files found after downloading.")
            if thumbnail:
                os.remove("thumb.jpg")
            else:
                pass
            xx.eor("Spotify Download Successful", time=10)
        except subprocess.CalledProcessError as e:
            error_message = f"Error occurred while downloading: {e.stderr.decode()}"
            return await xx.eor(error_message)
        except Exception as e:
            return await xx.eor(f"An error occurred: {str(e)}")
    else:
        return
    if opt != "sp":
        await download_yt(xx, url, ytd)

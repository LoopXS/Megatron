import os
import time
from datetime import datetime as dt
from secrets import token_hex

from CythonX.fns.tools import set_attributes

from . import (
    LOGS,
    ULTConfig,
    bash,
    downloader,
    eod,
    eor,
    genss,
    get_help,
    get_string,
    get_pstring,
    humanbytes,
    mediainfo,
    stdr,
    time_formatter,
    heartless_cmd,
    uploader,
)

__doc__ = get_help("help_audiotools")


@heartless_cmd(pattern="makevoice$")
async def vnc(e):
    if not e.reply_to:
        return await eod(e, get_string("audiotools_1"))
    r = await e.get_reply_message()
    if not (r and r.media and mediainfo(r.media).startswith(("audio", "video"))):
        return await eod(e, get_string("spcltool_1"))
    xxx = await e.eor(get_pstring("com_1", "load"))
    file, _ = await e.client.fast_downloader(
        r.document,
    )
    await xxx.edit(get_string("audiotools_2"))
    out = f"heartless_voice_{token_hex(4)}.ogg"
    _, err = await bash(
        f"ffmpeg -i '{file.name}' -map 0:a -codec:a libopus -b:a 100k -vbr on -y '{out}'"
    )
    if not os.path.exists(out) or os.path.getsize(out) == 0:
        os.remove(file.name)
        if os.path.exists(out):
            os.remove(out)
        return await xxx.edit(f"`Failed to convert to voice!`\n`{err or 'no output'}`")
    try:
        # Send as an actual voice note (no caption / no text overlay).
        await e.client.send_file(
            e.chat_id,
            out,
            voice_note=True,
            reply_to=r,
        )
    except Exception as er:
        LOGS.exception(er)
        os.remove(file.name)
        os.remove(out)
        return await xxx.edit("`Failed to send the voice message...`")
    await xxx.delete()
    os.remove(file.name)
    os.remove(out)


@heartless_cmd(pattern="atrim( (.*)|$)")
async def trim_aud(e):
    sec = e.pattern_match.group(1).strip()
    if not sec or "-" not in sec:
        return await eod(e, get_string("audiotools_3"))
    a, b = sec.split("-")
    if int(a) >= int(b):
        return await eod(e, get_string("audiotools_4"))
    vido = await e.get_reply_message()
    if vido and vido.media and mediainfo(vido.media).startswith(("video", "audio")):
        if hasattr(vido.media, "document"):
            vfile = vido.media.document
            name = vido.file.name
        else:
            vfile = vido.media
            name = ""
        if not name:
            name = dt.now().isoformat("_", "seconds") + ".mp4"
        xxx = await e.eor(get_string("audiotools_5"))
        c_time = time.time()
        file = await downloader(
            f"resources/downloads/{name}",
            vfile,
            xxx,
            c_time,
            f"Downloading {name}...",
        )

        o_size = os.path.getsize(file.name)
        d_time = time.time()
        diff = time_formatter((d_time - c_time) * 1000)
        file_name = file.name.split("/")[-1]
        stem = file_name.rsplit(".", 1)[0]
        out = f"{stem}_trimmed.m4a"
        if int(b) > int(await genss(file.name)):
            os.remove(file.name)
            return await eod(xxx, get_string("audiotools_6"))
        ss, dd = stdr(int(a)), stdr(int(b))
        xxx = await xxx.edit(
            f"Downloaded `{file.name}` of `{humanbytes(o_size)}` in `{diff}`.\n\nNow Trimming Audio from `{ss}` to `{dd}`..."
        )
        # Re-encode instead of stream-copying: "-acodec copy" into a raw .aac
        # container frequently produces an empty/invalid file, which Telegram
        # rejects with "The number of file parts is invalid".
        cmd = f'ffmpeg -i "{file.name}" -ss {ss} -to {dd} -vn -c:a aac -b:a 192k "{out}" -y'
        _, err = await bash(cmd)
        os.remove(file.name)
        if not os.path.exists(out) or os.path.getsize(out) == 0:
            return await eod(xxx, f"`Failed to trim the audio!`\n`{err or 'no output'}`")
        attributes = await set_attributes(out)
        caption = get_string("audiotools_7").format(ss, dd)
        try:
            await e.client.send_file(
                e.chat_id,
                out,
                caption=caption,
                attributes=attributes,
                force_document=False,
                reply_to=e.reply_to_msg_id,
            )
        finally:
            if os.path.exists(out):
                os.remove(out)
        await xxx.delete()
    else:
        await e.eor(get_string("audiotools_1"), time=5)


@heartless_cmd(pattern="extractaudio$")
async def ex_aud(e):
    reply = await e.get_reply_message()
    if not (reply and reply.media and mediainfo(reply.media).startswith("video")):
        return await e.eor(get_string("audiotools_8"))
    name = reply.file.name or "video.mp4"
    vfile = reply.media.document
    msg = await e.eor(get_pstring("com_1", "load"))
    c_time = time.time()
    file = await downloader(
        f"resources/downloads/{name}",
        vfile,
        msg,
        c_time,
        f"Downloading {name}...",
    )

    out_file = f"{file.name}.aac"
    cmd = f"ffmpeg -i {file.name} -vn -acodec copy {out_file}"
    o, err = await bash(cmd)
    os.remove(file.name)
    attributes = await set_attributes(out_file)

    f_time = time.time()
    try:
        fo = await uploader(out_file, out_file, f_time, msg, f"Uploading {out_file}...")

    except FileNotFoundError:
        return await eor(msg, get_string("audiotools_9"))
    await e.reply(
        get_string("audiotools_10"),
        file=fo,
        thumb=ULTConfig.thumb,
        attributes=attributes,
    )
    await msg.delete()

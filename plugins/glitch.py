"""

✘ Commands Available -

•`{i}wglitch <replt to media>`
    gives a glitchy gif.

"""
import os

from . import bash, eor, get_string, mediainfo, ultroid_cmd


@ultroid_cmd(pattern="wglitch$")
async def _(e):
    try:
        import glitch_me  # ignore :pylint
    except ModuleNotFoundError:
        await bash(
            "pip install -e git+https://github.com/1Danish-00/glitch_me.git#egg=glitch_me"
        )
    reply = await e.get_reply_message()
    if not (reply and reply.media):
        return await eor(e, "Reply to any media")
    wut = mediainfo(reply.media)
    if not wut.startswith(("pic", "sticker")):
        return await eor(e, get_string("com_4"))
    xx = await eor(e, "`Gliching...`")
    ok = await e.client.download_media(reply.media)
    cmd = f"glitch_me gif --line_count 200 -f 10 -d 50 '{ok}' heartless.gif"
    stdout, stderr = await bash(cmd)
    await e.reply(file="heartless.gif", force_document=False)
    await xx.delete()
    os.remove(ok)
    os.remove("heartless.gif")

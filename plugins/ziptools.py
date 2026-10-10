"""
✘ Commands Available

• `{i}zip <reply to file>`
    zip the replied file
    To set password on zip: `{i}zip <password>` reply to file

• `{i}unzip <reply to zip file>`
    unzip the replied file.

• `{i}azip <reply to file>`
   add file to batch for batch upload zip

• `{i}dozip`
   upload batch zip the files u added from `{i}azip`
   To set Password: `{i}dozip <password>`

"""

import os
import shlex
import time

from . import (
    HNDLR,
    ULTConfig,
    asyncio,
    bash,
    downloader,
    get_all_files,
    get_string,
    get_pstring,
    heartless_cmd,
    uploader,
)


@heartless_cmd(pattern="zip( (.*)|$)")
async def zipp(event):
    reply = await event.get_reply_message()
    t = time.time()
    if not reply:
        await event.eor(get_string("zip_1"))
        return
    xx = await event.eor(get_pstring("com_1", "load"))
    file = None
    if reply.media:
        if hasattr(reply.media, "document"):
            image = await downloader(
                reply.file.name, reply.media.document, xx, t, get_pstring("com_5", "load")
            )
            file = image.name
        else:
            file = await event.download_media(reply)
    if not file or not os.path.isfile(file):
        await xx.edit(get_string("zip_1"))
        return
    base, _ = os.path.splitext(file)
    inp = base + ".zip"
    password = event.pattern_match.group(1).strip()
    if password:
        await bash(
            f"zip -r --password {shlex.quote(password)} {shlex.quote(inp)} {shlex.quote(file)}"
        )
    else:
        await bash(f"zip -r {shlex.quote(inp)} {shlex.quote(file)}")
    if not os.path.isfile(inp):
        await xx.edit("`Failed to create zip archive. Is 'zip' installed?`")
        return
    k = time.time()
    xxx = await uploader(inp, inp, k, xx, get_pstring("com_6", "load"))
    await event.client.send_file(
        event.chat_id,
        xxx,
        force_document=True,
        thumb=ULTConfig.thumb,
        caption=f"`{xxx.name}`",
        reply_to=reply,
    )
    os.remove(inp)
    os.remove(file)
    await xx.delete()


@heartless_cmd(pattern="unzip( (.*)|$)")
async def unzipp(event):
    reply = await event.get_reply_message()
    file = event.pattern_match.group(1).strip()
    t = time.time()
    if not ((reply and reply.media) or file):
        await event.eor(get_string("zip_1"))
        return
    xx = await event.eor(get_pstring("com_1", "load"))
    if reply.media:
        if not hasattr(reply.media, "document"):
            return await xx.edit(get_string("zip_3"))
        file = reply.media.document
        if not reply.file.name.endswith(("zip", "rar", "exe")):
            return await xx.edit(get_string("zip_3"))
        image = await downloader(
            reply.file.name, reply.media.document, xx, t, get_pstring("com_5", "load")
        )
        file = image.name
    if os.path.isdir("unzip"):
        await bash("rm -rf unzip")
    os.mkdir("unzip")
    await bash(f"7z x {file} -aoa -ounzip")
    await asyncio.sleep(4)
    ok = get_all_files("unzip")
    for x in ok:
        k = time.time()
        xxx = await uploader(x, x, k, xx, get_pstring("com_6", "load"))
        await event.client.send_file(
            event.chat_id,
            xxx,
            force_document=True,
            thumb=ULTConfig.thumb,
            caption=f"`{xxx.name}`",
        )
    await xx.delete()


@heartless_cmd(pattern="addzip$")
async def azipp(event):
    reply = await event.get_reply_message()
    t = time.time()
    if not (reply and reply.media):
        await event.eor(get_string("zip_1"))
        return
    xx = await event.eor(get_pstring("com_1", "load"))
    if not os.path.isdir("zip"):
        os.mkdir("zip")
    if reply.media:
        if hasattr(reply.media, "document"):
            file = reply.media.document
            image = await downloader(
                f"zip/{reply.file.name}",
                reply.media.document,
                xx,
                t,
                get_pstring("com_5", "load"),
            )

            file = image.name
        else:
            file = await event.download_media(reply.media, "zip/")
    await xx.edit(
        f"Downloaded `{file}` succesfully\nNow Reply To Other Files To Add And Zip all at once"
    )


@heartless_cmd(pattern="dozip( (.*)|$)")
async def do_zip(event):
    if not os.path.isdir("zip"):
        return await event.eor(get_string("zip_2").format(HNDLR))
    xx = await event.eor(get_pstring("com_1", "load"))
    password = event.pattern_match.group(1).strip()
    if password:
        await bash(
            f"zip -r --password {shlex.quote(password)} heartless.zip zip/*"
        )
    else:
        await bash("zip -r heartless.zip zip/*")
    if not os.path.isfile("heartless.zip"):
        await bash("rm -rf zip")
        await xx.edit("`Failed to create zip archive. Is 'zip' installed?`")
        return
    k = time.time()
    xxx = await uploader("heartless.zip", "heartless.zip", k, xx, get_pstring("com_6", "load"))
    await event.client.send_file(
        event.chat_id,
        xxx,
        force_document=True,
        thumb=ULTConfig.thumb,
    )
    await bash("rm -rf zip")
    os.remove("heartless.zip")
    await xx.delete()

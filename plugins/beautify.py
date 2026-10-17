from . import get_help

__doc__ = get_help("help_beautify")


import os
import random

from telethon.utils import get_display_name

from . import Carbon, get_string, get_pstring, inline_mention, heartless_cmd

_colorspath = "resources/colorlist.txt"

if os.path.exists(_colorspath):
    with open(_colorspath, "r") as f:
        all_col = [c.strip() for c in f.read().split() if c.strip()]
else:
    all_col = []

if not all_col:
    all_col = [
        "White",
        "Black",
        "AliceBlue",
        "DarkCyan",
        "DeepSkyBlue",
        "DarkTurquoise",
        "MediumVioletRed",
        "Aquamarine",
        "PowderBlue",
    ]

DEFAULT_COLOR = "White"

# ray.so has no public HTTP API any more, so the command is rendered with
# Carbon.  These are the theme names accepted by the rendering backend.
RaySoTheme = [
    "breeze",
    "dracula",
    "nord",
    "one-dark",
    "monokai",
    "synthwave-84",
    "night-owl",
    "material",
]


async def _get_code(event, arg_text=None):
    """Return the snippet to render; a replied message takes precedence."""
    if event.reply_to_msg_id:
        reply = await event.get_reply_message()
        if reply is None:
            return arg_text or ""
        if reply.media:
            path = await event.client.download_media(reply)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            finally:
                os.remove(path)
        return reply.message or ""
    return (arg_text or "").strip()


@heartless_cmd(pattern="(rc|c)arbon(?:$| (.*))")
async def cr_bn(event):
    xxxx = await event.eor(get_pstring("com_1", "load"))
    te = event.pattern_match.group(1)
    args = event.pattern_match.group(2)
    col = random.choice(all_col) if te.startswith("r") else DEFAULT_COLOR
    code = await _get_code(event, args)
    if not code:
        return await xxxx.eor(get_string("carbon_2"))
    xx = await Carbon(code=code, file_name="heartless", backgroundColor=col)
    if isinstance(xx, dict):
        return await xxxx.edit(f"`{xx.get('error', xx)}`")
    await xxxx.delete()
    await event.reply(
        f"Carbonised by {inline_mention(event.sender)}",
        file=xx,
        force_document=True,
    )


@heartless_cmd(pattern="ccarbon(?:$| (.*))")
async def crbn(event):
    args = (event.pattern_match.group(1) or "").strip()
    if not args:
        return await event.eor(get_string("carbon_3"))
    msg = await event.eor(get_pstring("com_1", "load"))
    if event.reply_to_msg_id:
        color = args.split()[0]
        code = await _get_code(event)
    else:
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            return await msg.eor(get_string("carbon_3"))
        color, code = parts
    if not code:
        return await msg.eor(get_string("carbon_2"))
    xx = await Carbon(code=code, backgroundColor=color)
    if isinstance(xx, dict):
        return await msg.edit(f"`{xx.get('error', xx)}`")
    await msg.delete()
    await event.reply(
        f"Carbonised by {inline_mention(event.sender)}",
        file=xx,
        force_document=True,
    )


@heartless_cmd(pattern="rayso(?:$| (.*))")
async def pass_on(ult):
    proc = await ult.eor(get_pstring("com_1", "load"))
    args = (ult.pattern_match.group(1) or "").strip()
    title = get_display_name(ult.chat)
    theme, text = None, None
    if args:
        first, _, rest = args.partition(" ")
        if first == "list":
            return await proc.eor(
                "**List of Rayso Themes:**\n"
                + "\n".join(f"- `{th_}`" for th_ in RaySoTheme)
            )
        if first in RaySoTheme:
            theme = first
            text = rest.strip() or None
        else:
            text = args
    if ult.is_reply:
        msg = await ult.get_reply_message()
        text = msg.message
        title = get_display_name(msg.sender)
    if theme not in RaySoTheme:
        theme = random.choice(RaySoTheme)
    if not text:
        return await proc.eor("`Give some text (or reply to a message) to render!`")
    xx = await Carbon(code=text, file_name="rayso", rayso=True, theme=theme)
    if isinstance(xx, dict):
        return await proc.edit(f"`{xx.get('error', xx)}`")
    await proc.reply(file=xx)
    await proc.try_delete()

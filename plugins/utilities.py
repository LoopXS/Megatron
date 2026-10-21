"""
✘ Commands Available -

• `{i}kickme` : Leaves the group.

• `{i}date` : Show Calender.

• `{i}listreserved`
    List all usernames (channels/groups) you own.

• `{i}stats` : See your profile stats.

• `{i}bcal <equation>`
    A simple calculator.

• `{i}paste` - `Include long text / Reply to text file.`

• `{i}info <username/userid/chatid>`
    Reply to someone's msg.

• `{i}invite <username/userid>`
    Add user to the chat.

• `{i}rmbg <reply to pic>`
    Remove background from that picture.

• `{i}graph <reply to media/text>`
    Text → Telegraph page.
    Media → dbimg.app via docs curl (DB `DBIMG_KEY`).
    `{i}graph` — no password, no expiry
    `{i}graph <password>` — password, no expiry
    `{i}graph <password> 1d|1w|1m|3m` — password + expiry

• `{i}json <reply to msg>`
    Get the json encoding of the message.

• `{i}suggest <reply to message> or <poll title>`
    Create a Yes/No poll for the replied suggestion.

• `{i}ipinfo <ipAddress>` : Get info about that IP address.

• `{i}cpy <reply to message>`
   Copy the replied message, with formatting. Expires in 24hrs.
• `{i}pst`
   Paste the copied message, with formatting.

• `{i}thumb <reply file>` : Download the thumbnail of the replied file.

• `{i}getpost <message link>`
  Get media from chats with forward/copy restrictions.
"""

import calendar
import contextlib
import html
import io
import mimetypes
import os
import re
import tempfile
import asyncio
import pathlib
import time
import jdatetime
from pytz import timezone
from datetime import datetime as dt

import requests

try:
    from PIL import Image
except ImportError:
    Image = None

from CythonX._misc._assistant import asst_cmd
from CythonX.dB.gban_mute_db import is_gbanned
from CythonX.fns.tools import get_chat_and_msgid

from telethon.errors.rpcerrorlist import (
    ChatForwardsRestrictedError,
    UserBotError,
    YouBlockedUserError,
)
from telethon.events import NewMessage
from telethon.tl.custom import Dialog
from telethon.tl.functions.channels import (
    GetAdminedPublicChannelsRequest,
    InviteToChannelRequest,
    LeaveChannelRequest,
)
from telethon.tl.functions.contacts import GetBlockedRequest
from telethon.tl.functions.messages import AddChatUserRequest, GetAllStickersRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import (
    Channel,
    Chat,
    InputMediaPoll,
    Poll,
    PollAnswer,
    TLObject,
    User,
)
from telethon.utils import get_peer_id

from CythonX.fns.info import get_chat_info

from . import (
    HNDLR,
    LOGS,
    Image,
    ReTrieveFile,
    Telegraph,
    asst,
    async_searcher,
    bash,
    check_filename,
    eod,
    eor,
    get_paste,
    get_string,
    get_pstring,
    inline_mention,
    json_parser,
    mediainfo,
    udB,
    heartless_cmd,
    heartless_bot,
)

# =================================================================#

TMP_DOWNLOAD_DIRECTORY = "resources/downloads/"

_copied_msg = {}


@heartless_cmd(pattern="kickme$", fullsudo=True)
async def leave(ult):
    await ult.eor(f"`{ult.client.me.first_name} has left this group, bye!!.`")
    await ult.client(LeaveChannelRequest(ult.chat_id))


@heartless_cmd(
    pattern="date$",
)
async def date(event):
    m = dt.now().month
    y = dt.now().year
    tehran = timezone("Asia/Tehran")
    ndate = jdatetime.datetime.now(tehran)
    t = ndate.strftime("%H:%M:%S")
    d = dt.now().strftime("- %B %d, %Y")
    k = calendar.month(y, m)
    k = f"<code>{k}</code>"
    k = k.replace(f"{z:2}", f"</code><u><b>{z:2}</b></u><code>")
    await event.respond(f"{k}\n\n<code>{d}</code>\n<code>{t}</code>", parse_mode="html")



@heartless_cmd(
    pattern="listreserved$",
)
async def _(event):
    result = await event.client(GetAdminedPublicChannelsRequest())
    if not result.chats:
        return await event.eor("`No username Reserved`")
    output_str = "".join(
        f"- {channel_obj.title} @{channel_obj.username} \n"
        for channel_obj in result.chats
    )
    await event.eor(output_str)


@heartless_cmd(
    pattern="stats$",
)
async def stats(
    event: NewMessage.Event,
):
    ok = await event.eor("`Collecting stats...`")
    start_time = time.time()
    private_chats = 0
    bots = 0
    groups = 0
    broadcast_channels = 0
    admin_in_groups = 0
    creator_in_groups = 0
    admin_in_broadcast_channels = 0
    creator_in_channels = 0
    unread_mentions = 0
    unread = 0
    dialog: Dialog
    async for dialog in event.client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, Channel) and entity.broadcast:
            broadcast_channels += 1
            if entity.creator or entity.admin_rights:
                admin_in_broadcast_channels += 1
            if entity.creator:
                creator_in_channels += 1

        elif (isinstance(entity, Channel) and entity.megagroup) or isinstance(
            entity, Chat
        ):
            groups += 1
            if entity.creator or entity.admin_rights:
                admin_in_groups += 1
            if entity.creator:
                creator_in_groups += 1

        elif isinstance(entity, User):
            private_chats += 1
            if entity.bot:
                bots += 1

        unread_mentions += dialog.unread_mentions_count
        unread += dialog.unread_count
    stop_time = time.time() - start_time
    try:
        ct = (await event.client(GetBlockedRequest(1, 0))).count
    except AttributeError:
        ct = 0
    try:
        sp = await event.client(GetAllStickersRequest(0))
        sp_count = len(sp.sets)
    except BaseException:
        sp_count = 0
    full_name = inline_mention(event.client.me)
    response = f"🔸 **Stats for {full_name}** \n\n"
    response += f"**Private Chats:** {private_chats} \n"
    response += f"**  •• **`Users: {private_chats - bots}` \n"
    response += f"**  •• **`Bots: {bots}` \n"
    response += f"**Groups:** {groups} \n"
    response += f"**Channels:** {broadcast_channels} \n"
    response += f"**Admin in Groups:** {admin_in_groups} \n"
    response += f"**  •• **`Creator: {creator_in_groups}` \n"
    response += f"**  •• **`Admin Rights: {admin_in_groups - creator_in_groups}` \n"
    response += f"**Admin in Channels:** {admin_in_broadcast_channels} \n"
    response += f"**  •• **`Creator: {creator_in_channels}` \n"
    response += f"**  •• **`Admin Rights: {admin_in_broadcast_channels - creator_in_channels}` \n"
    response += f"**Unread:** {unread} \n"
    response += f"**Unread Mentions:** {unread_mentions} \n"
    response += f"**Blocked Users:** {ct}\n"
    response += f"**Total Stickers Pack Installed :** `{sp_count}`\n\n"
    response += f"**__It Took:__** {stop_time:.02f}s \n"
    await ok.edit(response)


@heartless_cmd(pattern="paste( (.*)|$)", manager=True, allow_all=True)
async def _(event):
    try:
        input_str = event.text.split(maxsplit=1)[1]
    except IndexError:
        input_str = None
    xx = await event.eor("` 《 Pasting... 》 `")
    downloaded_file_name = None
    if input_str:
        message = input_str
    elif event.reply_to_msg_id:
        previous_message = await event.get_reply_message()
        if previous_message.media:
            downloaded_file_name = await event.client.download_media(
                previous_message,
                "./resources/downloads",
            )
            with open(downloaded_file_name, "r") as fd:
                message = fd.read()
            os.remove(downloaded_file_name)
        else:
            message = previous_message.message
    else:
        message = None
    if not message:
        return await xx.eor(
            "`Reply to a Message/Document or Give me Some Text !`", time=5
        )
    done, key = await get_paste(message)
    if not done:
        return await xx.eor(key)
    link = f"https://spaceb.in/{key}"
    raw = f"https://spaceb.in/api/{key}/raw"
    reply_text = (
        f"• **Pasted to SpaceBin :** [Space]({link})\n• **Raw Url :** : [Raw]({raw})"
    )
    try:
        if event.client._bot:
            return await xx.eor(reply_text)
        ok = await event.client.inline_query(asst.me.username, f"pasta-{key}")
        await ok[0].click(event.chat_id, reply_to=event.reply_to_msg_id, hide_via=True)
        await xx.delete()
    except BaseException as e:
        LOGS.exception(e)
        await xx.edit(reply_text)


@heartless_cmd(
    pattern="bcal",
)
async def _(event):
    x = await eor(event, get_pstring("com_1", "load"))
    cmd = event.text.split(" ", maxsplit=1)[1]
    event.message.id
    if event.reply_to_msg_id:
        event.reply_to_msg_id
    wtf = f"print({cmd})"
    old_stderr = sys.stderr
    old_stdout = sys.stdout
    redirected_output = sys.stdout = io.StringIO()
    redirected_error = sys.stderr = io.StringIO()
    stdout, stderr, exc = None, None, None
    try:
        await aexec(wtf, event)
    except Exception:
        exc = traceback.format_exc()
    stdout = redirected_output.getvalue()
    stderr = redirected_error.getvalue()
    sys.stdout = old_stdout
    sys.stderr = old_stderr
    evaluation = ""
    if exc:
        evaluation = exc
    elif stderr:
        evaluation = stderr
    elif stdout:
        evaluation = stdout
    else:
        evaluation = "`Something went wrong`"

    final_output = """
**ⲈQⳘⲀⲦⲒⲞⲚ**:
`{}`
**ⲊⲞⳐⳘⲦⲒⲞⲚ**:
`{}`
""".format(
        cmd,
        evaluation,
    )
    await x.edit(final_output)


async def aexec(code, event):
    exec(f"async def __aexec(event): " + "".join(f"\n {l}" for l in code.split("\n")))
    return await locals()["__aexec"](event)


@heartless_cmd(pattern="info( (.*)|$)", manager=True, assistant=True)
async def _(event):
    if match := event.pattern_match.group(1).strip():
        try:
            user = await event.client.parse_id(match)
        except Exception as er:
            return await event.eor(str(er))
    elif event.is_reply:
        rpl = await event.get_reply_message()
        user = rpl.sender_id
    else:
        user = event.chat_id
    xx = await event.eor(get_pstring("com_1", "load"))
    try:
        _ = await event.client.get_entity(user)
    except Exception as er:
        return await xx.edit(f"**ERROR :** {er}")
    if not isinstance(_, User):
        try:
            peer = get_peer_id(_)
            photo, capt = await get_chat_info(_, event)
            if is_gbanned(peer):
                capt += "\n•<b> Is Gbanned:</b> <code>True</code>"
            if not photo:
                return await xx.eor(capt, parse_mode="html")
            await event.client.send_message(
                event.chat_id, capt[:1024], file=photo, parse_mode="html"
            )
            await xx.delete()
        except Exception as er:
            await event.eor("**ERROR ON CHATINFO**\n" + str(er))
        return
    try:
        full_user = (await event.client(GetFullUserRequest(user))).full_user
    except Exception as er:
        return await xx.edit(f"ERROR : {er}")
    user = _
    user_photos = (
        await event.client.get_profile_photos(user.id, limit=0)
    ).total or "NaN"
    user_id = user.id
    first_name = html.escape(user.first_name)
    if first_name is not None:
        first_name = first_name.replace("\u2060", "")
    last_name = user.last_name
    last_name = (
        last_name.replace("\u2060", "") if last_name else ("Last Name not found")
    )
    user_bio = full_user.about
    if user_bio is not None:
        user_bio = html.escape(full_user.about)
    common_chats = full_user.common_chats_count
    if user.photo:
        dc_id = user.photo.dc_id
    else:
        dc_id = "Need a Profile Picture to check this"
    chat = "@creationdatebot"
    async with event.client.conversation(chat) as conv:
        try:
            if bool(
                (
                    await event.client(GetFullUserRequest(user_id))
                ).full_user.private_forward_name
            ):
                create = "----"
            else:
                await conv.send_message(f"/id {user_id}")
                check = await conv.get_response()
                create = check.message
                await event.client.send_read_acknowledge(conv.chat_id)
        except YouBlockedUserError:
            LOGS.info("Please unblock bot and try again")
            return
    caption = """<b>Exᴛʀᴀᴄᴛᴇᴅ Dᴀᴛᴀ Fʀᴏᴍ Dᴀᴛᴀʙᴀsᴇ<b>
<b>••Tᴇʟᴇɢʀᴀᴍ ID</b>: <code>{}</code>
<b>••Pᴇʀᴍᴀɴᴇɴᴛ Lɪɴᴋ</b>: <a href='tg://user?id={}'>Click Here</a>
<b>••Fɪʀsᴛ Nᴀᴍᴇ</b>: <code>{}</code>
<b>••Sᴇᴄᴏɴᴅ Nᴀᴍᴇ</b>: <code>{}</code>
<b>••Bɪᴏ</b>: <code>{}</code>
<b>••Dᴄ ID</b>: <code>{}</code>
<b>••Nᴏ. Oғ PғPs</b> : <code>{}</code>
<b>••Cʀᴇᴀᴛɪᴏɴ Dᴀᴛᴇ</b> : <code>{}</code>
<b>••Is Rᴇsᴛʀɪᴄᴛᴇᴅ</b>: <code>{}</code>
<b>••Vᴇʀɪғɪᴇᴅ</b>: <code>{}</code>
<b>••Is Pʀᴇᴍɪᴜᴍ</b>: <code>{}</code>
<b>••Is A Bᴏᴛ</b>: <code>{}</code>
<b>••Gʀᴏᴜᴘs Iɴ Cᴏᴍᴍᴏɴ</b>: <code>{}</code>
""".format(
        user_id,
        user_id,
        first_name,
        last_name,
        user_bio,
        dc_id,
        user_photos,
        create,
        user.restricted,
        user.verified,
        user.premium,
        user.bot,
        common_chats,
    )
    if chk := is_gbanned(user_id):
        caption += f"""<b>••Gʟᴏʙᴀʟʟʏ Bᴀɴɴᴇᴅ</b>: <code>True</code>
<b>••Rᴇᴀsᴏɴ</b>: <code>{chk}</code>"""
    await event.client.send_message(
        event.chat_id,
        caption,
        reply_to=event.reply_to_msg_id,
        parse_mode="HTML",
        file=full_user.profile_photo,
        force_document=False,
        silent=True,
    )
    await xx.delete()


@heartless_cmd(
    pattern="invite( (.*)|$)",
    groups_only=True,
)
async def _(ult):
    xx = await ult.eor(get_pstring("com_1", "load"))
    to_add_users = ult.pattern_match.group(1).strip()
    if not ult.is_channel and ult.is_group:
        for user_id in to_add_users.split(" "):
            try:
                await ult.client(
                    AddChatUserRequest(
                        chat_id=ult.chat_id,
                        user_id=await ult.client.parse_id(user_id),
                        fwd_limit=1000000,
                    ),
                )
                await xx.edit(f"Successfully invited `{user_id}` to `{ult.chat_id}`")
            except Exception as e:
                await xx.edit(str(e))
    else:
        for user_id in to_add_users.split(" "):
            try:
                await ult.client(
                    InviteToChannelRequest(
                        channel=ult.chat_id,
                        users=[await ult.client.parse_id(user_id)],
                    ),
                )
                await xx.edit(f"Successfully invited `{user_id}` to `{ult.chat_id}`")
            except UserBotError:
                await xx.edit(
                    f"Bots can only be added as Admins in Channel.\nBetter Use `{HNDLR}promote {user_id}`"
                )
            except Exception as e:
                await xx.edit(str(e))


@heartless_cmd(
    pattern="rmbg($| (.*))",
)
async def abs_rmbg(event):
    RMBG_API = udB.get_key("RMBG_API")
    if not RMBG_API:
        return await event.eor(
            "Get your API key from [here](https://www.remove.bg/) for this plugin to work.",
        )
    match = event.pattern_match.group(1).strip()
    reply = await event.get_reply_message()
    if match and os.path.exists(match):
        dl = match
    elif reply and reply.media:
        if reply.document and reply.document.thumbs:
            dl = await reply.download_media(thumb=-1)
        else:
            dl = await reply.download_media()
    else:
        return await eod(
            event, f"Use `{HNDLR}rmbg` as reply to a pic to remove its background."
        )
    if not (dl and dl.endswith(("webp", "jpg", "png", "jpeg"))):
        os.remove(dl)
        return await event.eor(get_string("com_4"))
    if dl.endswith("webp"):
        file = f"{dl}.png"
        Image.open(dl).save(file)
        os.remove(dl)
        dl = file
    xx = await event.eor("`Sending to remove.bg`")
    dn, out = await ReTrieveFile(dl)
    os.remove(dl)
    if not dn:
        dr = out["errors"][0]
        de = dr.get("detail", "")
        return await xx.edit(
            f"**ERROR ~** `{dr['title']}`,\n`{de}`",
        )
    zz = Image.open(out)
    if zz.mode != "RGB":
        zz.convert("RGB")
    wbn = check_filename("rmbg.webp")
    zz.save(wbn, "webp")
    await event.client.send_file(
        event.chat_id,
        out,
        force_document=True,
        reply_to=reply,
    )
    await event.client.send_file(event.chat_id, wbn, reply_to=reply)
    os.remove(out)
    os.remove(wbn)
    await xx.delete()



_DBIMG_BASE = "https://dbimg.app"
_DBIMG_UPLOAD = f"{_DBIMG_BASE}/api/upload"
# User-facing tokens → API expiresIn (docs: 1d / 1w / 1mo / 3mo)
_GRAPH_EXPIRE_MAP = {
    "1d": "1d",
    "1w": "1w",
    "1m": "1mo",
    "1mo": "1mo",
    "3m": "3mo",
    "3mo": "3mo",
}


def _graph_guess_mime(path: str) -> str:
    mime = mimetypes.MimeTypes().guess_type(path)[0]
    if mime:
        return mime
    ext = os.path.splitext(path)[1].lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
    }.get(ext, "application/octet-stream")


async def _graph_prepare_dbimg(path: str, media_kind: str) -> str:
    """
    Light prep for dbimg (supports video/audio/gif natively).
    Only convert Telegram stickers / .tgs; keep original media otherwise.
    """
    kind = (media_kind or "").lower()
    lower = path.lower()

    if kind.endswith("animated") or lower.endswith(".tgs"):
        out = f"{path}.gif"
        await bash(f"lottie_convert.py '{path}' '{out}'")
        with contextlib.suppress(Exception):
            os.remove(path)
        if os.path.isfile(out) and os.path.getsize(out) > 0:
            return out
        return path

    return path


def _graph_parse_media_args(raw: str) -> tuple[str | None, str | None]:
    """
    Parse `.graph` media args → (password|None, user_expiry|None).

    User expiry tokens: ``1d`` / ``1w`` / ``1m`` / ``3m``
    (mapped to API ``1d`` / ``1w`` / ``1mo`` / ``3mo`` at upload).
    """
    parts = (raw or "").split()
    if not parts:
        return None, None
    if len(parts) == 1:
        token = parts[0]
        if token.lower() in _GRAPH_EXPIRE_MAP:
            return None, token.lower()
        return token, None
    password = parts[0]
    expires = parts[1].lower()
    if expires not in _GRAPH_EXPIRE_MAP:
        raise ValueError(
            f"Invalid expiry `{parts[1]}`. Use: 1d / 1w / 1m / 3m"
        )
    if len(parts) > 2:
        raise ValueError("Too many args. Usage: `.graph [password] [1d|1w|1m|3m]`")
    return password, expires


def _dbimg_abs(url: str | None) -> str:
    if not url:
        return ""
    text = str(url).strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text
    if not text.startswith("/"):
        text = "/" + text
    return _DBIMG_BASE + text


def _dbimg_api_key() -> str:
    """DB ``DBIMG_KEY`` (or ``DBIMG``) — value like ``dbimg_xxxxx``."""
    key = (
        udB.get_key("DBIMG_KEY")
        or udB.get_key("DBIMG")
        or udB.get_key("DBIMG_API")
        or ""
    )
    text = str(key).strip()
    if text.lower().startswith("bearer "):
        text = text[7:].strip()
    return text


def _dbimg_upload_sync(
    path: str,
    *,
    password: str | None = None,
    expires_in: str | None = None,
) -> dict:
    """
    Docs-style upload via ``curl`` (no Python HTTP / Cloudflare scraper):

      curl -X POST https://dbimg.app/api/upload \\
        -H "Authorization: Bearer dbimg_xxxxx" \\
        -F "file=@photo.jpg" \\
        [-F "password=…" ] [-F "expiresIn=1d|1w|1mo|3mo"]
    """
    import shutil
    import subprocess

    api_key = _dbimg_api_key()
    if not api_key:
        raise RuntimeError(
            "Set DB key `DBIMG_KEY` to your dbimg API token "
            "(https://dbimg.app → dashboard → API keys)."
        )
    if not shutil.which("curl"):
        raise RuntimeError("`curl` is required for dbimg uploads.")

    mime = _graph_guess_mime(path)
    raw_name = os.path.basename(path) or "upload.bin"
    # Keep curl -F filename safe (no ; " \)
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in raw_name)
    name = safe or "upload.bin"
    abs_path = os.path.abspath(path)
    # Map user 1m/3m → API 1mo/3mo (docs expiresIn values)
    api_expires = None
    if expires_in:
        api_expires = _GRAPH_EXPIRE_MAP.get(expires_in.lower(), expires_in)

    # Exact docs shape: Authorization Bearer + multipart -F file=@…
    file_arg = f"file=@{abs_path};filename={name};type={mime}"
    cmd = [
        "curl",
        "-sS",
        "-L",
        "-m",
        "120",
        "-X",
        "POST",
        _DBIMG_UPLOAD,
        "-H",
        f"Authorization: Bearer {api_key}",
        "-F",
        file_arg,
    ]
    if password:
        cmd.extend(["-F", f"password={password}"])
    if api_expires:
        cmd.extend(["-F", f"expiresIn={api_expires}"])

    last_err = None
    for attempt in range(3):
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=130,
                check=False,
            )
        except subprocess.TimeoutExpired:
            last_err = "curl timed out"
            time.sleep(1.2 * (attempt + 1))
            continue
        except Exception as exc:
            last_err = str(exc)
            time.sleep(1.2 * (attempt + 1))
            continue

        body = (proc.stdout or "").strip()
        if proc.returncode != 0 and not body:
            last_err = (proc.stderr or f"curl exit {proc.returncode}")[:200]
            time.sleep(1.2 * (attempt + 1))
            continue
        if (
            "Just a moment" in body
            or "cf-browser-verification" in body
            or "challenge-platform" in body
        ):
            last_err = "Cloudflare challenge HTML"
            time.sleep(1.5 * (attempt + 1))
            continue
        try:
            payload = json_parser(body)
        except Exception:
            last_err = f"bad JSON: {body[:180]}"
            time.sleep(1.0)
            continue
        if not isinstance(payload, dict):
            last_err = f"unexpected response: {body[:180]}"
            continue
        if payload.get("error") or payload.get("message"):
            err = payload.get("error") or payload.get("message")
            # Auth / validation — don't retry
            if any(
                x in str(err).lower()
                for x in ("api key", "unauthorized", "invalid", "required")
            ):
                raise RuntimeError(f"dbimg: {err}")
            last_err = str(err)
            time.sleep(1.0)
            continue
        if not (
            payload.get("shortId")
            or payload.get("mediaUrl")
            or payload.get("directUrl")
            or payload.get("shareUrl")
        ):
            last_err = f"missing urls: {body[:180]}"
            continue
        return payload

    raise RuntimeError(f"dbimg upload failed: {last_err}")


async def _dbimg_upload(
    path: str,
    *,
    password: str | None = None,
    expires_in: str | None = None,
) -> dict:
    return await asyncio.to_thread(
        _dbimg_upload_sync,
        path,
        password=password,
        expires_in=expires_in,
    )


def _dbimg_format_result(
    payload: dict,
    *,
    password: str | None,
    expires_in: str | None,
) -> str:
    """
    Docs response → user message.

    Public: ``mediaUrl`` / ``directUrl`` (+ CDN).
    Passworded: share page only. Always include ``deletionUrl`` when present.
    """
    short = payload.get("shortId") or ""
    has_password = bool(password) or bool(payload.get("hasPassword"))

    media_url = _dbimg_abs(
        payload.get("mediaUrl")
        or payload.get("directUrl")
        or payload.get("url")
    )
    if (
        not has_password
        and media_url.startswith(_DBIMG_BASE + "/image/")
        and short
    ):
        ext = os.path.splitext(media_url)[1] or ".jpg"
        media_url = f"https://cdn.dbimg.app/{short}{ext}"

    share_url = _dbimg_abs(payload.get("shareUrl")) or (
        f"{_DBIMG_BASE}/{short}" if short else ""
    )
    delete_url = _dbimg_abs(
        payload.get("deletionUrl") or payload.get("deleteUrl")
    )

    view_url = media_url or share_url
    if not view_url:
        raise RuntimeError(f"dbimg response missing URL: {payload!r}"[:200])

    lines = [f"Uploaded to [dbimg]({view_url}) !"]
    if not has_password and share_url and share_url != view_url:
        lines.append(f"Share: [page]({share_url})")
    if delete_url:
        lines.append(f"Delete: [link]({delete_url})")
    else:
        lines.append("Delete: _not provided by API_")
    if password:
        lines.append(f"Password: `{password}`")
    # Show user-facing expiry (1m/3m), not API 1mo/3mo
    if expires_in:
        lines.append(f"Expires: `{expires_in}`")
    elif payload.get("expiresAt"):
        lines.append(f"Expires: `{payload.get('expiresAt')}`")
    return "\n".join(lines)


@heartless_cmd(pattern="(graph|telegraph)( (.*)|$)", assistant=True, manager=True)
async def telegraphcmd(event):
    """Text → Telegraph page; media → dbimg.app (password / expiry optional)."""
    xx = await event.eor(get_pstring("com_1", "load"))
    raw_args = (
        event.pattern_match.group(3) or event.pattern_match.group(2) or ""
    ).strip()
    reply = await event.get_reply_message()
    if not reply:
        return await xx.eor("`Reply to Message.`")

    # Text → classic Telegraph page (title from args or Heartless).
    if not reply.media and reply.message:
        title = raw_args or "Heartless"
        content = reply.message
        makeit = Telegraph.create_page(
            title=title,
            content=[{"tag": "p", "children": [content]}],
        )
        return await xx.eor(
            f"Pasted to Telegraph : [Telegraph]({makeit['url']})",
            link_preview=False,
        )

    getit = await reply.download_media()
    if not getit:
        return await xx.eor("`Couldn't download media.`")
    dar = mediainfo(reply.media) or ""

    # Text-like documents → Telegraph paste (title from args).
    text_exts = (".txt", ".md", ".html", ".json", ".py", ".csv", ".log")
    if getit.lower().endswith(text_exts) or (
        "document" in dar.lower()
        and not any(
            getit.lower().endswith(x)
            for x in (
                ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm",
                ".mov", ".mp3", ".wav", ".ogg", ".mkv", ".avi",
            )
        )
    ):
        try:
            content = pathlib.Path(getit).read_text(
                encoding="utf-8", errors="ignore"
            )
        except Exception:
            with contextlib.suppress(Exception):
                os.remove(getit)
            return await xx.eor("`Unsupported file for Telegraph text paste.`")
        with contextlib.suppress(Exception):
            os.remove(getit)
        title = raw_args or "Heartless"
        makeit = Telegraph.create_page(
            title=title,
            content=[{"tag": "p", "children": [content]}],
        )
        return await xx.eor(
            f"Pasted to Telegraph : [Telegraph]({makeit['url']})",
            link_preview=False,
        )

    try:
        password, expires_in = _graph_parse_media_args(raw_args)
    except ValueError as e:
        with contextlib.suppress(Exception):
            os.remove(getit)
        return await xx.eor(f"`{e}`")

    try:
        getit = await _graph_prepare_dbimg(getit, dar)
    except Exception as e:
        with contextlib.suppress(Exception):
            os.remove(getit)
        return await xx.eor(f"`Couldn't prepare media: {e}`")

    try:
        payload = await _dbimg_upload(
            getit, password=password, expires_in=expires_in
        )
        msg = _dbimg_format_result(
            payload, password=password, expires_in=expires_in
        )
    except Exception as e:
        LOGS.warning("dbimg upload failed: %s", e)
        with contextlib.suppress(Exception):
            os.remove(getit)
        return await xx.eor(f"`Failed to upload:` `{e}`")
    with contextlib.suppress(Exception):
        os.remove(getit)
    return await xx.eor(msg, link_preview=True)


@heartless_cmd(pattern="json( (.*)|$)", assistant=True, manager=True)
async def _(event):
    reply_to_id = None
    match = event.pattern_match.group(1).strip()
    if event.reply_to_msg_id:
        msg = await event.get_reply_message()
        reply_to_id = event.reply_to_msg_id
    else:
        msg = event
        reply_to_id = event.message.id
    if match and hasattr(msg, match.split()[0]):
        msg = getattr(msg, match.split()[0])
        try:
            if hasattr(msg, "to_json"):
                msg = msg.to_json(ensure_ascii=False, indent=1)
            elif hasattr(msg, "to_dict"):
                msg = json_parser(msg.to_dict(), indent=1)
            else:
                msg = TLObject.stringify(msg)
        except Exception:
            pass
        msg = str(msg)
    else:
        msg = json_parser(msg.to_json(), indent=1)
    if "-t" in match:
        try:
            data = json_parser(msg)
            msg = json_parser(
                {key: data[key] for key in data.keys() if data[key]}, indent=1
            )
        except Exception:
            pass
    if len(msg) > 4096:
        with io.BytesIO(str.encode(msg)) as out_file:
            out_file.name = "json.txt"
            await event.client.send_file(
                event.chat_id,
                out_file,
                force_document=True,
                allow_cache=False,
                reply_to=reply_to_id,
            )
            await event.delete()
    else:
        await event.eor(f"```{msg or None}```")


@heartless_cmd(pattern="suggest( (.*)|$)", manager=True)
async def sugg(event):
    sll = event.text.split(maxsplit=1)
    try:
        text = sll[1]
    except IndexError:
        text = None
    if not (event.is_reply or text):
        return await eod(
            event,
            "`Please reply to a message to make a suggestion poll!`",
        )
    if event.is_reply and not text:
        reply = await event.get_reply_message()
        if reply.text and len(reply.text) < 35:
            text = reply.text
        else:
            text = "Do you Agree to Replied Suggestion ?"
    reply_to = event.reply_to_msg_id if event.is_reply else event.id
    try:
        await event.client.send_file(
            event.chat_id,
            file=InputMediaPoll(
                poll=Poll(
                    id=12345,
                    question=text,
                    answers=[PollAnswer("Yes", b"1"), PollAnswer("No", b"2")],
                ),
            ),
            reply_to=reply_to,
        )
    except Exception as e:
        return await eod(event, f"`Oops, you can't send polls here!\n\n{e}`")
    await event.delete()


@heartless_cmd(pattern="ipinfo( (.*)|$)")
async def ipinfo(event):
    ip = event.text.split()
    ipaddr = ""
    try:
        ipaddr = f"/{ip[1]}"
    except IndexError:
        ipaddr = ""
    det = await async_searcher(f"https://ipinfo.io{ipaddr}/geo", re_json=True)
    try:
        ip = det["ip"]
        city = det["city"]
        region = det["region"]
        country = det["country"]
        cord = det["loc"]
        try:
            zipc = det["postal"]
        except KeyError:
            zipc = "None"
        tz = det["timezone"]
        await eor(
            event,
            """
**IP Details Fetched.**

**IP:** `{}`
**City:** `{}`
**Region:** `{}`
**Country:** `{}`
**Co-ordinates:** `{}`
**Postal Code:** `{}`
**Time Zone:** `{}`
""".format(
                ip,
                city,
                region,
                country,
                cord,
                zipc,
                tz,
            ),
        )
    except BaseException:
        err = det["error"]["title"]
        msg = det["error"]["message"]
        await event.eor(f"ERROR:\n{err}\n{msg}", time=5)


@heartless_cmd(
    pattern="cpy$",
)
async def copp(event):
    msg = await event.get_reply_message()
    if not msg:
        return await event.eor(f"Use `{HNDLR}cpy` as reply to a message!", time=5)
    _copied_msg["CLIPBOARD"] = msg
    await event.eor(f"Copied. Use `{HNDLR}pst` to paste!", time=10)


@asst_cmd(pattern="pst$")
async def pepsodent(event):
    await toothpaste(event)


@heartless_cmd(
    pattern="pst$",
)
async def colgate(event):
    await toothpaste(event)


async def toothpaste(event):
    try:
        await event.respond(_copied_msg["CLIPBOARD"])
    except KeyError:
        return await eod(
            event,
            f"Nothing was copied! Use `{HNDLR}cpy` as reply to a message first!",
        )
    except Exception as ex:
        return await event.eor(str(ex), time=5)
    await event.delete()


@heartless_cmd(pattern="thumb$")
async def thumb_dl(event):
    reply = await event.get_reply_message()
    if not (reply and reply.file):
        return await eod(event, get_string("th_1"), time=5)
    if not reply.file.media.thumbs:
        return await eod(event, get_string("th_2"))
    await event.eor(get_pstring("com_1", "load"))
    x = await event.get_reply_message()
    m = await x.download_media(thumb=-1)
    await event.reply(file=m)
    os.remove(m)


def _parse_telegram_post_url(url: str):
    """
    Parse public or private Telegram message links.

    Returns (peer, msg_id) where peer is username (str) or -100 channel id (int).
    """
    text = (url or "").strip()
    # strip tracking / single flags
    text = text.split("?")[0].rstrip("/")
    # private: t.me/c/<internal_id>/<msg_id>[/<topic?>]
    priv = re.fullmatch(
        r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)"
        r"/c/(\d+)(?:/\d+)?/(\d+)",
        text,
        flags=re.I,
    )
    if priv:
        channel_id = int(priv.group(1))
        msg_id = int(priv.group(2))
        return int(f"-100{channel_id}"), msg_id
    # public: t.me/<username>/<msg_id>
    pub = re.fullmatch(
        r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)"
        r"/([A-Za-z][\w\d_]{3,})/(\d+)",
        text,
        flags=re.I,
    )
    if pub:
        username = pub.group(1)
        # reserved path segments that are not chats
        if username.lower() in {
            "c", "s", "joinchat", "addstickers", "share", "socks", "proxy",
            "setlanguage", "iv", "login", "confirmphone", "nft",
        }:
            return None
        return username, int(pub.group(2))
    return None


@heartless_cmd(pattern=r"getpost(?:\s+(.+))?$")
async def get_msgs(event):
    url = event.pattern_match.group(1)
    if not url:
        return await event.eor(
            "`Usage:`\n"
            "`.getpost https://t.me/c/3985749900/9`\n"
            "`.getpost https://t.me/username/123`",
            time=8,
        )
    parsed = _parse_telegram_post_url(url)
    if not parsed:
        return await event.eor(
            "`Invalid Telegram post URL.`\n"
            "Example:\n"
            "`.getpost https://t.me/c/3985749900/9`\n"
            "`.getpost https://t.me/username/123`",
            time=8,
        )
    peer_id, msg_id = parsed
    status = await event.eor("`Fetching message...`")
    try:
        msg = await event.client.get_messages(
            peer_id,
            ids=msg_id,
        )
        if not msg:
            return await status.edit("`Message not found.`")
        if not msg.media:
            return await status.edit(
                "`This message doesn't contain any media.`"
            )
        await status.edit("`Downloading media...`")
        if msg.grouped_id:
            start = max(1, msg.id - 15)
            end = msg.id + 15
            ids = list(range(start, end + 1))
            messages = await event.client.get_messages(
                peer_id,
                ids=ids,
            )
            album = [
                m for m in messages
                if m
                and m.media
                and m.grouped_id == msg.grouped_id
            ]
            album.sort(key=lambda m: m.id)
        else:
            album = [msg]
        if not album:
            return await status.edit("`No media found.`")
        with tempfile.TemporaryDirectory() as tmp:
            files = []
            for message in album:
                path = await event.client.download_media(
                    message,
                    file=tmp,
                )
                if path:
                    files.append(path)
            if not files:
                return await status.edit(
                    "`Failed to download media.`"
                )
            await status.edit("`Uploading media...`")
            await event.client.send_file(
                event.chat_id,
                files if len(files) > 1 else files[0],
                force_document=False,
                caption=msg.text or None,
            )
        await status.edit(
            f"`Successfully sent {len(files)} file(s)!`"
        )
        await asyncio.sleep(3)
        await status.delete()
    except Exception as e:
        await status.edit(
            f"**Error:**\n`{e}`"
    )

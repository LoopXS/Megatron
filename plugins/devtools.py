from . import get_help

__doc__ = get_help("help_devtools")

import inspect
import json
import os
import sys
import traceback
from io import BytesIO, StringIO
from os import remove
from pprint import pprint

import aiohttp

from telethon.utils import get_display_name

from CythonX import _ignore_eval

from . import *

# Used for Formatting Eval Code, if installed
try:
    import black
except ImportError:
    black = None
from random import choice

try:
    from yaml import safe_load
except ImportError:
    from CythonX.fns.tools import safe_load
from telethon.tl import functions

fn = functions


async def _upload_to_graph(file_path, domain="graph.org"):
    """Upload a local file to graph.org and return its public URL.

    Use aiohttp directly here.  The previous version routed the multipart
    request through async_searcher(), which can alter/handle multipart data
    in a way that makes graph.org return HTTP 400.
    """
    if not file_path or not os.path.isfile(file_path):
        raise FileNotFoundError(file_path)

    upload_url = f"https://{domain}/upload"

    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            with open(file_path, "rb") as media:
                form = aiohttp.FormData()
                form.add_field(
                    "file",
                    media,
                    filename=os.path.basename(file_path),
                    content_type="application/octet-stream",
                )

                async with session.post(
                    upload_url,
                    data=form,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (X11; Linux x86_64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/131.0 Safari/537.36"
                        ),
                    },
                ) as response:
                    raw = await response.read()
                    status = response.status
                    content_type = response.headers.get("Content-Type", "")

    except aiohttp.ClientError as exc:
        raise RuntimeError(f"Graph upload connection failed: {exc}") from exc

    body = raw.decode("utf-8", errors="replace").strip()

    if status >= 400:
        raise RuntimeError(
            f"Graph upload failed with HTTP {status}: {body[:500] or 'Unknown error'}"
        )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Graph upload returned invalid JSON "
            f"({content_type or 'unknown content type'}): {body[:500]}"
        ) from exc

    # graph.org/Telegraph normally returns:
    # [{"src": "/file/...."}]
    # Accept the common response variants as well.
    path = None

    if isinstance(payload, list) and payload:
        item = payload[0]
        if isinstance(item, dict):
            path = item.get("src") or item.get("url")
        elif isinstance(item, str):
            path = item

    elif isinstance(payload, dict):
        if payload.get("error"):
            raise RuntimeError(f"Graph upload error: {payload['error']}")
        path = payload.get("src") or payload.get("url")

    elif isinstance(payload, str):
        path = payload

    if not path:
        raise RuntimeError(f"Unexpected Graph upload response: {payload!r}")

    if path.startswith(("http://", "https://")):
        return path

    return f"https://{domain}{path}"


@heartless_cmd(
    pattern="sysinfo$",
)
async def _(e):
    xx = await e.eor(get_pstring("com_1", "load"))
    out = "neo.txt"
    if os.path.exists(out):
        remove(out)
    x, y = await bash("neofetch|sed 's/\x1B\\[[0-9;\\?]*[a-zA-Z]//g' > " + out)
    try:
        if y and y.endswith("NOT_FOUND"):
            return await xx.edit(f"Error: `{y}`")
        with open(out, "r", encoding="utf-8") as neo:
            p = (neo.read()).replace("\n\n", "")
        haa = None
        try:
            haa = await Carbon(
                code=p,
                file_name="neofetch",
                backgroundColor=choice(ATRA_COL),
            )
        except Exception as er:
            # The public Carbon API is unreliable and often down;
            # fall back to the raw neofetch output below.
            LOGS.exception(er)
        if isinstance(haa, dict):
            await xx.edit(f"`{haa}`")
        elif haa is not None:
            await e.reply(file=haa, force_document=True)
            await xx.delete()
        else:
            # Carbon failed - send the raw system info as a file.
            info = BytesIO(p.encode("utf-8"))
            info.name = "sysinfo.txt"
            await e.reply(file=info, force_document=True)
            await xx.delete()
    finally:
        if os.path.exists(out):
            remove(out)


@heartless_cmd(pattern="bash", fullsudo=True, only_devs=True)
async def _(event):
    carb, rayso, yamlf = None, None, False
    try:
        cmd = event.text.split(" ", maxsplit=1)[1]
        if cmd.split()[0] in ["-c", "--carbon"]:
            cmd = cmd.split(maxsplit=1)[1]
            carb = True
        if cmd.split()[0] in ["-r", "--rayso"]:
            cmd = cmd.split(maxsplit=1)[1]
            rayso = True
    except IndexError:
        return await event.eor(get_pstring("devs_1"), time=10)
    xx = await event.eor(get_pstring("com_1", "load"))
    reply_to_id = event.reply_to_msg_id or event.id
    stdout, stderr = await bash(cmd, run_code=1)
    OUT = get_pstring(f"{{p}} **Ⲃⲁⲋⲏ**\n\n{{p}} **Ⲥⲟⲙⲙⲁⲛⲇ:**\n`{cmd}` \n\n", "run", "kali")
    err, out = "", ""
    if stderr:
        err = get_pstring(f"{{p}} **Ⲉʀʀⲟʀ:** \n`{stderr}`\n\n", "warn")
    if stdout:
        if (carb or udB.get_key("CARBON_ON_BASH")) and (
            event.is_private
            or event.chat.admin_rights
            or event.chat.creator
            or event.chat.default_banned_rights.embed_links
        ):
            li = await Carbon(
                code=stdout,
                file_name="bash",
                download=True,
                backgroundColor=choice(ATRA_COL),
            )
            if isinstance(li, dict):
                await xx.edit(
                    f"Unknown Response from Carbon: `{li}`\n\nstdout`:{stdout}`\nstderr: `{stderr}`"
                )
                return
            url = await _upload_to_graph(li)
            OUT = f"[\xad]({url}){OUT}"
            out = get_pstring(f"{{p}} **Ⲟυⲧⲣυⲧ:**", "comp")
            remove(li)
        elif (rayso or udB.get_key("RAYSO_ON_BASH")) and (
            event.is_private
            or event.chat.admin_rights
            or event.chat.creator
            or event.chat.default_banned_rights.embed_links
        ):
            li = await Carbon(
                code=stdout,
                file_name="bash",
                download=True,
                backgroundColor=choice(ATRA_COL),
                rayso=True,
            )
            if isinstance(li, dict):
                await xx.edit(
                    f"Unknown Response from Carbon: `{li}`\n\nstdout`:{stdout}`\nstderr: `{stderr}`"
                )
                return
            url = await _upload_to_graph(li)
            OUT = f"[\xad]({url}){OUT}"
            out = get_pstring(f"{{p}} **Ⲟυⲧⲣυⲧ:**", "comp")
            remove(li)
        else:
            if "pip" in cmd and all(":" in line for line in stdout.split("\n")):
                try:
                    load = safe_load(stdout)
                    stdout = ""
                    for data in list(load.keys()):
                        res = load[data] or ""
                        if res and "http" not in str(res):
                            res = f"`{res}`"
                        stdout += f"**{data}**  :  {res}\n"
                    yamlf = True
                except Exception as er:
                    stdout = f"`{stdout}`"
                    LOGS.exception(er)
            else:
                stdout = f"`{stdout}`"
            out = get_pstring(f"{{p}} **Ⲟυⲧⲣυⲧ:**\n{stdout}", "comp")
    if not stderr and not stdout:
        out = get_pstring(f"{{p}} **Ⲟυⲧⲣυⲧ:**\n`Ⲋυⲥⲥⲉⲋⲋ`", "comp")
    OUT += err + out
    if len(OUT) > 4096:
        ultd = err + out
        with BytesIO(str.encode(ultd)) as out_file:
            out_file.name = "bash.txt"
            await event.client.send_file(
                event.chat_id,
                out_file,
                force_document=True,
                thumb=ULTConfig.thumb,
                allow_cache=False,
                caption=get_pstring(f"{{p}} `{cmd}`","run") if len(cmd) < 998 else None,
                reply_to=reply_to_id,
            )

            await xx.delete()
    else:
        await xx.edit(OUT, link_preview=not yamlf)


pp = pprint  # ignore: pylint
bot = heartless = heartless_bot


class u:
    _ = ""


def _parse_eval(value=None):
    if not value:
        return value
    if hasattr(value, "stringify"):
        try:
            return value.stringify()
        except TypeError:
            pass
    elif isinstance(value, dict):
        try:
            return json_parser(value, indent=1)
        except BaseException:
            pass
    elif isinstance(value, list):
        newlist = "["
        for index, child in enumerate(value):
            newlist += "\n  " + str(_parse_eval(child))
            if index < len(value) - 1:
                newlist += ","
        newlist += "\n]"
        return newlist
    return str(value)


@heartless_cmd(pattern="eval", fullsudo=True, only_devs=True)
async def _(event):
    try:
        cmd = event.text.split(maxsplit=1)[1]
    except IndexError:
        return await event.eor(get_pstring("devs_2"), time=5)
    xx = None
    mode = ""
    spli = cmd.split()

    async def get_():
        try:
            cm = cmd.split(maxsplit=1)[1]
        except IndexError:
            await event.eor("->> Wrong Format <<-")
            cm = None
        return cm

    if spli[0] in ["-s", "--silent"]:
        await event.delete()
        mode = "silent"
    elif spli[0] in ["-n", "-noedit"]:
        mode = "no-edit"
        xx = await event.reply(get_pstring("com_1", "load"))
    elif spli[0] in ["-gs", "--source"]:
        mode = "gsource"
    elif spli[0] in ["-ga", "--args"]:
        mode = "g-args"
    if mode:
        cmd = await get_()
    if not cmd:
        return
    if not mode == "silent" and not xx:
        xx = await event.eor(get_pstring("com_1", "load"))
    if black:
        try:
            cmd = black.format_str(cmd, mode=black.Mode())
        except BaseException:
            # Consider it as Code Error, and move on to be shown ahead.
            pass
    reply_to_id = event.reply_to_msg_id or event
    if any(item in cmd for item in KEEP_SAFE().All) and (
        not (event.out or event.sender_id == heartless_bot.uid)
    ):
        warning = await event.forward_to(udB.get_key("LOG_CHANNEL"))
        await warning.reply(
            f"Malicious Activities suspected by {inline_mention(await event.get_sender())}"
        )
        _ignore_eval.append(event.sender_id)
        return await xx.edit(
            "`Malicious Activities suspected⚠️!\nReported to owner. Aborted this request!`"
        )
    old_stderr = sys.stderr
    old_stdout = sys.stdout
    redirected_output = sys.stdout = StringIO()
    redirected_error = sys.stderr = StringIO()
    stdout, stderr, exc, timeg = None, None, None, None
    tima = time.time()
    try:
        value = await aexec(cmd, event)
    except Exception:
        value = None
        exc = traceback.format_exc()
    tima = time.time() - tima
    stdout = redirected_output.getvalue()
    stderr = redirected_error.getvalue()
    sys.stdout = old_stdout
    sys.stderr = old_stderr
    if value:
        try:
            if mode == "gsource":
                exc = inspect.getsource(value)
            elif mode == "g-args":
                args = inspect.signature(value).parameters.values()
                name = ""
                if hasattr(value, "__name__"):
                    name = value.__name__
                exc = f"**{name}**\n\n" + "\n ".join([str(arg) for arg in args])
        except Exception:
            exc = traceback.format_exc()
    evaluation = exc or stderr or stdout or _parse_eval(value) or get_pstring("instu_4")
    if mode == "silent":
        if exc:
            msg = f"• <b>Ⲉⳳⲁⳑ Ⲉʀʀⲟʀ\n\n• CHAT:</b> <code>{get_display_name(event.chat)}</code> [<code>{event.chat_id}</code>]"
            msg += f"\n\n∆ <b>CODE:</b>\n<code>{cmd}</code>\n\n∆ <b>Ⲉʀʀⲟʀ:</b>\n<code>{exc}</code>"
            log_chat = udB.get_key("LOG_CHANNEL")
            if len(msg) > 4000:
                with BytesIO(msg.encode()) as out_file:
                    out_file.name = "Eval-Error.txt"
                return await event.client.send_message(
                    log_chat, f"`{cmd}`", file=out_file
                )
            await event.client.send_message(log_chat, msg, parse_mode="html")
        return
    tmt = tima * 1000
    timef = time_formatter(tmt)
    timeform = timef if not timef == "0s" else f"{tmt:.3f}ms"
    final_output = get_pstring(f"{{p}} **Ⲉⳳⲁⳑ** (in {timeform})\n", "py") + f"```{cmd}```\n\n" + get_pstring(f"{{p}} **Ⲟυⲧⲣυⲧ:**\n```{evaluation}```", "comp")
    if len(final_output) > 4096:
        final_output = evaluation
        with BytesIO(str.encode(final_output)) as out_file:
            out_file.name = "eval.txt"
            await event.client.send_file(
                event.chat_id,
                out_file,
                force_document=True,
                thumb=ULTConfig.thumb,
                allow_cache=False,
                caption=get_pstring(f"{{p}} ```{cmd}```", "py") if len(cmd) < 998 else None,
                reply_to=reply_to_id,
            )
        return await xx.delete()
    await xx.edit(final_output)


def _stringify(text=None, *args, **kwargs):
    if text:
        u._ = text
        text = _parse_eval(text)
    return print(text, *args, **kwargs)


async def aexec(code, event):
    """Compile and run eval code in an async helper.

    Python 3.13+ no longer reliably exposes names created by bare ``exec``
    through ``locals()`` inside a function, which caused
    ``KeyError: '__aexec'``. Bind the helper into an explicit namespace.
    """
    src = (
        "async def __aexec(e, client):"
        + "\n print = p = _stringify"
        + "\n message = event = e"
        + "\n u.r = reply = await event.get_reply_message()"
        + "\n chat = event.chat_id"
        + "\n u.lr = locals()"
        + "".join(f"\n {line}" for line in code.split("\n"))
    )
    ns = {**globals(), "_stringify": _stringify}
    exec(compile(src, "<ultroid_aexec>", "exec"), ns, ns)
    return await ns["__aexec"](event, event.client)


DUMMY_CPP = """#include <iostream>
using namespace std;

int main(){
!code
}
"""


@heartless_cmd(pattern="cpp", only_devs=True)
async def doie(e):
    match = e.text.split(" ", maxsplit=1)
    try:
        match = match[1]
    except IndexError:
        return await e.eor(get_pstring("devs_3"))
    msg = await e.eor(get_pstring("com_1"))
    if "main(" not in match:
        new_m = "".join(" " * 4 + i + "\n" for i in match.split("\n"))
        match = DUMMY_CPP.replace("!code", new_m)
    open("cpp-heartless.cpp", "w").write(match)
    m = await bash("g++ -o CppHeartless cpp-heartless.cpp")
    o_cpp = f"• **Eval-Cpp**\n`{match}`"
    if m[1]:
        o_cpp += f"\n\n**• Error :**\n`{m[1]}`"
        if len(o_cpp) > 3000:
            os.remove("cpp-heartless.cpp")
            if os.path.exists("CppHeartless"):
                os.remove("CppHeartless")
            with BytesIO(str.encode(o_cpp)) as out_file:
                out_file.name = "error.txt"
                return await msg.reply(f"`{match}`", file=out_file)
        return await eor(msg, o_cpp)
    m = await bash("./CppHeartless")
    if m[0] != "":
        o_cpp += f"\n\n**• Output :**\n`{m[0]}`"
    if m[1]:
        o_cpp += f"\n\n**• Error :**\n`{m[1]}`"
    if len(o_cpp) > 3000:
        with BytesIO(str.encode(o_cpp)) as out_file:
            out_file.name = "eval.txt"
            await msg.reply(f"`{match}`", file=out_file)
    else:
        await eor(msg, o_cpp)
    os.remove("CppHeartless")
    os.remove("cpp-heartless.cpp")

import asyncio
import base64
import inspect
from datetime import datetime
from html import unescape
from random import choice
from re import compile as re_compile

from bs4 import BeautifulSoup as bs
from telethon import Button
from telethon.tl.alltlobjects import LAYER, tlobjects
from telethon.tl.types import DocumentAttributeAudio as Audio
from telethon.tl.types import InputWebDocument as wb

from CythonX.fns.misc import google_search
from CythonX.fns.tools import (
    _webupload_cache,
    async_searcher,
    get_google_images,
    get_ofox,
    saavn_search,
    webuploader,
)

from . import *
from . import _ult_cache
from urllib.parse import parse_qs, urlparse
try:
    from google_play_scraper import (
        app as google_play_app,
        search as google_play_search,
    )
except ImportError:
    google_play_app = None
    google_play_search = None

ofox = "https://graph.org/file/231f0049fcd722824f13b.jpg"
ippic = "https://telegra.ph/file/807e012dbe2789c0648ee.jpg"
gugirl = "https://telegra.ph/file/0df54ae4541abca96aa11.jpg"
gugirl = "https://graph.org/file/0df54ae4541abca96aa11.jpg"
ultpic = "https://graph.org/file/cc13c2fb42b9afdccdc6a.png"

apis = [
    "QUl6YVN5QXlEQnNZM1dSdEI1WVBDNmFCX3c4SkF5NlpkWE5jNkZV",
    "QUl6YVN5QkYwenhMbFlsUE1wOXh3TVFxVktDUVJxOERnZHJMWHNn",
    "QUl6YVN5RGRPS253blB3VklRX2xiSDVzWUU0Rm9YakFLSVFWMERR",
]


@in_pattern("bin")
async def _(e):
    try:
        quer = e.text.split(" ", maxsplit=1)[1]
    except IndexError:
        kkkk = e.builder.article(
            title="Bin Checker",
            description="Give me your bin number",
            thumb=wb(binpic, 0, "image/jpeg", []),
            text="**Ⲃⲓⲛ Ⲥⲏⲉⲥⲕⲉʀ**\n\nYou didn't search any bin number",
            buttons=Button.switch_inline("Sᴇᴀʀᴄʜ Aɢᴀɪɴ", query="bin ", same_peer=True),
        )
        await e.answer([kkkk])
    url = f"https://bins-su-api.vercel.app/api/{quer}"
    data = await async_searcher(url, re_json=True)
    results = data["result"]
    messages = data["message"]
    types = data["data"]["type"]
    bins = data["data"]["bin"]
    vendors = data["data"]["vendor"]
    levels = data["data"]["level"]
    banks = data["data"]["bank"]
    countrys = data["data"]["country"]
    text = """
**Ⳳⲁⳑⲓⲇⲓⲧⲩ**:- `{}`
**Ⲋⲧⲁⲧυⲋ**:- `{}`
**Ⲃⲓⲛ Ⲛυⲙⲃⲉʀ**:- `{}`
**Ⳳⲉⲛⲇⲟʀ**:- `{}`
**Ⳑⲉⳳⲉⳑ**:- `{}`
**Ⲧⲩⲣⲉ**:- `{}`
**Ⲃⲁⲛⲕ**:- `{}`
**Ⲥⲟυⲛⲧʀⲩ**:- `{}`
""".format(
        results,
        messages,
        bins,
        vendors,
        levels,
        types,
        banks,
        countrys,
    )
    but = [
        await e.builder.article(
            title=f"Bin Nuʍʙᴇr Sᴇᴀrᴄh Rᴇsulᴛ",
            description=f"{results}\n{messages}",
            text=text,
            thumb=wb(binpic, 0, "image/jpeg", []),
            link_preview=False,
            buttons=[
                [
                    Button.switch_inline(
                        "Sᴇᴀʀᴄʜ Aɢᴀɪɴ",
                        query="bin ",
                        same_peer=True,
                    ),
                    Button.switch_inline(
                        "Sʜᴀʀᴇ",
                        query=f"bin {quer}",
                        same_peer=False,
                    ),
                ],
            ],
        ),
    ]
    await e.answer(but)


@in_pattern("ip")
async def _(e):
    try:
        quer = e.text.split(" ", maxsplit=1)[1]
    except IndexError:
        kkkk = e.builder.article(
            title="Ip Info",
            description="Give me an ip address",
            thumb=wb(ippic, 0, "image/jpeg", []),
            text="**ⲒⲢ Ⲓⲛϝⲟ**\n\nYou didn't search any ip address",
            buttons=Button.switch_inline("Sᴇᴀʀᴄʜ Aɢᴀɪɴ", query="ip ", same_peer=True),
        )
        await e.answer([kkkk])
    url = f"http://ip-api.com/json/{quer}"
    data = await async_searcher(url, re_json=True)
    stat = data["status"]
    count = data["country"]
    countc = data["countryCode"]
    reg = data["region"]
    regn = data["regionName"]
    cit = data["city"]
    zp = data["zip"]
    lt = data["lat"]
    ln = data["lon"]
    tz = data["timezone"]
    isps = data["isp"]
    orgs = data["org"]
    ass = data["as"]
    que = data["query"]
    linkk = f"https://maps.google.com/?q={lt},{ln}"
    text = """
**IP Aɗɗrᥱss**:- `{}`
**𐍃ᴛᥲᴛᥙs**:- `{}`
**𑀝᧐ᥙᥒᴛry**:- `{}`
**𑀝᧐ᥙᥒᴛry 𑀝᧐ɗᥱ**:- `{}`
**Rᥱgi᧐ᥒ**:- `{}`
**Rᥱgi᧐ᥒ 𐌽ᥲⲙᥱ**:- `{}`
**𑀝iᴛy**:- `{}`
**Ziρ**:- `{}`
**𑀉ᥲᴛiᴛᥙɗᥱ**:- `{}`
**𑀉᧐ᥒgiᴛᥙɗᥱ**:- `{}`
**Tiⲙᥱ Z᧐ᥒᥱ**:- `{}`
**I𐍃P**:- `{}`
**𐌏RᏵ**:- `{}`
**A𐍃**:- `{}`
**𑀉᧐ᥴᥲᴛi᧐ᥒ 𑀉iᥒκ**:- [Link]({})
""".format(
        que,
        stat,
        count,
        countc,
        reg,
        regn,
        cit,
        zp,
        lt,
        ln,
        tz,
        isps,
        orgs,
        ass,
        linkk,
    )
    but = [
        await e.builder.article(
            title=f"IP Iᥒf᧐rⲙᥲᴛi᧐ᥒ Rᥱsᥙᥣᴛ",
            description=f"{stat}\n{count}",
            text=text,
            thumb=wb(ippic, 0, "image/jpeg", []),
            link_preview=False,
            buttons=[
                [
                    Button.switch_inline(
                        "Sᴇᴀʀᴄʜ Aɢᴀɪɴ",
                        query="ip ",
                        same_peer=True,
                    ),
                    Button.switch_inline(
                        "Sʜᴀʀᴇ",
                        query=f"ip {quer}",
                        same_peer=False,
                    ),
                ],
            ],
        ),
    ]
    await e.answer(but)


@in_pattern("ofox")
async def _(e):
    try:
        match = e.text.split(" ", maxsplit=1)[1]
    except IndexError:
        kkkk = e.builder.article(
            title="Enter Device Codename",
            thumb=wb(ofox, 0, "image/jpeg", []),
            text="**OFᴏx🦊Rᴇᴄᴏᴠᴇʀʏ**\n\nYou didn't search anything",
            buttons=Button.switch_inline("Sᴇᴀʀᴄʜ Aɢᴀɪɴ", query="ofox ", same_peer=True),
        )
        return await e.answer([kkkk])
    device, releases = await get_ofox(match)
    if device.get("detail") is None:
        fox = []
        fullname = device["full_name"]
        codename = device["codename"]
        str(device["supported"])
        maintainer = device["maintainer"]["name"]
        link = f"https://orangefox.download/device/{codename}"
        for data in releases["data"]:
            release = data["type"]
            version = data["version"]
            size = humanbytes(data["size"])
            release_date = datetime.utcfromtimestamp(data["date"]).strftime("%Y-%m-%d")
            text = f"[\xad]({ofox})**OʀᴀɴɢᴇFᴏx Rᴇᴄᴏᴠᴇʀʏ Fᴏʀ**\n\n"
            text += f"`  Fᴜʟʟ Nᴀᴍᴇ: {fullname}`\n"
            text += f"`  Cᴏᴅᴇɴᴀᴍᴇ: {codename}`\n"
            text += f"`  Mᴀɪɴᴛᴀɪɴᴇʀ: {maintainer}`\n"
            text += f"`  Bᴜɪʟᴅ Tʏᴘᴇ: {release}`\n"
            text += f"`  Vᴇʀsɪᴏɴ: {version}`\n"
            text += f"`  Sɪᴢᴇ: {size}`\n"
            text += f"`  Bᴜɪʟᴅ Dᴀᴛᴇ: {release_date}`"
            fox.append(
                await e.builder.article(
                    title=f"{fullname}",
                    description=f"{version}\n{release_date}",
                    text=text,
                    thumb=wb(ofox, 0, "image/jpeg", []),
                    link_preview=True,
                    buttons=[
                        Button.url("Dᴏᴡɴʟᴏᴀᴅ", url=f"{link}"),
                        Button.switch_inline(
                            "Sᴇᴀʀᴄʜ Aɢᴀɪɴ", query="ofox ", same_peer=True
                        ),
                    ],
                )
            )
        await e.answer(
            fox, switch_pm="OrangeFox Recovery Search", switch_pm_param="start"
        )
    else:
        await e.answer(
            [], switch_pm="OrangeFox Recovery Search", switch_pm_param="start"
        )


@in_pattern("fl2lnk ?(.*)")
async def _(e):
    match = e.pattern_match.group(1)
    chat_id, msg_id = match.split(":")
    filename = _webupload_cache[int(chat_id)][int(msg_id)]
    if "/" in filename:
        filename = filename.split("/")[-1]
    __cache = f"{chat_id}:{msg_id}"
    buttons = [
        [
            Button.inline("anonfiles", data=f"flanonfiles//{__cache}"),
            Button.inline("transfer", data=f"fltransfer//{__cache}"),
        ],
        [
            Button.inline("bayfiles", data=f"flbayfiles//{__cache}"),
            Button.inline("x0.at", data=f"flx0.at//{__cache}"),
        ],
        [
            Button.inline("file.io", data=f"flfile.io//{__cache}"),
            Button.inline("siasky", data=f"flsiasky//{__cache}"),
        ],
    ]
    try:
        lnk = [
            await e.builder.article(
                title=f"Upload {filename}",
                text=f"**File:**\n{filename}",
                buttons=buttons,
            )
        ]
    except BaseException as er:
        LOGS.exception(er)
        lnk = [
            await e.builder.article(
                title="fl2lnk",
                text="File not found",
            )
        ]
    await e.answer(lnk, switch_pm="File to Link", switch_pm_param="start")


@callback(
    re_compile(
        "fl(.*)",
    ),
)
async def _(e):
    t = (e.data).decode("UTF-8")
    data = t[2:]
    host = data.split("//")[0]
    chat_id, msg_id = data.split("//")[1].split(":")
    filename = _webupload_cache[int(chat_id)][int(msg_id)]
    if "/" in filename:
        filename = filename.split("/")[-1]
    await e.edit(f"Uploading `{filename}` on {host}")
    link = (await webuploader(chat_id, msg_id, host)).strip().replace("\n", "")
    await e.edit(f"Uploaded `{filename}` on {host}.", buttons=Button.url("View", link))


@in_pattern("go")
async def gsearch(q_event):
    try:
        match = q_event.text.split(maxsplit=1)[1]
    except IndexError:
        return await q_event.answer(
            [], switch_pm="Google Search. Enter a query!", switch_pm_param="start"
        )
    searcher = []
    gresults = await google_search(match)
    for i in gresults:
        try:
            title = i["title"]
            link = i["link"]
            desc = i["snippet"]
            searcher.append(
                await q_event.builder.article(
                    title=title,
                    description=desc,
                    thumb=wb(gugirl, 0, "image/jpeg", []),
                    text=f"**Gᴏᴏɢʟᴇ Sᴇᴀʀᴄʜ**\n\n**••Tɪᴛʟᴇ••**\n`{title}`\n\n**••Dᴇsᴄʀɪᴘᴛɪᴏɴ••**\n`{desc}`",
                    link_preview=False,
                    buttons=[
                        [Button.url("Lɪɴᴋ", url=f"{link}")],
                        [
                            Button.switch_inline(
                                "Sᴇᴀʀᴄʜ Aɢᴀɪɴ",
                                query="go ",
                                same_peer=True,
                            ),
                            Button.switch_inline(
                                "Sʜᴀʀᴇ",
                                query=f"go {match}",
                                same_peer=False,
                            ),
                        ],
                    ],
                ),
            )
        except IndexError:
            break
    await q_event.answer(searcher, switch_pm="Google Search", switch_pm_param="start")


IMG = {}


@in_pattern("img")
async def image_search(event):
    try:
        match = event.text.split(" ", maxsplit=1)[1].lower()
    except IndexError:
        return await event.answer(
            [], switch_pm="Enter Query to Search", switch_pm_param="start"
        )
    if IMG.get(match):
        return await event.answer(
            IMG[match], switch_pm=f"• Results for {match}", switch_pm_param="start"
        )
    ress = []
    images = await get_google_images(match)
    for img in images[:10]:
        try:
            image = img["original"]
            imga = wb(image, 0, "image/jpeg", [])
            ress.append(
                await event.builder.article(
                    title=match,
                    type="photo",
                    text="**✨ T.me/DarkPentester**",
                    content=imga,
                    thumb=imga,
                    include_media=True,
                    buttons=[
                        [
                            Button.switch_inline(
                                "Sᴇᴀʀᴄʜ Aɢᴀɪɴ",
                                query="img ",
                                same_peer=True,
                            ),
                            Button.switch_inline(
                                "Sʜᴀʀᴇ",
                                query=event.text,
                            ),
                        ],
                    ],
                )
            )
        except IndexError:
            break
    msg = f"Showing {len(ress)} Results!" if ress else "No Results Found"
    IMG.update({match: ress})
    await event.answer(ress, switch_pm=msg, switch_pm_param="start")


@in_pattern("mods")
async def _(e):
    try:
        quer = e.text.split(" ", maxsplit=1)[1]
    except IndexError:
        return await e.answer(
            [], switch_pm="Mod Apps Search. Enter app name!", switch_pm_param="start"
        )
    start = 0 * 3 + 1
    da = base64.b64decode(choice(apis)).decode("ascii")
    url = f"https://www.googleapis.com/customsearch/v1?key={da}&cx=25b3b50edb928435b&q={quer}&start={start}"
    data = await async_searcher(url, re_json=True)
    search_items = data.get("items", [])
    modss = []
    for a in search_items:
        title = a.get("title")
        desc = a.get("snippet")
        link = a.get("link")
        text = f"**••Tɪᴛʟᴇ••** `{title}`\n\n"
        text += f"**Dᴇsᴄʀɪᴘᴛɪᴏɴ** `{desc}`"
        modss.append(
            await e.builder.article(
                title=title,
                description=desc,
                text=text,
                link_preview=True,
                buttons=[
                    [Button.url("Dᴏᴡɴʟᴏᴀᴅ", url=f"{link}")],
                    [
                        Button.switch_inline(
                            "Mᴏʀᴇ Mᴏᴅs",
                            query="mods ",
                            same_peer=True,
                        ),
                        Button.switch_inline(
                            "Sʜᴀʀᴇ",
                            query=f"mods {quer}",
                            same_peer=False,
                        ),
                    ],
                ],
            ),
        )
    await e.answer(modss, switch_pm="Search Mod Applications", switch_pm_param="start")


@in_pattern("heartless", owner=True)
async def repo(e):
    res = [
        await e.builder.article(
            title="𝒉𝒆𝒂𝒓𝒕𝒍𝒆𝒔𝒔",
            description="℘ The less you know, The more at peace",
            thumb=wb(ultpic, 0, "image/jpeg", []),
            text="ᥴᥣiᥴκ δᥙᴛᴛ᧐ᥒ δᥱᥣ᧐ᥕ ᴛ᧐ ᥴ᧐ᥒᴛᥲᥴᴛ !",
            buttons=[
                [Button.url("• ꜱᴜᴘᴘᴏʀᴛ •", url="t.me/DarkPentester")],
            ],
        ),
    ]
    await e.answer(
        res, switch_pm="👨🏻‍💻: 𝒂𝒔𝒔𝒊𝒔𝒕𝒂𝒏𝒕 𝒐𝒇 𝒉𝒆𝒂𝒓𝒕𝒍𝒆𝒔𝒔", switch_pm_param="start"
    )


APP_CACHE = {}
RECENTS = {}
PLAY_DETAILS_CACHE = {}
PLAY_DETAILS_SEMAPHORE = asyncio.Semaphore(5)

def _clean_play_text(value):
    if value is None:
        return ""

    value = unescape(str(value))

    if "<" in value and ">" in value:
        value = bs(
            value,
            "html.parser",
        ).get_text(
            " ",
            strip=True,
        )

    value = value.replace(
        "\x00",
        " ",
    )

    value = " ".join(
        value.split()
    )

    return value.strip()

def _extract_play_app_id(app):

    if not isinstance(app, dict):
        return ""

    app_id = (
        app.get("appId")
        or app.get("app_id")
        or app.get("packageName")
        or app.get("package_name")
    )

    if app_id:
        return str(app_id).strip()

    play_url = (
        app.get("url")
        or app.get("link")
        or ""
    )

    if play_url:
        try:
            parsed = urlparse(
                str(play_url)
            )

            app_id = parse_qs(
                parsed.query
            ).get("id", [None])[0]

            if app_id:
                return str(
                    app_id
                ).strip()

        except Exception:
            pass

    return ""

async def _get_play_store_description(
    app_id,
    fallback="",
):

    fallback = _clean_play_text(
        fallback
    )

    if (
        not app_id
        or google_play_app is None
    ):
        return fallback

    cached = PLAY_DETAILS_CACHE.get(
        app_id
    )

    if cached:
        return cached

    try:
        details = await asyncio.to_thread(
            google_play_app,
            app_id,
            lang="en",
            country="us",
        )

        description = _clean_play_text(
            details.get("description")
            or details.get("descriptionHTML")
            or details.get("summary")
            or fallback
        )

        if description:
            PLAY_DETAILS_CACHE[
                app_id
            ] = description

            return description

    except Exception:
        LOGS.exception(
            "Google Play details failed for appId=%s",
            app_id,
        )

    return fallback


def _format_play_description(
    description,
    limit=1200,
):

    description = _clean_play_text(
        description
    )

    if len(description) <= limit:
        return description

    return (
        description[
            : limit - 3
        ].rstrip()
        + "..."
    )

async def _search_play_store(query):
    if google_play_search is None:
        raise DependencyMissingError(
            "Install google-play-scraper first."
        )

    return await asyncio.to_thread(
        google_play_search,
        query,
        lang="en",
        country="us",
        n_hits=50,
    )


@in_pattern("app")
async def app_inline(event):
    try:
        query = event.text.split(
            maxsplit=1
        )[1].strip()

    except IndexError:
        results = []

        if (
            APP_CACHE
            and RECENTS.get(
                event.sender_id
            )
        ):
            for app_name in RECENTS[
                event.sender_id
            ][-10:]:
                cached = APP_CACHE.get(
                    app_name
                )

                if cached:
                    results.extend(
                        cached
                    )

        return await event.answer(
            results,
            switch_pm=get_string(
                "instu_2"
            ),
            switch_pm_param="start",
        )

    query = query.lower()

    if query in APP_CACHE:
        return await event.answer(
            APP_CACHE[query],
            switch_pm=(
                "Application Searcher"
            ),
            switch_pm_param="start",
        )

    try:
        apps = await _search_play_store(
            query
        )

    except Exception as exc:
        LOGS.exception(
            "Google Play search failed"
        )

        result = await event.builder.article(
            title="Google Play Error",
            description=str(exc)[:200],
            text=(
                "**Application Searcher**\n\n"
                f"`{type(exc).__name__}: {exc}`"
            ),
        )

        return await event.answer(
            [result]
        )

    if not apps:
        result = await event.builder.article(
            title="No Applications Found",
            description=query,
            text=(
                f"❌ No Google Play application "
                f"found for `{query}`."
            ),
            buttons=Button.switch_inline(
                "Search Again",
                query="app ",
                same_peer=True,
            ),
        )

        return await event.answer(
            [result],
            switch_pm="Application Searcher",
            switch_pm_param="start",
        )

    results = []

    for app in apps[:50]:
        try:
            app_id = _extract_play_app_id(
                app
            )

            if not app_id:
                LOGS.warning(
                    "Google Play result has no valid appId: %r",
                    app,
                )
                continue

            title = (
                app.get("title")
                or "Unknown Application"
            )

            developer = (
                app.get("developer")
                or "Unknown Developer"
            )

            search_description = _clean_play_text(
                app.get("description")
                or app.get("summary")
                or ""
            )

            description = await _get_play_store_description(
                app_id,
                fallback=search_description,
            )

            description = _format_play_description(
                description,
                limit=1200,
            )

            play_url = (
                "https://play.google.com/"
                "store/apps/details?id="
                + app_id
            )

            text = (
                f"**••Aᴘᴘ Nᴀᴍᴇ••** "
                f"[{title}]({play_url})\n\n"

                f"**••Dᴇᴠᴇʟᴏᴘᴇʀ••** "
                f"`{developer}`\n\n"

                f"**••Dᴇsᴄʀɪᴘᴛɪᴏɴ••**\n"
                f"{description or 'No description available.'}\n\n"

                f"**✨ T.me/DarkPentester**"
            )

            buttons = [
                [
                    Button.url(
                        "Gᴘʟᴀʏ Lɪɴᴋ",
                        url=play_url,
                    )
                ],
                [
                    Button.switch_inline(
                        "Mᴏʀᴇ Aᴘᴘs",
                        query="app ",
                        same_peer=True,
                    ),
                    Button.switch_inline(
                        "Sʜᴀʀᴇ",
                        query=f"app {query}",
                        same_peer=False,
                    ),
                ],
            ]

            icon = app.get(
                "icon"
            )

            try:
                thumb = (
                    wb(
                        icon,
                        0,
                        "image/jpeg",
                        [],
                    )
                    if icon
                    else None
                )

            except Exception:
                thumb = None

            results.append(
                await event.builder.article(
                    title=title,

                    description=(
                        f"{developer}\n"
                        f"{description[:150]}"
                    ),

                    thumb=thumb,
                    text=text,
                    link_preview=True,
                    buttons=buttons,
                )
            )

        except Exception as exc:
            LOGS.warning(
                "Skipping invalid Play result: %s",
                exc,
            )

    APP_CACHE[
        query
    ] = results

    RECENTS.setdefault(
        event.sender_id,
        [],
    )

    if query in RECENTS[
        event.sender_id
    ]:
        RECENTS[
            event.sender_id
        ].remove(query)

    RECENTS[
        event.sender_id
    ].append(query)

    RECENTS[
        event.sender_id
    ] = RECENTS[
        event.sender_id
    ][-10:]

    return await event.answer(
        results,
        switch_pm="Application Searcher",
        switch_pm_param="start",
        )

Wandbox_URI = "https://wandbox.org/api"
Wandbox_COMPILERS = {}
Wandbox_ALIASES = {}


async def _get_wandbox_compilers():
    if Wandbox_COMPILERS:
        return Wandbox_COMPILERS

    data = await async_searcher(
        f"{Wandbox_URI}/list.json",
        re_json=True,
    )

    if not isinstance(data, list):
        raise RuntimeError(
            "Invalid response from Wandbox."
        )

    for compiler in data:
        name = compiler.get("name")

        if not name:
            continue

        Wandbox_COMPILERS[
            name
        ] = compiler

        for alias in compiler.get(
            "switches",
            []
        ):
            alias_name = alias.get(
                "name"
            )

            if alias_name:
                Wandbox_ALIASES[
                    alias_name.lower()
                ] = name

    return Wandbox_COMPILERS


def _find_wandbox_compiler(
    language,
    compilers,
):
    language = language.lower().strip()

    aliases = {
        "py": "python",
        "python3": "python",
        "js": "nodejs",
        "javascript": "nodejs",
        "node": "nodejs",
        "ts": "typescript",
        "cpp": "gcc-head",
        "c++": "gcc-head",
        "cxx": "gcc-head",
        "c": "gcc-head",
        "rust": "rust",
        "rs": "rust",
        "go": "go",
        "golang": "go",
        "java": "openjdk",
        "kotlin": "kotlin",
        "php": "php",
        "ruby": "ruby",
        "rb": "ruby",
        "perl": "perl",
        "swift": "swift",
        "bash": "bash",
        "sh": "bash",
    }

    candidate = aliases.get(
        language,
        language,
    )

    if candidate in compilers:
        return candidate

    for name in compilers:
        if (
            name.lower()
            == language
        ):
            return name

    for name in compilers:
        if candidate.lower() in name.lower():
            return name

    return None


@in_pattern("run")
async def run_inline(event):
    try:
        query = event.text.split(
            maxsplit=2
        )

        if len(query) < 3:
            raise ValueError

        language = query[1].strip()
        code = query[2].strip()

    except ValueError:
        result = await event.builder.article(
            title="Bad Query",
            description="Usage: run <language> <code>",
            thumb=wb(
                "https://graph.org/file/e33c57fc5f1044547e4d8.jpg",
                0,
                "image/jpeg",
                [],
            ),
            text=(
                "**Inline Usage**\n\n"
                f"`@{asst.me.username} "
                "run python print(\"hello world\")`"
            ),
        )

        return await event.answer(
            [result]
        )

    if len(code) > 15000:
        result = await event.builder.article(
            title="Code Too Long",
            description="Maximum code length is 15000 characters.",
            text="Please shorten your code.",
        )

        return await event.answer(
            [result]
        )

    try:
        compilers = (
            await _get_wandbox_compilers()
        )

        compiler = _find_wandbox_compiler(
            language,
            compilers,
        )

        if not compiler:
            result = await event.builder.article(
                title="Unsupported Language",
                description=language,
                text=(
                    f"❌ Unsupported language: "
                    f"`{language}`"
                ),
            )

            return await event.answer(
                [result]
            )

        payload = {
            "code": code,
            "codes": [],
            "compiler": compiler,
            "options": "",
            "stdin": "",
            "compiler-option-raw": "",
            "runtime-option-raw": "",
            "save": False,
        }

        output = await async_searcher(
            f"{Wandbox_URI}/compile.json",
            post=True,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=payload,
            re_json=True,
            retries=2,
        )

        if not isinstance(
            output,
            dict,
        ):
            raise RuntimeError(
                "Invalid compiler response."
            )

        compiler_message = (
            output.get(
                "compiler_message"
            )
            or ""
        )

        program_message = (
            output.get(
                "program_message"
            )
            or ""
        )

        status = output.get(
            "status"
        )

        signal = output.get(
            "signal"
        )

        final_output = (
            program_message.strip()
            or compiler_message.strip()
            or get_string("instu_4")
        )

        if signal:
            final_output += (
                f"\n\nSignal: `{signal}`"
            )

        if status is not None:
            final_output += (
                f"\nExit code: `{status}`"
            )

        if len(final_output) > 3000:
            final_output = (
                final_output[:3000]
                + "..."
            )

        result = await event.builder.article(
            title="Result",
            description=final_output[:250],
            text=(
                f"• **Language:**\n"
                f"`{language}`\n\n"
                f"• **Compiler:**\n"
                f"`{compiler}`\n\n"
                f"• **Code:**\n"
                f"`{code}`\n\n"
                f"• **Result:**\n"
                f"`{final_output}`"
            ),
            thumb=wb(
                "https://graph.org/file/871ee4a481f58117dccc4.jpg",
                0,
                "image/jpeg",
                [],
            ),
            buttons=Button.switch_inline(
                "Fork",
                query=event.text,
                same_peer=True,
            ),
        )

        return await event.answer(
            [result],
            switch_pm="• Run Code •",
            switch_pm_param="start",
        )

    except Exception as exc:
        LOGS.exception(
            "Inline run failed"
        )

        result = await event.builder.article(
            title="Execution Error",
            description=str(exc)[:200],
            text=(
                "**Run Code Error**\n\n"
                f"`{type(exc).__name__}: {exc}`"
            ),
        )

        return await event.answer(
            [result]
                )

FDROID_ = {}


@in_pattern("fdroid")
async def do_magic(event):
    try:
        match = event.text.split(" ", maxsplit=1)[1].lower()
    except IndexError:
        return await event.answer(
            [], switch_pm="Enter Query to Search", switch_pm_param="start"
        )
    if FDROID_.get(match):
        return await event.answer(
            FDROID_[match], switch_pm=f"• Results for {match}", switch_pm_param="start"
        )
    link = "https://search.f-droid.org/?q=" + match.replace(" ", "+")
    content = await async_searcher(link, re_content=True)
    BSC = bs(content, "html.parser", from_encoding="utf-8")
    ress = []
    for dat in BSC.find_all("a", "package-header")[:10]:
        image = dat.find("img", "package-icon")["src"]
        if image.endswith("/"):
            image = "https://graph.org/file/a8dd4a92c5a53a89d0eff.jpg"
        title = dat.find("h4", "package-name").text.strip()
        desc = dat.find("span", "package-summary").text.strip()
        text = f"• **Name :** `{title}`\n\n"
        text += f"• **Description :** `{desc}`\n"
        text += f"• **License :** `{dat.find('span', 'package-license').text.strip()}`"
        imga = wb(image, 0, "image/jpeg", [])
        ress.append(
            await event.builder.article(
                title=title,
                type="photo",
                description=desc,
                text=text,
                content=imga,
                thumb=imga,
                include_media=True,
                buttons=[
                    Button.inline(
                        "• Download •", "fd" + dat["href"].split("packages/")[-1]
                    ),
                    Button.switch_inline("• Share •", query=event.text),
                ],
            )
        )
    msg = f"Showing {len(ress)} Results!" if ress else "No Results Found"
    FDROID_.update({match: ress})
    await event.answer(ress, switch_pm=msg, switch_pm_param="start")


# Thanks to OpenSource
_bearer_collected = [
    "AAAAAAAAAAAAAAAAAAAAALIKKgEAAAAA1DRuS%2BI7ZRKiagD6KHYmreaXomo%3DP5Vaje4UTtEkODg0fX7nCh5laSrchhtLxeyEqxXpv0w9ZKspLD",
    "AAAAAAAAAAAAAAAAAAAAAL5iUAEAAAAAmo6FYRjqdKlI3cNziIm%2BHUQB9Xs%3DS31pj0mxARMTOk2g9dvQ1yP9wknvY4FPBPUlE00smJcncw4dPR",
    "AAAAAAAAAAAAAAAAAAAAAN6sVgEAAAAAMMjMMWrwgGyv7YQOWN%2FSAsO5SGM%3Dg8MG9Jq93Rlllaok6eht7HvRCruN4Vpzp4NaVsZaaHHWSTzKI8",
]


@in_pattern("twitter")
async def twitter_search(event):
    try:
        match = event.text.split(maxsplit=1)[1].lower()
    except IndexError:
        return await event.answer(
            [], switch_pm="Enter Query to Search", switch_pm_param="start"
        )
    try:
        return await event.answer(
            _ult_cache["twitter"][match],
            switch_pm="• Twitter Search •",
            switch_pm_param="start",
        )
    except KeyError:
        pass
    headers = {"Authorization": f"bearer {choice(_bearer_collected)}"}
    res = await async_searcher(
        f"https://api.twitter.com/1.1/users/search.json?q={match}",
        headers=headers,
        re_json=True,
    )
    reso = []
    for user in res:
        thumb = wb(user["profile_image_url_https"], 0, "image/jpeg", [])
        if user.get("profile_banner_url"):
            url = user["profile_banner_url"]
            text = f"[\xad]({url})• **Name :** `{user['name']}`\n"
        else:
            text = f"• **Name :** `{user['name']}`\n"
        text += f"• **Description :** `{user['description']}`\n"
        text += f"• **Username :** `@{user['screen_name']}`\n"
        text += f"• **Followers :** `{user['followers_count']}`    • **Following :** `{user['friends_count']}`\n"
        pro_ = "https://twitter.com/" + user["screen_name"]
        text += f"• **Link :** [Click Here]({pro_})\n_"
        reso.append(
            await event.builder.article(
                title=user["name"],
                description=user["description"],
                url=pro_,
                text=text,
                thumb=thumb,
            )
        )
    swi_ = f"🐦 Showing {len(reso)} Results!" if reso else "No User Found :("
    await event.answer(reso, switch_pm=swi_, switch_pm_param="start")
    if _ult_cache.get("twitter"):
        _ult_cache["twitter"].update({match: reso})
    else:
        _ult_cache.update({"twitter": {match: reso}})


_savn_cache = {}


@in_pattern("saavn")
async def savn_s(event):
    try:
        query = event.text.split(maxsplit=1)[1].lower()
    except IndexError:
        return await event.answer(
            [], switch_pm="Enter Query to search 🔍", switch_pm_param="start"
        )
    if query in _savn_cache:
        return await event.answer(
            _savn_cache[query],
            switch_pm=f"Showing Results for {query}",
            switch_pm_param="start",
        )
    results = await saavn_search(query)
    swi = "🎵 Saavn Search" if results else "No Results Found!"
    res = []
    for song in results:
        thumb = wb(song["image"], 0, "image/jpeg", [])
        text = f"• **Title :** {song['title']}"
        text += f"\n• **Year :** {song['year']}"
        text += f"\n• **Lang :** {song['language']}"
        text += f"\n• **Artist :** {song['artists']}"
        text += f"\n• **Release Date :** {song['release_date']}"
        res.append(
            await event.builder.article(
                title=song["title"],
                description=song["artists"],
                type="audio",
                text=text,
                include_media=True,
                buttons=Button.switch_inline(
                    "Search Again 🔍", query="saavn", same_peer=True
                ),
                thumb=thumb,
                content=wb(
                    song["url"],
                    0,
                    "audio/mp4",
                    [
                        Audio(
                            title=song["title"],
                            duration=int(song["duration"]),
                            performer=song["artists"],
                        )
                    ],
                ),
            )
        )
    await event.answer(res, switch_pm=swi, switch_pm_param="start")
    _savn_cache.update({query: res})


@in_pattern("tl")
async def inline_tl(ult):
    try:
        match = ult.text.split(maxsplit=1)[1]
    except IndexError:
        text = f"**Telegram TlObjects Searcher.**\n__(Don't use if you don't know what it is!)__\n\n• Example Usage\n`@{asst.me.username} tl GetFullUserRequest`"
        return await ult.answer(
            [
                await ult.builder.article(
                    title="How to Use?",
                    description="Tl Searcher by DarkPentester",
                    url="https://t.me/DarkPentester",
                    text=text,
                )
            ],
            switch_pm="Tl Search 🔍",
            switch_pm_param="start",
        )
    res = []
    for key in tlobjects.values():
        if match.lower() in key.__name__.lower():
            tyyp = "Function" if "tl.functions." in str(key) else "Type"
            text = f"**Name:** `{key.__name__}`\n"
            text += f"**Category:** `{tyyp}`\n"
            text += f"\n`from {key.__module__} import {key.__name__}`\n\n"
            if args := str(inspect.signature(key))[1:][:-1]:
                text += "**Parameter:**\n"
                for para in args.split(","):
                    text += " " * 4 + "`" + para + "`\n"
            text += f"✨ [Reference Link](https://tl.telethon.dev/?q={key.__name__})"
            text += f"\n**Layer:** `{LAYER}`"
            res.append(
                await ult.builder.article(
                    title=key.__name__,
                    description=tyyp,
                    url="https://t.me/DarkPentester",
                    text=text[:4000],
                )
            )
    mo = f"Showing {len(res)} results!" if res else f"No Results for {match}!"
    await ult.answer(res[:50], switch_pm=mo, switch_pm_param="start")


InlinePlugin.update(
    {
        "Pʟᴀʏ Sᴛᴏʀᴇ Aᴘᴘs": "app telegram",
        "Mᴏᴅᴅᴇᴅ Aᴘᴘs": "mods minecraft",
        "Sᴇᴀʀᴄʜ Oɴ Gᴏᴏɢʟᴇ": "go Heartless",
        "WʜɪSᴘᴇʀ": "wspr @username Hello🎉",
        "YᴏᴜTᴜʙᴇ Dᴏᴡɴʟᴏᴀᴅᴇʀ": "yt alan walker faded",
        "Piston Eval": "run javascript console.log('Hello Heartless')",
        "OʀᴀɴɢᴇFᴏx🦊": "ofox beryllium",
        "Tᴡɪᴛᴛᴇʀ Usᴇʀ": "twitter heartless",
        "Fᴅʀᴏɪᴅ Sᴇᴀʀᴄʜ": "fdroid telegram",
        "Sᴀᴀᴠɴ sᴇᴀʀᴄʜ": "saavn",
        "Tʟ Sᴇᴀʀᴄʜ": "tl",
    }
)

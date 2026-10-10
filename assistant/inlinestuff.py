import asyncio
import base64
import inspect
import time
from datetime import datetime
from html import unescape
from random import choice
from re import compile as re_compile
from urllib.parse import parse_qs, quote, urlparse

from bs4 import BeautifulSoup as bs
from telethon import Button
from telethon.tl.alltlobjects import LAYER, tlobjects
from telethon.tl.types import DocumentAttributeAudio as Audio
from telethon.tl.types import InputWebDocument as wb

from CythonX.fns.misc import google_search
from CythonX.fns.tools import (
    async_searcher,
    get_google_images,
    get_ofox,
    saavn_search,
)

from . import *
from . import _ult_cache
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

_INLINE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)


@in_pattern("ip")
async def _(e):
    try:
        quer = e.text.split(" ", maxsplit=1)[1].strip()
    except IndexError:
        quer = ""
    if not quer:
        tip = await e.builder.article(
            title="Ip Info",
            description="Give me an ip address",
            thumb=wb(ippic, 0, "image/jpeg", []),
            text="**ⲒⲢ Ⲓⲛϝⲟ**\n\nYou didn't search any ip address",
            buttons=Button.switch_inline("Sᴇᴀʀᴄʜ Aɢᴀɪɴ", query="ip ", same_peer=True),
        )
        return await e.answer([tip], switch_pm="IP Info", switch_pm_param="start")

    url = f"http://ip-api.com/json/{quote(quer)}"
    try:
        data = await async_searcher(url, re_json=True)
    except Exception as er:
        LOGS.exception(er)
        data = None

    if not isinstance(data, dict):
        err = await e.builder.article(
            title="IP Lookup Failed",
            description="Could not reach IP API",
            text=f"**ⲒⲢ Ⲓⲛϝⲟ**\n\nCould not look up `{quer}`.",
            buttons=Button.switch_inline("Sᴇᴀʀᴄʜ Aɢᴀɪɴ", query="ip ", same_peer=True),
        )
        return await e.answer([err])

    status = str(data.get("status") or "fail").lower()
    if status != "success":
        message = data.get("message") or "Invalid query"
        err = await e.builder.article(
            title="IP Not Found",
            description=str(message),
            text=(
                f"**ⲒⲢ Ⲓⲛϝⲟ**\n\n"
                f"**Qᴜᴇʀʏ**:- `{quer}`\n"
                f"**𐍃ᴛᥲᴛᥙs**:- `{status}`\n"
                f"**Mᴇssᴀɢᴇ**:- `{message}`"
            ),
            thumb=wb(ippic, 0, "image/jpeg", []),
            buttons=[
                Button.switch_inline("Sᴇᴀʀᴄʜ Aɢᴀɪɴ", query="ip ", same_peer=True),
                Button.switch_inline("Sʜᴀʀᴇ", query=f"ip {quer}", same_peer=False),
            ],
        )
        return await e.answer([err], switch_pm="IP Info", switch_pm_param="start")

    lat = data.get("lat")
    lon = data.get("lon")
    maps = (
        f"https://maps.google.com/?q={lat},{lon}"
        if lat is not None and lon is not None
        else None
    )
    query_ip = data.get("query") or quer
    country = data.get("country") or "—"
    country_code = data.get("countryCode") or "—"
    region = data.get("region") or "—"
    region_name = data.get("regionName") or "—"
    city = data.get("city") or "—"
    zip_code = data.get("zip") or "—"
    timezone = data.get("timezone") or "—"
    isp = data.get("isp") or "—"
    org = data.get("org") or "—"
    asn = data.get("as") or "—"
    location_link = f"[Link]({maps})" if maps else "`—`"
    lat_v = lat if lat is not None else "—"
    lon_v = lon if lon is not None else "—"

    text = f"""**IP Aɗɗrᥱss**:- `{query_ip}`
**𐍃ᴛᥲᴛᥙs**:- `{status}`
**𑀝᧐ᥙᥒᴛry**:- `{country}`
**𑀝᧐ᥙᥒᴛry 𑀝᧐ɗᥱ**:- `{country_code}`
**Rᥱgi᧐ᥒ**:- `{region}`
**Rᥱgi᧐ᥒ 𐌽ᥲⲙᥱ**:- `{region_name}`
**𑀝iᴛy**:- `{city}`
**Ziρ**:- `{zip_code}`
**𑀉ᥲᴛiᴛᥙɗᥱ**:- `{lat_v}`
**𑀉᧐ᥒgiᴛᥙɗᥱ**:- `{lon_v}`
**Tiⲙᥱ Z᧐ᥒᥱ**:- `{timezone}`
**I𐍃P**:- `{isp}`
**𐌏RᏵ**:- `{org}`
**A𐍃**:- `{asn}`
**𑀉᧐ᥴᥲᴛi᧐ᥒ 𑀉iᥒκ**:- {location_link}
**✨ T.me/DarkPentester**"""

    buttons = [
        [
            Button.switch_inline("Sᴇᴀʀᴄʜ Aɢᴀɪɴ", query="ip ", same_peer=True),
            Button.switch_inline("Sʜᴀʀᴇ", query=f"ip {quer}", same_peer=False),
        ]
    ]
    if maps:
        buttons.insert(0, [Button.url("📍 Maps", maps)])

    result = await e.builder.article(
        title="IP Iᥒf᧐rⲙᥲᴛi᧐ᥒ Rᥱsᥙᥣᴛ",
        description=f"{status}\n{country}",
        text=text,
        thumb=wb(ippic, 0, "image/jpeg", []),
        link_preview=False,
        buttons=buttons,
    )
    await e.answer([result], switch_pm="IP Info", switch_pm_param="start")


@in_pattern("ofox", owner=True)
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


async def _ddg_search(query):
    """Fallback search using DuckDuckGo HTML."""
    url = "https://html.duckduckgo.com/html/"
    params = {"q": query}
    content = await async_searcher(url, post=True, data=params, re_content=True)
    soup = bs(content, "html.parser")
    results = []
    for result in soup.select(".result__body")[:10]:
        title_elem = result.select_one(".result__title a")
        snippet_elem = result.select_one(".result__snippet")
        if title_elem and title_elem.get("href"):
            title = title_elem.get_text(strip=True)
            link = title_elem["href"]
            desc = snippet_elem.get_text(strip=True) if snippet_elem else ""
            results.append({"title": title, "link": link, "snippet": desc})
    # Also try the lite version if no results
    if not results:
        try:
            lite_url = "https://lite.duckduckgo.com/lite/"
            lite_content = await async_searcher(lite_url, post=True, data={"q": query}, re_content=True)
            lite_soup = bs(lite_content, "html.parser")
            for link_elem in lite_soup.select("table tr td a")[:10]:
                title = link_elem.get_text(strip=True)
                link = link_elem.get("href", "")
                if title and link:
                    results.append({"title": title, "link": link, "snippet": ""})
        except Exception:
            pass
    return results


@in_pattern("go", owner=True)
async def gsearch(q_event):
    try:
        match = q_event.text.split(maxsplit=1)[1]
    except IndexError:
        return await q_event.answer(
            [], switch_pm="Google Search. Enter a query!", switch_pm_param="start"
        )
    searcher = []
    gresults = await google_search(match)
    # Fallback to DuckDuckGo if no results from Google
    if not gresults:
        gresults = await _ddg_search(match)
    for i in gresults:
        try:
            title = i.get("title") or ""
            link = i.get("link") or i.get("url") or ""
            desc = i.get("snippet") or i.get("description") or ""
            if not title or not link:
                continue
            searcher.append(
                await q_event.builder.article(
                    title=title,
                    description=desc[:200] if desc else "No description",
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
        except Exception:
            continue
    await q_event.answer(searcher, switch_pm="Google Search", switch_pm_param="start")


IMG = {}


@in_pattern("img", owner=True)
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
    for idx, img in enumerate(images[:10], start=1):
        image = (img or {}).get("original") or (img or {}).get("link")
        if not image or not str(image).startswith("http"):
            continue
        title = (img or {}).get("title") or f"{match} #{idx}"
        try:
            ress.append(
                await event.builder.photo(
                    image,
                    text=(
                        f"**🖼 {match}**\n"
                        f"_{str(title)[:80]}_\n\n"
                        f"**✨ T.me/DarkPentester**"
                    ),
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
                                same_peer=False,
                            ),
                        ],
                    ],
                )
            )
        except Exception as er:
            LOGS.exception("Inline image result failed: %s", er)
            continue
    if not ress:
        empty = await event.builder.article(
            title="No Images Found",
            description=match,
            text=f"**Image Search**\n\nNo images found for `{match}`.",
            buttons=Button.switch_inline(
                "Sᴇᴀʀᴄʜ Aɢᴀɪɴ", query="img ", same_peer=True
            ),
        )
        return await event.answer(
            [empty], switch_pm="No Results Found", switch_pm_param="start"
        )
    msg = f"Showing {len(ress)} Results!"
    IMG.update({match: ress})
    await event.answer(ress, switch_pm=msg, switch_pm_param="start")


@in_pattern("mods", owner=True)
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


def _play_store_stats(app):
    """Compact metadata line for Play Store inline cards."""
    bits = []
    score = app.get("score")
    if score is not None:
        try:
            bits.append(f"⭐ `{float(score):.1f}`")
        except (TypeError, ValueError):
            bits.append(f"⭐ `{score}`")
    installs = app.get("installs") or app.get("realInstalls")
    if installs:
        bits.append(f"📥 `{installs}`")
    if app.get("free") is True:
        bits.append("🆓 **Free**")
    elif app.get("price"):
        bits.append(f"💰 `{app.get('price')}`")
    genre = app.get("genre")
    if genre:
        bits.append(f"🏷 `{genre}`")
    version = app.get("version")
    if version:
        bits.append(f"📌 `v{version}`")
    updated = app.get("updated")
    if updated:
        bits.append(f"🗓 `{updated}`")
    return " · ".join(bits)

def _apk_download_url(app_id):
    """APKPure has a stable latest-APK endpoint keyed by Android package name."""
    return f"https://d.apkpure.com/b/APK/{app_id}?version=latest"


def _rank_play_apps(apps, query):
    q = query.strip().lower()
    if not q:
        return apps

    seen = set()

    # Known official package names for common apps
    known_packages = {
        "telegram": "org.telegram.messenger",
        "whatsapp": "com.whatsapp",
        "instagram": "com.instagram.android",
        "facebook": "com.facebook.katana",
        "twitter": "com.twitter.android",
        "youtube": "com.google.android.youtube",
        "gmail": "com.google.android.gm",
        "maps": "com.google.android.apps.maps",
        "chrome": "com.android.chrome",
    }

    def score(app):
        if not isinstance(app, dict):
            return -1
        app_id = str(
            app.get("appId")
            or app.get("app_id")
            or app.get("packageName")
            or app.get("package_name")
            or ""
        ).strip().lower()
        title = str(app.get("title") or "").strip().lower()
        developer = str(app.get("developer") or "").strip().lower()

        if not app_id:
            return -1
        if app_id in seen:
            return -1
        seen.add(app_id)

        # Exact title match gets highest priority
        if title == q:
            base = 1000
        # Known official package gets very high priority
        elif q in known_packages and app_id == known_packages[q]:
            base = 990
        # Exact package match
        elif app_id == q:
            base = 950
        # Package ends with query (e.g., org.telegram.messenger for query "messenger")
        elif app_id.endswith(f".{q}"):
            base = 900
        # Title starts with query
        elif title.startswith(q):
            base = 800
        # Developer exact match
        elif developer == q:
            base = 700
        # Query in package name
        elif q in app_id:
            base = 600
        # Query in title
        elif q in title:
            base = 400
        # Query in developer
        elif q in developer:
            base = 200
        else:
            base = 0

        # Keep Google Play relevance as a tie-breaker.
        try:
            base += float(app.get("score") or 0) / 100
        except Exception:
            pass
        return base

    return sorted(apps, key=score, reverse=True)


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


# Known official package names for common apps that Play Store search often misses
KNOWN_OFFICIAL_PACKAGES = {
    "telegram": "org.telegram.messenger",
    "whatsapp": "com.whatsapp",
    "instagram": "com.instagram.android",
    "facebook": "com.facebook.katana",
    "twitter": "com.twitter.android",
    "youtube": "com.google.android.youtube",
    "gmail": "com.google.android.gm",
    "maps": "com.google.android.apps.maps",
    "chrome": "com.android.chrome",
}


async def _fetch_official_app(package_name):
    """Fetch app details by exact package name."""
    if google_play_app is None:
        return None
    try:
        details = await asyncio.to_thread(
            google_play_app,
            package_name,
            lang="en",
            country="us",
        )
        return details
    except Exception:
        return None


@in_pattern("app", owner=True)
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
        apps = _rank_play_apps(
            apps,
            query,
        )

        # Fallback: If known official app is missing from search results, fetch it directly
        q_lower = query.lower()
        if q_lower in KNOWN_OFFICIAL_PACKAGES:
            official_pkg = KNOWN_OFFICIAL_PACKAGES[q_lower]
            # Check if official app is already in results
            found = any(
                _extract_play_app_id(app).lower() == official_pkg.lower()
                for app in apps
            )
            if not found:
                official_app = await _fetch_official_app(official_pkg)
                if official_app:
                    # Add to beginning of results
                    apps.insert(0, official_app)

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
            stats = _play_store_stats(app)

            text = (
                f"**📱 [{title}]({play_url})**\n\n"
                f"**• Dᴇᴠᴇʟᴏᴘᴇʀ •** `{developer}`\n"
                f"**• Pᴀᴄᴋᴀɢᴇ •** `{app_id}`\n"
            )
            if stats:
                text += f"**• Sᴛᴀᴛs •** {stats}\n"
            text += (
                f"\n**• Aʙᴏᴜᴛ •**\n"
                f"{description or 'No description available.'}\n\n"
                f"**✨ T.me/DarkPentester**"
            )

            buttons = [
                [
                    Button.url("Gᴘʟᴀʏ Lɪɴᴋ", url=play_url),
                    Button.inline("📥 Dᴏᴡɴʟᴏᴀᴅ Aᴘᴋ", data=f"gpa{app_id}"),
                ],
                [
                    Button.switch_inline("Mᴏʀᴇ Aᴘᴘs", query="app ", same_peer=True),
                    Button.switch_inline(
                        "Sʜᴀʀᴇ", query=f"app {query}", same_peer=False
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

PISTON_API = "https://emkc.org/api/v2/piston"
PISTON_RUNTIMES = {}
PISTON_ALIASES = {}


async def _get_piston_runtimes():
    if PISTON_RUNTIMES and PISTON_ALIASES:
        return PISTON_RUNTIMES

    data = await async_searcher(
        f"{PISTON_API}/runtimes",
        re_json=True,
    )

    if not isinstance(data, list):
        raise RuntimeError("Invalid response from Piston.")

    for runtime in data:
        name = (runtime.get("language") or runtime.get("name") or "").lower()
        if not name or name in PISTON_RUNTIMES:
            continue
        PISTON_RUNTIMES[name] = runtime
        for alias in runtime.get("aliases", []) or []:
            PISTON_ALIASES[str(alias).lower()] = name

    if not PISTON_RUNTIMES:
        raise RuntimeError("Piston returned no runtimes.")

    return PISTON_RUNTIMES


def _find_piston_language(language, runtimes):
    language = language.lower().strip()
    aliases = {
        "py": "python",
        "python3": "python",
        "js": "javascript",
        "javascript": "javascript",
        "node": "nodejs",
        "ts": "typescript",
        "cpp": "c++",
        "c++": "c++",
        "cxx": "c++",
        "c": "c",
        "rust": "rust",
        "rs": "rust",
        "go": "go",
        "golang": "go",
        "java": "java",
        "kotlin": "kotlin",
        "php": "php",
        "ruby": "ruby",
        "rb": "ruby",
        "perl": "perl",
        "swift": "swift",
        "bash": "bash",
        "sh": "shellscript",
    }

    candidate = aliases.get(language, language)
    if candidate in runtimes:
        return candidate

    # Check PISTON_ALIASES for runtime-specific aliases
    if candidate in PISTON_ALIASES:
        canonical = PISTON_ALIASES[candidate]
        if canonical in runtimes:
            return canonical

    for name in runtimes:
        if name == candidate:
            return name

    for name, runtime in runtimes.items():
        runtime_aliases = [str(x).lower() for x in runtime.get("aliases", []) or []]
        if candidate in runtime_aliases:
            return name

    for name in runtimes:
        if candidate in name or name in candidate:
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
        runtimes = await _get_piston_runtimes()
        language_name = _find_piston_language(language, runtimes)

        if not language_name:
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

        runtime = runtimes[language_name]
        payload = {
            "language": runtime.get("language") or language_name,
            "version": runtime.get("version") or "*",
            "files": [{"content": code}],
            "stdin": "",
            "run_timeout": 3000,
        }

        output = await async_searcher(
            f"{PISTON_API}/execute",
            post=True,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=payload,
            re_json=True,
            retries=2,
        )

        if not isinstance(output, dict):
            raise RuntimeError(
                "Invalid Piston response."
            )

        run_output = output.get("run") or {}
        compiler_message = (
            output.get("compile", {}).get("stderr")
            or output.get("compile", {}).get("stdout")
            or ""
        )
        program_message = (
            run_output.get("stdout")
            or run_output.get("stderr")
            or ""
        )
        status = run_output.get("code")
        signal = run_output.get("signal")

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
                f"`{language_name}`\n\n"
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

def _rank_fdroid_apps(apps, query):
    """Rank F-Droid apps by relevance to query."""
    q = query.strip().lower()
    if not q:
        return apps

    seen = set()

    def score(app):
        if not isinstance(app, dict):
            return -1
        package = str(app.get("package", "")).strip().lower()
        title = str(app.get("title", "")).strip().lower()
        if not package or package in seen:
            return -1
        seen.add(package)

        if title == q:
            base = 1000
        elif package == q or package.endswith(f".{q}"):
            base = 950
        elif title.startswith(q):
            base = 800
        elif q in package:
            base = 600
        elif q in title:
            base = 400
        else:
            base = 0
        return base

    return sorted(apps, key=score, reverse=True)


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
    apps = []
    for dat in BSC.find_all("a", "package-header")[:20]:
        try:
            image = dat.find("img", "package-icon")["src"]
            if image.endswith("/"):
                image = "https://graph.org/file/a8dd4a92c5a53a89d0eff.jpg"
            title = dat.find("h4", "package-name").text.strip()
            desc = dat.find("span", "package-summary").text.strip()
            license_el = dat.find("span", "package-license")
            license_name = (
                license_el.text.strip() if license_el else ""
            )
            package = dat["href"].split("packages/")[-1].rstrip("/")
            page_url = (
                dat["href"]
                if str(dat["href"]).startswith("http")
                else f"https://f-droid.org{dat['href']}"
            )
            apps.append({
                "title": title,
                "description": desc,
                "package": package,
                "image": image,
                "href": dat["href"],
                "page_url": page_url,
                "license": license_name,
            })
        except Exception:
            continue
    
    apps = _rank_fdroid_apps(apps, match)
    
    ress = []
    for app in apps[:10]:
        imga = wb(app["image"], 0, "image/jpeg", [])
        page_url = app.get("page_url") or (
            f"https://f-droid.org/packages/{app['package']}/"
        )
        text = (
            f"**📦 [{app['title']}]({page_url})**\n\n"
            f"**• Pᴀᴄᴋᴀɢᴇ •** `{app['package']}`\n"
        )
        if app.get("license"):
            text += f"**• Lɪᴄᴇɴsᴇ •** `{app['license']}`\n"
        text += (
            f"\n**• Sᴜᴍᴍᴀʀʏ •**\n"
            f"{app['description']}\n\n"
            f"**✨ T.me/DarkPentester**"
        )
        ress.append(
            await event.builder.article(
                title=app["title"],
                description=app["description"][:200],
                text=text,
                content=imga,
                thumb=imga,
                link_preview=False,
                buttons=[
                    [
                        Button.url("F-Droid Pᴀɢᴇ", page_url),
                        Button.inline(
                            "📥 Dᴏᴡɴʟᴏᴀᴅ Aᴘᴋ", "fd" + app["package"]
                        ),
                    ],
                    [
                        Button.switch_inline(
                            "Sᴇᴀʀᴄʜ Aɢᴀɪɴ",
                            query="fdroid ",
                            same_peer=True,
                        ),
                        Button.switch_inline(
                            "Sʜᴀʀᴇ", query=event.text, same_peer=False
                        ),
                    ],
                ],
            )
        )
    msg = f"Showing {len(ress)} Results!" if ress else "No Results Found"
    FDROID_.update({match: ress})
    await event.answer(ress, switch_pm=msg, switch_pm_param="start")


# Public web guest bearer (same token the X website uses for logged-out clients).
_TWITTER_GUEST_BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%"
    "3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
_TWITTER_USER_QUERY_ID = "sLVLhk0bGj3MVFEKTdax1w"
_twitter_guest_cache = {"token": None, "ts": 0}


async def _twitter_guest_token(force=False):
    """Fetch (and briefly cache) an X guest token."""
    now = time.time()
    if (
        not force
        and _twitter_guest_cache["token"]
        and now - _twitter_guest_cache["ts"] < 600
    ):
        return _twitter_guest_cache["token"]

    data = await async_searcher(
        "https://api.twitter.com/1.1/guest/activate.json",
        post=True,
        headers={
            "Authorization": f"Bearer {_TWITTER_GUEST_BEARER}",
            "User-Agent": _INLINE_UA,
        },
        re_json=True,
    )
    token = (data or {}).get("guest_token")
    if not token:
        raise RuntimeError("Could not obtain Twitter guest token.")
    _twitter_guest_cache.update({"token": token, "ts": now})
    return token


def _twitter_screen_candidates(query):
    """Build likely @handles from a free-text query."""
    raw = (query or "").strip().lstrip("@")
    if not raw:
        return []
    parts = [p for p in raw.replace("@", " ").split() if p]
    joined = "".join(parts)
    underscored = "_".join(parts)
    candidates = []
    for item in (raw, joined, underscored, parts[0] if parts else ""):
        handle = "".join(ch for ch in item if ch.isalnum() or ch == "_")
        if handle and handle.lower() not in {c.lower() for c in candidates}:
            candidates.append(handle)
    return candidates[:6]


async def _twitter_user_by_screen_name(screen_name, guest_token):
    variables = quote(
        '{"screen_name":"%s","withSafetyModeUserFields":true}'
        % screen_name.replace('"', "")
    )
    features = quote(
        "{"
        '"hidden_profile_subscriptions_enabled":true,'
        '"rweb_tipjar_consumption_enabled":true,'
        '"responsive_web_graphql_exclude_directive_enabled":true,'
        '"verified_phone_label_enabled":false,'
        '"subscriptions_verification_info_is_identity_verified_enabled":true,'
        '"subscriptions_verification_info_verified_since_enabled":true,'
        '"highlights_tweets_tab_ui_enabled":true,'
        '"responsive_web_twitter_article_tweet_consumption_enabled":true,'
        '"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,'
        '"responsive_web_graphql_timeline_navigation_enabled":true'
        "}"
    )
    url = (
        f"https://twitter.com/i/api/graphql/{_TWITTER_USER_QUERY_ID}/"
        f"UserByScreenName?variables={variables}&features={features}"
    )
    headers = {
        "Authorization": f"Bearer {_TWITTER_GUEST_BEARER}",
        "x-guest-token": guest_token,
        "User-Agent": _INLINE_UA,
        "x-twitter-active-user": "yes",
        "content-type": "application/json",
    }
    try:
        data = await async_searcher(url, headers=headers, re_json=True)
    except Exception:
        return None
    try:
        result = data["data"]["user"]["result"]
        if not result or result.get("__typename") == "UserUnavailable":
            return None
        legacy = result.get("legacy") or {}
        screen = legacy.get("screen_name") or result.get("rest_id")
        if not screen:
            return None
        avatar = legacy.get("profile_image_url_https") or ""
        if avatar:
            avatar = avatar.replace("_normal.", "_400x400.")
        return {
            "name": legacy.get("name") or screen,
            "screen_name": screen,
            "description": legacy.get("description") or "",
            "profile_image_url_https": avatar,
            "profile_banner_url": legacy.get("profile_banner_url") or "",
            "followers_count": legacy.get("followers_count") or 0,
            "friends_count": legacy.get("friends_count") or 0,
        }
    except (KeyError, TypeError, AttributeError):
        return None


async def _twitter_lookup_users(query):
    """Resolve users via X guest GraphQL (Nitter / v1.1 search are dead)."""
    guest = await _twitter_guest_token()
    users = []
    seen = set()
    for candidate in _twitter_screen_candidates(query):
        user = await _twitter_user_by_screen_name(candidate, guest)
        if user is None:
            # Guest token can expire mid-loop; refresh once and retry.
            guest = await _twitter_guest_token(force=True)
            user = await _twitter_user_by_screen_name(candidate, guest)
        if not user:
            continue
        key = user["screen_name"].lower()
        if key in seen:
            continue
        seen.add(key)
        users.append(user)
    return users


@in_pattern("twitter", owner=True)
async def twitter_search(event):
    try:
        match = event.text.split(maxsplit=1)[1].strip()
    except IndexError:
        return await event.answer(
            [], switch_pm="Enter Query to Search", switch_pm_param="start"
        )
    cache_key = match.lower()
    try:
        return await event.answer(
            _ult_cache["twitter"][cache_key],
            switch_pm="• Twitter Search •",
            switch_pm_param="start",
        )
    except KeyError:
        pass

    try:
        res = await _twitter_lookup_users(match)
    except Exception as exc:
        LOGS.exception("Twitter lookup failed")
        result = await event.builder.article(
            title="Twitter Error",
            description=str(exc)[:200],
            text=f"**Twitter Search Error**\n\n`{type(exc).__name__}: {exc}`",
        )
        return await event.answer([result])

    reso = []
    for user in res:
        profile_image = user.get("profile_image_url_https") or ""
        if not profile_image:
            profile_image = "https://abs.twimg.com/sticky/default_profile_images/default_profile_400x400.png"
        thumb = wb(profile_image, 0, "image/jpeg", [])
        description = user.get("description") or ""
        name = user.get("name") or "Unknown"
        screen_name = user.get("screen_name") or ""
        if user.get("profile_banner_url"):
            banner = user["profile_banner_url"]
            text = f"[\xad]({banner})• **Name :** `{name}`\n"
        else:
            text = f"• **Name :** `{name}`\n"
        text += f"• **Description :** `{description}`\n"
        text += f"• **Username :** `@{screen_name}`\n"
        text += (
            f"• **Followers :** `{user.get('followers_count', 0)}`    "
            f"• **Following :** `{user.get('friends_count', 0)}`\n"
        )
        pro_ = "https://x.com/" + screen_name
        text += f"• **Link :** [Click Here]({pro_})\n_"
        reso.append(
            await event.builder.article(
                title=name,
                description=description or f"@{screen_name}",
                url=pro_,
                text=text,
                thumb=thumb,
                buttons=Button.url("Open Profile", pro_),
            )
        )
    swi_ = f"🐦 Showing {len(reso)} Results!" if reso else "No User Found :("
    await event.answer(reso, switch_pm=swi_, switch_pm_param="start")
    if _ult_cache.get("twitter"):
        _ult_cache["twitter"].update({cache_key: reso})
    else:
        _ult_cache.update({"twitter": {cache_key: reso}})


_savn_cache = {}


@in_pattern("saavn", owner=True)
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


@in_pattern("tl", owner=True)
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
                    url="https://t.me/AssisXBot",
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
                    url="https://t.me/AssisXBot",
                    text=text[:4000],
                )
            )
    mo = f"Showing {len(res)} results!" if res else f"No Results for {match}!"
    await ult.answer(res[:50], switch_pm=mo, switch_pm_param="start")


InlinePlugin.update(
    {
        "IP Iɴғᴏ": "ip 8.8.8.8",
        "Iᴍᴀɢᴇ Sᴇᴀʀᴄʜ": "img Rose",
        "Sᴇᴀʀᴄʜ Oɴ Gᴏᴏɢʟᴇ": "go Heartless",
        "Pʟᴀʏ Sᴛᴏʀᴇ Aᴘᴘs": "app telegram",
        "Fᴅʀᴏɪᴅ Sᴇᴀʀᴄʜ": "fdroid telegram",
        "Mᴏᴅᴅᴇᴅ Aᴘᴘs": "mods minecraft",
        "OʀᴀɴɢᴇFᴏx🦊": "ofox beryllium",
        "Tᴡɪᴛᴛᴇʀ Usᴇʀ": "twitter Heartless",
        "Sᴀᴀᴠɴ Sᴇᴀʀᴄʜ": "saavn alan walker faded",
        "Tʟ Sᴇᴀʀᴄʜ": "tl Message",
        "Pɪsᴛᴏɴ Eᴠᴀʟ": "run python print('heartless')",
        "YᴏᴜTᴜʙᴇ Dᴏᴡɴʟᴏᴀᴅᴇʀ": "yt alan walker faded",
        "WʜɪSᴘᴇʀ": "wspr @username Hello",
        "Wᴇᴀᴛʜᴇʀ": "weather Tehran",
        "Tʀᴀɴsʟᴀᴛᴇ": "tr fa hello",
        "Wᴇʙ Uᴘʟᴏᴀᴅ": "webupload",
        "URL Shᴏʀᴛᴇɴᴇʀ": "short",
        "Iɴsᴛᴀɢʀᴀᴍ": "ig https://www.instagram.com/telegram/",
        "Qᴜɪᴢ Gᴀᴍᴇ": "quiz",
        "Cᴀʟᴄᴜʟᴀᴛᴏʀ": "calc",
        "Fɪʟᴇ Shᴀʀᴇ": "fs",
        "Fᴏɴᴛ Pᴀɴᴇʟ": "font heartless",
        "GɪᴛHᴜʙ": "gh ToxygenX",
        "ᴘʏᴘɪ sᴇᴀʀᴄʜ": "pypi requests",
        "Iᴍᴅʙ Sᴇᴀʀᴄʜ": "imdb inception",
        "Sᴇᴀʀᴄʜ Wɪɴɢᴇᴛ": "winget telegram",
    }
)

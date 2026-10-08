"""
✘ Commands Available -

• `{i}saavn <search query>`
    Download songs from Saavn.

• `{i}go <query>`
    For doing google search.

• `{i}github <username>`
    Get full information of the users github profile.

• `{i}img <query> ; <no of results>`
  `{i}img <query>`
    For doing images search.

• `{i}reverse`
    Reply an image or sticker to find its sauce.
"""

import os

import requests
from bs4 import BeautifulSoup as bs

try:
    from PIL import Image
except ImportError:
    Image = None
try:
    import cv2
except ImportError:
    cv2 = None
from telethon.tl.types import DocumentAttributeAudio

from CythonX.fns.misc import google_search
from CythonX.fns.tools import get_google_images, saavn_search

from . import LOGS, async_searcher, con, eod, fast_download, get_string, get_pstring, heartless_cmd


@heartless_cmd(
    pattern="github (.*)",
)
async def gitsearch(event):
    usrname = event.pattern_match.group(1).strip()
    if not usrname:
        return await event.eor(get_string("srch_1"))
    url = f"https://api.github.com/users/{usrname}"
    ult = await async_searcher(url, re_json=True)
    try:
        uname = ult["login"]
        uid = ult["id"]
        upic = f"https://avatars.githubusercontent.com/u/{uid}"
        ulink = ult["html_url"]
        uacc = ult["name"]
        ucomp = ult["company"]
        ublog = ult["blog"]
        ulocation = ult["location"]
        ubio = ult["bio"]
        urepos = ult["public_repos"]
        ufollowers = ult["followers"]
        ufollowing = ult["following"]
    except BaseException:
        return await event.eor(get_string("srch_2"))
    fullusr = f"""
**[GITHUB]({ulink})**
**Name** - {uacc}
**UserName** - {uname}
**ID** - {uid}
**Company** - {ucomp}
**Blog** - {ublog}
**Location** - {ulocation}
**Bio** - {ubio}
**Repos** - {urepos}
**Followers** - {ufollowers}
**Following** - {ufollowing}
"""
    await event.respond(fullusr, file=upic)
    await event.delete()


@heartless_cmd(pattern="go( (.*)|$)")
async def google(event):
    inp = event.pattern_match.group(1).strip()
    if not inp:
        return await eod(event, get_string("autopic_1"))
    x = await event.eor(get_pstring("com_2", "load"))
    gs = await google_search(inp)
    if not gs:
        return await eod(x, get_string("autopic_2").format(inp))
    out = ""
    for item in gs:
        text = item["title"]
        url = item["link"]
        des = item["snippet"]
        out += f"✨ [{text}]({url})\n`{des}`\n\n"
    omk = f"**✵ Google Search By Heartless**\n\n**✵ Query :** `{inp}`\n\n**✵ Results :**\n{out}"
    await x.eor(omk, link_preview=False)


@heartless_cmd(pattern="img( (.*)|$)")
async def goimg(event):
    query = event.pattern_match.group(1).strip()
    if not query:
        return await event.eor(get_string("autopic_1"))
    nn = await event.eor(get_pstring("com_1", "load"))
    lmt = 5
    if ";" in query:
        try:
            lmt = int(query.split(";")[1])
            query = query.split(";")[0]
        except BaseException:
            pass
    images = await get_google_images(query)
    for img in images[:lmt]:
        try:
            await event.client.send_file(
                event.chat_id,
                file=img["original"],
                caption="**✨ T.me/DarkPentester**",
                force_document=False,
            )
        except Exception as er:
            LOGS.exception(er)
    await nn.delete()


@heartless_cmd(pattern="reverse$")
async def reverse(event):
    reply = await event.get_reply_message()
    if not reply:
        return await event.eor("`Reply to an Image`")

    ult = await event.eor(get_pstring("com_1", "load"))
    dl = None
    file = None

    try:
        dl = await reply.download_media()
        if not dl:
            return await ult.eor("`Unable to download the replied media.`")

        file = await con.convert(dl, convert_to="png")
        if not file:
            return await ult.eor("`Unable to convert the replied media to an image.`")

        img = Image.open(file)
        try:
            x, y = img.size
        finally:
            img.close()

        # Google changed the HTML used by the old implementation.  The
        # previous code depended on the class "r5a77d", which is no longer
        # guaranteed to exist and caused IndexError when it was absent.
        with open(file, "rb") as image_file:
            grs = requests.post(
                "https://www.google.com/searchbyimage/upload",
                files={"encoded_image": (os.path.basename(file), image_file, "image/png")},
                data={"image_content": ""},
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0 Safari/537.36"
                    ),
                },
                allow_redirects=False,
                timeout=30,
            )

        loc = grs.headers.get("Location")
        if not loc:
            return await ult.eor(
                "`Google did not return a reverse-search URL. Try again later.`"
            )

        response = await async_searcher(
            loc,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0 Safari/537.36"
                ),
            },
        )

        if not response:
            return await ult.eor("`Google returned an empty reverse-search page.`")

        xx = bs(response, "html.parser")

        # Do not depend on Google's old "r5a77d" class.  Try several
        # structures that have been used by Google Images result pages.
        result = None

        for selector in (
            "div.r5a77d a",
            "a[href*='http']",
            "div[data-ved] a",
            "div[data-snhf] a",
        ):
            result = xx.select_one(selector)
            if result and result.get("href") and result.get_text(strip=True):
                break
            result = None

        if result is None:
            # Search for a result container by text/content as a final
            # fallback instead of indexing an empty list.
            for anchor in xx.find_all("a", href=True):
                text = anchor.get_text(" ", strip=True)
                href = anchor.get("href", "")
                if text and href.startswith(("http://", "https://")):
                    result = anchor
                    break

        if result is None:
            return await ult.eor(
                "`No source was found. Google may have changed its reverse-image page.`"
            )

        link = result.get("href")
        text = result.get_text(" ", strip=True)

        if link.startswith("/"):
            link = f"https://www.google.com{link}"

        await ult.edit(
            f"`Dimension ~ {x} : {y}`\n"
            f"Source ~ [{text}]({link})"
        )

    except requests.RequestException:
        await ult.eor("`Google reverse image search is temporarily unavailable.`")
    except Exception as er:
        LOGS.exception("Reverse image search failed: %s", er)
        await ult.eor("`Reverse image search failed. Please try again later.`")
    finally:
        if file and os.path.exists(file):
            try:
                os.remove(file)
            except OSError:
                pass
        if dl and dl != file and os.path.exists(dl):
            try:
                os.remove(dl)
            except OSError:
                pass


@heartless_cmd(
    pattern="saavn( (.*)|$)",
)
async def siesace(e):
    song = e.pattern_match.group(1).strip()
    if not song:
        return await e.eor("`Give me Something to Search", time=5)
    eve = await e.eor(f"`Searching for {song} on Saavn...`")
    try:
        data = (await saavn_search(song))[0]
    except IndexError:
        return await eve.eor(f"`{song} not found on saavn.`")
    try:
        title = data["title"]
        url = data["url"]
        img = data["image"]
        duration = data["duration"]
        performer = data["artists"]
    except KeyError:
        return await eve.eor("`Something went wrong.`")
    song, _ = await fast_download(url, filename=f"{title}.m4a")
    thumb, _ = await fast_download(img, filename=f"{title}.jpg")
    song, _ = await e.client.fast_uploader(song, to_delete=True)
    await eve.eor(
        file=song,
        text=f"`{title}`\n`From Saavn`",
        attributes=[
            DocumentAttributeAudio(
                duration=int(duration),
                title=title,
                performer=performer,
            )
        ],
        supports_streaming=True,
        thumb=thumb,
    )
    await eve.delete()
    os.remove(thumb)

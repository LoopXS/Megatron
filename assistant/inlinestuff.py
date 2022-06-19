import base64
from datetime import datetime
from random import choice
from re import compile as re_compile
from bs4 import BeautifulSoup as bs
from cython.functions.misc import google_search
from cython.functions.tools import async_searcher, dloader, get_ofox
from telethon import Button
from telethon.tl.types import InputWebDocument as wb

from . import *

ofox = "https://telegra.ph/file/231f0049fcd722824f13b.jpg"
binpic = "https://telegra.ph/file/be4dd7375ef2313a43c41.jpg"
ippic = "https://telegra.ph/file/807e012dbe2789c0648ee.jpg"
gugirl = "https://telegra.ph/file/0df54ae4541abca96aa11.jpg"
yeah = "https://telegra.ph/file/e3c67885e16a194937516.jpg"
ps = "https://telegra.ph/file/de0b8d9c858c62fae3b6e.jpg"
ultpic = "https://telegra.ph/file/9098ea976b4e104371522.jpg"
xkcdpic = "https://telegra.ph/file/040b5ab6e50e438fc215e.jpg"

api1 = base64.b64decode("QUl6YVN5QXlEQnNZM1dSdEI1WVBDNmFCX3c4SkF5NlpkWE5jNkZV").decode(
    "ascii"
)
api2 = base64.b64decode("QUl6YVN5QkYwenhMbFlsUE1wOXh3TVFxVktDUVJxOERnZHJMWHNn").decode(
    "ascii"
)
api3 = base64.b64decode("QUl6YVN5RGRPS253blB3VklRX2xiSDVzWUU0Rm9YakFLSVFWMERR").decode(
    "ascii"
)


@in_pattern("xkcd", owner=True)
async def _(e):
    try:
        quer = e.text.split(" ", maxsplit=1)[1]
    except IndexError:
        kkkk = e.builder.article(
            title="xkcd",
            description="Random Meme",
            thumb=wb(xkcdpic, 0, "image/jpeg", []),
            text="**XKCD Recovery**\n\nYou didn't search any query",
            buttons=Button.switch_inline("Sᴇᴀʀᴄʜ Aɢᴀɪɴ", query="xkcd ", same_peer=True),
        )
        await e.answer([kkkk])
        return
    xkcd_id = None
    if quer:
        if quer.isdigit():
            xkcd_id = quer
        else:
            xkcd_search_url = "https://relevantxkcd.appspot.com/process?"
            queryresult = requests.get(
                xkcd_search_url, params={"action": "xkcd", "query": quote(quer)}
            ).text
            xkcd_id = queryresult.split(" ")[2].lstrip("\n")
    if xkcd_id is None:
        xkcd_url = "https://xkcd.com/info.0.json"
    else:
        xkcd_url = "https://xkcd.com/{}/info.0.json".format(xkcd_id)
    r = requests.get(xkcd_url)
    if r.ok:
        data = r.json()
        year = data.get("year")
        month = data["month"].zfill(2)
        day = data["day"].zfill(2)
        xkcd_link = "https://xkcd.com/{}".format(data.get("num"))
        safe_title = data.get("safe_title")
        data.get("transcript")
        alt = data.get("alt")
        img = data.get("img")
        data.get("title")
        output_str = """
[XKCD]({})
Title: {}
Alt: {}
Day: {}
Month: {}
Year: {}""".format(
            xkcd_link, safe_title, alt, day, month, year
        )
        lul_k = builder.photo(file=img, text=output_str)
        await e.answer([lul_k])
    else:
        resultm = builder.article(
            title="- No Results :/ -", text=f"No Results Found.\n(C) CɪᴘʜᴇʀX"
        )
        await e.answer([resultm])

        
@in_pattern("bin", owner=True)
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


@in_pattern("ofox", owner=True)
async def _(e):
    match = None
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
            fox, switch_pm="OrangeFox Recovery Search.", switch_pm_param="start"
        )
    else:
        await e.answer(
            [], switch_pm="OrangeFox Recovery Search.", switch_pm_param="start"
        )
    
    
@in_pattern("fl2lnk ?(.*)", owner=True)
async def _(e):
    file_path = e.pattern_match.group(1)
    file_name = file_path.split("/")[-1]
    bitton = [
        [
            Button.inline("anonfiles", data=f"flanonfiles//{file_path}"),
            Button.inline("transfer", data=f"fltransfer//{file_path}"),
        ],
        [
            Button.inline("bayfiles", data=f"flbayfiles//{file_path}"),
            Button.inline("x0", data=f"flx0//{file_path}"),
        ],
        [
            Button.inline("file.io", data=f"flfile.io//{file_path}"),
            Button.inline("siasky", data=f"flsiasky//{file_path}"),
        ],
    ]
    try:
        lnk = e.builder.article(
            title="fl2lnk",
            text=f"**File:**\n{file_name}",
            buttons=bitton,
        )
    except BaseException:
        lnk = e.builder.article(
            title="fl2lnk",
            text="File not found",
        )
    await e.answer([lnk], switch_pm="File to Link.", switch_pm_param="start")


@callback(
    re_compile(
        "fl(.*)",
    ),
    owner=True,
)
async def _(e):
    t = (e.data).decode("UTF-8")
    data = t[2:]
    host = data.split("//")[0]
    file = data.split("//")[1]
    file_name = file.split("/")[-1]
    await e.edit(f"Uploading `{file_name}` on {host}")
    await dloader(e, host, file)

@in_pattern("heartless", owner=True)
async def repo(e):
    res = [
        await e.builder.article(
            title="𝒉𝒆𝒂𝒓𝒕𝒍𝒆𝒔𝒔",
            description="• 𝒖𝒏 𝒂𝒎𝒂𝒏𝒕 𝒔𝒂𝒏𝒔 𝒄𝒐𝒆𝒖𝒓 | 𝒆𝒏𝒔 𝒑𝒂𝒓𝒊𝒔 🎭",
            thumb=wb(ultpic, 0, "image/jpeg", []),
            text="ᥴᥣiᥴκ ᴛɦᥱ δᥙᴛᴛ᧐ᥒ δᥱᥣ᧐ᥕ ᴛ᧐ ᥴ᧐ᥒᴛᥲᥴᴛ !",
            buttons=[
                [Button.url("• ꜱᴜᴘᴘᴏʀᴛ •", url="t.me/DarkPentesterX")],
            ],
        ),
    ]
    await e.answer(res, switch_pm="CɪᴘʜᴇʀX Suᴩᴇr Tᴇᴄhnᴏlᴏgy Bᴏᴛ", switch_pm_param="start")
    
    
@in_pattern("go", owner=True)
async def gsearch(q_event):
    try:
        match = q_event.text.split(" ", maxsplit=1)[1]
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
            desc = i["description"]
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
    await q_event.answer(searcher, switch_pm="Google Search.", switch_pm_param="start")
    

@in_pattern("mods", owner=True)
async def _(e):
    try:
        quer = e.text.split(" ", maxsplit=1)[1]
    except IndexError:
        return await e.answer(
            [], switch_pm="Mod Apps Search. Enter app name!", switch_pm_param="start"
        )
    page = 1
    start = (page - 1) * 3 + 1
    da = choice([api1, api2, api3])
    url = f"https://www.googleapis.com/customsearch/v1?key={da}&cx=25b3b50edb928435b&q={quer}&start={start}"
    data = await async_searcher(url, re_json=True)
    search_items = data.get("items")
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
    await e.answer(modss, switch_pm="Search Mod Applications.", switch_pm_param="start")

    
@in_pattern("xda", owner=True)
async def xda_dev(event):
    QUERY = event.text.split(" ", maxsplit=1)
    try:
        query = QUERY[1]
    except IndexError:
        return await event.answer(
            [], switch_pm=get_string("instu_3"), switch_pm_param="start"
        )
    le = "https://www.xda-developers.com/search/" + query.replace(" ", "+")
    ct = await async_searcher(le, re_content=True)
    ml = bs(ct, "html.parser", from_encoding="utf-8")
    ml = ml.find_all("div", re_compile("layout_post_"), id=re_compile("post-"))
    out = []
    for on in ml:
        data = on.find_all("img", "xda_image")[0]
        title = data["alt"]
        thumb = data["src"]
        hre = on.find_all("div", "item_content")[0].find("h4").find("a")["href"]
        desc = on.find_all("div", "item_meta clearfix")[0].text
        thumb = wb(thumb, 0, "image/jpeg", [])
        text = f"[{title}]({hre})"
        out.append(
            await event.builder.article(
                title=title, description=desc, url=hre, thumb=thumb, text=text
            )
        )
    uppar = "No Results Found :(" if not out else "|| XDA Search Results ||"
    await event.answer(out, switch_pm=uppar, switch_pm_param="start")


APP_CACHE = {}


@in_pattern("app", owner=True)
async def _(e):
    try:
        f = e.text.split(" ", maxsplit=1)[1]
    except IndexError:
        swa = get_string("instu_1")
        res = []
        if APP_CACHE:
            [res.append(APP_CACHE[a][0]) for a in APP_CACHE.keys()]
            swa = get_string("instu_2")
        return await e.answer(res, switch_pm=swa, switch_pm_param="start")
    try:
        return await e.answer(
            APP_CACHE[f], switch_pm="Application Searcher.", switch_pm_param="start"
        )
    except KeyError:
        pass
    foles = []
    base_uri = "https://play.google.com"
    url = f"{base_uri}/store/search?q={f.replace(' ', '%20')}&c=apps"
    aap = await async_searcher(url, re_content=True)
    b_ = bs(aap, "html.parser", from_encoding="utf-8")
    aap = b_.find_all("div", "Vpfmgd")
    for z in aap[:10]:
        url = base_uri + z.find("a")["href"]
        scra = await async_searcher(url, re_content=True)
        bp = bs(scra, "html.parser", from_encoding="utf-8")
        name = z.find("div", "WsMG1c nnK0zc")["title"]
        desc = (
            str(bp.find("div", jsname="sngebd"))
            .replace('<div jsname="sngebd">', "")
            .replace("<br/>", "\n")
            .replace("</div>", "")[:300]
            + "..."
        )
        dev = z.find("div", "KoLSrc").text
        icon = z.find("img", "T75of QNCnCf")["data-src"]
        text = f"**••Aᴘᴘ Nᴀᴍᴇ••** [{name}]({icon})\n"
        text += f"**••Dᴇᴠᴇʟᴏᴘᴇʀ••** `{dev}`\n"
        text += f"**••Dᴇsᴄʀɪᴘᴛɪᴏɴ••**\n`{desc}`"
        foles.append(
            await e.builder.article(
                title=name,
                description=dev,
                thumb=wb(icon, 0, "image/jpeg", []),
                text=text,
                link_preview=True,
                buttons=[
                    [Button.url("Lɪɴᴋ", url=url)],
                    [
                        Button.switch_inline(
                            "Mᴏʀᴇ Aᴘᴘs",
                            query="app ",
                            same_peer=True,
                        ),
                        Button.switch_inline(
                            "Sʜᴀʀᴇ",
                            query=f"app {f}",
                            same_peer=False,
                        ),
                    ],
                ],
            ),
        )
    APP_CACHE.update({f: foles})
    await e.answer(foles, switch_pm="Application Searcher.", switch_pm_param="start")


PISTON_URI = "https://emkc.org/api/v2/piston/"
PISTON_LANGS = {}


@in_pattern("run", owner=True)
async def piston_run(event):
    try:
        lang = event.text.split()[1]
        code = event.text.split(maxsplit=2)[2]
    except IndexError:
        result = await event.builder.article(
            title="Bad Query",
            description="Usage: [Language] [code]",
            text=f'**Inline Usage**\n\n`@{asst.me.username} run python print("hello world")`\n\n[Language List](https://telegra.ph/Ultroid-09-01-6)',
        )
        return await event.answer([result])
    if not PISTON_LANGS:
        se = await async_searcher(PISTON_URI + "runtimes", re_json=True)
        PISTON_LANGS.update({lang.pop("language"): lang for lang in se})
    if lang in PISTON_LANGS.keys():
        version = PISTON_LANGS[lang]["version"]
    else:
        result = await event.builder.article(
            title="Unsupported Language",
            description="Usage: [Language] [code]",
            text=f'**Inline Usage**\n\n`@{asst.me.username} run python print("hello world")`\n\n[Language List](https://telegra.ph/Ultroid-09-01-6)',
        )
        return await event.answer([result])
    output = (
        await async_searcher(
            PISTON_URI + "execute",
            post=True,
            json={"language": lang, "version": version, "files": [{"content": code}]},
            re_json=True,
        )
    )["run"]["output"] or get_string("instu_4")
    if len(output) > 3000:
        output = output[:3000] + "..."
    result = await event.builder.article(
        title="Result",
        description=output,
        text=f"• **Language:**\n`{lang}`\n\n• **Code:**\n`{code}`\n\n• **Result:**\n`{output}`",
        buttons=Button.switch_inline("Fork", query=event.text, same_peer=True),
    )
    await event.answer([result], switch_pm="• Piston •", switch_pm_param="start")


@in_pattern("clipart", owner=True)
async def clip(e):
    try:
        quer = e.text.split(" ", maxsplit=1)[1]
    except IndexError:
        await e.answer([], switch_pm="ClipArt Search", switch_pm_param="start")
    quer = quer.replace(" ", "+")
    sear = f"https://clipartix.com/search/{quer}"
    html = urlopen(sear)
    bs = BeautifulSoup(html, "html.parser", from_encoding="utf-8")
    resul = bs.find_all("img", "attachment-full size-full")
    buil = e.builder
    hm = []
    for res in resul:
        hm += [buil.photo(include_media=True, file=res["src"])]
    await e.answer(
        hm, gallery=True, switch_pm="Clipart Searcher", switch_pm_param="start"
    )


@in_pattern("ebooks", owner=True)
async def clip(e):
    try:
        quer = e.text.split(" ", maxsplit=1)[1]
    except IndexError:
        await e.answer(
            [], switch_pm="Enter Query to Look for EBook", switch_pm_param="start"
        )
        return
    quer = quer.replace(" ", "+")
    sear = f"http://www.gutenberg.org/ebooks/search/?query={quer}&submit_search=Go%21"
    magma = requests.get(sear).content
    bs = BeautifulSoup(magma, "html.parser", from_encoding="utf-8")
    out = bs.find_all("img")
    Alink = bs.find_all("a", "link")
    if len(out) == 0:
        return await e.answer(
            [], switch_pm="No Results Found !", switch_pm_param="start"
        )
    buil = e.builder
    dont_take = [
        "Authors",
        "Did you mean",
        "Sort Alpha",
        "Sort by",
        "Subjects",
        "Bookshelves",
    ]
    hm = []
    titles = []
    for num in Alink:
        try:
            rt = num.find("span", "title").text
            if not rt.startswith(tuple(dont_take)):
                titles.append(rt)
        except BaseException:
            pass
    for rs in range(len(out)):
        if "/cache/epub" in out[rs]["src"]:
            link = out[rs]["src"]
            num = link.split("/")[3]
            link = "https://gutenberg.org" + link.replace("small", "medium")
            file = wb(link, 0, "image/jpeg", [])
            hm.append(
                buil.article(
                    title=titles[rs],
                    type="photo",
                    description="GutenBerg Search",
                    thumb=file,
                    content=file,
                    include_media=True,
                    text=f"**• Ebook Search**\n\n->> `{titles[rs]}`",
                    buttons=Button.inline("Get as Doc", data=f"ebk_{num}"),
                )
            )
    await e.answer(hm, switch_pm="Ebooks Search", switch_pm_param="start")

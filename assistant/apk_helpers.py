import os

from telethon import Button

from CythonX.fns.helper import fast_download
from CythonX.fns.tools import async_searcher

from . import LOGS

_APK_DL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://apkpure.com/",
}

_APTOIDE_PACKAGE_ALIASES = {
    "org.telegram.messenger": "org.telegram.messenger.web",
}

PLAY_APK_MEDIA = {}


def format_apk_panel(title, package, page_url, source_label):
    safe_title = title or package
    return (
        f"**📦 {safe_title}**\n\n"
        f"**• Pᴀᴄᴋᴀɢᴇ •** `{package}`\n"
        f"**• Sᴏᴜʀᴄᴇ •** {source_label}\n"
        f"**• Sᴛᴀᴛᴜs •** ✅ APK ready — save from this message\n\n"
        f"**• Lɪsᴛɪɴɢ •** [Open page]({page_url})\n\n"
        f"**✨ T.me/DarkPentester**"
    )


async def _aptoide_apk_url(package_name):
    data = await async_searcher(
        "https://ws75.aptoide.com/api/7/app/getMeta",
        params={"package_name": package_name},
        re_json=True,
    )
    if isinstance(data, dict) and (data.get("info") or {}).get("status") == "OK":
        path = ((data.get("data") or {}).get("file") or {}).get("path")
        if path:
            return path, (data.get("data") or {}).get("name") or package_name

    data = await async_searcher(
        "https://ws75.aptoide.com/api/7/apps/search",
        params={"query": package_name, "limit": 30},
        re_json=True,
    )
    for app in (data or {}).get("datalist", {}).get("list", []) or []:
        if str(app.get("package") or "").lower() != package_name.lower():
            continue
        path = (app.get("file") or {}).get("path")
        if path:
            return path, app.get("name") or package_name
    return None, None


async def _play_apk_sources(app_id):
    packages = [app_id]
    alias = _APTOIDE_PACKAGE_ALIASES.get(app_id)
    if alias:
        packages.append(alias)

    for package in packages:
        try:
            url, title = await _aptoide_apk_url(package)
            if url:
                yield url, title or package, {
                    "User-Agent": _APK_DL_HEADERS["User-Agent"],
                    "Accept": "*/*",
                }
        except Exception as exc:
            LOGS.info("Aptoide resolve failed for %s: %s", package, exc)

    for url in (
        f"https://d.apkpure.com/b/APK/{app_id}?version=latest",
        f"https://d.apkpure.net/b/APK/{app_id}?version=latest",
        f"https://download.apkpure.com/b/APK/{app_id}?version=latest",
    ):
        yield url, app_id, _APK_DL_HEADERS


async def download_and_upload_play_apk(event, app_id):
    from . import deliver_inline_apk

    apk_path = None
    errors = []
    title = app_id
    downloaded = False

    async for apk_url, src_title, headers in _play_apk_sources(app_id):
        title = src_title or app_id
        try:
            await event.edit(f"• Downloading `{title}`… •")
        except Exception:
            pass
        try:
            apk_path, _ = await fast_download(
                apk_url,
                filename=f"{app_id}.apk",
                headers=headers,
            )
            downloaded = True
            break
        except Exception as exc:
            errors.append(f"{apk_url.split('/')[2]}: {exc}")
            if apk_path and os.path.exists(apk_path):
                try:
                    os.remove(apk_path)
                except OSError:
                    pass
            apk_path = None

    if not downloaded or not apk_path:
        raise RuntimeError("No APK source available. " + "; ".join(errors[:3]))

    safe_name = f"{title}.apk".replace("/", "_")
    try:
        await event.edit(f"• Uploading `{title}`… •")
    except Exception:
        pass

    n_file, _ = await event.client.fast_uploader(
        apk_path,
        filename=safe_name,
        show_progress=False,
        to_delete=True,
    )

    play_url = f"https://play.google.com/store/apps/details?id={app_id}"
    caption = format_apk_panel(title, app_id, play_url, "Google Play")
    buttons = [
        [
            Button.url("Gᴘʟᴀʏ Lɪɴᴋ", play_url),
            Button.switch_inline("Mᴏʀᴇ Aᴘᴘs", query="app ", same_peer=True),
        ],
    ]
    msg = await deliver_inline_apk(event, n_file, caption, buttons=buttons)
    if msg and getattr(msg, "media", None):
        PLAY_APK_MEDIA[app_id] = msg.media
    return msg

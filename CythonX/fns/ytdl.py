import glob
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from aiohttp import ClientSession

from telethon import Button

from .. import LOGS, udB, HNDLR

try:
    from spotifysearch.async_client import SPOTLOGS
    from spotifysearch.async_client import Client as SpotifySearch
except ImportError:
    SPOTLOGS = None
    SpotifySearch = None
    LOGS.warning("'spotifysearch' not installed!")
    
try:
    from .ytsearch import Playlist, VideosSearch
except ImportError:
    Playlist, VideosSearch = None, None

from yt_dlp import YoutubeDL

from .helper import download_file, humanbytes, run_async, time_formatter, cusmo, get_pstring
from .tools import set_attributes


# ---------------Spotify---------------#


def spoti_search_api():
    return udB.get_key("SPOTIFY") or {}


def spoti_get():
    data = spoti_search_api()
    return data.get("SpotCliID"), data.get("SpotCliSec")


def create_spotify_client():
    """Create a configured Spotify API client.

    This compatibility wrapper is kept for plugins that import the
    historical helper from ``CythonX.fns.ytdl``.
    """
    if SpotifySearch is None:
        raise RuntimeError("spotifysearch is not installed.")

    client_id, client_secret = spoti_get()
    client_id = str(client_id or "").strip()
    client_secret = str(client_secret or "").strip()

    if not client_id:
        raise RuntimeError("Spotify Client ID is not configured.")
    if not client_secret:
        raise RuntimeError("Spotify Client Secret is not configured.")

    market = str(udB.get_key("SPOTIFY_MARKET") or "US").upper()
    return SpotifySearch(client_id, client_secret, market=market)


def normalize_spotify_url(value):
    """Normalize a Spotify URL/URI using the bundled Spotify client."""
    if SpotifySearch is None:
        return None
    return SpotifySearch.normalize_url(value)


def add_spot_search(client_id, client_secret):
    existing_data = spoti_search_api()
    existing_data["SpotCliID"] = client_id
    existing_data["SpotCliSec"] = client_secret
    udB.set_key("SPOTIFY", existing_data)
    return f"Spotify: client_id: {client_id}, client_secret {client_secret} Set" 


async def spsearch(query, limit=8, types=None):
    emoji = cusmo("spot")
    x, xx = spoti_get()
    Spotify = SpotifySearch(x, xx)
    search = await Spotify.search(query, types=["track", "playlist"])
    results = ""
    if types:
        for t in types:
            if t.lower() == "playlist":
                playlists = await search.get_playlists()
                playlists = playlists[:limit]
                for pl in playlists:
                    results += (
                        f"{emoji}[{pl.name}]({pl.url}) ~\n`{HNDLR}ytsp {pl.url}` \n\n"
                    )
            elif t.lower() == "album":
                albums = await search.get_albums()
                albums = albums[:limit]
                for alb in albums:
                    results += f"{emoji}[{alb.name} by {alb.artists[0].name}]({alb.url}) ~\n`{HNDLR}ytsp {alb.url}` \n\n"
    else:
        tracks = await search.get_tracks()
        tracks = tracks[:limit]
        for track in tracks:
            track_str = f"[{track.name} by {track.artists[0].name}]({track.url})"
            results += f"{emoji}{track_str} ~\n`{HNDLR}ytsp {track.url}` \n\n"
    return results


async def extract_thumbnail_url(spotify_url):
    try:
        response = requests.get(spotify_url)
        if response.status_code == 200:
            html = response.text
            match = re.search(r'"og:image"\s*content="([^"]+)"', html)
            if match:
                return match.group(1)
    except Exception as e:
        SPOTLOGS.info(f"Error extracting thumbnail URL: {e}")
    return None


async def extract_spotify_details(spotify_url):
    x, xx = spoti_get()
    Spotify = SpotifySearch(x, xx)
    try:
        response = requests.get(spotify_url)
        if response.status_code == 200:
            html = response.text
            soup = BeautifulSoup(html, "html.parser")
            title_tag = soup.find("title")
            title = title_tag.text if title_tag else None

            if title:
                #SPOTLOGS.info(f"Title found: {title}")
                title = re.sub(r"[#!$&]", "", title)

                if " - " in title and "by" in title:
                    title_parts = title.split(" - ", 1)
                    if len(title_parts) > 1:
                        title = (
                            title_parts[0].strip()
                            + " "
                            + title_parts[1].split(" by ", 1)[-1].strip()
                        )
                    else:
                        title = title_parts[0].strip()
                if title:
                    #SPOTLOGS.info(f"Processed title: {title}")
                    if "| Spotify" in title:
                        title = title.split("| Spotify")[0].strip()

                    #SPOTLOGS.info(f"Searching for title: {title}")
                    search = await Spotify.search(title)
                    tracks = await search.get_tracks()
                    #SPOTLOGS.info(f"Tracks found: {len(tracks)}")

                    closest_match = None
                    for track in tracks:
                        #SPOTLOGS.info(f"Checking track: {track.name}, URL: {track.url}")
                        if track.url == spotify_url:
                            title = track.name
                            #SPOTLOGS.info(f"Track title: {title}")
                            artist = ", ".join(artist.name for artist in track.artists)
                            #SPOTLOGS.info(f"Track artist: {artist}")
                            album = track.album.name
                            #SPOTLOGS.info(f"Album: {album}")
                            release_date = track.album.release_date
                            #SPOTLOGS.info(f"Track release: {release_date}")
                            duration = track.get_string_duration()
                            #SPOTLOGS.info(f"Track duration: {duration}")

                            link = f"[Spotify]({spotify_url})"
                            #SPOTLOGS.info(f"Track link: {link}")

                            return get_pstring("spotify_1", "spot").format(
                                title, link, duration, album, release_date, artist
                            )
                        if not closest_match:
                            closest_match = track

                    if closest_match:
                        SPOTLOGS.info(
                            f"Falling back to closest match: {closest_match.name}, URL: {closest_match.url}"
                        )
                        title = closest_match.name
                        artist = ", ".join(
                            artist.name for artist in closest_match.artists
                        )
                        album = closest_match.album.name
                        release_date = closest_match.album.release_date
                        duration = closest_match.get_string_duration()

                        link = f"[Spotify]({spotify_url})"

                        return get_pstring("spotify_1", "spotify").format(
                            title, link, duration, album, release_date, artist
                        )

            else:
                SPOTLOGS.info("Title tag not found.")
        else:
            SPOTLOGS.info(
                f"Failed to retrieve URL: {spotify_url}, status code: {response.status_code}"
            )
    except Exception as e:
        SPOTLOGS.info(f"Error extracting Spotify details: {e}")
    return None
                

async def get_spotify_list(url):
    x, xx = spoti_get()
    Spotify = SpotifySearch(x, xx)
    get_list = await Spotify.search(url)
    if "album" in url:
        tracks = [
            {
                "url": track.url,
                "name": track.name,
                "thumbnail": get_list.thumb,
            }
            for track in get_list.tracks
        ]
    else:
        tracks = [
            {
                "url": track.url,
                "name": track.name,
                "thumbnail": track.thumb,
            }
            for track in get_list.tracks
        ]
    return {"tracks": tracks}


def get_yt_link(query):
    search = VideosSearch(query, limit=1).result()
    try:
        return search["result"][0]["link"]
    except IndexError:
        return


async def insps(query, limit=8):
    x, xx = spoti_get()
    Spotify = SpotifySearch(x, xx)
    #    searchresults = await Spotify.search(query, types=["playlist", "track"], json=True)
    results = []
    if query[0] == "a":
        cmd = query[0]
        query = query[2:]
        SPOTLOGS.info(f"CMD SET: {cmd} : Querying: {query}")
    elif query[0] == "p":
        cmd = query[0]
        query = query[2:]
        SPOTLOGS.info(f"CMD SET: {cmd} : Querying: {query}")
    else:
        cmd = "False"
        SPOTLOGS.info(f"Querying: {query}")
    if cmd == "a":
        searchresults = await Spotify.search(
            query, types=["playlist", "track"], json=True, titleex=True
        )
    else:
        searchresults = await Spotify.search(
            query, types=["playlist", "track"], json=True
        )
    seen_urls = set()
    if query.startswith("https://open.spotify"):
        query = re.sub(r"\?si=[^&]*", "", query)
        if "playlist" in query:
            playlists = searchresults.get_playlist()
            title = playlists.name
            if playlists.description:
                if "href" not in playlists.description:
                    description = playlists.description
                else:
                    description = None
            else:
                description = None
            lnktitle = f"[{playlists.name}]({playlists.url})"
            total_tracks = playlists.total_tracks
            publicvisibility = playlists.public
            if playlists.creator:
                creator = playlists.creator
                creator_url = playlists.creator_url
                lnkcreator = f"[{creator[0]}]({creator_url[0]})"
            thumbnail_url = playlists.thumb
            total_duration = playlists.total_duration_string()
            url = playlists.url
            track_info = {
                "title": title,
                "description": description,
                "lnktitle": lnktitle,
                "total_tracks": total_tracks,
                "publicvis": publicvisibility[0],
                "lnkcreator": lnkcreator,
                "creator": creator,
                "total_duration": total_duration,
                "thumbnail_url": thumbnail_url,
                "url": url,
            }
            results.append(track_info)
            return results
        elif "album" in query:
            albums = await searchresults.get_albums()
            for al in albums[:limit]:
                album = await Spotify.search(al.url)
                artist_names = []
                linked_artists = []
                for artist in al.artists:
                    artist_names.append(artist.name)
                    linked_artists.append(f"[{artist.name}]({artist.url})")
                    artist_followers = await Spotify.get_artist_followers(artist.url)
                    artist_followers_str = (
                        str(artist_followers)
                        if artist_followers is not None
                        else "Unknown"
                    )
                    lnkartist = ", ".join(linked_artists)
                if al.url not in seen_urls:
                    seen_urls.add(al.url)
                    title = album.name
                    lnktitle = f"[{album.name}]({al.url})"
                    total_tracks = album.total_tracks
                    total_duration = album.total_duration_string()
                    thumbnail_url = album.thumb
                    popularity = album.popularity
                    record_label = album.label
                    url = al.url
                    track_info = {
                        "title": title,
                        "lnktitle": lnktitle,
                        "artist": ", ".join(artist_names),
                        "followers": artist_followers_str,
                        "lnkartist": lnkartist,
                        "total_tracks": total_tracks,
                        "total_duration": total_duration,
                        "thumbnail_url": thumbnail_url,
                        "popularity": popularity,
                        "url": url,
                        "record_label": record_label,
                    }
                    results.append(track_info)
            return results
        elif "track" in query:
            tracks = await searchresults.get_tracks()
            for track in tracks:
                title = track.name
                lnktitle = f"[{track.name}]({track.url})"
                artist = ", ".join(artist.name for artist in track.artists)
                lnkartist = ", ".join(
                    f"[{artist.name}]({artist.url})" for artist in track.artists
                )
                url = f"[Link]({track.url})"
                thumbnail_url = track.album.images[0].url
                album_name = track.album.name
                lnkalbum = f"[{track.album.name}]({track.album.url})"
                album_url = track.album.url
                popularity = track.popularity
                release_date = track.album.release_date
                duration = track.get_string_duration()
                preview = track.preview
                track_info = {
                    "title": title,
                    "lnktitle": lnktitle,
                    "duration": duration,
                    "album": album_name,
                    "lnkalbum": lnkalbum,
                    "album_url": album_url,
                    "popularity": popularity,
                    "artist": artist,
                    "lnkartist": lnkartist,
                    "release_date": release_date,
                    "thumbnail_url": thumbnail_url,
                    "url": url,
                    "preview": preview,
                }
                results.append(track_info)
            return results
    elif cmd == "p":
        playlists = await searchresults.get_playlists()
        for pl in playlists[:limit]:
            try:
                if pl.description:
                    if "href" not in pl.description:
                        description = pl.description
                    else:
                        description = "N/A"
                else:
                    description = "N/A"
            except AttributeError:
                description = "N/A"
                continue
            playlist = await Spotify.search(pl.url)
            if pl.url not in seen_urls:
                seen_urls.add(pl.url)
                title = playlist.name
                lnktitle = f"[{playlist.name}]({pl.url})"
                total_tracks = pl.total_tracks
                total_duration = playlist.total_duration_string()
                thumbnail_url = playlist.thumb
                publicvisibility = playlist.public
                if pl.creator:
                    lnkcreator = f"[{pl.creator}]({pl.creator_url})"
                    creator = pl.creator
                url = pl.url
                track_info = {
                    "title": title,
                    "description": description,
                    "lnktitle": lnktitle,
                    "total_tracks": total_tracks,
                    "total_duration": total_duration,
                    "thumbnail_url": thumbnail_url,
                    "lnkcreator": lnkcreator,
                    "creator": creator,
                    "publicvis": publicvisibility[0],
                    "url": url,
                }
                results.append(track_info)
        return results
    elif cmd == "a":
        albums = await searchresults.get_albums()
        for al in albums[:limit]:
            album = await Spotify.search(al.url)
            artist_names = []
            linked_artists = []
            for artist in al.artists:
                artist_names.append(artist.name)
                linked_artists.append(f"[{artist.name}]({artist.url})")
                artist_followers = await Spotify.get_artist_followers(artist.url)
                artist_name = ", ".join(artist_names)
                artist_followers_str = (
                    str(artist_followers) if artist_followers is not None else "Unknown"
                )
                lnkartist = ", ".join(linked_artists)
            if al.url not in seen_urls:
                seen_urls.add(al.url)
                title = album.name
                lnktitle = f"[{album.name}]({al.url})"
                total_tracks = album.total_tracks
                total_duration = album.total_duration_string()
                thumbnail_url = album.thumb
                popularity = album.popularity
                record_label = album.label
                url = al.url
                track_info = {
                    "title": title,
                    "lnktitle": lnktitle,
                    "artist": artist_name,
                    "followers": artist_followers_str,
                    "lnkartist": lnkartist,
                    "total_tracks": total_tracks,
                    "total_duration": total_duration,
                    "thumbnail_url": thumbnail_url,
                    "popularity": popularity,
                    "url": url,
                    "record_label": record_label,
                }
                results.append(track_info)
        return results
    else:
        tracks = await searchresults.get_tracks()
        if cmd == "False":
            for track in tracks[:limit]:
                title = track.name
                lnktitle = f"[{track.name}]({track.url})"
                artist = ", ".join(artist.name for artist in track.artists)
                lnkartist = ", ".join(
                    f"[{artist.name}]({artist.url})" for artist in track.artists
                )
                url = f"[Link]({track.url})"
                thumbnail_url = track.album.images[0].url
                album_name = track.album.name
                lnkalbum = f"[{track.album.name}]({track.album.url})"
                album_url = track.album.url
                popularity = track.popularity
                release_date = track.album.release_date
                duration = track.get_string_duration()
                preview = track.preview
                track_info = {
                    "title": title,
                    "lnktitle": lnktitle,
                    "duration": duration,
                    "album": album_name,
                    "lnkalbum": lnkalbum,
                    "album_url": album_url,
                    "popularity": popularity,
                    "artist": artist,
                    "lnkartist": lnkartist,
                    "release_date": release_date,
                    "thumbnail_url": thumbnail_url,
                    "url": url,
                    "preview": preview,
                }
                results.append(track_info)
            return results


# ---------------Spotify---------------#



    if len(title) > 20:
        title = title[:17] + "..."
    id_ = info["id"]
    thumb = id_ + ".jpg"
    await download_file(
        info.get("thumbnail", None) or f"https://i.ytimg.com/vi/{id_}/hqdefault.jpg",
        thumb,
    )
    ext = "." + ytd["outtmpl"]["default"].split(".")[-1]
    for _ext in [".m4a", ".mp3", ".opus"]:
        if ext == _ext:
            ext = _ext
            break
    id = None
    for x in glob.glob(f"{id_}*"):
        if not x.endswith("jpg"):
            id = x
    if not id:
        return
    ext = "." + id.split(".")[-1]
    file = title + ext
    try:
        os.rename(id, file)
    except FileNotFoundError:
        os.rename(id + ext, file)
    attributes = await set_attributes(file)
    res, _ = await event.client.fast_uploader(
        file, show_progress=True, event=event, to_delete=True
    )
    caption = f"`{info['title']}`"
    await event.client.send_file(
        event.chat_id,
        file=res,
        caption=caption,
        attributes=attributes,
        supports_streaming=True,
        thumb=thumb,
        reply_to=reply_to,
    )
    os.remove(thumb)
    try:
        await event.delete()
    except BaseException:
        pass


# ---------------YouTube Downloader Inline---------------



async def ytdl_progress(k, start_time, event):
    """Update a Telegram status message from a yt-dlp progress hook."""
    status = k.get("status")
    if status == "error":
        try:
            await event.edit("`YouTube download failed.`")
        except Exception:
            pass
        return

    if status != "downloading":
        return

    now = time.time()
    # Avoid hammering Telegram with edits.
    last_edit = getattr(event, "_ytdl_last_edit", 0)
    if now - last_edit < 4:
        return
    try:
        event._ytdl_last_edit = now
    except Exception:
        pass

    downloaded = k.get("downloaded_bytes") or 0
    total = k.get("total_bytes") or k.get("total_bytes_estimate") or 0
    speed = k.get("speed") or 0
    eta = k.get("eta")

    text = "`Downloading...`\n"
    if total:
        text += f"`{humanbytes(downloaded)} / {humanbytes(total)}`"
    else:
        text += f"`{humanbytes(downloaded)}`"
    if speed:
        text += f" `• {humanbytes(speed)}/s`"
    if eta is not None:
        text += f" `• ETA {time_formatter(int(eta) * 1000)}`"

    try:
        await event.edit(text)
    except Exception as ex:
        LOGS.debug(f"ytdl_progress: {ex}")


def get_yt_link(query):
    """Return the first YouTube result for a search query."""
    if not VideosSearch:
        return None
    try:
        search = VideosSearch(query, limit=1).result()
        return search.get("result", [{}])[0].get("link")
    except Exception as ex:
        LOGS.exception(ex)
        return None


def _yt_runtime_options():
    """
    EGM-Downloader style yt-dlp runtime configuration.

    EGM currently relies on modern yt-dlp + EJS + a JavaScript runtime,
    curl_cffi and bgutil-ytdlp-pot-provider for current YouTube extraction.
    """
    options = {
        "remote_components": ["ejs:github"],
        "retries": 25,
        "fragment_retries": 25,
        "socket_timeout": 30,
        "retry_sleep": "linear=1::5",
        "concurrent_fragment_downloads": 4,
        "noprogress": False,
        "quiet": True,
        "no_warnings": False,
        "nocheckcertificate": True,
        "geo_bypass": True,
    }

    # Current yt-dlp supports Node >= 22 for EJS. Dockerfile installs Node 22
    # and the bgutil provider in /root/bgutil-ytdlp-pot-provider.
    node = shutil.which("node") or "/usr/local/bin/node"
    if os.path.isfile(node) and os.access(node, os.X_OK):
        options["js_runtimes"] = {"node": {"path": node}}

    # Only use cookies when the file actually exists. Passing a missing
    # cookiefile can make an otherwise valid public-video request fail.
    cookiefile = os.path.abspath("cookies.txt")
    if os.path.isfile(cookiefile) and os.path.getsize(cookiefile) > 0:
        options["cookiefile"] = cookiefile

    return options


def _merge_yt_options(user_options=None):
    """Merge caller options without mutating the caller's dictionary."""
    merged = _yt_runtime_options()
    if user_options:
        merged.update(dict(user_options))

    # Keep EGM-style reliability options unless the caller explicitly overrides.
    merged.setdefault("retries", 25)
    merged.setdefault("fragment_retries", 25)
    merged.setdefault("socket_timeout", 30)
    merged.setdefault("remote_components", ["ejs:github"])

    return merged


def _find_downloaded_file(directory, video_id=None, preferred_ext=None):
    """Find the finished media file while ignoring yt-dlp temporary artifacts."""
    candidates = []
    for path in glob.glob(os.path.join(directory, "*")):
        if not os.path.isfile(path):
            continue
        name = os.path.basename(path)
        if any(name.endswith(ext) for ext in (".part", ".ytdl", ".temp", ".jpg", ".jpeg", ".webp")):
            continue
        if video_id and not name.startswith(f"{video_id}."):
            continue
        if os.path.getsize(path) <= 0:
            continue
        candidates.append(path)

    if preferred_ext:
        preferred = [p for p in candidates if p.lower().endswith(preferred_ext.lower())]
        if preferred:
            candidates = preferred

    if not candidates:
        return None

    return max(candidates, key=os.path.getmtime)


async def download_yt(event, link, ytd):
    """
    Normal command downloader.

    Kept compatible with the existing plugin API, but uses the same modern
    yt-dlp runtime configuration as the inline downloader.
    """
    reply_to = event.reply_to_msg_id or event
    opts = _merge_yt_options(ytd)
    opts.setdefault("outtmpl", "%(id)s.%(ext)s")

    try:
        info = await dler(event, link, opts, download=True)
    except Exception as ex:
        LOGS.exception(ex)
        try:
            await event.eor(f"`YouTube download failed: {ex}`")
        except Exception:
            pass
        return

    if not info:
        return

    entries = info.get("entries") if isinstance(info, dict) else None
    if entries:
        entries = [entry for entry in entries if entry]
        total = len(entries)

        for num, file_info in enumerate(entries, 1):
            video_id = file_info.get("id")
            if not video_id:
                continue

            downloaded_file = _find_downloaded_file(".", video_id)
            if not downloaded_file:
                await event.client.send_message(
                    event.chat_id,
                    f"`[{num}/{total}] Download finished but output file was not found.`",
                )
                continue

            title = file_info.get("title") or video_id
            ext = os.path.splitext(downloaded_file)[1]
            filename = f"{title}{ext}"

            try:
                os.replace(downloaded_file, filename)
            except OSError:
                filename = downloaded_file

            try:
                thumb = f"{video_id}.jpg"
                await download_file(
                    file_info.get("thumbnail")
                    or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                    thumb,
                )
            except Exception:
                thumb = None

            try:
                attributes = await set_attributes(filename)
                uploaded, _ = await event.client.fast_uploader(
                    filename,
                    show_progress=True,
                    event=event,
                    to_delete=True,
                )
                await event.client.send_file(
                    event.chat_id,
                    uploaded,
                    caption=f"`[{num}/{total}]` `{title}`",
                    attributes=attributes,
                    supports_streaming=True,
                    thumb=thumb,
                    reply_to=reply_to,
                )
            finally:
                if thumb and os.path.exists(thumb):
                    try:
                        os.remove(thumb)
                    except OSError:
                        pass

        try:
            await event.delete()
        except Exception:
            pass
        return

    video_id = info.get("id")
    downloaded_file = _find_downloaded_file(".", video_id)
    if not downloaded_file:
        await event.eor("`Download completed but the media file was not found.`")
        return

    title = info.get("title") or video_id or "YouTube"
    ext = os.path.splitext(downloaded_file)[1]
    filename = f"{title}{ext}"

    try:
        os.replace(downloaded_file, filename)
    except OSError:
        filename = downloaded_file

    thumb = f"{video_id}.jpg" if video_id else None
    try:
        if thumb:
            await download_file(
                info.get("thumbnail")
                or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                thumb,
            )

        attributes = await set_attributes(filename)
        uploaded, _ = await event.client.fast_uploader(
            filename,
            show_progress=True,
            event=event,
            to_delete=True,
        )
        await event.client.send_file(
            event.chat_id,
            uploaded,
            caption=f"`{info.get('title', title)}`",
            attributes=attributes,
            supports_streaming=True,
            thumb=thumb,
            reply_to=reply_to,
        )
    finally:
        if thumb and os.path.exists(thumb):
            try:
                os.remove(thumb)
            except OSError:
                pass

    try:
        await event.delete()
    except Exception:
        pass


# ---------------YouTube Downloader Inline---------------


def get_formats(type, id, data):
    """
    Build inline format choices using the same strategy as EGM Downloader:
    choose the highest-bitrate stream for each resolution and pair it with
    the best available audio stream at download time.
    """
    if not data or type not in ("audio", "video"):
        return []

    if type == "audio":
        audio = []
        # EGM supports 320 kbps MP3 as its high-quality default. Keep the
        # Telegram inline UI compact while still offering useful choices.
        for quality in ("128", "192", "320"):
            audio.append(
                {
                    "ytid": id,
                    "type": "audio",
                    "id": quality,
                    "quality": f"{quality}KBPS",
                    "ext": "mp3",
                }
            )
        return audio

    formats = data.get("formats") or []
    best_by_height = {}
    best_audio_size = 0

    for fmt in formats:
        if not isinstance(fmt, dict):
            continue

        vcodec = fmt.get("vcodec") or "none"
        acodec = fmt.get("acodec") or "none"

        if vcodec == "none" and acodec != "none":
            size = fmt.get("filesize") or fmt.get("filesize_approx") or 0
            try:
                best_audio_size = max(best_audio_size, int(size))
            except (TypeError, ValueError):
                pass
            continue

        if vcodec == "none":
            continue

        height = fmt.get("height")
        format_id = str(fmt.get("format_id") or "")
        if not height or not format_id:
            continue

        # yt-dlp format IDs are normally alphanumeric. Keep callback data safe.
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", format_id):
            continue

        try:
            height = int(height)
        except (TypeError, ValueError):
            continue

        bitrate = fmt.get("tbr") or 0
        try:
            bitrate = float(bitrate)
        except (TypeError, ValueError):
            bitrate = 0

        current = best_by_height.get(height)
        if current is None or bitrate > current["_bitrate"]:
            best_by_height[height] = {
                "fmt": fmt,
                "_bitrate": bitrate,
            }

    video = []
    # Telegram uploads become unreliable above ~2 GiB. Do not expose a
    # selection that is known to exceed the normal Bot API/userbot limit.
    TELEGRAM_LIMIT = 2 * 1024 * 1024 * 1024 - 16 * 1024 * 1024

    for height in sorted(best_by_height, reverse=True):
        fmt = best_by_height[height]["fmt"]
        format_id = str(fmt["format_id"])

        video_size = fmt.get("filesize") or fmt.get("filesize_approx") or 0
        try:
            estimated_size = int(video_size or 0) + int(best_audio_size or 0)
        except (TypeError, ValueError):
            estimated_size = 0

        if estimated_size and estimated_size >= TELEGRAM_LIMIT:
            continue

        dynamic_range = str(fmt.get("dynamic_range") or "").upper()
        hdr = dynamic_range not in ("", "SDR")
        ext = "mkv" if hdr or fmt.get("ext") == "webm" else "mp4"

        video.append(
            {
                "ytid": id,
                "type": "video",
                "id": format_id,
                "quality": f"{height}p" + (" HDR" if hdr else ""),
                "size": estimated_size,
                "ext": ext,
                "height": height,
                "hdr": hdr,
            }
        )

    return video


def get_buttons(listt):
    if not listt:
        return []

    video_id = listt[0]["ytid"]
    unique = {}

    # One button per resolution/quality.
    for item in listt:
        quality = item.get("quality", "Unknown")
        old = unique.get(quality)
        if old is None or item.get("size", 0) > old.get("size", 0):
            unique[quality] = item

    buttons = []
    for item in unique.values():
        label = item["quality"]
        if item.get("size"):
            label += f" {humanbytes(item['size'])}"

        data = (
            f"ytdownload:{item['type']}:{item['id']}:{item['ytid']}"
            f":{item.get('ext', 'mp4')}"
        )
        buttons.append(Button.inline(label, data=data))

    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([Button.inline("« Back", f"ytdl_back:{video_id}")])
    return rows


async def _inline_download(event, video_id, media_type, format_id, quality, ext):
    """Download one selected inline format and upload it back to Telegram."""
    import tempfile

    link = f"https://www.youtube.com/watch?v={video_id}"
    temp_dir = tempfile.mkdtemp(prefix=f"ytdl_{video_id}_")

    try:
        # Fetch metadata separately from the download so the output filename,
        # duration and thumbnail are known before upload.
        info = await extract_info(
            link,
            _merge_yt_options(
                {
                    "noplaylist": True,
                    "skip_download": True,
                }
            ),
        )
        if not info:
            raise RuntimeError("YouTube returned no metadata.")

        title = info.get("title") or video_id
        safe_title = re.sub(r'[\\/:*?"<>|]+', "_", title).strip()[:180] or video_id

        opts = _merge_yt_options(
            {
                "noplaylist": True,
                "outtmpl": os.path.join(temp_dir, "%(id)s.%(ext)s"),
                "overwrites": True,
                "continuedl": True,
                "progress_hooks": [lambda data: None],
            }
        )

        if media_type == "audio":
            opts.update(
                {
                    "format": "bestaudio/best",
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": str(quality),
                        },
                        {"key": "FFmpegMetadata"},
                    ],
                    "outtmpl": os.path.join(temp_dir, "%(id)s.%(ext)s"),
                }
            )
            preferred_ext = ".mp3"
        else:
            # EGM-style format fallback: selected video stream + best audio,
            # then best available combined stream as a last resort.
            video_selector = (
                f"{format_id}+bestaudio/{format_id}/"
                "bestvideo+bestaudio/best"
            )
            opts.update(
                {
                    "format": video_selector,
                    "merge_output_format": "mp4",
                    "postprocessor_args": [
                        "ffmpeg:-c:v copy -c:a aac -b:a 192k -movflags +faststart"
                    ],
                    "postprocessors": [{"key": "FFmpegMetadata"}],
                    "outtmpl": os.path.join(temp_dir, "%(id)s.%(ext)s"),
                }
            )
            preferred_ext = ".mp4"

        # Use a real progress hook instead of parsing yt-dlp's terminal output.
        start_time = time.time()

        def progress_hook(status):
            # Schedule the async Telegram update without blocking yt-dlp.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            loop.create_task(ytdl_progress(status, start_time, event))

        opts["progress_hooks"] = [progress_hook]

        await event.edit(
            "`Downloading from YouTube...`\n"
            f"`{safe_title}`"
        )

        await ytdownload(link, opts)

        output = _find_downloaded_file(
            temp_dir,
            video_id=video_id,
            preferred_ext=preferred_ext,
        )
        if not output:
            # Some containers are produced with a different extension after
            # post-processing. Pick any finished media file as a final fallback.
            output = _find_downloaded_file(temp_dir, video_id=video_id)

        if not output:
            raise RuntimeError(
                "yt-dlp completed without producing a media file. "
                "Check the bot log for the extractor error."
            )

        size = os.path.getsize(output)
        if size >= 2 * 1024 * 1024 * 1024:
            raise RuntimeError("The selected media is larger than Telegram's 2 GiB limit.")

        filename = f"{safe_title}{os.path.splitext(output)[1]}"

        thumb = None
        thumbnail_url = info.get("thumbnail")
        if thumbnail_url:
            try:
                thumb, _ = await download_file(
                    thumbnail_url,
                    os.path.join(temp_dir, "thumb.jpg"),
                )
            except Exception:
                thumb = None

        uploaded, _ = await event.client.fast_uploader(
            output,
            filename=filename,
            show_progress=True,
            event=event,
            to_delete=False,
        )

        attributes = await set_attributes(output)

        await event.edit(
            f"`{safe_title}`\n"
            f"`Size: {humanbytes(size)}`"
        )
        await event.edit(
            f"`{safe_title}`",
            file=uploaded,
            attributes=attributes,
            supports_streaming=media_type == "video",
            thumb=thumb,
            buttons=Button.switch_inline(
                "Search More",
                query="yt ",
                same_peer=True,
            ),
        )
    except Exception as ex:
        LOGS.exception("Inline YouTube download failed")
        try:
            await event.edit(
                "`YouTube download failed.`\n\n"
                f"`{str(ex)[:900]}`"
            )
        except Exception:
            pass
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


async def dler(event, url, opts=None, download=False):
    """
    Compatibility wrapper used by the existing plugins.

    The old implementation always passed a non-existent cookies.txt and used
    a mutable default dict. Both are fixed here.
    """
    merged = _merge_yt_options(opts)

    try:
        await event.edit("`Getting Data...`")
    except Exception:
        pass

    if download:
        await ytdownload(url, merged)

    try:
        return await extract_info(url, merged)
    except Exception as ex:
        LOGS.exception("yt-dlp extract_info failed")
        try:
            await event.edit(
                "`YouTube extraction failed.`\n"
                f"`{str(ex)[:900]}`"
            )
        except Exception:
            pass
        return None


@run_async
def ytdownload(url, opts):
    """Run yt-dlp with the modern EGM-compatible configuration."""
    try:
        options = _merge_yt_options(opts)
        with YoutubeDL(options) as ydl:
            return ydl.download([url])
    except Exception as ex:
        LOGS.exception(f"yt-dlp download failed: {ex}")
        raise


@run_async
def extract_info(url, opts=None):
    """Extract metadata with modern EJS/PO-token capable yt-dlp."""
    options = _merge_yt_options(opts)
    options.setdefault("noplaylist", True)
    options["skip_download"] = True

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url=url, download=False)
            return ydl.sanitize_info(info)
    except Exception as ex:
        LOGS.exception(f"yt-dlp extract failed: {ex}")
        raise


@run_async
def get_videos_link(url):
    """Extract video URLs from a YouTube playlist without youtubesearchpython."""
    playlist_match = re.search(
        r"(?:[?&]list=)([A-Za-z0-9_-]+)",
        url or "",
        flags=re.I,
    )
    if not playlist_match:
        return []

    playlist_id = playlist_match.group(1)
    playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"

    try:
        opts = _merge_yt_options(
            {
                "extract_flat": True,
                "skip_download": True,
                "noplaylist": False,
            }
        )
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)

        result = []
        for entry in (info or {}).get("entries") or []:
            if not entry:
                continue
            video_url = entry.get("webpage_url") or entry.get("url")
            if video_url and video_url.startswith("http"):
                result.append(video_url)
            elif entry.get("id"):
                result.append(f"https://www.youtube.com/watch?v={entry['id']}")
        return result
    except Exception as ex:
        LOGS.exception(f"YouTube playlist extraction failed: {ex}")
        return []

from __future__ import annotations

import asyncio
import html
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from telethon import Button

from CythonX._misc._decorators import (
    heartless_cmd,
)

from CythonX.fns.ytdl import (
    create_spotify_client,
    normalize_spotify_url,
    spoti_get,
)

from spotifysearch import (
    Album,
    Client as SpotifyClient,
    Playlist,
    Track,
)

from . import (
    InlinePlugin,
    LOGS,
    callback,
    in_pattern,
    udB,
    heartless_bot,
)


# ============================================================================
# Configuration
# ============================================================================

MAX_RESULTS = 10

INLINE_RESULTS = 10

TRACKS_PER_PAGE = 8

STATE_TTL = 30 * 60

DOWNLOAD_ROOT = Path(
    "resources/downloads/spotify"
)

SUPPORTED_AUDIO_EXTENSIONS = {
    ".mp3",
    ".m4a",
    ".opus",
    ".flac",
    ".ogg",
    ".wav",
    ".aac",
}


# ============================================================================
# Runtime state
# ============================================================================

STATES: dict[
    str,
    dict[str, Any],
] = {}

DOWNLOAD_LOCKS: dict[
    str,
    asyncio.Lock,
] = {}


# ============================================================================
# Generic helpers
# ============================================================================


def esc(
    value: Any,
) -> str:

    return html.escape(
        str(value or ""),
        quote=False,
    )


def make_key() -> str:

    return os.urandom(
        12
    ).hex()


def cleanup_states() -> None:

    now = time.time()

    for key, state in list(
        STATES.items()
    ):

        created = float(
            state.get(
                "created",
                now,
            )
        )

        if (
            now - created
            <= STATE_TTL
        ):
            continue

        STATES.pop(
            key,
            None,
        )

        DOWNLOAD_LOCKS.pop(
            key,
            None,
        )

        tmpdir = state.get(
            "tmpdir"
        )

        if tmpdir:

            shutil.rmtree(
                tmpdir,
                ignore_errors=True,
            )


def save_state(
    *,
    value: str,
    kind: str,
    title: str,
    obj: Any = None,
) -> str:

    cleanup_states()

    key = make_key()

    STATES[key] = {
        "created": time.time(),
        "value": value,
        "kind": kind,
        "title": title,
        "object": obj,
        "file": None,
        "tmpdir": None,
    }

    return key


def get_state(
    key: str,
) -> dict[str, Any] | None:

    cleanup_states()

    return STATES.get(
        key
    )


# ============================================================================
# Spotify client
# ============================================================================


def spotify_credentials() -> tuple[
    str,
    str,
]:

    client_id, client_secret = (
        spoti_get()
    )

    client_id = (
        str(client_id or "")
        .strip()
    )

    client_secret = (
        str(client_secret or "")
        .strip()
    )

    if not client_id:
        raise RuntimeError(
            "Spotify Client ID is not configured."
        )

    if not client_secret:
        raise RuntimeError(
            "Spotify Client Secret is not configured."
        )

    return (
        client_id,
        client_secret,
    )


def create_client() -> SpotifyClient:

    client_id, client_secret = (
        spotify_credentials()
    )

    market = (
        udB.get_key(
            "SPOTIFY_MARKET"
        )
        or "US"
    )

    return SpotifyClient(
        client_id,
        client_secret,
        market=str(
            market
        ).upper(),
    )


# ============================================================================
# Formatting
# ============================================================================


def artist_names(
    track: Track,
) -> str:

    names = [
        artist.name
        for artist in (
            track.artists
            or []
        )
        if artist.name
    ]

    return (
        ", ".join(names)
        or "Unknown"
    )


def track_caption(
    track: Track,
) -> str:

    album = track.album

    album_name = (
        album.name
        if album
        else "Unknown"
    )

    release = (
        album.release_date
        if album
        else ""
    )

    lines = [
        (
            f"🎵 <b>"
            f"{esc(track.name)}"
            f"</b>"
        ),
        "",
        (
            f"👤 <b>Artist:</b> "
            f"{esc(artist_names(track))}"
        ),
        (
            f"💿 <b>Album:</b> "
            f"{esc(album_name)}"
        ),
        (
            f"⏱ <b>Duration:</b> "
            f"{esc(track.get_string_duration())}"
        ),
    ]

    if release:

        lines.append(
            (
                f"📅 <b>Release:</b> "
                f"{esc(release)}"
            )
        )

    if track.url:

        lines.append(
            (
                f'🔗 <a href="{esc(track.url)}">'
                f"Spotify</a>"
            )
        )

    return "\n".join(
        lines
    )


def album_caption(
    album: Album,
) -> str:

    artists = ", ".join(
        artist.name
        for artist in (
            album.artists
            or []
        )
        if artist.name
    )

    lines = [
        (
            f"💿 <b>"
            f"{esc(album.name)}"
            f"</b>"
        ),
        "",
        (
            f"🎤 <b>Artist:</b> "
            f"{esc(artists or 'Unknown')}"
        ),
        (
            f"🎵 <b>Tracks:</b> "
            f"{album.total_tracks}"
        ),
    ]

    if album.release_date:

        lines.append(
            (
                f"📅 <b>Release:</b> "
                f"{esc(album.release_date)}"
            )
        )

    if album.label:

        lines.append(
            (
                f"🏷 <b>Label:</b> "
                f"{esc(album.label)}"
            )
        )

    if album.url:

        lines.append(
            (
                f'🔗 <a href="{esc(album.url)}">'
                f"Spotify</a>"
            )
        )

    return "\n".join(
        lines
    )


def playlist_caption(
    playlist: Playlist,
) -> str:

    lines = [
        (
            f"📚 <b>"
            f"{esc(playlist.name)}"
            f"</b>"
        ),
        "",
        (
            f"🎵 <b>Tracks:</b> "
            f"{playlist.total_tracks}"
        ),
    ]

    if playlist.creator:

        lines.append(
            (
                f"👤 <b>Creator:</b> "
                f"{esc(playlist.creator)}"
            )
        )

    if playlist.description:

        description = (
            playlist.description
        )

        if len(description) > 500:

            description = (
                description[:497]
                + "..."
            )

        lines.append(
            (
                f"📝 "
                f"{esc(description)}"
            )
        )

    if playlist.url:

        lines.append(
            (
                f'🔗 <a href="{esc(playlist.url)}">'
                f"Spotify</a>"
            )
        )

    return "\n".join(
        lines
    )


# ============================================================================
# Buttons
# ============================================================================


def track_buttons(
    key: str,
):

    return [
        [
            Button.inline(
                "⬇️ Download",
                data=(
                    f"spdl:{key}"
                ),
            )
        ],
        [
            Button.switch_inline(
                "🔎 Search",
                query="sp ",
                same_peer=True,
            )
        ],
    ]


def resource_buttons(
    key: str,
):

    return [
        [
            Button.inline(
                "🎵 Track List",
                data=(
                    f"splist:{key}:0"
                ),
            )
        ],
        [
            Button.inline(
                "⬇️ Download All",
                data=(
                    f"spall:{key}"
                ),
            )
        ],
        [
            Button.switch_inline(
                "🔎 Search Again",
                query="sp ",
                same_peer=True,
            )
        ],
    ]


# ============================================================================
# spotDL
# ============================================================================


def _spotdl_command(
    url: str,
    directory: Path,
) -> list[str]:

    executable = (
        shutil.which("spotdl")
    )

    if executable:

        command = [
            executable
        ]

    else:

        command = [
            sys.executable,
            "-m",
            "spotdl",
        ]

    output_template = (
        directory
        / "{title}.{output-ext}"
    )

    command.extend(
        [
            "download",
            url,
            "--output",
            str(output_template),
            "--format",
            "mp3",
            "--overwrite",
            "skip",
            "--print-errors",
        ]
    )

    client_id, client_secret = (
        spotify_credentials()
    )

    command.extend(
        [
            "--client-id",
            client_id,
            "--client-secret",
            client_secret,
            "--use-official-api",
            "--no-cache",
        ]
    )

    cookie_file = (
        udB.get_key(
            "SPOTIFY_COOKIES"
        )
        or udB.get_key(
            "YTDL_COOKIES"
        )
    )

    if not cookie_file:

        cookie_file = (
            "cookies.txt"
        )

    cookie_file = str(
        cookie_file
    )

    if os.path.isfile(
        cookie_file
    ):

        command.extend(
            [
                "--cookie-file",
                cookie_file,
            ]
        )

    return command


async def download_with_spotdl(
    url: str,
    directory: Path,
) -> list[Path]:

    normalized = (
        normalize_spotify_url(
            url
        )
    )

    if not normalized:

        raise ValueError(
            "Invalid Spotify URL."
        )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    command = _spotdl_command(
        normalized,
        directory,
    )

    LOGS.info(
        "Starting spotDL: %s",
        " ".join(
            (
                "<hidden>"
                if (
                    item
                    in {
                        spotify_credentials()[0],
                        spotify_credentials()[1],
                    }
                )
                else item
            )
            for item in command
        ),
    )

    process = (
        await asyncio.create_subprocess_exec(
            *command,
            cwd=str(directory),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    )

    stdout, stderr = (
        await process.communicate()
    )

    output = (
        stdout
        + b"\n"
        + stderr
    ).decode(
        "utf-8",
        "ignore",
    )

    files = sorted(
        [
            path
            for path in directory.iterdir()
            if (
                path.is_file()
                and path.suffix.lower()
                in SUPPORTED_AUDIO_EXTENSIONS
                and path.stat().st_size > 0
            )
        ],
        key=lambda path: (
            path.stat().st_mtime
        ),
    )

    if (
        process.returncode != 0
        and not files
    ):

        raise RuntimeError(
            output[-4000:]
            or (
                "spotDL failed with "
                f"exit code "
                f"{process.returncode}"
            )
        )

    return files


async def download_track(
    key: str,
    state: dict[str, Any],
) -> Path:

    lock = DOWNLOAD_LOCKS.setdefault(
        key,
        asyncio.Lock(),
    )

    async with lock:

        existing = state.get(
            "file"
        )

        if existing:

            path = Path(
                existing
            )

            if (
                path.is_file()
                and path.stat().st_size > 0
            ):

                return path

        DOWNLOAD_ROOT.mkdir(
            parents=True,
            exist_ok=True,
        )

        directory = Path(
            tempfile.mkdtemp(
                prefix="track_",
                dir=str(
                    DOWNLOAD_ROOT
                ),
            )
        )

        state[
            "tmpdir"
        ] = str(directory)

        files = (
            await download_with_spotdl(
                state["value"],
                directory,
            )
        )

        if not files:

            raise RuntimeError(
                "spotDL did not produce "
                "an audio file."
            )

        state[
            "file"
        ] = str(files[0])

        return files[0]


# ============================================================================
# Spotify API operations
# ============================================================================


async def search_tracks(
    query: str,
):

    client = create_client()

    try:

        result = await client.search(
            query,
            types=["track"],
            limit=MAX_RESULTS,
        )

        return result.tracks

    finally:

        await client.close()


async def resolve_spotify_url(
    url: str,
):

    normalized = (
        normalize_spotify_url(
            url
        )
    )

    if not normalized:

        raise ValueError(
            "Invalid Spotify URL."
        )

    client = create_client()

    try:

        return await client.get_url(
            normalized,
            include_tracks=True,
        )

    finally:

        await client.close()


# ============================================================================
# .sp command
# ============================================================================


@heartless_cmd(
    pattern=r"^sp(?:\s+(.*))?$"
)
async def spotify_command(
    event,
):

    query = (
        event.pattern_match.group(
            1
        )
        or ""
    ).strip()

    if not query:

        return await event.eor(
            (
                "🎵 <b>Spotify</b>\n\n"
                "Usage:\n"
                "<code>.sp song name</code>\n\n"
                "Or use a Spotify URL."
            ),
            parse_mode="html",
        )

    loading = await event.eor(
        "🔎 <b>Searching Spotify...</b>",
        parse_mode="html",
    )

    try:

        normalized = (
            normalize_spotify_url(
                query
            )
        )

        if normalized:

            resource = (
                await resolve_spotify_url(
                    normalized
                )
            )

            key = save_state(
                value=normalized,
                kind=(
                    "track"
                    if isinstance(
                        resource,
                        Track,
                    )
                    else (
                        "album"
                        if isinstance(
                            resource,
                            Album,
                        )
                        else "playlist"
                    )
                ),
                title=(
                    resource.name
                ),
                obj=resource,
            )

            if isinstance(
                resource,
                Track,
            ):

                return await loading.edit(
                    track_caption(
                        resource
                    ),
                    buttons=track_buttons(
                        key
                    ),
                    parse_mode="html",
                    link_preview=False,
                )

            if isinstance(
                resource,
                Album,
            ):

                return await loading.edit(
                    album_caption(
                        resource
                    ),
                    buttons=resource_buttons(
                        key
                    ),
                    parse_mode="html",
                    link_preview=False,
                )

            if isinstance(
                resource,
                Playlist,
            ):

                return await loading.edit(
                    playlist_caption(
                        resource
                    ),
                    buttons=resource_buttons(
                        key
                    ),
                    parse_mode="html",
                    link_preview=False,
                )

            raise RuntimeError(
                "Unsupported Spotify resource."
            )

        results = await search_tracks(
            query
        )

    except Exception as exc:

        LOGS.exception(
            "Spotify command failed"
        )

        return await loading.edit(
            (
                "❌ <b>Spotify Error</b>\n\n"
                f"<code>{esc(exc)}</code>"
            ),
            parse_mode="html",
        )

    if not results:

        return await loading.edit(
            "🔍 No Spotify result found.",
            parse_mode="html",
        )

    track = results[0]

    key = save_state(
        value=track.url,
        kind="track",
        title=track.name,
        obj=track,
    )

    await loading.edit(
        track_caption(
            track
        ),
        buttons=track_buttons(
            key
        ),
        parse_mode="html",
        link_preview=False,
    )


# ============================================================================
# Inline search
# ============================================================================


@in_pattern("sp")
async def spotify_inline(
    event,
):

    cleanup_states()

    try:

        query = (
            event.text.split(
                " ",
                1,
            )[1].strip()
        )

    except (
        IndexError,
        AttributeError,
    ):

        query = ""

    if not query:

        article = (
            await event.builder.article(
                title="🎵 Spotify",
                description=(
                    "Search Spotify tracks"
                ),
                text=(
                    "🎵 <b>Spotify Search</b>\n\n"
                    "Type a song, artist or "
                    "Spotify URL."
                ),
                buttons=[
                    [
                        Button.switch_inline(
                            "🎵 Search",
                            query="sp ",
                            same_peer=True,
                        )
                    ]
                ],
            )
        )

        return await event.answer(
            [article],
            cache_time=1,
        )

    try:

        normalized = (
            normalize_spotify_url(
                query
            )
        )

        if normalized:

            resource = (
                await resolve_spotify_url(
                    normalized
                )
            )

            return await answer_resource(
                event,
                resource,
                normalized,
            )

        tracks = await search_tracks(
            query
        )

    except Exception as exc:

        LOGS.exception(
            "Spotify inline search failed"
        )

        article = (
            await event.builder.article(
                title="❌ Spotify Error",
                description=str(
                    exc
                )[:180],
                text=(
                    "❌ <b>Spotify Error</b>\n\n"
                    f"<code>{esc(exc)}</code>"
                ),
            )
        )

        return await event.answer(
            [article],
            cache_time=0,
        )

    if not tracks:

        article = (
            await event.builder.article(
                title="🔍 No Results",
                description=(
                    "No matching Spotify track."
                ),
                text=(
                    "🔍 <b>No Results</b>\n\n"
                    f"No Spotify track found "
                    f"for <code>{esc(query)}</code>."
                ),
            )
        )

        return await event.answer(
            [article],
            cache_time=1,
        )

    articles = []

    for track in tracks[
        :INLINE_RESULTS
    ]:

        key = save_state(
            value=track.url,
            kind="track",
            title=track.name,
            obj=track,
        )

        article = (
            await event.builder.article(
                title=track.name[:64],
                description=(
                    f"{track.get_string_duration()}"
                    f" • "
                    f"{artist_names(track)}"
                )[:180],
                text=track_caption(
                    track
                ),
                buttons=track_buttons(
                    key
                ),
                link_preview=False,
            )
        )

        articles.append(
            article
        )

    await event.answer(
        articles,
        cache_time=1,
    )


# ============================================================================
# Resource inline result
# ============================================================================


async def answer_resource(
    event,
    obj,
    url: str,
):

    if isinstance(
        obj,
        Track,
    ):

        key = save_state(
            value=url,
            kind="track",
            title=obj.name,
            obj=obj,
        )

        article = (
            await event.builder.article(
                title=obj.name[:64],
                description=(
                    f"{obj.get_string_duration()}"
                    f" • "
                    f"{artist_names(obj)}"
                ),
                text=track_caption(
                    obj
                ),
                buttons=track_buttons(
                    key
                ),
                link_preview=False,
            )
        )

        return await event.answer(
            [article],
            cache_time=1,
        )

    if isinstance(
        obj,
        Album,
    ):

        key = save_state(
            value=url,
            kind="album",
            title=obj.name,
            obj=obj,
        )

        article = (
            await event.builder.article(
                title=obj.name[:64],
                description=(
                    f"Album • "
                    f"{obj.total_tracks} tracks"
                ),
                text=album_caption(
                    obj
                ),
                buttons=resource_buttons(
                    key
                ),
                link_preview=False,
            )
        )

        return await event.answer(
            [article],
            cache_time=1,
        )

    if isinstance(
        obj,
        Playlist,
    ):

        key = save_state(
            value=url,
            kind="playlist",
            title=obj.name,
            obj=obj,
        )

        article = (
            await event.builder.article(
                title=obj.name[:64],
                description=(
                    f"Playlist • "
                    f"{obj.total_tracks} tracks"
                ),
                text=playlist_caption(
                    obj
                ),
                buttons=resource_buttons(
                    key
                ),
                link_preview=False,
            )
        )

        return await event.answer(
            [article],
            cache_time=1,
        )

    raise RuntimeError(
        "Unsupported Spotify resource."
    )


# ============================================================================
# Download one track
# ============================================================================


@callback(
    re.compile(
        r"^spdl:([a-f0-9]+)$"
    )
)
async def spotify_download_callback(
    event,
):

    key = (
        event.pattern_match.group(1)
    )

    state = get_state(
        key
    )

    if not state:

        return await event.answer(
            "This result has expired.",
            alert=True,
        )

    if (
        state.get("kind")
        != "track"
    ):

        return await event.answer(
            "This is not a track.",
            alert=True,
        )

    await event.answer(
        "⬇️ Downloading..."
    )

    try:

        path = await download_track(
            key,
            state,
        )

        caption = (
            f"🎵 <b>"
            f"{esc(state['title'])}"
            f"</b>\n\n"
            "Downloaded successfully."
        )

        await event.edit(
            caption,
            file=str(path),
            buttons=[
                [
                    Button.switch_inline(
                        "🔎 Search More",
                        query="sp ",
                        same_peer=True,
                    )
                ]
            ],
            parse_mode="html",
        )

    except Exception as exc:

        LOGS.exception(
            "Spotify track download failed"
        )

        await event.edit(
            (
                "❌ <b>Download Failed</b>\n\n"
                f"<code>{esc(exc)}</code>"
            ),
            parse_mode="html",
            buttons=[
                [
                    Button.url(
                        "🔗 Open Spotify",
                        state["value"],
                    )
                ]
            ],
        )


# ============================================================================
# Track list
# ============================================================================


@callback(
    re.compile(
        r"^splist:([a-f0-9]+):(\d+)$"
    )
)
async def spotify_track_list_callback(
    event,
):

    key = (
        event.pattern_match.group(1)
    )

    page = int(
        event.pattern_match.group(2)
    )

    state = get_state(
        key
    )

    if not state:

        return await event.answer(
            "This result has expired.",
            alert=True,
        )

    obj = state.get(
        "object"
    )

    tracks = list(
        getattr(
            obj,
            "tracks",
            [],
        )
        or []
    )

    if not tracks:

        return await event.answer(
            "No tracks available.",
            alert=True,
        )

    total_pages = max(
        1,
        (
            len(tracks)
            + TRACKS_PER_PAGE
            - 1
        )
        // TRACKS_PER_PAGE,
    )

    page = max(
        0,
        min(
            page,
            total_pages - 1,
        ),
    )

    chunk = tracks[
        page * TRACKS_PER_PAGE:
        (
            page + 1
        ) * TRACKS_PER_PAGE
    ]

    buttons = []

    for track in chunk:

        if not track.url:
            continue

        buttons.append(
            [
                Button.switch_inline(
                    track.name[:35],
                    query=(
                        f"sp {track.url}"
                    ),
                    same_peer=True,
                )
            ]
        )

    navigation = []

    if page > 0:

        navigation.append(
            Button.inline(
                "◀️",
                data=(
                    f"splist:"
                    f"{key}:"
                    f"{page - 1}"
                ),
            )
        )

    navigation.append(
        Button.inline(
            (
                f"{page + 1}/"
                f"{total_pages}"
            ),
            data=(
                f"splist:"
                f"{key}:"
                f"{page}"
            ),
        )
    )

    if page < total_pages - 1:

        navigation.append(
            Button.inline(
                "▶️",
                data=(
                    f"splist:"
                    f"{key}:"
                    f"{page + 1}"
                ),
            )
        )

    buttons.append(
        navigation
    )

    await event.edit(
        (
            f"🎵 <b>"
            f"{esc(state['title'])}"
            f"</b>\n\n"
            "Select a track:"
        ),
        buttons=buttons,
        parse_mode="html",
    )


# ============================================================================
# Batch download
# ============================================================================


@callback(
    re.compile(
        r"^spall:([a-f0-9]+)$"
    )
)
async def spotify_download_all_callback(
    event,
):

    key = (
        event.pattern_match.group(1)
    )

    state = get_state(
        key
    )

    if not state:

        return await event.answer(
            "This result has expired.",
            alert=True,
        )

    if state.get(
        "kind"
    ) not in {
        "album",
        "playlist",
    }:

        return await event.answer(
            "This item cannot be batch downloaded.",
            alert=True,
        )

    await event.answer(
        "⬇️ Starting batch download..."
    )

    directory: Path | None = None

    try:

        DOWNLOAD_ROOT.mkdir(
            parents=True,
            exist_ok=True,
        )

        directory = Path(
            tempfile.mkdtemp(
                prefix="collection_",
                dir=str(
                    DOWNLOAD_ROOT
                ),
            )
        )

        state[
            "tmpdir"
        ] = str(directory)

        files = (
            await download_with_spotdl(
                state["value"],
                directory,
            )
        )

        if not files:

            raise RuntimeError(
                "No tracks were downloaded."
            )

        chat_id = getattr(
            event,
            "chat_id",
            None,
        )

        if chat_id is None:

            raise RuntimeError(
                "Destination chat is unavailable."
            )

        sent = 0

        for path in files:

            try:

                await heartless_bot.send_file(
                    chat_id,
                    str(path),
                    caption=(
                        f"🎵 <b>"
                        f"{esc(path.stem)}"
                        f"</b>"
                    ),
                    parse_mode="html",
                )

                sent += 1

            except Exception:

                LOGS.exception(
                    "Failed to upload %s",
                    path,
                )

        await event.edit(
            (
                "✅ <b>Batch Download Complete</b>\n\n"
                f"Uploaded: "
                f"<b>{sent}</b> / "
                f"<b>{len(files)}</b>"
            ),
            parse_mode="html",
        )

    except Exception as exc:

        LOGS.exception(
            "Spotify batch download failed"
        )

        await event.edit(
            (
                "❌ <b>Batch Download Failed</b>\n\n"
                f"<code>{esc(exc)}</code>"
            ),
            parse_mode="html",
        )

    finally:

        if directory:

            shutil.rmtree(
                directory,
                ignore_errors=True,
            )

        state[
            "tmpdir"
        ] = None


# ============================================================================
# Inline plugin
# ============================================================================

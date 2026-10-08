from __future__ import annotations

import asyncio
import logging
import os
import re

from typing import Any, Iterable
from urllib.parse import urlparse

import aiohttp

from .async_calls import (
    SpotifyHTTPError,
    request_api,
)

from .async_classes import (
    Authenticator,
)

from .constructor import (
    build_album,
    build_album_track,
    build_artist,
    build_episode,
    build_playlist,
    build_track,
)

from .classes import (
    Album,
    Artist,
    Episode,
    Playlist,
    Results,
    Track,
)

from .urlbuilder import (
    build_search_params,
)


SPOTLOGS = logging.getLogger(
    "spotifysearch"
)

SPOTLOGS.addHandler(
    logging.NullHandler()
)


SPOTIFY_ID_RE = re.compile(
    r"^[A-Za-z0-9]{22}$"
)


SUPPORTED_TYPES = {
    "track",
    "album",
    "playlist",
    "artist",
    "show",
    "episode",
    "audiobook",
}


class Client:
    """
    Asynchronous Spotify Web API client.

    Uses Spotify Client Credentials authentication
    and is intended for public catalog metadata.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        market: str | None = None,
        timeout: float = 25,
    ) -> None:

        self.auth = Authenticator(
            client_id,
            client_secret,
        )

        self.market = (
            market
            or os.getenv(
                "SPOTIFY_MARKET"
            )
            or "US"
        ).strip().upper()

        self.timeout = (
            aiohttp.ClientTimeout(
                total=float(timeout)
            )
        )

        self._session: (
            aiohttp.ClientSession
            | None
        ) = None

        self._session_lock = (
            asyncio.Lock()
        )

        self._closed = False

    async def _get_session(
        self,
    ) -> aiohttp.ClientSession:

        if self._closed:

            raise RuntimeError(
                "Spotify client is closed."
            )

        if (
            self._session is None
            or self._session.closed
        ):

            async with (
                self._session_lock
            ):

                if (
                    self._session is None
                    or self._session.closed
                ):

                    self._session = (
                        aiohttp.ClientSession(
                            timeout=self.timeout
                        )
                    )

        return self._session

    async def close(self) -> None:

        if (
            self._session is not None
            and not self._session.closed
        ):

            await self._session.close()

        self._session = None

        self._closed = True

    async def __aenter__(
        self,
    ) -> Client:

        return self

    async def __aexit__(
        self,
        exc_type,
        exc,
        tb,
    ) -> None:

        await self.close()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any]
        | None = None,
    ) -> Any:

        session = (
            await self._get_session()
        )

        token = (
            await self.auth.get_access_token()
        )

        try:

            return await request_api(
                token,
                method,
                path,
                params=params,
                session=session,
                timeout=int(
                    self.timeout.total
                    or 25
                ),
            )

        except SpotifyHTTPError as exc:

            if exc.status != 401:
                raise

            await self.auth.invalidate()

            token = (
                await self.auth.get_access_token()
            )

            return await request_api(
                token,
                method,
                path,
                params=params,
                session=session,
                timeout=int(
                    self.timeout.total
                    or 25
                ),
            )

    @staticmethod
    def normalize_url(
        value: str | None,
    ) -> str | None:

        if not value:
            return None

        value = value.strip()

        # Spotify URI:
        #
        # spotify:track:<id>
        #
        if value.startswith(
            "spotify:"
        ):

            parts = value.split(":")

            if (
                len(parts) == 3
                and parts[1]
                in SUPPORTED_TYPES
                and SPOTIFY_ID_RE.fullmatch(
                    parts[2]
                )
            ):

                return (
                    "https://open.spotify.com/"
                    f"{parts[1]}/{parts[2]}"
                )

            return None

        parsed = urlparse(value)

        if parsed.scheme not in {
            "http",
            "https",
        }:

            return None

        if (
            parsed.netloc.lower()
            not in {
                "open.spotify.com",
                "www.open.spotify.com",
            }
        ):

            return None

        parts = [
            item
            for item in parsed.path.split("/")
            if item
        ]

        if len(parts) < 2:
            return None

        entity = (
            parts[0].lower()
        )

        ident = parts[1]

        if (
            entity not in SUPPORTED_TYPES
            or not SPOTIFY_ID_RE.fullmatch(
                ident
            )
        ):

            return None

        return (
            "https://open.spotify.com/"
            f"{entity}/{ident}"
        )

    def parse_url(
        self,
        value: str | None,
    ) -> tuple[
        str | None,
        str | None,
    ]:

        normalized = (
            self.normalize_url(value)
        )

        if not normalized:
            return None, None

        parts = (
            normalized
            .rstrip("/")
            .split("/")
        )

        return (
            parts[-2],
            parts[-1],
        )

    @staticmethod
    def extract_id(
        value: str | None,
        entity: str,
    ) -> str | None:

        normalized = (
            Client.normalize_url(value)
        )

        if not normalized:
            return None

        parts = (
            normalized
            .rstrip("/")
            .split("/")
        )

        if (
            len(parts) >= 2
            and parts[-2] == entity
        ):

            return parts[-1]

        return None

    async def _paged(
        self,
        path: str,
        key: str,
        *,
        limit: int = 50,
        extra_params: dict[
            str,
            Any
        ] | None = None,
    ) -> list[dict[str, Any]]:

        wanted = max(
            0,
            int(limit),
        )

        if wanted == 0:
            return []

        output: list[
            dict[str, Any]
        ] = []

        offset = 0

        while len(output) < wanted:

            page_limit = min(
                50,
                wanted - len(output),
            )

            params = {
                "limit": page_limit,
                "offset": offset,
            }

            if extra_params:
                params.update(
                    extra_params
                )

            page = await self._request(
                "GET",
                path,
                params,
            )

            items = (
                page.get(key, [])
                if isinstance(
                    page,
                    dict,
                )
                else []
            )

            if (
                not isinstance(
                    items,
                    list,
                )
                or not items
            ):

                break

            output.extend(
                item
                for item in items
                if isinstance(
                    item,
                    dict,
                )
            )

            offset += len(items)

            total = (
                page.get("total")
                if isinstance(
                    page,
                    dict,
                )
                else None
            )

            if (
                isinstance(
                    total,
                    int,
                )
                and offset >= total
            ):

                break

        return output[:wanted]

    async def _album_full(
        self,
        data: dict[str, Any],
    ) -> Album:

        tracks: list[
            Any
        ] = []

        album_id = data.get(
            "id"
        )

        if album_id:

            items = await self._paged(
                f"/albums/{album_id}/tracks",
                "items",
                limit=int(
                    data.get(
                        "total_tracks"
                    )
                    or 50
                ),
                extra_params={
                    "market": self.market
                },
            )

            tracks = [
                build_album_track(item)
                for item in items
            ]

        return build_album(
            data,
            tracks,
        )

    async def _playlist_full(
        self,
        data: dict[str, Any],
    ) -> Playlist:

        tracks: list[Track] = []

        playlist_id = data.get(
            "id"
        )

        if playlist_id:

            total = (
                (
                    data.get(
                        "tracks"
                    )
                    or {}
                ).get(
                    "total"
                )
                or data.get(
                    "items_total"
                )
                or 1000
            )

            items = await self._paged(
                f"/playlists/{playlist_id}/items",
                "items",
                limit=int(total),
                extra_params={
                    "market": self.market
                },
            )

            for item in items:

                track = (
                    item.get("item")
                    or item.get("track")
                )

                if (
                    isinstance(
                        track,
                        dict,
                    )
                    and track.get(
                        "type"
                    ) == "track"
                ):

                    tracks.append(
                        build_track(
                            track
                        )
                    )

        return build_playlist(
            data,
            tracks,
        )

    async def get_url(
        self,
        url: str,
        *,
        include_tracks: bool = True,
    ) -> Any:

        entity, ident = (
            self.parse_url(url)
        )

        if (
            not entity
            or not ident
        ):

            raise ValueError(
                "Invalid Spotify URL or Spotify URI."
            )

        if entity == "track":

            data = await self._request(
                "GET",
                f"/tracks/{ident}",
                {
                    "market": self.market
                },
            )

            return build_track(data)

        if entity == "album":

            data = await self._request(
                "GET",
                f"/albums/{ident}",
                {
                    "market": self.market
                },
            )

            if include_tracks:
                return await self._album_full(
                    data
                )

            return build_album(data)

        if entity == "playlist":

            data = await self._request(
                "GET",
                f"/playlists/{ident}",
                {
                    "market": self.market
                },
            )

            if include_tracks:
                return await self._playlist_full(
                    data
                )

            return build_playlist(data)

        if entity == "artist":

            data = await self._request(
                "GET",
                f"/artists/{ident}",
            )

            return build_artist(data)

        if entity == "episode":

            data = await self._request(
                "GET",
                f"/episodes/{ident}",
                {
                    "market": self.market
                },
            )

            return build_episode(data)

        raise ValueError(
            "Spotify resource type "
            f"'{entity}' is not supported."
        )

    async def search(
        self,
        keywords: str,
        *,
        types: Iterable[str]
        | None = None,
        filters: dict[str, str]
        | None = None,
        market: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        json: bool = False,
        titleex: bool = False,
    ) -> (
        Results
        | dict[str, Any]
        | Any
    ):

        # Kept only for compatibility
        # with the old userbot code.
        del titleex

        keywords = (
            keywords or ""
        ).strip()

        if not keywords:

            raise ValueError(
                "Spotify search query cannot be empty."
            )

        entity, ident = (
            self.parse_url(keywords)
        )

        if entity and ident:

            return await self.get_url(
                keywords,
                include_tracks=True,
            )

        selected = [
            str(item)
            .strip()
            .lower()
            for item in (
                types
                or ["track"]
            )
            if str(item).strip()
        ]

        params = build_search_params(
            keywords,
            selected,
            filters=filters,
            market=(
                market
                or self.market
            ),
            limit=(
                10
                if limit is None
                else limit
            ),
            offset=(
                0
                if offset is None
                else offset
            ),
        )

        data = await self._request(
            "GET",
            "/search",
            params,
        )

        if json:
            return data

        result = Results(
            data=data
        )

        if "track" in selected:

            result.tracks = [
                build_track(item)
                for item in (
                    data.get(
                        "tracks"
                    )
                    or {}
                ).get(
                    "items",
                    [],
                )
                if isinstance(
                    item,
                    dict,
                )
            ]

        if "album" in selected:

            result.albums = [
                build_album(item)
                for item in (
                    data.get(
                        "albums"
                    )
                    or {}
                ).get(
                    "items",
                    [],
                )
                if isinstance(
                    item,
                    dict,
                )
            ]

        if "artist" in selected:

            result.artists = [
                build_artist(item)
                for item in (
                    data.get(
                        "artists"
                    )
                    or {}
                ).get(
                    "items",
                    [],
                )
                if isinstance(
                    item,
                    dict,
                )
            ]

        if "playlist" in selected:

            result.playlists = [
                build_playlist(item)
                for item in (
                    data.get(
                        "playlists"
                    )
                    or {}
                ).get(
                    "items",
                    [],
                )
                if isinstance(
                    item,
                    dict,
                )
            ]

        if "episode" in selected:

            result.episodes = [
                build_episode(item)
                for item in (
                    data.get(
                        "episodes"
                    )
                    or {}
                ).get(
                    "items",
                    [],
                )
                if isinstance(
                    item,
                    dict,
                )
            ]

        if "show" in selected:

            result.shows = [
                item
                for item in (
                    data.get(
                        "shows"
                    )
                    or {}
                ).get(
                    "items",
                    [],
                )
                if isinstance(
                    item,
                    dict,
                )
            ]

        if "audiobook" in selected:

            result.audiobooks = [
                item
                for item in (
                    data.get(
                        "audiobooks"
                    )
                    or {}
                ).get(
                    "items",
                    [],
                )
                if isinstance(
                    item,
                    dict,
                )
            ]

        return result

    async def get_track_preview(
        self,
        track_link: str,
    ) -> str:

        entity, ident = (
            self.parse_url(
                track_link
            )
        )

        if (
            entity != "track"
            or not ident
        ):

            return ""

        data = await self._request(
            "GET",
            f"/tracks/{ident}",
            {
                "market": self.market
            },
        )

        return str(
            data.get(
                "preview_url"
            )
            or ""
        )

    async def get_artist_followers(
        self,
        artist_link: str,
    ) -> int | None:

        entity, ident = (
            self.parse_url(
                artist_link
            )
        )

        if (
            entity != "artist"
            or not ident
        ):

            return None

        data = await self._request(
            "GET",
            f"/artists/{ident}",
        )

        followers = (
            data.get(
                "followers"
            )
            or {}
        )

        return int(
            followers.get(
                "total"
            )
            or 0
        )

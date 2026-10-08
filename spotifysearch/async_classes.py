from __future__ import annotations

import asyncio
import time

from .async_calls import request_access_token

from .classes import (
    Album,
    AlbumCover,
    AlbumTrack,
    Artist,
    BaseObject,
    Episode,
    Playlist,
    Results,
    Track,
    TrackPreview,
)


class Authenticator:
    """
    Spotify Client Credentials token cache.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
    ) -> None:

        self.client_id = (
            client_id or ""
        ).strip()

        self.client_secret = (
            client_secret or ""
        ).strip()

        self._token: str | None = None

        self._expires_at = 0.0

        self._lock = asyncio.Lock()

    def encode_credentials(self) -> str:

        import base64

        raw = (
            f"{self.client_id}:"
            f"{self.client_secret}"
            .encode("utf-8")
        )

        return base64.b64encode(
            raw
        ).decode("ascii")

    async def get_access_token(
        self,
    ) -> str:

        if (
            self._token
            and time.monotonic()
            < self._expires_at - 60
        ):

            return self._token

        async with self._lock:

            if (
                self._token
                and time.monotonic()
                < self._expires_at - 60
            ):

                return self._token

            if not self.client_id:

                raise RuntimeError(
                    "Spotify Client ID is not configured."
                )

            if not self.client_secret:

                raise RuntimeError(
                    "Spotify Client Secret is not configured."
                )

            payload = (
                await request_access_token(
                    self.client_id,
                    self.client_secret,
                )
            )

            token = payload.get(
                "access_token"
            )

            if not token:

                raise RuntimeError(
                    "Spotify did not return an access token."
                )

            expires_in = int(
                payload.get(
                    "expires_in"
                )
                or 3600
            )

            self._token = str(token)

            self._expires_at = (
                time.monotonic()
                + max(
                    60,
                    expires_in,
                )
            )

            return self._token

    async def invalidate(self) -> None:

        async with self._lock:

            self._token = None
            self._expires_at = 0.0

    async def get_acess_token(
        self,
    ) -> str:
        """
        Backward-compatible misspelled method.
        """

        return await self.get_access_token()


__all__ = [
    "Authenticator",

    "BaseObject",

    "Artist",
    "AlbumCover",
    "AlbumTrack",
    "Album",

    "TrackPreview",
    "Track",

    "Episode",

    "Playlist",

    "Results",
]

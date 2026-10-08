from __future__ import annotations

import base64
from typing import Any

import aiohttp


SPOTIFY_ACCOUNTS_URL = (
    "https://accounts.spotify.com"
)

SPOTIFY_API_URL = (
    "https://api.spotify.com/v1"
)

DEFAULT_TIMEOUT = 30


class SpotifyHTTPError(RuntimeError):

    def __init__(
        self,
        status: int,
        message: str,
        payload: Any = None,
    ) -> None:

        self.status = status
        self.payload = payload

        super().__init__(
            f"Spotify HTTP {status}: {message}"
        )


async def _read_payload(
    response: aiohttp.ClientResponse,
) -> Any:

    try:

        return await response.json(
            content_type=None
        )

    except Exception:

        return await response.text()


async def request_access_token(
    client_id: str,
    client_secret: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:

    if not client_id:
        raise ValueError(
            "Spotify client_id is required."
        )

    if not client_secret:
        raise ValueError(
            "Spotify client_secret is required."
        )

    credentials = (
        f"{client_id}:{client_secret}"
        .encode("utf-8")
    )

    encoded = base64.b64encode(
        credentials
    ).decode("ascii")

    headers = {
        "Authorization": (
            f"Basic {encoded}"
        ),
        "Content-Type": (
            "application/x-www-form-urlencoded"
        ),
        "Accept": "application/json",
    }

    data = {
        "grant_type": "client_credentials"
    }

    client_timeout = aiohttp.ClientTimeout(
        total=timeout
    )

    async with aiohttp.ClientSession(
        timeout=client_timeout
    ) as session:

        async with session.post(
            f"{SPOTIFY_ACCOUNTS_URL}/api/token",
            data=data,
            headers=headers,
        ) as response:

            payload = await _read_payload(
                response
            )

            if response.status >= 400:

                if isinstance(
                    payload,
                    dict,
                ):

                    message = (
                        payload.get(
                            "error_description"
                        )
                        or payload.get("error")
                        or "Spotify authentication failed."
                    )

                else:

                    message = (
                        "Spotify authentication failed."
                    )

                raise SpotifyHTTPError(
                    response.status,
                    str(message),
                    payload,
                )

            if not isinstance(
                payload,
                dict,
            ):

                raise SpotifyHTTPError(
                    response.status,
                    "Invalid Spotify token response.",
                    payload,
                )

            return payload


async def request_api(
    access_token: str,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    session: aiohttp.ClientSession | None = None,
) -> Any:

    if not access_token:
        raise ValueError(
            "Spotify access token is required."
        )

    path = "/" + path.lstrip("/")

    url = (
        f"{SPOTIFY_API_URL}"
        f"{path}"
    )

    headers = {
        "Authorization": (
            f"Bearer {access_token}"
        ),
        "Accept": "application/json",
    }

    own_session = session is None

    if own_session:

        session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(
                total=timeout
            )
        )

    try:

        assert session is not None

        async with session.request(
            method.upper(),
            url,
            params=params,
            headers=headers,
        ) as response:

            payload = await _read_payload(
                response
            )

            if response.status >= 400:

                message = (
                    "Spotify API request failed."
                )

                if isinstance(
                    payload,
                    dict,
                ):

                    error = payload.get(
                        "error"
                    )

                    if isinstance(
                        error,
                        dict,
                    ):

                        message = str(
                            error.get(
                                "message"
                            )
                            or error.get(
                                "status"
                            )
                            or message
                        )

                    else:

                        message = str(
                            payload.get(
                                "error_description"
                            )
                            or error
                            or message
                        )

                raise SpotifyHTTPError(
                    response.status,
                    message,
                    payload,
                )

            return payload

    finally:

        if (
            own_session
            and session is not None
        ):

            await session.close()

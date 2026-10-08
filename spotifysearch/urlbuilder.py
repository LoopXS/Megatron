from __future__ import annotations

from urllib.parse import urlencode


SPOTIFY_API_URL = (
    "https://api.spotify.com/v1"
)


SEARCH_TYPES = {
    "album",
    "artist",
    "playlist",
    "track",
    "show",
    "episode",
    "audiobook",
}


def build_search_params(
    keywords: str,
    allowed_types: list[str] | tuple[str, ...] | None,
    *,
    filters: dict[str, str] | None = None,
    market: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> dict[str, str | int]:

    query = (
        keywords or ""
    ).strip()

    if not query:

        raise ValueError(
            "Spotify search query cannot be empty."
        )

    types = [
        str(value)
        .strip()
        .lower()
        for value in (
            allowed_types
            or ["track"]
        )
        if str(value).strip()
    ]

    invalid = [
        value
        for value in types
        if value not in SEARCH_TYPES
    ]

    if invalid:

        raise ValueError(
            "Unsupported Spotify search "
            f"type(s): {', '.join(invalid)}"
        )

    limit = max(
        1,
        min(
            int(limit),
            10,
        ),
    )

    offset = max(
        0,
        min(
            int(offset),
            1000,
        ),
    )

    if filters:

        for key, value in filters.items():

            key = str(key).strip()
            value = str(value).strip()

            if key and value:

                query += (
                    f" {key}:{value}"
                )

    params = {
        "q": query,
        "type": ",".join(types),
        "limit": limit,
        "offset": offset,
    }

    if market:

        market = (
            market
            .strip()
            .upper()
        )

        if len(market) != 2:

            raise ValueError(
                "Spotify market must be "
                "a 2-letter ISO country code."
            )

        params["market"] = market

    return params


def search_endpoint(
    keywords: str,
    allowed_types: list[str] | tuple[str, ...] | None,
    filters: dict[str, str] | None = None,
    market: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> str:

    params = build_search_params(
        keywords,
        allowed_types,
        filters=filters,
        market=market,
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

    return (
        f"{SPOTIFY_API_URL}/search?"
        f"{urlencode(params)}"
    )

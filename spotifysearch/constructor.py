from __future__ import annotations

from typing import Any

from .classes import (
    Album,
    AlbumCover,
    AlbumTrack,
    Artist,
    Episode,
    Playlist,
    Track,
    TrackPreview,
)


def _dict(
    value: Any,
) -> dict[str, Any]:

    if isinstance(
        value,
        dict,
    ):

        return value

    return {}


def build_cover(
    data: dict[str, Any],
) -> AlbumCover:

    return AlbumCover(
        width=int(
            data.get("width")
            or 0
        ),
        height=int(
            data.get("height")
            or 0
        ),
        url=str(
            data.get("url")
            or ""
        ),
    )


def build_artist(
    data: dict[str, Any],
) -> Artist:

    external = _dict(
        data.get(
            "external_urls"
        )
    )

    followers = _dict(
        data.get(
            "followers"
        )
    )

    return Artist(
        data=data,
        type=str(
            data.get("type")
            or "artist"
        ),
        name=str(
            data.get("name")
            or ""
        ),
        url=str(
            external.get("spotify")
            or ""
        ),
        id=str(
            data.get("id")
            or ""
        ),
        followers=int(
            followers.get("total")
            or 0
        ),
    )


def build_album_track(
    data: dict[str, Any],
) -> AlbumTrack:

    external = _dict(
        data.get(
            "external_urls"
        )
    )

    artists = (
        data.get("artists")
        or []
    )

    return AlbumTrack(
        url=str(
            external.get("spotify")
            or ""
        ),
        name=str(
            data.get("name")
            or ""
        ),
        artists=", ".join(
            str(
                _dict(artist).get(
                    "name"
                )
                or ""
            )
            for artist in artists
        ),
        track_number=int(
            data.get("track_number")
            or 0
        ),
        duration_ms=int(
            data.get("duration_ms")
            or 0
        ),
    )


def build_album(
    data: dict[str, Any],
    tracks: list[AlbumTrack] | None = None,
) -> Album:

    external = _dict(
        data.get(
            "external_urls"
        )
    )

    return Album(
        data=data,

        type=str(
            data.get("type")
            or "album"
        ),

        name=str(
            data.get("name")
            or ""
        ),

        url=str(
            external.get("spotify")
            or ""
        ),

        id=str(
            data.get("id")
            or ""
        ),

        images=[
            build_cover(
                _dict(image)
            )
            for image in (
                data.get("images")
                or []
            )
        ],

        artists=[
            build_artist(
                _dict(artist)
            )
            for artist in (
                data.get("artists")
                or []
            )
        ],

        available_markets=list(
            data.get(
                "available_markets"
            )
            or []
        ),

        release_date=str(
            data.get(
                "release_date"
            )
            or ""
        ),

        total_tracks=int(
            data.get(
                "total_tracks"
            )
            or 0
        ),

        label=str(
            data.get("label")
            or ""
        ),

        popularity=int(
            data.get("popularity")
            or 0
        ),

        tracks=list(
            tracks
            or []
        ),
    )


def build_track(
    data: dict[str, Any],
) -> Track:

    external = _dict(
        data.get(
            "external_urls"
        )
    )

    album_data = _dict(
        data.get("album")
    )

    preview_url = data.get(
        "preview_url"
    )

    return Track(
        data=data,

        type=str(
            data.get("type")
            or "track"
        ),

        name=str(
            data.get("name")
            or ""
        ),

        url=str(
            external.get("spotify")
            or ""
        ),

        id=str(
            data.get("id")
            or ""
        ),

        explicit=bool(
            data.get("explicit")
        ),

        duration_ms=int(
            data.get("duration_ms")
            or 0
        ),

        preview=(
            TrackPreview(
                str(preview_url)
            )
            if preview_url
            else None
        ),

        artists=[
            build_artist(
                _dict(artist)
            )
            for artist in (
                data.get("artists")
                or []
            )
        ],

        album=build_album(
            album_data
        ),

        available_markets=list(
            data.get(
                "available_markets"
            )
            or []
        ),

        disc_number=int(
            data.get(
                "disc_number"
            )
            or 1
        ),

        track_number=int(
            data.get(
                "track_number"
            )
            or 0
        ),

        popularity=int(
            data.get(
                "popularity"
            )
            or 0
        ),
    )


def build_playlist(
    data: dict[str, Any],
    tracks: list[Track] | None = None,
) -> Playlist:

    external = _dict(
        data.get(
            "external_urls"
        )
    )

    owner = _dict(
        data.get("owner")
    )

    owner_external = _dict(
        owner.get(
            "external_urls"
        )
    )

    track_meta = _dict(
        data.get("tracks")
    )

    total = (
        track_meta.get("total")
        or data.get("items_total")
        or 0
    )

    return Playlist(
        data=data,

        type="playlist",

        name=str(
            data.get("name")
            or ""
        ),

        url=str(
            external.get("spotify")
            or ""
        ),

        id=str(
            data.get("id")
            or ""
        ),

        images=[
            build_cover(
                _dict(image)
            )
            for image in (
                data.get("images")
                or []
            )
        ],

        tracks=list(
            tracks
            or []
        ),

        description=str(
            data.get("description")
            or ""
        ),

        public=bool(
            data.get("public")
        ),

        total_tracks=int(
            total
        ),

        creator=str(
            owner.get(
                "display_name"
            )
            or ""
        ),

        creator_url=str(
            owner_external.get(
                "spotify"
            )
            or ""
        ),
    )


def build_episode(
    data: dict[str, Any],
) -> Episode:

    external = _dict(
        data.get(
            "external_urls"
        )
    )

    return Episode(
        data=data,

        type=str(
            data.get("type")
            or "episode"
        ),

        name=str(
            data.get("name")
            or ""
        ),

        url=str(
            external.get("spotify")
            or ""
        ),

        id=str(
            data.get("id")
            or ""
        ),

        duration_ms=int(
            data.get("duration_ms")
            or 0
        ),

        description=str(
            data.get("description")
            or ""
        ),

        html_description=str(
            data.get(
                "html_description"
            )
            or ""
        ),

        images=[
            build_cover(
                _dict(image)
            )
            for image in (
                data.get("images")
                or []
            )
        ],

        language=str(
            data.get("language")
            or ""
        ),

        languages=list(
            data.get("languages")
            or []
        ),

        release_date=str(
            data.get(
                "release_date"
            )
            or ""
        ),
    )

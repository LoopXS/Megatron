from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def format_duration(milliseconds: int | None) -> str:
    """Return a Spotify duration in MM:SS or HH:MM:SS format."""

    total_seconds = max(
        0,
        int(milliseconds or 0),
    ) // 1000

    hours, remainder = divmod(
        total_seconds,
        3600,
    )

    minutes, seconds = divmod(
        remainder,
        60,
    )

    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    return f"{minutes:02d}:{seconds:02d}"


@dataclass(slots=True)
class BaseObject:
    data: dict[str, Any] = field(
        default_factory=dict
    )

    type: str = ""
    name: str = ""
    url: str = ""
    id: str = ""

    def export_json(
        self,
        path: str | Path,
    ) -> None:

        destination = Path(path)

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination.write_text(
            json.dumps(
                self.data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


@dataclass(slots=True)
class Artist(BaseObject):
    followers: int = 0


@dataclass(slots=True)
class AlbumCover:
    width: int = 0
    height: int = 0
    url: str = ""


@dataclass(slots=True)
class AlbumTrack:
    url: str = ""
    name: str = ""
    artists: str = ""
    track_number: int = 0
    duration_ms: int = 0

    @property
    def duration(self) -> str:
        return format_duration(
            self.duration_ms
        )

    def get_string_duration(self) -> str:
        return self.duration


@dataclass(slots=True)
class Album(BaseObject):
    images: list[AlbumCover] = field(
        default_factory=list
    )

    artists: list[Artist] = field(
        default_factory=list
    )

    available_markets: list[str] = field(
        default_factory=list
    )

    release_date: str = ""

    total_tracks: int = 0

    label: str = ""

    popularity: int = 0

    tracks: list[AlbumTrack] = field(
        default_factory=list
    )

    @property
    def thumb(self) -> str | None:
        if not self.images:
            return None

        return self.images[0].url

    async def get_tracks(
        self,
    ) -> list[AlbumTrack]:

        return self.tracks

    def total_duration(self) -> str:

        return format_duration(
            sum(
                track.duration_ms
                for track in self.tracks
            )
        )

    def total_duration_string(self) -> str:
        return self.total_duration()


@dataclass(slots=True)
class TrackPreview:
    url: str

    def __bool__(self) -> bool:
        return bool(self.url)


@dataclass(slots=True)
class Track(BaseObject):
    explicit: bool = False

    duration_ms: int = 0

    preview: TrackPreview | None = None

    artists: list[Artist] = field(
        default_factory=list
    )

    album: Album | None = None

    available_markets: list[str] = field(
        default_factory=list
    )

    disc_number: int = 1

    track_number: int = 0

    popularity: int = 0

    @property
    def thumb(self) -> str | None:

        if not self.album:
            return None

        return self.album.thumb

    @property
    def duration(self) -> str:
        return format_duration(
            self.duration_ms
        )

    def get_string_duration(self) -> str:
        return self.duration

    def get_formatted_duration(
        self,
    ) -> dict[str, int]:

        total_seconds = max(
            0,
            self.duration_ms // 1000,
        )

        hours, remainder = divmod(
            total_seconds,
            3600,
        )

        minutes, seconds = divmod(
            remainder,
            60,
        )

        return {
            "hours": hours,
            "minutes": minutes,
            "seconds": seconds,
        }

    async def get_tracks(
        self,
    ) -> list[Track]:

        return [self]


@dataclass(slots=True)
class Episode(Track):
    description: str = ""

    html_description: str = ""

    images: list[AlbumCover] = field(
        default_factory=list
    )

    language: str = ""

    languages: list[str] = field(
        default_factory=list
    )

    release_date: str = ""


@dataclass(slots=True)
class Playlist(BaseObject):
    images: list[AlbumCover] = field(
        default_factory=list
    )

    tracks: list[Track] = field(
        default_factory=list
    )

    description: str = ""

    public: bool = False

    total_tracks: int = 0

    creator: str = ""

    creator_url: str = ""

    @property
    def thumb(self) -> str | None:

        if not self.images:
            return None

        return self.images[0].url

    async def get_tracks(
        self,
    ) -> list[Track]:

        return self.tracks

    def total_duration(self) -> str:

        return format_duration(
            sum(
                track.duration_ms
                for track in self.tracks
            )
        )

    def total_duration_string(self) -> str:
        return self.total_duration()


@dataclass(slots=True)
class Results:
    data: dict[str, Any] = field(
        default_factory=dict
    )

    tracks: list[Track] = field(
        default_factory=list
    )

    albums: list[Album] = field(
        default_factory=list
    )

    artists: list[Artist] = field(
        default_factory=list
    )

    playlists: list[Playlist] = field(
        default_factory=list
    )

    episodes: list[Episode] = field(
        default_factory=list
    )

    shows: list[dict[str, Any]] = field(
        default_factory=list
    )

    audiobooks: list[dict[str, Any]] = field(
        default_factory=list
    )

    @property
    def total(self) -> int:

        return sum(
            len(items)
            for items in (
                self.tracks,
                self.albums,
                self.artists,
                self.playlists,
                self.episodes,
                self.shows,
                self.audiobooks,
            )
        )

    async def get_tracks(self):
        return self.tracks

    async def get_albums(self):
        return self.albums

    async def get_artists(self):
        return self.artists

    async def get_playlists(self):
        return self.playlists

    async def get_episodes(self):
        return self.episodes

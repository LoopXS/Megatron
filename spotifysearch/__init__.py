"""Reliable asynchronous Spotify Web API client used by the userbot."""

import logging


SPOTLOGS = logging.getLogger("spotifysearch")
SPOTLOGS.addHandler(logging.NullHandler())


from .async_classes import Authenticator
from .async_client import Client, SpotifyHTTPError

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
    format_duration,
)


# ---------------------------------------------------------------------------
# Compatibility aliases
# ---------------------------------------------------------------------------

AsyncClient = Client
AsyncAuthenticator = Authenticator

Base = BaseObject
AsyncBase = BaseObject

TrackBase = Track
AsyncTrackBase = Track


__all__ = [
    "Client",
    "AsyncClient",
    "SpotifyHTTPError",

    "Authenticator",
    "AsyncAuthenticator",

    "Base",
    "BaseObject",
    "AsyncBase",

    "TrackBase",
    "AsyncTrackBase",

    "Artist",
    "AlbumCover",
    "Album",
    "AlbumTrack",
    "TrackPreview",
    "Track",

    "Episode",
    "Playlist",
    "Results",

    "format_duration",

    "SPOTLOGS",
]

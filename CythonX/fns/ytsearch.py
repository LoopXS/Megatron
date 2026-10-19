"""Compatibility shim for the archived ``youtubesearchpython`` package.

Some YouTube search responses omit the channel ``browseId`` for a video (Shorts,
livestreams and auto-generated channels are common offenders).  Upstream then
runs::

    component['channel']['link'] = (
        'https://www.youtube.com/channel/' + component['channel']['id']
    )

with ``component['channel']['id'] is None`` and raises::

    TypeError: can only concatenate str (not "NoneType") to str

inside ``ComponentHandler._getVideoComponent`` (``_getPlaylistComponent`` and
``_getChannelComponent`` have the same pattern).  The upstream project is
archived and unmaintained, so we wrap the component builders: when one of them
hits this specific error we retry with ``None`` values coerced to ``""``.  A
missing id then degrades to an empty string instead of taking the whole search
down.

Import ``VideosSearch`` / ``Playlist`` from here instead of directly from
``youtubesearchpython`` so the guard is always installed.
"""

import functools
import logging

LOGS = logging.getLogger(__name__)


def _install_null_guard() -> bool:
    """Make ``ComponentHandler`` tolerate missing video/channel/playlist ids.

    Returns ``True`` when the guard is in place (also when it already was), or
    ``False`` when ``youtubesearchpython`` is unavailable.
    """
    try:
        from youtubesearchpython.handlers import componenthandler
    except Exception:  # dependency not installed - nothing to patch
        return False

    handler = componenthandler.ComponentHandler
    if getattr(handler, "_null_guard_installed", False):
        return True

    original_get_value = handler._getValue

    def safe_get_value(self, source, path):
        value = original_get_value(self, source, path)
        return "" if value is None else value

    def guard(method):
        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            try:
                return method(self, *args, **kwargs)
            except TypeError as exc:
                if "NoneType" not in str(exc):
                    raise
                # Retry with `None` coerced to "" so id concatenation succeeds.
                LOGS.debug("youtubesearchpython null-id guard engaged: %s", exc)
                handler._getValue = safe_get_value
                try:
                    return method(self, *args, **kwargs)
                finally:
                    handler._getValue = original_get_value

        return wrapper

    for name in (
        "_getVideoComponent",
        "_getChannelComponent",
        "_getPlaylistComponent",
    ):
        method = getattr(handler, name, None)
        if callable(method):
            setattr(handler, name, guard(method))
    handler._null_guard_installed = True
    return True


_INSTALLED = _install_null_guard()

try:
    from youtubesearchpython import Playlist, VideosSearch
except ImportError:
    Playlist, VideosSearch = None, None

__all__ = ["Playlist", "VideosSearch"]

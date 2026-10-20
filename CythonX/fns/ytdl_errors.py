"""Classification helpers for yt-dlp/YouTube errors.

Keeping this logic separate from :mod:`CythonX.fns.ytdl` makes it testable
without importing Telethon, aiohttp or the rest of the bot runtime.
"""

import re

# Messages YouTube uses when it refuses an unauthenticated/flagged request.
_AUTH_MARKERS = (
    "sign in to confirm you're not a bot",
    "sign in to confirm you\u2019re not a bot",
    "confirm you're not a bot",
    "cookies for the authentication",
    "login required",
    "please sign in",
)


# yt-dlp emits these when it cannot run YouTube's JavaScript challenges.
_JS_CHALLENGE_MARKERS = (
    "the page needs to be reloaded",
    "signature solving failed",
    "n challenge solving failed",
    "no supported javascript runtime",
)


def one_line_error(error):
    """Collapse an error into one line and strip ANSI colour escapes."""
    text = re.sub(r"\x1b\[[0-9;]*m", "", str(error))
    return " ".join(text.split()).strip()


def is_youtube_auth_error(error):
    """Return ``True`` when YouTube demands a signed-in session."""
    text = one_line_error(error).lower().replace("\u2019", "'")
    return any(marker in text for marker in _AUTH_MARKERS)


def is_youtube_js_challenge_error(error):
    """Return ``True`` when the player JavaScript challenge could not run."""
    text = one_line_error(error).lower()
    return any(marker in text for marker in _JS_CHALLENGE_MARKERS)

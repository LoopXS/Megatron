"""Helpers for making YouTube ``cookies.txt`` files usable by yt-dlp.

yt-dlp reads Netscape cookie files through :class:`http.cookiejar.MozillaCookieJar`,
which only accepts **tab**-separated fields.  Some cookie exporters (and the
``cookies.txt`` that used to be committed to this repository) separate the
seven Netscape fields with spaces.  yt-dlp then logs ``skipping cookie file
entry due to invalid length 1`` for every line, silently drops all cookies and
turns an authenticated request into an anonymous one.  YouTube answers that
with ``Sign in to confirm you're not a bot``.

The helpers below normalise such files into a private, tab-separated copy.
The original file is never handed to yt-dlp directly because yt-dlp rewrites
the cookie file it is given when the downloader closes.
"""

import hashlib
import os
import tempfile

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_COPY_DIR = os.path.join(tempfile.gettempdir(), "megatron-ytdl-cookies")


def _is_cookie_line(line):
    """Return ``True`` for a non-comment Netscape cookie line."""
    text = line.strip()
    if not text:
        return False
    if text.startswith("#") and not text.startswith("#HttpOnly_"):
        return False
    return len(text.split()) >= 7


def normalise_cookie_line(line):
    """Return *line* with its Netscape fields separated by tabs.

    Blank lines, comments and malformed lines are returned unchanged.
    """
    text = line.strip()
    if not _is_cookie_line(text):
        return line

    fields = text.split(None, 6)
    if len(fields) != 7:
        return line
    return "\t".join(fields)


def prepare_cookie_file(path):
    """Return a tab-separated copy of *path* suitable for yt-dlp.

    ``None`` is returned when *path* is missing, empty or contains no cookie
    entries.
    """
    if not path:
        return None

    try:
        path = os.path.expanduser(str(path))
        if not os.path.isfile(path) or os.path.getsize(path) <= 0:
            return None
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            lines = handle.readlines()
    except OSError:
        return None

    has_cookie = False
    normalised = []
    for line in lines:
        stripped = line.rstrip("\r\n")
        if _is_cookie_line(stripped):
            has_cookie = True
        normalised.append(normalise_cookie_line(stripped) + "\n")

    if not has_cookie:
        return None

    temporary = None
    try:
        os.makedirs(_COPY_DIR, mode=0o700, exist_ok=True)
        digest = hashlib.sha1(
            os.path.abspath(path).encode("utf-8", "replace")
        ).hexdigest()[:12]
        target = os.path.join(_COPY_DIR, f"cookies-{digest}.txt")

        fd, temporary = tempfile.mkstemp(prefix="cookies-", dir=_COPY_DIR)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.writelines(normalised)
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        temporary = None
        return target
    except OSError:
        return None
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def cookie_candidates(configured=None, project_root=None):
    """Yield possible cookie-file locations in priority order."""
    root = project_root or PROJECT_ROOT
    seen = set()

    candidates = [
        configured,
        os.path.join(root, "cookies.txt"),
        os.path.abspath("cookies.txt"),
    ]

    for candidate in candidates:
        if not candidate:
            continue
        candidate = os.path.expanduser(str(candidate))
        key = os.path.abspath(candidate)
        if key in seen:
            continue
        seen.add(key)
        yield candidate


def first_existing_cookie(configured=None, project_root=None):
    """Return the first cookie path that exists, even if it is malformed."""
    for candidate in cookie_candidates(configured, project_root):
        if os.path.isfile(candidate):
            return candidate
    return None


def find_cookie_file(configured=None, project_root=None):
    """Return a yt-dlp-ready cookie file, or ``None``."""
    for candidate in cookie_candidates(configured, project_root):
        prepared = prepare_cookie_file(candidate)
        if prepared:
            return prepared
    return None

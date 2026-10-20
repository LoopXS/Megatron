"""Locate the ffmpeg/ffprobe pair required by yt-dlp postprocessing.

yt-dlp needs both binaries for audio extraction (``FFmpegExtractAudio``),
metadata embedding and stream merging.  It looks on ``PATH`` by default,
which is not always the ``PATH`` the bot service runs with.  Resolve the
location explicitly and pass it as ``ffmpeg_location``.
"""

import os
import shutil

FFMPEG_HINT = (
    "Install ffmpeg (which includes ffprobe) on the server, for example "
    "'sudo apt install -y ffmpeg', then restart the bot."
)

# Directories used by distro packages and common static/Jellyfin builds.
_COMMON_DIRECTORIES = (
    "/usr/bin",
    "/usr/local/bin",
    "/opt/ffmpeg/bin",
    "/opt/ffmpeg",
    "/usr/lib/jellyfin-ffmpeg",
    "~/.local/bin",
    "/snap/bin",
)


def _is_executable(path):
    return os.path.isfile(path) and os.access(path, os.X_OK)


def _directory_has_pair(directory):
    directory = os.path.expanduser(str(directory))
    return _is_executable(os.path.join(directory, "ffmpeg")) and _is_executable(
        os.path.join(directory, "ffprobe")
    )


def find_ffmpeg_location(configured=None):
    """Return a value suitable for yt-dlp's ``ffmpeg_location``.

    A directory is returned when ``ffmpeg`` and ``ffprobe`` share one.  If the
    binaries are on ``PATH`` in different directories, the ffmpeg binary path
    is returned.  ``None`` means the pair is incomplete or missing.
    """
    candidates = []

    if configured:
        configured = os.path.expanduser(str(configured))
        if os.path.isdir(configured):
            candidates.append(configured)
        elif os.path.isfile(configured):
            candidates.append(os.path.dirname(os.path.abspath(configured)))

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg and ffprobe:
        ffmpeg_dir = os.path.dirname(os.path.abspath(ffmpeg))
        ffprobe_dir = os.path.dirname(os.path.abspath(ffprobe))
        if ffmpeg_dir == ffprobe_dir:
            candidates.insert(0, ffmpeg_dir)
        else:
            # yt-dlp can use the ffmpeg binary directly; ffprobe is on PATH.
            return os.path.abspath(ffmpeg)

    candidates.extend(_COMMON_DIRECTORIES)

    for directory in candidates:
        if _directory_has_pair(directory):
            return os.path.expanduser(str(directory))
    return None

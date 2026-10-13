"""
Megatron NSFW Guard
===================
Real-time, local NSFW moderation for Telethon/Megatron.

What it does
------------
Watches incoming media in enabled chats and removes pornographic /
NSFW content the moment it is detected.  It supports photos,
videos, GIFs, animated stickers, video notes and any document
that carries visual media.

Detection
---------
* **NudeNet** (local, recommended) is the primary detector.
* **DeepAI** is an optional cloud fallback for inconclusive cases.
* Videos are analysed by extracting frames spread evenly across the
  *whole* duration (not just the thumbnail), so content anywhere in
  a clip is seen, even in large files.
* Positive results are cached and concurrent duplicate uploads are
  de-duplicated.

Moderation
----------
On detection the plugin:
1. Forwards the offending media to the log destination
   (``LOG_GROUP``, falling back to ``LOG_CHANNEL``) for review.
2. Deletes the offending message.
3. Bans or mutes the sender (configurable per chat).
4. Purges the sender's recent messages from the chat
   (subject to the account's permissions; disable globally with
   ``setdb NSFW_PURGE off``).

Admins, the owner and other bots are ignored.  Per-chat settings
are persisted through the project's NSFW database.

Installation
------------
    pip install nudenet          # local detector (recommended)
    # ffmpeg + ffprobe in PATH for video frame sampling

Commands
--------
    .nsfw                    show guard status
    .nsfw on [ban|mute]      enable the guard (default: ban)
    .nsfw off                disable the guard
    .nsfw api <key>          set the DeepAI fallback key
    .nsfw api                clear the DeepAI fallback key

Limitations
-----------
* NudeNet must be installed for local detection; without it the
  guard relies on the DeepAI fallback (if configured).
* Video analysis needs ffmpeg/ffprobe; without them only the
  video thumbnail is inspected.
* Purging and moderation require the account to be an admin with
  the appropriate rights in the chat.
"""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from telethon import events
from telethon.errors import ChatAdminRequiredError, FloodWaitError, RPCError

from . import (
    Button,
    LOGS,
    Redis,
    eor,
    get_help,
    udB,
    heartless_bot,
    heartless_cmd,
)
from CythonX.dB.nsfw_db import is_nsfw, nsfw_chat, rem_nsfw

__doc__ = get_help("nsfwfilter") or __doc__

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_ACTION = "ban"
SUPPORTED_ACTIONS = {"ban", "mute"}

# Largest media we will download and analyse.
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_VIDEO_BYTES = 150 * 1024 * 1024

# Frames sampled from a video.  They are spread evenly across the
# whole duration so content anywhere in a clip is seen, not just
# the opening seconds.  Longer videos get more frames (up to
# MAX_VIDEO_SAMPLES) to keep temporal coverage tight.
VIDEO_SAMPLE_COUNT = 8
MAX_VIDEO_SAMPLES = 16
SAMPLE_INTERVAL = 10  # seconds between sampled frames, roughly

# Hard time budget for frame extraction so a pathological video
# can never tie up a worker for minutes on end.
EXTRACT_BUDGET = 120

DETECTOR_SCORE = 0.55
MAX_CONCURRENT_SCANS = 2
CACHE_TTL = 6 * 60 * 60
# Wait this long before retrying a failed NudeNet load instead of
# disabling local detection until restart.
DETECTOR_RETRY_DELAY = 300

# Purge limits: how many of the sender's messages are removed and
# how the deletion is paced to respect Telegram's rate limits.
MAX_PURGE = 500
PURGE_BATCH = 50
PURGE_DELAY = 0.5

_SCAN_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_SCANS)

_DETECTOR = None
_DETECTOR_ERROR = None
_DETECTOR_RETRY_AT = 0.0
_DETECTOR_LOCK = asyncio.Lock()

# Only positive detections are cached (see _scan_message), so a
# single false negative is never remembered.
_RESULT_CACHE: dict[str, tuple[float, float]] = {}
_ACTIVE_CHATS: set[int] = set()

# Per-media locks de-duplicate concurrent scans of the same upload.
_DIGEST_LOCKS: dict[str, asyncio.Lock] = {}
_DIGEST_LOCKS_GUARD = asyncio.Lock()
_MAX_DIGEST_LOCKS = 512


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _deepai_key() -> str | None:
    return udB.get_key("DEEP_API") or udB.get_key("NSFW_DEEPAI_API")


def _log_chat_id():
    """The moderation log destination.

    A dedicated ``LOG_GROUP`` (if configured) takes precedence;
    otherwise the standard ``LOG_CHANNEL`` used across the project.
    """
    for key in ("LOG_GROUP", "LOG_CHANNEL"):
        value = Redis(key)
        if value is None:
            value = udB.get_key(key)
        if value:
            try:
                return int(value)
            except (TypeError, ValueError):
                return value
    return None


def _purge_enabled() -> bool:
    value = udB.get_key("NSFW_PURGE")
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _safe_name(user) -> str:
    name = " ".join(
        x for x in [getattr(user, "first_name", None), getattr(user, "last_name", None)]
        if x
    ).strip()
    return name or "Unknown"


def _mention(user) -> str:
    uid = getattr(user, "id", None)
    name = _safe_name(user)
    # Escape characters that would break the markdown link.
    for ch in ("\\", "`", "*", "_", "[", "]"):
        name = name.replace(ch, "\\" + ch)
    return f"[{name}](tg://user?id={uid})" if uid else f"`{name}`"


def _chat_title(chat) -> str:
    return (
        getattr(chat, "title", None)
        or getattr(chat, "first_name", None)
        or getattr(chat, "username", None)
        or "Unknown chat"
    )


def _chat_url(chat, message=None) -> str | None:
    username = getattr(chat, "username", None)
    if username:
        return f"https://t.me/{username}"

    cid = getattr(chat, "id", None)
    if cid is None:
        return None

    # Private supergroups/channels use the /c/ form.  The same URL is
    # useful even when the original message has already been deleted.
    if int(cid) < 0:
        internal = str(abs(int(cid)))
        if internal.startswith("100"):
            internal = internal[3:]
        if internal:
            if message is not None:
                mid = getattr(message, "id", None)
                if mid:
                    return f"https://t.me/c/{internal}/{mid}"
            return f"https://t.me/c/{internal}"
    return None


def _profile_url(user) -> str | None:
    uid = getattr(user, "id", None)
    return f"tg://user?id={uid}" if uid else None


def _mime(message) -> str:
    try:
        return (message.file.mime_type or "").lower()
    except Exception:
        return ""


def _looks_visual(message) -> bool:
    if not getattr(message, "media", None):
        return False

    # Native photo / video / video-note / GIF containers are always
    # visual, even when the mime type is missing or generic.
    if any(
        getattr(message, attr, None)
        for attr in ("photo", "video", "video_note", "gif")
    ):
        return True

    mime = _mime(message)
    if mime.startswith(("image/", "video/")):
        return True

    file_name = (getattr(getattr(message, "file", None), "name", None) or "").lower()
    ext = Path(file_name).suffix.lower()
    return ext in {
        ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".apng",
        ".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi", ".3gp",
        ".tgs",
    }


def _is_admin_like(sender) -> bool:
    if not sender:
        return False
    if getattr(sender, "bot", False):
        return True
    if getattr(sender, "is_self", False):
        return True
    if getattr(sender, "is_admin", False):
        return True
    return False


def _cleanup(path: str | Path | None):
    if not path:
        return
    try:
        p = Path(path)
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink(missing_ok=True)
    except Exception:
        pass


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


async def _lock_for_digest(digest: str) -> asyncio.Lock:
    """Return (and track) the lock that serialises scans of one media."""
    async with _DIGEST_LOCKS_GUARD:
        lock = _DIGEST_LOCKS.get(digest)
        if lock is None:
            if len(_DIGEST_LOCKS) >= _MAX_DIGEST_LOCKS:
                for stale in list(_DIGEST_LOCKS)[: _MAX_DIGEST_LOCKS // 2]:
                    _DIGEST_LOCKS.pop(stale, None)
            lock = asyncio.Lock()
            _DIGEST_LOCKS[digest] = lock
        return lock


# ---------------------------------------------------------------------------
# NudeNet
# ---------------------------------------------------------------------------

async def _get_detector():
    global _DETECTOR, _DETECTOR_ERROR, _DETECTOR_RETRY_AT

    if _DETECTOR is not None:
        return _DETECTOR

    now = time.monotonic()
    if _DETECTOR_ERROR is not None and now < _DETECTOR_RETRY_AT:
        # Still inside the cooldown window that follows a failed
        # load; try again once it elapses.
        return None

    async with _DETECTOR_LOCK:
        if _DETECTOR is not None:
            return _DETECTOR
        now = time.monotonic()
        if _DETECTOR_ERROR is not None and now < _DETECTOR_RETRY_AT:
            return None

        try:
            from nudenet import NudeDetector

            _DETECTOR = NudeDetector()
            _DETECTOR_ERROR = None
            LOGS.info("NSFW Guard: NudeNet detector loaded.")
        except Exception as exc:
            # Do not latch a transient failure (e.g. a model
            # download hiccup) permanently: that would disable
            # local detection until the userbot restarts.
            _DETECTOR_ERROR = repr(exc)
            _DETECTOR_RETRY_AT = time.monotonic() + DETECTOR_RETRY_DELAY
            LOGS.error("NSFW Guard: NudeNet unavailable: %s", exc)

    return _DETECTOR


def _nudenet_score_sync(detector, image_path: str) -> float:
    """
    Convert NudeNet detections to a conservative 0..1 score.

    Explicit sexual classes are weighted more heavily than exposed-body
    classes.  This reduces false positives on normal beach/sports images.
    """
    detections = detector.detect(image_path) or []
    explicit = {
        "FEMALE_GENITALIA_EXPOSED",
        "MALE_GENITALIA_EXPOSED",
        "ANUS_EXPOSED",
        "FEMALE_BREAST_EXPOSED",
    }
    sexual = {
        "FEMALE_GENITALIA_COVERED",
        "MALE_GENITALIA_COVERED",
        "BUTTOCKS_EXPOSED",
        "FEMALE_BREAST_COVERED",
    }

    best = 0.0
    for item in detections:
        label = str(item.get("class", "")).upper()
        score = float(item.get("score", 0.0))
        if label in explicit:
            best = max(best, score)
        elif label in sexual:
            best = max(best, score * 0.78)
    return min(1.0, best)


async def _nudenet_score(path: Path) -> float:
    detector = await _get_detector()
    if detector is None:
        return 0.0
    return await asyncio.to_thread(_nudenet_score_sync, detector, str(path))


# ---------------------------------------------------------------------------
# Optional DeepAI fallback
# ---------------------------------------------------------------------------

async def _deepai_score(path: Path) -> float:
    api_key = _deepai_key()
    if not api_key:
        return 0.0

    try:
        import aiohttp
    except ImportError:
        return 0.0

    timeout = aiohttp.ClientTimeout(total=45)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            with path.open("rb") as fp:
                form = aiohttp.FormData()
                form.add_field(
                    "image",
                    fp,
                    filename=path.name,
                    content_type=mimetypes.guess_type(path.name)[0]
                    or "application/octet-stream",
                )
                async with session.post(
                    "https://api.deepai.org/api/nsfw-detector",
                    data=form,
                    headers={"api-key": api_key},
                ) as resp:
                    if resp.status != 200:
                        LOGS.warning("NSFW Guard: DeepAI HTTP %s", resp.status)
                        return 0.0
                    data = await resp.json(content_type=None)
                    return float(data.get("output", {}).get("nsfw_score", 0.0))
    except Exception as exc:
        LOGS.warning("NSFW Guard: DeepAI failed: %s", exc)
        return 0.0


# ---------------------------------------------------------------------------
# Media extraction
# ---------------------------------------------------------------------------

async def _download_thumbnail(message, workdir: Path) -> Path | None:
    """Download the server-side thumbnail Telegram generates for a message."""
    try:
        target = workdir / "thumb.jpg"
        result = await message.download_media(file=str(target), thumb=-1)
        if not result:
            return None
        return Path(result)
    except Exception:
        return None


async def _download_media(message, workdir: Path) -> Path | None:
    try:
        target = workdir / "source"

        # TGS/Lottie stickers are gzip-compressed animation data.  NudeNet
        # cannot inspect the JSON directly, but Telegram can provide a
        # rendered thumbnail for sticker messages.
        mime = _mime(message)
        file_name = (getattr(getattr(message, "file", None), "name", None) or "").lower()
        is_tgs = mime in {"application/x-tgsticker", "application/x-tgs"} or file_name.endswith(".tgs")

        if is_tgs:
            return await _download_thumbnail(message, workdir)

        result = await message.download_media(file=str(target))

        if not result:
            return None
        return Path(result)
    except Exception as exc:
        LOGS.warning("NSFW Guard: media download failed: %s", exc)
        return None


def _is_video_file(path: Path, message) -> bool:
    mime = _mime(message)
    if mime.startswith("video/"):
        return True
    # Telethon exposes the native containers that carry a video
    # even when the mime type is missing or generic.
    if any(getattr(message, attr, None) for attr in ("video", "gif", "video_note")):
        return True
    return path.suffix.lower() in {
        ".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi", ".3gp", ".gif", ".apng"
    }


def _probe_duration_ffmpeg_sync(video: Path) -> float:
    """Derive the duration from ffmpeg's own input probe."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return 0.0
    try:
        out = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(video)],
            check=False,
            capture_output=True,
            timeout=20,
        )
    except Exception:
        return 0.0

    text = (out.stderr or b"").decode(errors="ignore")
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not match:
        return 0.0
    hours, minutes, seconds = int(match.group(1)), int(match.group(2)), float(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def _probe_duration_sync(video: Path) -> float:
    """Return the video duration in seconds, or 0.0 when unknown."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        cmd = [
            ffprobe, "-hide_banner", "-loglevel", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video),
        ]
        try:
            out = subprocess.run(cmd, check=False, capture_output=True, timeout=20)
        except Exception:
            out = None
        text = (getattr(out, "stdout", None) or b"").decode(errors="ignore").strip()
        try:
            return float(text)
        except (TypeError, ValueError):
            pass
    # ffprobe is missing or failed: fall back to ffmpeg itself.
    return _probe_duration_ffmpeg_sync(video)


def _sample_count(duration: float) -> int:
    """Pick how many frames to sample for a video of ``duration`` seconds."""
    if duration <= 0:
        return VIDEO_SAMPLE_COUNT
    # Aim for roughly one frame every SAMPLE_INTERVAL seconds,
    # bounded so long videos stay fast.
    count = int(duration // SAMPLE_INTERVAL) + 1
    return max(VIDEO_SAMPLE_COUNT, min(MAX_VIDEO_SAMPLES, count))


def _extract_video_frames_sync(
    video: Path,
    output_dir: Path,
    count: int = VIDEO_SAMPLE_COUNT,
) -> list[Path]:
    """
    Extract ``count`` frames spread evenly across the *whole* video.

    Sampling with a fixed ``fps`` and capping the output at ``count``
    frames only ever covered the first few seconds of a clip, so
    explicit content appearing later in the video was missed
    entirely.  Seeking to evenly spaced timestamps samples the
    entire duration instead, and input seeking (``-ss`` placed
    before ``-i``) keeps this fast even for large files.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    duration = _probe_duration_sync(video)
    count = _sample_count(duration)
    deadline = time.monotonic() + EXTRACT_BUDGET

    if duration > 0:
        frames: list[Path] = []
        for i in range(count):
            if time.monotonic() > deadline:
                break
            # Sample at the centre of each segment so both the
            # opening and the tail of the video are represented.
            ts = duration * (i + 0.5) / count
            out = output_dir / f"frame_{i:02d}.jpg"
            cmd = [
                ffmpeg, "-hide_banner", "-loglevel", "error",
                "-ss", f"{ts:.3f}",
                "-i", str(video),
                "-frames:v", "1",
                "-vf", "scale=640:-2:force_original_aspect_ratio=decrease",
                "-q:v", "4",
                str(out),
            ]
            try:
                subprocess.run(
                    cmd,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                )
            except Exception:
                continue
            if out.exists() and out.stat().st_size > 0:
                frames.append(out)
        if frames:
            return frames

    # Duration probing failed: fall back to a fixed-rate sample so a
    # video is still inspected rather than skipped outright.
    pattern = str(output_dir / "fps_%02d.jpg")
    vf = "fps=1/2,scale=640:-2:force_original_aspect_ratio=decrease"
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-i", str(video),
        "-vf", vf,
        "-frames:v", str(count),
        "-q:v", "4",
        pattern,
    ]
    try:
        subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=45,
        )
    except Exception:
        return []

    return sorted(output_dir.glob("fps_*.jpg"))[:count]


async def _visual_candidates(message, source: Path, workdir: Path) -> list[Path]:
    if _is_video_file(source, message):
        frames = await asyncio.to_thread(
            _extract_video_frames_sync,
            source,
            workdir / "frames",
        )
        if frames:
            return frames

        # NudeNet cannot decode a video container.  When frame
        # extraction fails (ffmpeg missing, corrupt or oversized
        # file), fall back to the server-side thumbnail instead
        # of feeding the raw video to the detector, which would
        # always score 0.
        thumb = await _download_thumbnail(message, workdir)
        if thumb and thumb.exists():
            return [thumb]
        return []

    # Static images, photos and (already rendered) sticker
    # thumbnails are scanned directly.
    return [source]


# ---------------------------------------------------------------------------
# Detection pipeline
# ---------------------------------------------------------------------------

async def _scan_message(message) -> tuple[bool, float, str]:
    if not _looks_visual(message):
        return False, 0.0, "non_visual"

    with tempfile.TemporaryDirectory(prefix="megatron-nsfw-") as tmp:
        workdir = Path(tmp)
        source = await _download_media(message, workdir)
        if not source or not source.exists():
            return False, 0.0, "download_failed"

        try:
            if source.stat().st_size > MAX_VIDEO_BYTES:
                return False, 0.0, "file_too_large"

            digest = await asyncio.to_thread(_file_hash, source)

            # Serialize concurrent scans of the same media so a
            # duplicate upload is not analysed more than once.
            lock = await _lock_for_digest(digest)
            async with lock:
                now = time.monotonic()
                cached = _RESULT_CACHE.get(digest)
                if cached and now - cached[0] < CACHE_TTL:
                    return cached[1] >= DETECTOR_SCORE, cached[1], "cache"

                candidates = await _visual_candidates(message, source, workdir)

                best = 0.0
                provider = "none"

                # Pass 1: local NudeNet over every sampled frame.
                for candidate in candidates:
                    if candidate.stat().st_size > MAX_IMAGE_BYTES:
                        continue

                    score = await _nudenet_score(candidate)
                    if score > best:
                        best = score
                        provider = "nudenet"

                    if best >= DETECTOR_SCORE:
                        break

                # Pass 2: only when local detection is inconclusive,
                # consult the optional DeepAI fallback.
                if best < DETECTOR_SCORE and _deepai_key():
                    for candidate in candidates:
                        if candidate.stat().st_size > MAX_IMAGE_BYTES:
                            continue

                        score = await _deepai_score(candidate)
                        if score > best:
                            best = score
                            provider = "deepai"

                        if best >= DETECTOR_SCORE:
                            break

                # Remember positive results only.  Caching a low
                # score would turn a single false negative into a
                # permanent one for the whole cache lifetime.
                if best >= DETECTOR_SCORE:
                    _RESULT_CACHE[digest] = (time.monotonic(), best)

                return best >= DETECTOR_SCORE, best, provider

        except Exception as exc:
            LOGS.exception("NSFW Guard scan failure: %s", exc)
            return False, 0.0, "error"


# ---------------------------------------------------------------------------
# Moderation action
# ---------------------------------------------------------------------------

async def _take_action(chat_id: int, user_id: int, action: str) -> str:
    action = action if action in SUPPORTED_ACTIONS else DEFAULT_ACTION

    if action == "mute":
        await heartless_bot.edit_permissions(
            chat_id,
            user_id,
            send_messages=False,
            send_media=False,
            send_stickers=False,
            send_gifs=False,
            send_games=False,
            send_inline=False,
        )
        return "MUTED"

    await heartless_bot.edit_permissions(
        chat_id,
        user_id,
        view_messages=False,
        send_messages=False,
        send_media=False,
        send_stickers=False,
        send_gifs=False,
        send_games=False,
        send_inline=False,
    )
    return "BANNED"


async def _purge_user_messages(chat_id: int, user_id: int) -> int:
    """
    Delete up to ``MAX_PURGE`` recent messages sent by ``user_id`` in
    ``chat_id``.  Only the target user's messages are touched.  Deletion
    is batched and paced to respect Telegram's rate limits, and any
    failure (e.g. missing delete rights) is reported without raising.
    """
    if not _purge_enabled():
        return 0

    try:
        ids = [
            msg.id
            async for msg in heartless_bot.iter_messages(
                chat_id, from_user=user_id, limit=MAX_PURGE
            )
        ]
    except Exception as exc:
        LOGS.warning("NSFW Guard: could not list messages to purge: %s", exc)
        return 0

    if not ids:
        return 0

    deleted = 0
    for start in range(0, len(ids), PURGE_BATCH):
        batch = ids[start : start + PURGE_BATCH]
        try:
            await heartless_bot.delete_messages(chat_id, batch)
            deleted += len(batch)
        except Exception as exc:
            LOGS.warning("NSFW Guard: purge batch failed: %s", exc)
        await asyncio.sleep(PURGE_DELAY)

    return deleted


# ---------------------------------------------------------------------------
# Logging and reporting
# ---------------------------------------------------------------------------

async def _forward_to_log(log_chat, message):
    """
    Preserve the original detected message in the log destination when
    Telegram permits it.  Protected content may prevent forwarding; the
    metadata report still works in that case.
    """
    try:
        result = await heartless_bot.forward_messages(log_chat, message)
        if isinstance(result, list):
            return result[0] if result else None
        return result
    except Exception as exc:
        LOGS.warning("NSFW Guard: forwarding to log failed: %s", exc)
        return None


async def _send_log_report(
    log_chat,
    message,
    sender,
    score: float,
    provider: str,
    action_result: str,
    purged: int,
    forwarded,
):
    try:
        chat = await message.get_chat()
    except Exception:
        chat = None

    chat_link = _chat_url(chat, message)
    profile_link = _profile_url(sender)

    buttons = []
    row = []
    if chat_link:
        row.append(Button.url("🔗 Open Group", chat_link))
    if profile_link:
        row.append(Button.url("👤 Open Profile", profile_link))
    if row:
        buttons.append(row)

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    text = (
        "🚨 **NSFW GUARD — CONTENT REMOVED**\n\n"
        f"👤 **User:** {_mention(sender)}\n"
        f"🆔 **User ID:** `{getattr(sender, 'id', 'unknown')}`\n"
        f"💬 **Chat:** `{_chat_title(chat)}`\n"
        f"🆔 **Chat ID:** `{getattr(chat, 'id', 'unknown')}`\n"
        f"🧪 **Detector:** `{provider}`\n"
        f"📊 **Score:** `{score:.2%}`\n"
        f"🛡 **Action:** `{action_result}`\n"
        f"🧹 **Messages purged:** `{purged}`\n"
        f"🧾 **Message ID:** `{getattr(message, 'id', 'unknown')}`\n"
        f"🕒 **Time (UTC):** `{timestamp}`"
    )
    if forwarded:
        text += "\n📎 **Detected content:** forwarded above."
    else:
        text += "\n📎 **Detected content:** unavailable (protected / forward failed)."

    try:
        await heartless_bot.send_message(
            log_chat, text, buttons=buttons or None, parse_mode="md"
        )
    except Exception as exc:
        LOGS.warning("NSFW Guard: log send failed: %s", exc)
        # Retry as plain text in case markdown parsing was the issue.
        try:
            await heartless_bot.send_message(log_chat, text, buttons=buttons or None)
        except Exception as exc2:
            LOGS.warning("NSFW Guard: plain-text log send failed: %s", exc2)


# ---------------------------------------------------------------------------
# Main event handler
# ---------------------------------------------------------------------------

async def _nsfw_event(event):
    chat_id = event.chat_id
    if not chat_id or chat_id not in _ACTIVE_CHATS:
        return

    message = event.message
    if not message or not message.media:
        return

    # Ignore outgoing, service and inline-bot messages.
    if getattr(message, "out", False) or getattr(message, "via_bot_id", None):
        return

    try:
        sender = await event.get_sender()
    except Exception:
        sender = None

    if _is_admin_like(sender):
        return

    if sender is not None:
        try:
            permissions = await heartless_bot.get_permissions(chat_id, sender)
            if getattr(permissions, "is_admin", False) or getattr(
                permissions, "is_creator", False
            ):
                return
        except Exception:
            # Failure to read permissions must not disable moderation.
            pass

    action = is_nsfw(chat_id) or DEFAULT_ACTION
    if action not in SUPPORTED_ACTIONS:
        action = DEFAULT_ACTION

    async with _SCAN_SEMAPHORE:
        detected, score, provider = await _scan_message(message)

    if not detected:
        return

    log_chat = _log_chat_id()

    # 1. Preserve the offending media in the log destination
    #    BEFORE deleting anything, so the original content is
    #    available for review even when forwarding is the only
    #    way to keep a copy.
    forwarded = None
    if log_chat:
        forwarded = await _forward_to_log(log_chat, message)

    # 2. Remove the offending message immediately.
    try:
        await message.delete()
    except Exception as exc:
        LOGS.warning("NSFW Guard: could not delete message %s: %s", message.id, exc)

    # 3. Apply the configured moderation action (ban/mute) and
    #    purge the sender's other recent messages.  Both need a
    #    known author, so they are skipped for anonymous posts.
    action_result = "NO SENDER"
    purged = 0
    if sender is not None:
        action_result = "ACTION FAILED"
        try:
            action_result = await _take_action(chat_id, sender.id, action)
        except (ChatAdminRequiredError, RPCError) as exc:
            LOGS.warning(
                "NSFW Guard: moderation action failed in %s for %s: %s",
                chat_id,
                sender.id,
                exc,
            )
        except Exception as exc:
            LOGS.exception("NSFW Guard: moderation action error: %s", exc)

        purged = await _purge_user_messages(chat_id, sender.id)

    # 4. Record the full moderation report.
    if log_chat:
        await _send_log_report(
            log_chat, message, sender, score, provider, action_result, purged, forwarded
        )


# ---------------------------------------------------------------------------
# Configuration commands
# ---------------------------------------------------------------------------

@heartless_cmd(pattern=r"nsfw(?:\s+(.*))?$", admins_only=True)
async def nsfw_command(e):
    raw = (e.pattern_match.group(1) or "").strip()
    parts = raw.split()
    sub = parts[0].lower() if parts else ""
    rest = parts[1:]

    if sub == "on":
        await _cmd_enable(e, rest)
    elif sub == "off":
        await _cmd_disable(e)
    elif sub == "api":
        await _cmd_api(e, rest)
    else:
        await _cmd_status(e)


async def _cmd_enable(e, rest):
    action = rest[0].lower() if rest else DEFAULT_ACTION
    if action not in SUPPORTED_ACTIONS:
        action = DEFAULT_ACTION

    if await _get_detector() is None and not _deepai_key():
        return await eor(
            e,
            "⚠️ **No NSFW detector available.**\n\n"
            "Install the local detector with:\n"
            "`pip install nudenet`\n"
            "or configure the DeepAI fallback with `.nsfw api <key>`.",
            time=12,
        )

    nsfw_chat(e.chat_id, action)
    _ACTIVE_CHATS.add(e.chat_id)

    await eor(
        e,
        "✅ **NSFW Guard enabled**\n"
        f"• Action: `{action}`\n"
        "• Detector: `NudeNet`"
        + (" + `DeepAI fallback`" if _deepai_key() else "")
        + f"\n• Purge: `{'on' if _purge_enabled() else 'off'}`",
        time=8,
    )


async def _cmd_disable(e):
    rem_nsfw(e.chat_id)
    _ACTIVE_CHATS.discard(e.chat_id)
    await eor(e, "✅ NSFW Guard disabled for this chat.", time=6)


async def _cmd_api(e, rest):
    key = " ".join(rest).strip()
    if not key:
        try:
            udB.set_key("DEEP_API", None)
        except Exception:
            pass
        return await eor(e, "✅ DeepAI fallback key removed.", time=6)

    udB.set_key("DEEP_API", key)
    await eor(
        e,
        "✅ DeepAI NSFW fallback configured.\n"
        "Local NudeNet remains the primary detector.",
        time=8,
    )


async def _cmd_status(e):
    detector = "loaded" if _DETECTOR is not None else (
        "unavailable" if _DETECTOR_ERROR else "not loaded"
    )
    ffmpeg = "available" if shutil.which("ffmpeg") else "missing"
    ffprobe = "available" if shutil.which("ffprobe") else "missing"
    log = "configured" if _log_chat_id() else "NOT configured"
    chat_action = is_nsfw(e.chat_id)

    lines = [
        "🛡 **NSFW Guard Status**",
        "",
        f"• NudeNet: `{detector}`",
        f"• FFmpeg: `{ffmpeg}`",
        f"• FFprobe: `{ffprobe}`",
        f"• DeepAI fallback: `{'configured' if _deepai_key() else 'disabled'}`",
        f"• Log destination: `{log}`",
        f"• Purge on detection: `{'on' if _purge_enabled() else 'off'}`",
        f"• This chat: `{'enabled (' + chat_action + ')' if chat_action else 'disabled'}`",
        f"• Active chats: `{len(_ACTIVE_CHATS)}`",
        f"• Threshold: `{DETECTOR_SCORE:.0%}`",
    ]
    await eor(e, "\n".join(lines), time=10)


# ---------------------------------------------------------------------------
# Load persisted chats and register one global event handler.
# ---------------------------------------------------------------------------

def _load_active_chats():
    try:
        data = udB.get_key("NSFW") or {}
        for chat_id, action in data.items():
            try:
                cid = int(chat_id)
            except (TypeError, ValueError):
                continue
            if action in SUPPORTED_ACTIONS:
                _ACTIVE_CHATS.add(cid)
    except Exception as exc:
        LOGS.warning("NSFW Guard: failed to load active chats: %s", exc)


_load_active_chats()

# A single handler is intentionally used instead of adding one handler
# per chat every time the guard is enabled.  This prevents duplicate
# scans and keeps message processing consistent.
heartless_bot.add_handler(
    _nsfw_event,
    events.NewMessage(incoming=True),
)

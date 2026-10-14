"""
Megatron NSFW Guard
-------------------
Real-time NSFW moderation for Telethon/Megatron.

Design
------
* Streams media bytes from Telegram DCs via ``iter_download`` — never waits
  for a full offline copy of large videos.
* Photos/documents are scanned from a streamed mid/high-quality image, not
  the tiny THUMB/stripped thumbnail.
* Videos/GIFs are streamed from Telegram into a seekable temp file (capped),
  then ffmpeg samples frames across the clip — piping MP4 into ffmpeg stdin
  does not work because the moov atom is usually at the end.
* Local NudeNet is primary; optional DeepAI fallback on sampled frames.
* Deletes detected content, bans/mutes the sender, and logs to LOG_CHANNEL.

Commands
--------
    .addnsfw [ban|mute]
    .remnsfw
    .getnsfw
    .setnsfwapi <key>
    .clearnsfwapi
    .nsfwstatus
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import mimetypes
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from telethon import events
from telethon.errors import ChatAdminRequiredError, FloodWaitError, RPCError
from telethon.tl import types

from . import Button, LOGS, Redis, eor, udB, heartless_bot, heartless_cmd
from CythonX.dB.nsfw_db import is_nsfw, nsfw_chat, rem_nsfw


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_ACTION = "ban"
SUPPORTED_ACTIONS = {"ban", "mute"}
MAX_IMAGE_STREAM = 8 * 1024 * 1024
# Telegram GIFs are usually MP4. Piping incomplete MP4 into ffmpeg fails
# because the moov atom is often at the end — materialize a seekable temp
# file from the TG stream instead (still not a gallery "re-download").
MAX_VIDEO_MATERIALIZE = 40 * 1024 * 1024
VIDEO_SAMPLE_COUNT = 5
DETECTOR_SCORE = 0.50
VIDEO_DETECTOR_SCORE = 0.42  # multi-frame; slightly more sensitive
MAX_CONCURRENT_SCANS = 2
CACHE_TTL = 6 * 60 * 60
STREAM_CHUNK = 512 * 1024
FFMPEG_TIMEOUT = 35

_SCAN_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_SCANS)
_DETECTOR = None
_DETECTOR_ERROR = None
_DETECTOR_LOCK = asyncio.Lock()
_RESULT_CACHE: dict[str, tuple[float, float]] = {}
_ACTIVE_CHATS: set[int] = set()


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _deepai_key() -> str | None:
    return udB.get_key("DEEP_API") or udB.get_key("NSFW_DEEPAI_API")


def _log_chat_id():
    value = Redis("LOG_CHANNEL")
    if value is None:
        value = udB.get_key("LOG_CHANNEL")
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _safe_name(user) -> str:
    name = " ".join(
        x for x in [getattr(user, "first_name", None), getattr(user, "last_name", None)]
        if x
    ).strip()
    return name or "Unknown"


def _mention(user) -> str:
    uid = getattr(user, "id", None)
    name = _safe_name(user).replace("[", "\\[").replace("]", "\\]")
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

    if int(cid) < 0:
        internal = str(abs(int(cid)))
        if internal.startswith("100"):
            internal = internal[3:]
        if internal:
            mid = getattr(message, "id", None) if message is not None else None
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
    if getattr(message, "photo", None):
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


def _document_size(message) -> int | None:
    doc = getattr(message, "document", None)
    if doc is not None and getattr(doc, "size", None):
        try:
            return int(doc.size)
        except (TypeError, ValueError):
            return None
    try:
        size = getattr(message.file, "size", None)
        return int(size) if size is not None else None
    except Exception:
        return None


def _is_animated_document(message) -> bool:
    """True for Telegram GIFs (usually MP4 + DocumentAttributeAnimated)."""
    if getattr(message, "gif", None):
        return True
    doc = getattr(message, "document", None)
    for attr in getattr(doc, "attributes", None) or []:
        if isinstance(attr, types.DocumentAttributeAnimated):
            return True
        if isinstance(attr, types.DocumentAttributeVideo) and getattr(
            attr, "round_message", False
        ):
            return True
    return False


def _is_video_like(message) -> bool:
    mime = _mime(message)
    if mime.startswith("video/") or mime == "image/gif":
        return True
    if _is_animated_document(message):
        return True
    if getattr(message, "video", None) or getattr(message, "video_note", None):
        return True
    name = (getattr(getattr(message, "file", None), "name", None) or "").lower()
    return Path(name).suffix.lower() in {
        ".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi", ".3gp", ".gif", ".apng",
    }


def _is_tgs(message) -> bool:
    mime = _mime(message)
    name = (getattr(getattr(message, "file", None), "name", None) or "").lower()
    return mime in {"application/x-tgsticker", "application/x-tgs"} or name.endswith(
        ".tgs"
    )


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


def _bytes_digest(chunks: bytes) -> str:
    return hashlib.sha256(chunks).hexdigest()


def _cache_get(digest: str):
    item = _RESULT_CACHE.get(digest)
    if not item:
        return None
    created, score = item
    if time.monotonic() - created >= CACHE_TTL:
        _RESULT_CACHE.pop(digest, None)
        return None
    return score


def _cache_put(digest: str, score: float):
    _RESULT_CACHE[digest] = (time.monotonic(), score)
    # Bound cache growth.
    if len(_RESULT_CACHE) > 2048:
        oldest = sorted(_RESULT_CACHE.items(), key=lambda kv: kv[1][0])[:256]
        for key, _ in oldest:
            _RESULT_CACHE.pop(key, None)


# ---------------------------------------------------------------------------
# NudeNet / DeepAI
# ---------------------------------------------------------------------------

async def _get_detector():
    global _DETECTOR, _DETECTOR_ERROR

    if _DETECTOR is not None:
        return _DETECTOR

    async with _DETECTOR_LOCK:
        if _DETECTOR is not None:
            return _DETECTOR
        if _DETECTOR_ERROR is not None:
            return None
        try:
            from nudenet import NudeDetector

            _DETECTOR = NudeDetector()
            LOGS.info("NSFW Guard: NudeNet detector loaded.")
        except Exception as exc:
            _DETECTOR_ERROR = repr(exc)
            LOGS.error("NSFW Guard: NudeNet unavailable: %s", exc)
    return _DETECTOR


def _nudenet_score_sync(detector, image_path: str) -> float:
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


async def _deepai_score(path: Path) -> float:
    api_key = _deepai_key()
    if not api_key:
        return 0.0
    try:
        import aiohttp
    except ImportError:
        return 0.0

    timeout = aiohttp.ClientTimeout(total=30)
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
# Telegram streaming helpers
# ---------------------------------------------------------------------------

def _pick_photo_size(photo: types.Photo):
    """Pick a scannable photo size — never the stripped/path thumbnail."""
    usable = []
    for size in getattr(photo, "sizes", None) or []:
        if isinstance(size, (types.PhotoSize, types.PhotoSizeProgressive)):
            w = int(getattr(size, "w", 0) or 0)
            h = int(getattr(size, "h", 0) or 0)
            if w * h <= 0:
                continue
            # Prefer mid/high quality (~720–1600px on the long edge).
            usable.append((w * h, size))
    if not usable:
        return None
    usable.sort(key=lambda item: item[0])
    # Avoid the tiniest preview; prefer something near the upper mid range.
    if len(usable) == 1:
        return usable[0][1]
    # Skip the smallest; take the second-largest when available (faster than max).
    if len(usable) >= 3:
        return usable[-2][1]
    return usable[-1][1]


def _media_for_stream(message):
    """
    Return a Telethon downloadable media object that is NOT a thumb-only
    preview when a full visual payload exists.
    """
    if _is_tgs(message):
        # Lottie JSON cannot be scanned by NudeNet; skip rather than thumb-only.
        return None

    photo = getattr(message, "photo", None)
    if isinstance(photo, types.Photo):
        size = _pick_photo_size(photo)
        if size is None:
            return None
        # InputPhotoFileLocation for that size streams the real image bytes.
        try:
            return types.InputPhotoFileLocation(
                id=photo.id,
                access_hash=photo.access_hash,
                file_reference=photo.file_reference,
                thumb_size=size.type,
            )
        except Exception:
            return photo

    document = getattr(message, "document", None)
    if document is not None:
        return document

    # Fall back to message.media for uncommon wrappers.
    return message.media


async def _stream_to_path(
    client,
    media,
    dest: Path,
    *,
    max_bytes: int,
) -> tuple[Optional[Path], bytes]:
    """
    Stream Telegram file bytes to ``dest``, aborting after ``max_bytes``.

    Returns (path_or_None, prefix_bytes_for_hashing).
    """
    hasher = hashlib.sha256()
    written = 0
    prefix = bytearray()
    try:
        with dest.open("wb") as out:
            async for chunk in client.iter_download(
                media,
                request_size=STREAM_CHUNK,
            ):
                if not chunk:
                    continue
                out.write(chunk)
                hasher.update(chunk)
                if len(prefix) < 64 * 1024:
                    need = 64 * 1024 - len(prefix)
                    prefix.extend(chunk[:need])
                written += len(chunk)
                if written >= max_bytes:
                    break
    except FloodWaitError as exc:
        LOGS.warning("NSFW Guard: flood wait during stream: %ss", exc.seconds)
        return None, b""
    except Exception as exc:
        LOGS.warning("NSFW Guard: stream failed: %s", exc)
        if written <= 0:
            return None, b""

    if written <= 0 or not dest.exists():
        return None, b""
    return dest, bytes(prefix) or hasher.digest()


def _ffprobe_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe") or shutil.which("ffmpeg")
    if not ffprobe:
        return 0.0
    # Prefer ffprobe; fall back to ffmpeg -i parsing only via ffprobe binary.
    if Path(ffprobe).name.startswith("ffmpeg"):
        ffprobe_bin = shutil.which("ffprobe")
        if not ffprobe_bin:
            return 0.0
        ffprobe = ffprobe_bin
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        out = subprocess_run_capture(cmd, timeout=12)
        return max(0.0, float((out or "0").strip() or 0))
    except Exception:
        return 0.0


def subprocess_run_capture(cmd, timeout: float = 20) -> str:
    result = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return (result.stdout or "").strip()


def _extract_frames_seekable_sync(
    video: Path,
    frames_dir: Path,
    count: int = VIDEO_SAMPLE_COUNT,
) -> list[Path]:
    """Sample frames from a seekable local file (materialized TG stream)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []

    frames_dir.mkdir(parents=True, exist_ok=True)
    duration = _ffprobe_duration(video)

    # Spread samples across the clip. Short GIFs still get several grabs.
    if duration <= 0.05:
        timestamps = [0.0]
    elif duration < 2.0:
        timestamps = [i * duration / max(count, 1) for i in range(count)]
    else:
        # Skip a tiny lead-in; sample evenly through the body.
        timestamps = [
            max(0.05, duration * (i + 0.5) / count) for i in range(count)
        ]

    frames: list[Path] = []
    for index, ts in enumerate(timestamps):
        out = frames_dir / f"frame_{index:02d}.jpg"
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{ts:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            "scale=720:-2:force_original_aspect_ratio=decrease",
            "-q:v",
            "3",
            "-y",
            str(out),
        ]
        try:
            subprocess.run(
                cmd,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=FFMPEG_TIMEOUT,
            )
        except Exception:
            continue
        if out.exists() and out.stat().st_size > 0:
            frames.append(out)

    # Fallback: sequential fps dump if seeks produced nothing (odd containers).
    if not frames:
        pattern = str(frames_dir / "seq_%02d.jpg")
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-vf",
            "fps=2,scale=720:-2:force_original_aspect_ratio=decrease",
            "-frames:v",
            str(count),
            "-q:v",
            "3",
            "-y",
            pattern,
        ]
        try:
            subprocess.run(
                cmd,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=FFMPEG_TIMEOUT,
            )
        except Exception:
            return []
        frames = sorted(frames_dir.glob("seq_*.jpg"))[:count]

    return frames


async def _materialize_and_sample_frames(
    client,
    media,
    workdir: Path,
    *,
    max_bytes: int = MAX_VIDEO_MATERIALIZE,
    count: int = VIDEO_SAMPLE_COUNT,
) -> list[Path]:
    """
    Stream the GIF/video from Telegram DCs into a temp file, then sample
    frames with ffmpeg seeks.

    Piping MP4/GIF-as-MP4 into ffmpeg stdin usually yields zero frames because
    the container is not seekable until the file is complete.
    """
    dest = workdir / "media.bin"
    path, _prefix = await _stream_to_path(
        client, media, dest, max_bytes=max_bytes
    )
    if path is None:
        LOGS.warning("NSFW Guard: could not materialize video/GIF stream")
        return []

    # Give ffmpeg a recognizable extension when possible.
    named = workdir / "media.mp4"
    with contextlib.suppress(Exception):
        path.rename(named)
        path = named

    frames_dir = workdir / "frames"
    frames = await asyncio.to_thread(
        _extract_frames_seekable_sync, path, frames_dir, count
    )
    if not frames:
        LOGS.warning(
            "NSFW Guard: ffmpeg produced no frames from streamed media (%s bytes)",
            path.stat().st_size if path.exists() else 0,
        )
    return frames


# ---------------------------------------------------------------------------
# Detection pipeline
# ---------------------------------------------------------------------------

async def _score_images(
    paths: list[Path], *, threshold: float = DETECTOR_SCORE
) -> tuple[float, str]:
    best = 0.0
    provider = "none"
    for path in paths:
        if not path.exists() or path.stat().st_size <= 0:
            continue
        if path.stat().st_size > MAX_IMAGE_STREAM:
            continue
        score = await _nudenet_score(path)
        if score > best:
            best = score
            provider = "nudenet"
        if best < threshold and _deepai_key():
            score = await _deepai_score(path)
            if score > best:
                best = score
                provider = "deepai"
        if best >= threshold:
            break
    return best, provider


async def _scan_message(message) -> tuple[bool, float, str]:
    if not _looks_visual(message):
        return False, 0.0, "non_visual"
    if _is_tgs(message):
        # Cannot stream-scan Lottie safely without a rasterizer.
        return False, 0.0, "tgs_unsupported"

    media = _media_for_stream(message)
    if media is None:
        return False, 0.0, "no_streamable_media"

    client = message.client
    with tempfile.TemporaryDirectory(prefix="megatron-nsfw-") as tmp:
        workdir = Path(tmp)
        try:
            if _is_video_like(message):
                size = _document_size(message)
                # Animated GIFs are usually small; allow full materialize.
                cap = MAX_VIDEO_MATERIALIZE
                if size and size <= MAX_VIDEO_MATERIALIZE:
                    cap = size + 1024
                elif _is_animated_document(message):
                    cap = MAX_VIDEO_MATERIALIZE

                frames = await _materialize_and_sample_frames(
                    client, media, workdir, max_bytes=cap
                )
                if not frames:
                    return False, 0.0, "video_frames_empty"

                digest = await asyncio.to_thread(
                    lambda: hashlib.sha256(frames[0].read_bytes()).hexdigest()
                )
                cached = _cache_get(digest)
                if cached is not None:
                    return (
                        cached >= VIDEO_DETECTOR_SCORE,
                        cached,
                        "cache",
                    )
                best, provider = await _score_images(
                    frames, threshold=VIDEO_DETECTOR_SCORE
                )
                _cache_put(digest, best)
                return best >= VIDEO_DETECTOR_SCORE, best, provider

            # Still image / photo / image document — stream from TG DC.
            dest = workdir / "image.bin"
            path, prefix = await _stream_to_path(
                client, media, dest, max_bytes=MAX_IMAGE_STREAM
            )
            if path is None:
                return False, 0.0, "image_stream_failed"

            mime = _mime(message)
            ext = ".jpg"
            if "png" in mime:
                ext = ".png"
            elif "webp" in mime:
                ext = ".webp"
            named = workdir / f"image{ext}"
            path.rename(named)

            digest = _bytes_digest(prefix) if prefix else await asyncio.to_thread(
                lambda: hashlib.sha256(named.read_bytes()[:65536]).hexdigest()
            )
            cached = _cache_get(digest)
            if cached is not None:
                return cached >= DETECTOR_SCORE, cached, "cache"

            best, provider = await _score_images([named])
            _cache_put(digest, best)
            return best >= DETECTOR_SCORE, best, provider
        except Exception as exc:
            LOGS.exception("NSFW Guard scan failure: %s", exc)
            return False, 0.0, "error"


# ---------------------------------------------------------------------------
# Moderation action / logging
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


async def _preserve_to_log(log_chat, message):
    """Copy the offending media to LOG_CHANNEL while the message still exists."""
    try:
        result = await heartless_bot.forward_messages(log_chat, message)
        if isinstance(result, list):
            return result[0] if result else None
        return result
    except Exception as forward_exc:
        LOGS.debug("NSFW Guard: forward failed (%s); trying re-upload", forward_exc)

    # Protected chats / already-restricted messages: re-stream the file to log.
    try:
        with tempfile.TemporaryDirectory(prefix="megatron-nsfw-log-") as tmp:
            dest = Path(tmp) / "evidence"
            path = await message.download_media(file=str(dest))
            if not path:
                return None
            return await heartless_bot.send_file(
                log_chat,
                path,
                caption="📎 NSFW evidence (re-uploaded)",
                force_document=False,
            )
    except Exception as exc:
        LOGS.warning("NSFW Guard: evidence preserve failed: %s", exc)
        return None


async def _send_log(
    message,
    score: float,
    provider: str,
    action_result: str,
    *,
    preserved=None,
):
    log_chat = _log_chat_id()
    if not log_chat:
        return

    sender = await message.get_sender()
    chat = await message.get_chat()
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

    text = (
        "🚨 **NSFW GUARD — CONTENT REMOVED**\n\n"
        f"👤 **User:** {_mention(sender)}\n"
        f"🆔 **User ID:** `{getattr(sender, 'id', 'unknown')}`\n"
        f"💬 **Chat:** `{_chat_title(chat)}`\n"
        f"🆔 **Chat ID:** `{getattr(chat, 'id', 'unknown')}`\n"
        f"🧪 **Detector:** `{provider}`\n"
        f"📊 **Score:** `{score:.2%}`\n"
        f"🛡 **Action:** `{action_result}`\n"
        f"🧾 **Message ID:** `{getattr(message, 'id', 'unknown')}`\n"
        "📡 **Mode:** `telegram-stream`"
    )
    if preserved:
        text += "\n📎 **Detected content:** preserved above."
    else:
        text += "\n📎 **Detected content:** unavailable (protected/copy failed)."

    try:
        await heartless_bot.send_message(
            log_chat,
            text,
            buttons=buttons or None,
            parse_mode="md",
        )
    except Exception as exc:
        LOGS.warning("NSFW Guard: log send failed: %s", exc)


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
    if getattr(message, "out", False):
        return

    try:
        sender = await event.get_sender()
    except Exception:
        sender = None

    if _is_admin_like(sender):
        return

    try:
        permissions = await heartless_bot.get_permissions(chat_id, sender)
        if getattr(permissions, "is_admin", False) or getattr(
            permissions, "is_creator", False
        ):
            return
    except Exception:
        pass

    action = is_nsfw(chat_id) or DEFAULT_ACTION
    if action not in SUPPORTED_ACTIONS:
        action = DEFAULT_ACTION

    async with _SCAN_SEMAPHORE:
        detected, score, provider = await _scan_message(message)

    if not detected:
        return

    # Preserve evidence BEFORE delete — ForwardMessages after delete raises
    # MessageIdInvalidError (the GIF log failure you were seeing).
    preserved = None
    log_chat = _log_chat_id()
    if log_chat:
        preserved = await _preserve_to_log(log_chat, message)

    try:
        await message.delete()
    except Exception as exc:
        LOGS.warning("NSFW Guard: could not delete message %s: %s", message.id, exc)

    action_result = "ACTION FAILED"
    try:
        if sender and getattr(sender, "id", None):
            action_result = await _take_action(chat_id, sender.id, action)
    except (ChatAdminRequiredError, RPCError) as exc:
        LOGS.warning(
            "NSFW Guard: moderation action failed in %s for %s: %s",
            chat_id,
            getattr(sender, "id", None),
            exc,
        )
    except Exception as exc:
        LOGS.exception("NSFW Guard: moderation action error: %s", exc)

    await _send_log(
        message, score, provider, action_result, preserved=preserved
    )


# ---------------------------------------------------------------------------
# Configuration commands
# ---------------------------------------------------------------------------

@heartless_cmd(pattern=r"addnsfw(?:\s+(ban|mute))?$", admins_only=True)
async def add_nsfw(e):
    action = (e.pattern_match.group(1) or DEFAULT_ACTION).lower()
    if action not in SUPPORTED_ACTIONS:
        action = DEFAULT_ACTION

    if await _get_detector() is None and not _deepai_key():
        return await e.eor(
            "`NSFW detector is not installed.`\n\n"
            "Install NudeNet with:\n"
            "`pip install nudenet`\n\n"
            "Then restart the userbot.",
            time=12,
        )

    nsfw_chat(e.chat_id, action)
    _ACTIVE_CHATS.add(e.chat_id)
    await e.eor(
        f"✅ **NSFW Guard enabled**\n"
        f"Action: `{action}`\n"
        f"Mode: `telegram-stream`\n"
        f"Detector: `NudeNet`"
        + (" + `DeepAI fallback`" if _deepai_key() else ""),
        time=8,
    )


@heartless_cmd(pattern=r"remnsfw$", admins_only=True)
async def remove_nsfw(e):
    rem_nsfw(e.chat_id)
    _ACTIVE_CHATS.discard(e.chat_id)
    await e.eor("✅ NSFW Guard disabled for this chat.", time=6)


@heartless_cmd(pattern=r"getnsfw$", admins_only=True)
async def get_nsfw(e):
    action = is_nsfw(e.chat_id)
    if not action:
        return await e.eor("ℹ️ NSFW Guard is disabled in this chat.", time=6)
    await e.eor(
        f"🛡 **NSFW Guard**\nStatus: `enabled`\nAction: `{action}`\nMode: `telegram-stream`",
        time=7,
    )


@heartless_cmd(pattern=r"setnsfwapi(?:\s+(.+))?$", admins_only=True)
async def set_nsfw_api(e):
    key = (e.pattern_match.group(1) or "").strip()
    if not key:
        return await e.eor("Usage: `.setnsfwapi <DeepAI API key>`", time=8)
    udB.set_key("DEEP_API", key)
    await e.eor(
        "✅ DeepAI NSFW fallback configured.\n"
        "Local NudeNet remains the primary detector.",
        time=8,
    )


@heartless_cmd(pattern=r"clearnsfwapi$", admins_only=True)
async def clear_nsfw_api(e):
    try:
        udB.set_key("DEEP_API", None)
    except Exception:
        pass
    await e.eor("✅ DeepAI fallback key removed.", time=6)


@heartless_cmd(pattern=r"nsfwstatus$", admins_only=True)
async def nsfw_status(e):
    detector = "loaded" if _DETECTOR is not None else (
        "unavailable" if _DETECTOR_ERROR else "not loaded"
    )
    ffmpeg = "available" if shutil.which("ffmpeg") else "missing"
    log = "configured" if _log_chat_id() else "NOT configured"
    await e.eor(
        "🛡 **NSFW Guard Status**\n\n"
        f"• Mode: `telegram-stream`\n"
        f"• NudeNet: `{detector}`\n"
        f"• FFmpeg: `{ffmpeg}`\n"
        f"• DeepAI fallback: `{'configured' if _deepai_key() else 'disabled'}`\n"
        f"• LOG_CHANNEL: `{log}`\n"
        f"• Active chats: `{len(_ACTIVE_CHATS)}`\n"
        f"• Threshold: `{DETECTOR_SCORE:.0%}`\n"
        f"• Image stream cap: `{MAX_IMAGE_STREAM // (1024 * 1024)}MB`\n"
        f"• Video materialize cap: `{MAX_VIDEO_MATERIALIZE // (1024 * 1024)}MB`\n"
        f"• Video threshold: `{VIDEO_DETECTOR_SCORE:.0%}`",
        time=12,
    )


# ---------------------------------------------------------------------------
# Bootstrap
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

heartless_bot.add_handler(
    _nsfw_event,
    events.NewMessage(incoming=True),
)

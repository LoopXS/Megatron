"""
Plugin - nsfwfilter
✘ Commands Available -

• `{i}nsfw`
    Show NSFW Guard status for this chat and the whole setup.

• `{i}nsfw on [ban|mute]`
    Enable the guard in this chat. ban (default) bans the sender, mute only restricts them.

• `{i}nsfw off`
    Disable the guard in this chat.

• `{i}nsfw api <key>`
    Set the optional DeepAI fallback API key.

• `{i}nsfw api`
    Remove the DeepAI fallback key.

  On detection the offending media is forwarded to LOG_GROUP (or LOG_CHANNEL), the message is deleted, the sender is banned/muted and their recent messages are purged.

  Requires nudenet for local detection and ffmpeg/ffprobe for video analysis. Disable the purge globally with setdb NSFW_PURGE off.
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

from . import Button, HNDLR, LOGS, Redis, eor, udB, cipherx_bot, cipherx_cmd
from CythonX.dB.nsfw_db import is_nsfw, nsfw_chat, rem_nsfw


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_ACTION = "ban"
SUPPORTED_ACTIONS = {"ban", "mute"}
MAX_IMAGE_STREAM = 10 * 1024 * 1024
# Telegram GIFs are usually small MP4s — fully materialize for reliable seeks.
MAX_GIF_MATERIALIZE = 30 * 1024 * 1024
# Large videos: stream a capped prefix for early-frame decode (fast path),
# then extend once if needed. Never re-upload evidence to the log chat.
MAX_VIDEO_FAST = 18 * 1024 * 1024
MAX_VIDEO_FULL = 80 * 1024 * 1024
VIDEO_SAMPLE_COUNT = 6
DETECTOR_SCORE = 0.48
VIDEO_DETECTOR_SCORE = 0.36
# Document thumbs alone are weaker signal — used as a fast first pass only.
THUMB_DETECTOR_SCORE = 0.55
MAX_CONCURRENT_SCANS = 3
CACHE_TTL = 6 * 60 * 60
STREAM_CHUNK = 512 * 1024
FFMPEG_TIMEOUT = 40
PURGE_LIMIT = 40

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


def _purge_enabled() -> bool:
    raw = udB.get_key("NSFW_PURGE")
    if raw is None:
        return True
    if raw is False or raw == 0:
        return False
    if isinstance(raw, str) and raw.strip().lower() in {
        "0", "false", "off", "no", "disable", "disabled",
    }:
        return False
    return True


def _log_chat_id():
    """Prefer LOG_GROUP, then LOG_CHANNEL."""
    for key in ("LOG_GROUP", "LOG_CHANNEL"):
        value = Redis(key)
        if value is None:
            value = udB.get_key(key)
        if not value:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    return None


def _safe_name(user) -> str:
    name = " ".join(
        x
        for x in [
            getattr(user, "first_name", None),
            getattr(user, "last_name", None),
        ]
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
        ".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi", ".3gp", ".tgs",
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
    if getattr(message, "gif", None):
        return True
    doc = getattr(message, "document", None)
    for attr in getattr(doc, "attributes", None) or []:
        if isinstance(attr, types.DocumentAttributeAnimated):
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
        "BUTTOCKS_EXPOSED",
    }
    sexual = {
        "FEMALE_GENITALIA_COVERED",
        "MALE_GENITALIA_COVERED",
        "FEMALE_BREAST_COVERED",
        "BELLY_EXPOSED",
        "ARMPITS_EXPOSED",
    }
    best = 0.0
    for item in detections:
        label = str(item.get("class") or item.get("label") or "").upper()
        score = float(item.get("score", 0.0) or 0.0)
        if label in explicit:
            best = max(best, score)
        elif label in sexual:
            best = max(best, score * 0.85)
        elif "EXPOSED" in label and "FACE" not in label and "FEET" not in label:
            best = max(best, score * 0.72)
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
    timeout = aiohttp.ClientTimeout(total=25)
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
                        return 0.0
                    data = await resp.json(content_type=None)
                    return float(data.get("output", {}).get("nsfw_score", 0.0))
    except Exception as exc:
        LOGS.debug("NSFW Guard: DeepAI failed: %s", exc)
        return 0.0


# ---------------------------------------------------------------------------
# Telegram streaming / frame sampling
# ---------------------------------------------------------------------------

def _pick_photo_size(photo: types.Photo):
    usable = []
    for size in getattr(photo, "sizes", None) or []:
        if isinstance(size, (types.PhotoSize, types.PhotoSizeProgressive)):
            w = int(getattr(size, "w", 0) or 0)
            h = int(getattr(size, "h", 0) or 0)
            if w * h > 0:
                usable.append((w * h, size))
    if not usable:
        return None
    usable.sort(key=lambda item: item[0])
    if len(usable) >= 3:
        return usable[-2][1]
    return usable[-1][1]


def _media_for_stream(message):
    if _is_tgs(message):
        return None
    photo = getattr(message, "photo", None)
    if isinstance(photo, types.Photo):
        size = _pick_photo_size(photo)
        if size is None:
            return None
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
    return message.media


async def _stream_to_path(
    client,
    media,
    dest: Path,
    *,
    max_bytes: int,
) -> tuple[Optional[Path], int]:
    written = 0
    try:
        with dest.open("wb") as out:
            async for chunk in client.iter_download(media, request_size=STREAM_CHUNK):
                if not chunk:
                    continue
                out.write(chunk)
                written += len(chunk)
                if written >= max_bytes:
                    break
    except FloodWaitError as exc:
        LOGS.warning("NSFW Guard: flood wait during stream: %ss", exc.seconds)
        return None, 0
    except Exception as exc:
        LOGS.warning("NSFW Guard: stream failed: %s", exc)
        if written <= 0:
            return None, 0
    if written <= 0 or not dest.exists():
        return None, 0
    return dest, written


def _ffprobe_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0.0
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(
            cmd, check=False, capture_output=True, text=True, timeout=12,
        )
        return max(0.0, float((result.stdout or "0").strip() or 0))
    except Exception:
        return 0.0


def _extract_frames_sync(
    video: Path,
    frames_dir: Path,
    count: int = VIDEO_SAMPLE_COUNT,
) -> list[Path]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []
    frames_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []

    # Path A — sequential early frames (works even when moov is incomplete /
    # near the start after Telegram re-encode). Best for GIFs and short clips.
    seq_pattern = str(frames_dir / "seq_%02d.jpg")
    seq_cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-fflags", "+genpts+discardcorrupt",
        "-probesize", "64M", "-analyzeduration", "30M",
        "-i", str(video),
        "-vf", "fps=3,scale=720:-2:force_original_aspect_ratio=decrease",
        "-frames:v", str(count),
        "-q:v", "3", "-y", seq_pattern,
    ]
    try:
        subprocess.run(
            seq_cmd, check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=FFMPEG_TIMEOUT,
        )
    except Exception:
        pass
    frames = sorted(frames_dir.glob("seq_*.jpg"))[:count]
    if frames:
        return frames

    # Path B — timestamp seeks across the clip (needs a complete/seekable file).
    duration = _ffprobe_duration(video)
    if duration <= 0.05:
        timestamps = [0.0]
    elif duration < 3.0:
        timestamps = [duration * i / max(count, 1) for i in range(count)]
    else:
        timestamps = [max(0.05, duration * (i + 0.35) / count) for i in range(count)]

    for index, ts in enumerate(timestamps):
        out = frames_dir / f"seek_{index:02d}.jpg"
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-ss", f"{ts:.3f}", "-i", str(video),
            "-frames:v", "1",
            "-vf", "scale=720:-2:force_original_aspect_ratio=decrease",
            "-q:v", "3", "-y", str(out),
        ]
        try:
            subprocess.run(
                cmd, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=FFMPEG_TIMEOUT,
            )
        except Exception:
            continue
        if out.exists() and out.stat().st_size > 0:
            frames.append(out)
    return frames


async def _optional_doc_thumb(message, workdir: Path) -> Optional[Path]:
    """Largest document thumb as one extra frame — never used alone."""
    try:
        dest = workdir / "doc_thumb.jpg"
        path = await message.download_media(file=str(dest), thumb=-1)
        if path and Path(path).exists() and Path(path).stat().st_size > 2048:
            return Path(path)
    except Exception:
        return None
    return None


async def _materialize_and_sample_frames(
    client,
    media,
    message,
    workdir: Path,
) -> list[Path]:
    """
    Stream GIF/video from Telegram, sample frames with ffmpeg.

    Prefer a complete seekable file whenever the known size fits under the
    materialize cap — partial MP4 prefixes often have the moov atom at the
    end and yield zero frames.
    """
    size = _document_size(message) or 0
    animated = _is_animated_document(message)
    dest = workdir / "media.bin"

    if animated:
        cap = min(size + 2048, MAX_GIF_MATERIALIZE) if size else MAX_GIF_MATERIALIZE
    elif size and size <= MAX_VIDEO_FULL:
        # Full file — required for reliable MP4 seeks on large clips.
        cap = size + 2048
    elif size and size <= MAX_VIDEO_FAST:
        cap = size + 2048
    else:
        # Unknown / huge: pull as much as we allow in one pass.
        cap = MAX_VIDEO_FULL

    path, written = await _stream_to_path(client, media, dest, max_bytes=cap)
    if path is None:
        return []

    named = workdir / "media.mp4"
    with contextlib.suppress(Exception):
        path.rename(named)
        path = named

    frames_dir = workdir / "frames"
    frames = await asyncio.to_thread(
        _extract_frames_sync, path, frames_dir, VIDEO_SAMPLE_COUNT
    )

    # If the first pass was a truncated huge file and yielded nothing, we
    # cannot fetch the trailing moov cheaply — rely on thumb fallback upstream.
    thumb = await _optional_doc_thumb(message, workdir)
    if thumb is not None:
        frames.append(thumb)

    if not frames:
        LOGS.warning(
            "NSFW Guard: no frames from media (bytes=%s size=%s animated=%s)",
            written, size or "?", animated,
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
        return False, 0.0, "tgs_unsupported"

    media = _media_for_stream(message)
    if media is None:
        return False, 0.0, "no_streamable_media"

    client = message.client
    with tempfile.TemporaryDirectory(prefix="megatron-nsfw-") as tmp:
        workdir = Path(tmp)
        try:
            if _is_video_like(message):
                # Fast path for large videos: score the largest document thumb
                # first (not the only check). Strong hits skip heavy streaming.
                thumb = await _optional_doc_thumb(message, workdir)
                if thumb is not None:
                    t_score, t_provider = await _score_images(
                        [thumb], threshold=THUMB_DETECTOR_SCORE
                    )
                    if t_score >= THUMB_DETECTOR_SCORE:
                        digest = await asyncio.to_thread(
                            lambda: hashlib.sha256(thumb.read_bytes()).hexdigest()
                        )
                        _cache_put(digest, t_score)
                        return True, t_score, f"{t_provider}+thumb"

                frames = await _materialize_and_sample_frames(
                    client, media, message, workdir
                )
                if not frames:
                    # Thumb was weak/absent and ffmpeg got nothing — last resort
                    # accept a lower thumb score so huge files are not skipped.
                    if thumb is not None:
                        weak, prov = await _score_images(
                            [thumb], threshold=VIDEO_DETECTOR_SCORE
                        )
                        if weak >= VIDEO_DETECTOR_SCORE:
                            return True, weak, f"{prov}+thumb-fallback"
                    return False, 0.0, "video_frames_empty"
                digest = await asyncio.to_thread(
                    lambda: hashlib.sha256(frames[0].read_bytes()).hexdigest()
                )
                cached = _cache_get(digest)
                if cached is not None:
                    return cached >= VIDEO_DETECTOR_SCORE, cached, "cache"
                best, provider = await _score_images(
                    frames, threshold=VIDEO_DETECTOR_SCORE
                )
                _cache_put(digest, best)
                return best >= VIDEO_DETECTOR_SCORE, best, provider

            dest = workdir / "image.bin"
            path, written = await _stream_to_path(
                client, media, dest, max_bytes=MAX_IMAGE_STREAM
            )
            if path is None or written <= 0:
                return False, 0.0, "image_stream_failed"

            mime = _mime(message)
            ext = ".jpg"
            if "png" in mime:
                ext = ".png"
            elif "webp" in mime:
                ext = ".webp"
            named = workdir / f"image{ext}"
            path.rename(named)

            digest = await asyncio.to_thread(
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
# Moderation / logging / purge
# ---------------------------------------------------------------------------

async def _take_action(chat_id: int, user_id: int, action: str) -> str:
    action = action if action in SUPPORTED_ACTIONS else DEFAULT_ACTION
    if action == "mute":
        await cipherx_bot.edit_permissions(
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

    await cipherx_bot.edit_permissions(
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


async def _purge_sender(chat_id: int, user_id: int, *, around_id: int | None = None):
    """Delete the sender's recent messages in this chat (best-effort)."""
    if not _purge_enabled():
        return 0
    ids = []
    try:
        async for msg in cipherx_bot.iter_messages(
            chat_id,
            from_user=user_id,
            limit=PURGE_LIMIT,
        ):
            mid = getattr(msg, "id", None)
            if mid:
                ids.append(mid)
        if around_id and around_id not in ids:
            ids.append(around_id)
        if not ids:
            return 0
        # Telegram accepts batches of up to 100.
        for i in range(0, len(ids), 100):
            await cipherx_bot.delete_messages(chat_id, ids[i : i + 100])
        return len(ids)
    except Exception as exc:
        LOGS.debug("NSFW Guard: purge failed: %s", exc)
        return 0


async def _forward_to_log(log_chat, message):
    """Forward only — never re-upload (huge videos must stay fast)."""
    try:
        # Telethon 1.45: reply_to is keyword-only; pass explicitly for older pins.
        if hasattr(message, "forward_to"):
            result = await message.forward_to(log_chat, reply_to=None)
        else:
            result = await cipherx_bot.forward_messages(
                log_chat,
                message,
                reply_to=None,
            )
        if isinstance(result, list):
            return result[0] if result else None
        return result
    except TypeError:
        # Extremely old forks without reply_to kw.
        try:
            result = await cipherx_bot.forward_messages(log_chat, message)
            if isinstance(result, list):
                return result[0] if result else None
            return result
        except Exception as exc:
            LOGS.warning("NSFW Guard: forward to log failed: %s", exc)
            return None
    except Exception as exc:
        LOGS.warning("NSFW Guard: forward to log failed: %s", exc)
        return None


async def _send_log(
    message,
    score: float,
    provider: str,
    action_result: str,
    *,
    preserved=None,
    purged: int = 0,
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
        f"🧹 **Purged:** `{purged}`\n"
        f"🧾 **Message ID:** `{getattr(message, 'id', 'unknown')}`"
    )
    if preserved:
        text += "\n📎 **Detected content:** forwarded above."
    else:
        text += "\n📎 **Detected content:** forward failed (protected/unavailable)."

    try:
        await cipherx_bot.send_message(
            log_chat,
            text,
            buttons=buttons or None,
            parse_mode="md",
        )
    except Exception as exc:
        LOGS.warning("NSFW Guard: log send failed: %s", exc)


# ---------------------------------------------------------------------------
# Event handler
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
        permissions = await cipherx_bot.get_permissions(chat_id, sender)
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

    # Forward BEFORE delete. Never re-upload — that stalls on large videos.
    preserved = None
    log_chat = _log_chat_id()
    if log_chat:
        preserved = await _forward_to_log(log_chat, message)

    msg_id = getattr(message, "id", None)
    try:
        await message.delete()
    except Exception as exc:
        LOGS.warning("NSFW Guard: could not delete message %s: %s", msg_id, exc)

    action_result = "ACTION FAILED"
    purged = 0
    try:
        if sender and getattr(sender, "id", None):
            action_result = await _take_action(chat_id, sender.id, action)
            purged = await _purge_sender(
                chat_id, sender.id, around_id=msg_id
            )
    except (ChatAdminRequiredError, RPCError) as exc:
        LOGS.warning(
            "NSFW Guard: moderation failed in %s for %s: %s",
            chat_id,
            getattr(sender, "id", None),
            exc,
        )
    except Exception as exc:
        LOGS.exception("NSFW Guard: moderation error: %s", exc)

    await _send_log(
        message,
        score,
        provider,
        action_result,
        preserved=preserved,
        purged=purged,
    )


# ---------------------------------------------------------------------------
# Commands — unified `.nsfw` helper
# ---------------------------------------------------------------------------

def _usage() -> str:
    i = HNDLR
    return (
        f"**Plugin — nsfwfilter**\n"
        f"✘ Commands Available -\n\n"
        f"• `{i}nsfw`\n"
        f"    Show NSFW Guard status for this chat and the whole setup.\n\n"
        f"• `{i}nsfw on [ban|mute]`\n"
        f"    Enable the guard in this chat. `ban` (default) bans the sender, "
        f"`mute` only restricts them.\n\n"
        f"• `{i}nsfw off`\n"
        f"    Disable the guard in this chat.\n\n"
        f"• `{i}nsfw api <key>`\n"
        f"    Set the optional DeepAI fallback API key.\n\n"
        f"• `{i}nsfw api`\n"
        f"    Remove the DeepAI fallback key.\n\n"
        f"On detection the offending media is forwarded to `LOG_GROUP` "
        f"(or `LOG_CHANNEL`), the message is deleted, the sender is banned/muted "
        f"and their recent messages are purged.\n\n"
        f"Requires `nudenet` and `ffmpeg`/`ffprobe`. "
        f"Disable purge with `setdb NSFW_PURGE off`."
    )


def _status_text(chat_id: int | None = None) -> str:
    detector = (
        "loaded"
        if _DETECTOR is not None
        else ("unavailable" if _DETECTOR_ERROR else "not loaded")
    )
    ffmpeg = "available" if shutil.which("ffmpeg") else "missing"
    log = "configured" if _log_chat_id() else "NOT configured"
    chat_line = ""
    if chat_id is not None:
        action = is_nsfw(chat_id)
        if action:
            chat_line = f"• This chat: `ON` (`{action}`)\n"
        else:
            chat_line = "• This chat: `OFF`\n"
    return (
        "🛡 **NSFW Guard Status**\n\n"
        f"{chat_line}"
        f"• NudeNet: `{detector}`\n"
        f"• FFmpeg: `{ffmpeg}`\n"
        f"• DeepAI: `{'configured' if _deepai_key() else 'disabled'}`\n"
        f"• Log target: `{log}`\n"
        f"• Purge: `{'on' if _purge_enabled() else 'off'}`\n"
        f"• Active chats: `{len(_ACTIVE_CHATS)}`\n"
        f"• Image threshold: `{DETECTOR_SCORE:.0%}`\n"
        f"• Video/GIF threshold: `{VIDEO_DETECTOR_SCORE:.0%}`"
    )


@cipherx_cmd(pattern=r"nsfw(?:\s+([\s\S]+))?$", admins_only=True)
async def nsfw_cmd(e):
    raw = (e.pattern_match.group(1) or "").strip()
    low = raw.casefold()

    if not raw or low in {"status", "info"}:
        return await e.eor(_status_text(e.chat_id), time=12)
    if low in {"help", "-h", "--help"}:
        return await e.eor(_usage(), time=18)

    parts = raw.split(maxsplit=1)
    sub = parts[0].casefold()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if sub in {"on", "enable", "start"}:
        action = (rest or DEFAULT_ACTION).casefold()
        if action not in SUPPORTED_ACTIONS:
            return await e.eor(
                f"Invalid action. Use `{HNDLR}nsfw on ban` or "
                f"`{HNDLR}nsfw on mute`.",
                time=8,
            )
        if await _get_detector() is None and not _deepai_key():
            return await e.eor(
                "`NSFW detector is not installed.`\n\n"
                "Install with:\n`pip install nudenet`\nThen restart.",
                time=12,
            )
        nsfw_chat(e.chat_id, action)
        _ACTIVE_CHATS.add(e.chat_id)
        return await e.eor(
            f"✅ **NSFW Guard enabled**\n"
            f"Action: `{action}`\n"
            f"Log: forward-only → `LOG_GROUP`/`LOG_CHANNEL`",
            time=8,
        )

    if sub in {"off", "disable", "stop"}:
        rem_nsfw(e.chat_id)
        _ACTIVE_CHATS.discard(e.chat_id)
        return await e.eor("✅ NSFW Guard disabled for this chat.", time=6)

    if sub == "api":
        if not rest:
            with contextlib.suppress(Exception):
                udB.del_key("DEEP_API")
            with contextlib.suppress(Exception):
                udB.del_key("NSFW_DEEPAI_API")
            return await e.eor("✅ DeepAI fallback key removed.", time=6)
        udB.set_key("DEEP_API", rest)
        return await e.eor(
            "✅ DeepAI NSFW fallback configured.\n"
            "Local NudeNet remains primary.",
            time=8,
        )

    return await e.eor(_usage(), time=15)


# Legacy aliases
@cipherx_cmd(pattern=r"addnsfw(?:\s+(ban|mute))?$", admins_only=True)
async def add_nsfw_legacy(e):
    action = (e.pattern_match.group(1) or DEFAULT_ACTION).lower()
    if action not in SUPPORTED_ACTIONS:
        action = DEFAULT_ACTION
    if await _get_detector() is None and not _deepai_key():
        return await e.eor(
            "`NSFW detector is not installed.`\nInstall `nudenet` and restart.",
            time=12,
        )
    nsfw_chat(e.chat_id, action)
    _ACTIVE_CHATS.add(e.chat_id)
    await e.eor(
        f"✅ **NSFW Guard enabled**\n"
        f"Action: `{action}`\n"
        f"(alias of `{HNDLR}nsfw on {action}`)",
        time=8,
    )


@cipherx_cmd(pattern=r"remnsfw$", admins_only=True)
async def rem_nsfw_legacy(e):
    rem_nsfw(e.chat_id)
    _ACTIVE_CHATS.discard(e.chat_id)
    await e.eor(f"✅ Disabled (alias of `{HNDLR}nsfw off`).", time=6)


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

cipherx_bot.add_handler(
    _nsfw_event,
    events.NewMessage(incoming=True),
)

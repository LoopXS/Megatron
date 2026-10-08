"""
Megatron NSFW Guard
-------------------
Real-time NSFW moderation for Telethon/Megatron.

Features
--------
* Watches every incoming media message in enabled chats.
* Supports photos, videos, GIFs, stickers, documents containing visual media,
  video notes and animated media.
* Local NudeNet detector (recommended) with optional DeepAI fallback.
* Videos/GIFs are sampled with ffmpeg instead of uploading the entire video.
* Deletes detected content immediately.
* Automatically bans or mutes the sender.
* Sends a moderation log to LOG_CHANNEL, including the original media when
  Telegram allows forwarding, plus sender/chat details and two URL buttons:
  group and sender profile.
* Admins/owners/bots are ignored by default.
* Per-chat configuration is persisted through the project's NSFW database.

Installation
------------
Recommended:
    pip install nudenet

For video/GIF sampling:
    ffmpeg must be available in PATH.

Optional fallback:
    .setnsfwapi YOUR_DEEPAI_KEY

Commands
--------
    .addnsfw [ban|mute]
    .remnsfw
    .getnsfw
    .setnsfwapi <key>
    .clearnsfwapi
    .nsfwstatus

Examples
--------
    .addnsfw ban
    .addnsfw mute
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

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
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_VIDEO_BYTES = 150 * 1024 * 1024
VIDEO_SAMPLE_COUNT = 5
DETECTOR_SCORE = 0.55
MAX_CONCURRENT_SCANS = 2
CACHE_TTL = 6 * 60 * 60

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

    # Private supergroups/channels use the /c/ form.  The same URL is useful
    # even when the original message has already been deleted.
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

    # Photo is always visual.
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
        ".tgs", ".webp",
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


# ---------------------------------------------------------------------------
# NudeNet
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
            thumb_target = workdir / "sticker_thumb.jpg"
            result = await message.download_media(
                file=str(thumb_target),
                thumb=-1,
            )
        else:
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
    return path.suffix.lower() in {
        ".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi", ".3gp", ".gif", ".apng"
    }


def _extract_video_frames_sync(
    video: Path,
    output_dir: Path,
    count: int = VIDEO_SAMPLE_COUNT,
) -> list[Path]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(output_dir / "frame_%02d.jpg")

    # fps=1/2 gives a time-spread sample for normal videos.  The final
    # scale keeps CPU/memory consumption reasonable.
    vf = f"fps=1/2,scale=640:-2:force_original_aspect_ratio=decrease"
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

    return sorted(output_dir.glob("frame_*.jpg"))[:count]


async def _visual_candidates(message, source: Path, workdir: Path) -> list[Path]:
    if _is_video_file(source, message):
        frames = await asyncio.to_thread(
            _extract_video_frames_sync,
            source,
            workdir / "frames",
        )
        if frames:
            return frames

    # Static images, photo thumbnails, stickers, and video files when ffmpeg
    # is unavailable are scanned directly where possible.
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
            now = time.monotonic()
            cached = _RESULT_CACHE.get(digest)
            if cached and now - cached[0] < CACHE_TTL:
                return cached[1] >= DETECTOR_SCORE, cached[1], "cache"

            candidates = await _visual_candidates(message, source, workdir)
            best = 0.0
            provider = "none"

            for candidate in candidates:
                if candidate.stat().st_size > MAX_IMAGE_BYTES:
                    continue

                score = await _nudenet_score(candidate)
                if score > best:
                    best = score
                    provider = "nudenet"

                # If local detection isn't conclusive, use the configured
                # fallback provider. This keeps normal messages fast.
                if best < DETECTOR_SCORE and _deepai_key():
                    score = await _deepai_score(candidate)
                    if score > best:
                        best = score
                        provider = "deepai"

                if best >= DETECTOR_SCORE:
                    break

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


async def _forward_to_log(log_chat, message):
    """
    Preserve the original detected message in the log channel when Telegram
    permits it. Protected content may prevent forwarding; the metadata log
    still works in that case.
    """
    try:
        result = await heartless_bot.forward_messages(log_chat, message)
        if isinstance(result, list):
            return result[0] if result else None
        return result
    except Exception as exc:
        LOGS.warning("NSFW Guard: forwarding to log failed: %s", exc)
        return None


async def _send_log(message, score: float, provider: str, action_result: str):
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

    forwarded = await _forward_to_log(log_chat, message)

    text = (
        "🚨 **NSFW GUARD — CONTENT REMOVED**\n\n"
        f"👤 **User:** {_mention(sender)}\n"
        f"🆔 **User ID:** `{getattr(sender, 'id', 'unknown')}`\n"
        f"💬 **Chat:** `{_chat_title(chat)}`\n"
        f"🆔 **Chat ID:** `{getattr(chat, 'id', 'unknown')}`\n"
        f"🧪 **Detector:** `{provider}`\n"
        f"📊 **Score:** `{score:.2%}`\n"
        f"🛡 **Action:** `{action_result}`\n"
        f"🧾 **Message ID:** `{getattr(message, 'id', 'unknown')}`"
    )

    if forwarded:
        text += "\n📎 **Detected content:** forwarded above."
    else:
        text += "\n📎 **Detected content:** unavailable (protected/forward failed)."

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

    # Ignore service messages, outgoing messages, and bot/self messages.
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
        # Failure to read permissions must not disable moderation.
        pass

    action = is_nsfw(chat_id) or DEFAULT_ACTION
    if action not in SUPPORTED_ACTIONS:
        action = DEFAULT_ACTION

    async with _SCAN_SEMAPHORE:
        detected, score, provider = await _scan_message(message)

    if not detected:
        return

    # Delete first.  The message object remains usable for forwarding in
    # Telethon in most cases, but if deletion invalidates it we still retain
    # the metadata-only log fallback.
    try:
        await message.delete()
    except Exception as exc:
        LOGS.warning("NSFW Guard: could not delete message %s: %s", message.id, exc)

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

    await _send_log(message, score, provider, action_result)


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
        f"🛡 **NSFW Guard**\nStatus: `enabled`\nAction: `{action}`",
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
        f"• NudeNet: `{detector}`\n"
        f"• FFmpeg: `{ffmpeg}`\n"
        f"• DeepAI fallback: `{'configured' if _deepai_key() else 'disabled'}`\n"
        f"• LOG_CHANNEL: `{log}`\n"
        f"• Active chats: `{len(_ACTIVE_CHATS)}`\n"
        f"• Threshold: `{DETECTOR_SCORE:.0%}`",
        time=10,
    )


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

# A single handler is intentionally used instead of adding one handler per
# chat every time `.addnsfw` is called.  This prevents duplicate scans.
heartless_bot.add_handler(
    _nsfw_event,
    events.NewMessage(incoming=True),
)

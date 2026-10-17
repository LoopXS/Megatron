"""Pure helpers backing the ``.setdur`` (fake display duration) command.

Nothing here touches the network or the filesystem: parsing a human
duration, classifying a document and rebuilding its Telegram attributes
are all side-effect free.  That keeps the logic unit-testable in isolation
while the plugin handler stays a thin download/upload wrapper.
"""

import re
from typing import Iterable, List, Optional, Sequence

from telethon.tl.types import (
    DocumentAttributeAnimated,
    DocumentAttributeAudio,
    DocumentAttributeVideo,
)

__all__ = ["MAX_DURATION", "parse_duration", "classify", "build_attributes"]

# Telegram stores the duration as a 32-bit signed integer; a week is a
# generous, human-friendly ceiling that still leaves plenty of headroom.
MAX_DURATION = 7 * 24 * 60 * 60  # 604800 seconds

_PLAIN = re.compile(r"^\d+$")
_MMSS = re.compile(r"^(\d+):([0-5]?\d)$")
_HMMSS = re.compile(r"^(\d+):([0-5]?\d):([0-5]?\d)$")


def parse_duration(value) -> int:
    """Turn a user supplied duration into whole seconds.

    Accepts either a plain number of seconds (``90``) or a colon clock
    (``1:30`` / ``1:02:03``).  Minutes and seconds must stay in ``0..59``
    in the colon form.  Raises :class:`ValueError` for anything that is
    not a positive duration of at most :data:`MAX_DURATION` seconds.
    """
    if value is None:
        raise ValueError("No duration provided")

    text = str(value).strip()
    if not text:
        raise ValueError("No duration provided")

    match = _HMMSS.match(text)
    if match:
        hours, minutes, seconds = (int(part) for part in match.groups())
    else:
        match = _MMSS.match(text)
        if match:
            hours = 0
            minutes, seconds = (int(part) for part in match.groups())
        elif _PLAIN.match(text):
            hours = minutes = 0
            seconds = int(text)
        else:
            raise ValueError(f"Invalid duration: {value!r}")

    total = hours * 3600 + minutes * 60 + seconds
    if total <= 0:
        raise ValueError("Duration must be greater than zero")
    if total > MAX_DURATION:
        raise ValueError("Duration must not exceed 7 days")
    return total


def classify(attributes: Iterable) -> Optional[str]:
    """Return the playable kind of a document from its attributes.

    One of ``voice``, ``audio``, ``video``, ``video_note`` or
    ``animation`` — or ``None`` when the document is not a playable
    timed media (e.g. a plain file, sticker or image).
    """
    attrs = list(attributes or [])
    animated = any(isinstance(attr, DocumentAttributeAnimated) for attr in attrs)

    for attr in attrs:
        if isinstance(attr, DocumentAttributeAudio):
            return "voice" if attr.voice else "audio"
        if isinstance(attr, DocumentAttributeVideo):
            if attr.round_message:
                return "video_note"
            return "animation" if animated else "video"

    return "animation" if animated else None


def build_attributes(attributes: Sequence, duration: int) -> List:
    """Rebuild ``attributes`` with every timed duration set to ``duration``.

    The original attribute objects are never mutated: audio and video
    attributes are recreated so their type-specific extras (voice flag,
    waveform, title/performer, dimensions, round-message and streaming
    flags) survive untouched, while every other attribute (filename,
    animated marker, ...) is passed through by reference.
    """
    duration = int(duration)
    built: List = []

    for attr in attributes or []:
        if isinstance(attr, DocumentAttributeAudio):
            built.append(
                DocumentAttributeAudio(
                    duration=duration,
                    voice=attr.voice,
                    title=attr.title,
                    performer=attr.performer,
                    waveform=attr.waveform,
                )
            )
        elif isinstance(attr, DocumentAttributeVideo):
            built.append(
                DocumentAttributeVideo(
                    duration=duration,
                    w=attr.w,
                    h=attr.h,
                    round_message=attr.round_message,
                    supports_streaming=attr.supports_streaming,
                )
            )
        else:
            built.append(attr)

    return built

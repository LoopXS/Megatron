"""Asyncio helpers for Python 3.10+ / 3.14 compatibility.

Python 3.10+ no longer auto-creates an event loop on
``get_event_loop()``; on 3.12+ / 3.14 it raises ``RuntimeError`` when
none is set. Telethon and heartlessClient still expect a loop during
synchronous startup (``run_until_complete``).
"""

from __future__ import annotations

import asyncio


def ensure_event_loop() -> asyncio.AbstractEventLoop:
    """Return the running loop, or create and set one for this thread."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        pass

    # Prefer the loop already bound to this thread (if any). On Python 3.14
    # ``get_event_loop()`` raises when none is set — that is expected.
    try:
        loop = asyncio.get_event_loop()
        if loop is not None and not loop.is_closed():
            return loop
    except RuntimeError:
        pass

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop
